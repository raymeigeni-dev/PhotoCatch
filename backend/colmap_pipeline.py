"""COLMAP SfM/MVS execution plus explicit mesh-quality gates.

This module never substitutes a silhouette extrusion when photogrammetry fails.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from backend.panorama_rig import write_rig_config


class ReconstructionError(RuntimeError):
    pass


def _run(command: list[str], stage: str, timeout: int = 1800, cwd: str | Path | None = None) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False,
                                cwd=str(cwd) if cwd is not None else None)
    except subprocess.TimeoutExpired as exc:
        raise ReconstructionError(f"{stage} 超时；素材过长或计算资源不足") from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()[-2500:]
        raise ReconstructionError(f"{stage} 失败（退出码 {result.returncode}）。{details}")
    # Keep both streams: OpenMVS can exit successfully while producing zero points,
    # and its useful diagnosis is often printed to stderr rather than stdout.
    return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def _openmvs_densify_command(
    executable: str, scene: str | Path, *, resolution_level: int | None = None
) -> list[str]:
    """Use depth-map fusion; optionally retry at full image resolution."""
    command = [executable, str(scene), "--fusion-mode", "0"]
    if resolution_level is not None:
        command += ["--resolution-level", str(resolution_level)]
    return command


def _validate_openmvs_scene_image_paths(scene_path: str | Path, image_dir: str | Path) -> None:
    """Reject OpenMVS scenes that embed stale absolute image paths."""
    scene = Path(scene_path)
    images = Path(image_dir).resolve()
    if not scene.is_file() or scene.stat().st_size < 128:
        raise ReconstructionError("OpenMVS scene.mvs 缺失或文件无效")
    available = [p for p in images.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}] if images.is_dir() else []
    if not available:
        raise ReconstructionError(f"OpenMVS 图片目录不存在或没有可用图片：{images}")
    raw = scene.read_bytes()
    # Paths in the binary scene are NUL-terminated; limit matching to printable
    # ASCII so the validator itself remains safe for binary input.
    embedded = re.findall(rb'/[ -~]{1,512}/images/frame_[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png)', raw, flags=re.IGNORECASE)
    stale = []
    for encoded in embedded:
        try:
            path = Path(encoded.decode("utf-8", errors="strict"))
        except UnicodeDecodeError:
            continue
        if path.is_absolute() and not path.is_file():
            stale.append(str(path))
    if stale:
        raise ReconstructionError("OpenMVS scene.mvs 引用了不存在的图片路径：" + ", ".join(stale[:3]) + f"；预期图片目录为 {images}")


def _validate_point_cloud(point_cloud_path: str | Path) -> dict[str, int]:
    """Ensure a PLY is parseable and contains finite, non-degenerate 3D points."""
    path = Path(point_cloud_path)
    if not path.is_file() or path.stat().st_size < 128:
        raise ReconstructionError("点云文件缺失或过小，不能验收")
    try:
        cloud = trimesh.load(str(path), file_type="ply", force="pointcloud", process=False)
        vertices = np.asarray(cloud.vertices, dtype=float)
    except Exception as exc:
        raise ReconstructionError(f"无法解析 PLY 点云文件：{exc}") from exc
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        raise ReconstructionError("PLY 点云没有有效的三维点")
    if not np.isfinite(vertices).all():
        raise ReconstructionError("PLY 点云包含 NaN 或无穷坐标")
    extent = np.ptp(vertices, axis=0)
    if not np.isfinite(extent).all() or float(extent.max()) <= 1e-9:
        raise ReconstructionError("PLY 点云空间范围退化，拒绝作为有效重建结果")
    return {"points": int(len(vertices)), "bytes": int(path.stat().st_size)}


def inspect_mesh(mesh_path: str | Path) -> dict[str, Any]:
    """Inspect a PLY mesh without silently repairing it."""
    path = Path(mesh_path)
    if not path.is_file() or path.stat().st_size < 128:
        raise ReconstructionError("模型文件缺失或过小，不能验收")
    try:
        mesh = trimesh.load(str(path), file_type="ply", force="mesh", process=False)
    except Exception as exc:
        raise ReconstructionError(f"无法解析 COLMAP 网格文件：{exc}") from exc
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) < 4 or len(mesh.faces) < 4:
        raise ReconstructionError("网格没有足够的顶点/三角面，拒绝作为有效模型")
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ReconstructionError("网格顶点含 NaN/无穷值或数组格式错误")
    if faces.ndim != 2 or faces.shape[1] != 3 or (faces < 0).any() or (faces >= len(vertices)).any():
        raise ReconstructionError("网格三角面索引无效")
    sorted_faces = np.sort(faces, axis=1)
    duplicate_faces = int(len(sorted_faces) - len(np.unique(sorted_faces, axis=0)))
    triangles = vertices[faces]
    double_areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                            triangles[:, 2] - triangles[:, 0]), axis=1)
    degenerate_faces = int(np.sum(double_areas <= 1e-12))
    # Reject corrupt topology before operations such as connected-component
    # splitting, which may invoke optional graph-repair dependencies.
    if duplicate_faces:
        raise ReconstructionError(f"网格质量检查失败：发现 {duplicate_faces} 个重复三角面")
    if degenerate_faces:
        raise ReconstructionError(f"网格质量检查失败：发现 {degenerate_faces} 个退化三角面")
    areas = np.asarray(mesh.area_faces)
    bounds = np.asarray(mesh.bounds, dtype=float)
    extent = bounds[1] - bounds[0]
    if not np.isfinite(extent).all() or float(extent.max()) <= 1e-9:
        raise ReconstructionError("模型包围盒尺寸无效或退化")
    if not np.isfinite(areas).all() or float(areas.sum()) <= 1e-10:
        raise ReconstructionError("网格表面积无效")
    # Face connectivity via shared vertices; avoids trimesh.split's optional
    # networkx dependency and keeps the quality gate deterministic.
    parent = list(range(len(faces)))
    rank = [0] * len(faces)
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
    first_face_by_vertex: dict[int, int] = {}
    for face_index, face in enumerate(faces):
        for vertex_index in map(int, face):
            previous = first_face_by_vertex.setdefault(vertex_index, face_index)
            union(face_index, previous)
    component_sizes: dict[int, int] = {}
    for face_index in range(len(faces)):
        root = find(face_index)
        component_sizes[root] = component_sizes.get(root, 0) + 1
    component_count = len(component_sizes)
    largest_component_faces = max(component_sizes.values(), default=0)
    largest_component_ratio = float(largest_component_faces / len(faces))
    # A high face count can hide a fragmented reconstruction. Report an explicit
    # preview-quality gate rather than treating file creation as reconstruction success.
    small_component_faces = sum(size for size in component_sizes.values()
                                if size < max(10, int(len(faces) * 0.001)))
    small_component_ratio = float(small_component_faces / len(faces))
    has_vertex_colors = bool(
        getattr(mesh.visual, "kind", None) == "vertex"
        and getattr(mesh.visual, "vertex_colors", None) is not None
        and len(getattr(mesh.visual, "vertex_colors", [])) == len(vertices)
    )
    textured = bool(getattr(mesh.visual, "kind", None) == "texture")
    warnings = [
        *(["网格不是水密封闭表面，存在孔洞或开放边界风险"] if not mesh.is_watertight else []),
        *(["网格包含多个独立连通组件；需检查漂浮碎片"] if component_count > 1 else []),
        *(["网格严重碎片化：独立组件过多或最大组件占比过低"] if component_count > 25 or largest_component_ratio < 0.70 else []),
        *(["存在大量极小连通碎片，可能是漂浮噪声"] if small_component_ratio > 0.05 else []),
        *(["输出不包含真实 UV 纹理贴图"] if not textured else []),
        *(["输出没有有效顶点颜色"] if not has_vertex_colors else []),
        "几何指标不能判断模型是否为正确目标；请在浏览器中人工核验",
    ]
    severe_fragmentation = component_count > 25 or largest_component_ratio < 0.70 or small_component_ratio > 0.05
    appearance_available = textured or has_vertex_colors
    return {
        "vertices": int(len(vertices)),
        "faces": int(len(faces)),
        "duplicate_faces": duplicate_faces,
        "degenerate_faces": degenerate_faces,
        "connected_components": int(component_count),
        "largest_component_face_ratio": round(largest_component_ratio, 5),
        "small_component_face_ratio": round(small_component_ratio, 5),
        "severe_fragmentation": bool(severe_fragmentation),
        "preview_quality_pass": bool(not severe_fragmentation and appearance_available),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "surface_area": round(float(areas.sum()), 6),
        "bounds": [[round(float(n), 6) for n in row] for row in bounds],
        "extent": [round(float(n), 6) for n in extent],
        "has_vertex_colors": has_vertex_colors,
        "textured": textured,
        "warnings": warnings,
    }


def _remove_same_capture_panorama_pairs(database_path: str | Path) -> int:
    """Remove pairwise constraints between virtual views from the same source frame.

    Virtual perspective crops share one physical camera center. Treating their
    matches as a translational baseline can create false triangulation. This
    filter removes those pairs from both COLMAP match tables; it does not replace
    full rig/frame pose constraints, which remain a limitation of this pipeline.
    """
    path = Path(database_path)
    if not path.is_file():
        return 0
    with sqlite3.connect(str(path)) as db:
        rows = db.execute("SELECT image_id, name FROM images").fetchall()
        grouped: dict[str, list[int]] = {}
        pattern = re.compile(r"(?:^|/)(?:front|right|back|left|up|down)/frame_(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)
        for image_id, name in rows:
            match = pattern.search(str(name))
            if match:
                grouped.setdefault(match.group(1), []).append(int(image_id))
        pair_ids: set[int] = set()
        for ids in grouped.values():
            for index, first in enumerate(ids):
                for second in ids[index + 1:]:
                    a, b = sorted((first, second))
                    pair_ids.add(2147483647 * a + b)
        for pair_id in pair_ids:
            db.execute("DELETE FROM matches WHERE pair_id = ?", (pair_id,))
            db.execute("DELETE FROM two_view_geometries WHERE pair_id = ?", (pair_id,))
        db.commit()
    return len(pair_ids)


def run_colmap_mvs(images_dir: str | Path, output_dir: str | Path, *, executable: str = "colmap") -> dict[str, Any]:
    """Run feature extraction, matching, sparse mapping and dense meshing on prepared images."""
    images = Path(images_dir).resolve()
    out = Path(output_dir).resolve()
    valid_extensions = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    image_files = sorted(p for p in images.iterdir() if p.is_file() and p.suffix.lower() in valid_extensions) if images.is_dir() else []
    if len(image_files) < 8:
        raise ReconstructionError(f"摄影测量图像不足：发现 {len(image_files)} 张，至少需要 8 张有效图像")
    binary = shutil.which(executable)
    if not binary:
        raise ReconstructionError("未找到 COLMAP 可执行文件。请安装 COLMAP 并确保 colmap 在 PATH 中。")
    out.mkdir(parents=True, exist_ok=True)
    database = out / "database.db"
    sparse = out / "sparse"
    dense = out / "dense"
    sparse.mkdir(exist_ok=True)
    panorama_sensor_names = ("front", "right", "back", "left", "up", "down")
    is_panorama_rig = all(
        (images / sensor).is_dir()
        and any(p.suffix.lower() in valid_extensions for p in (images / sensor).iterdir() if p.is_file())
        for sensor in panorama_sensor_names
    )
    feature_command = [binary, "feature_extractor", "--database_path", str(database),
                       "--image_path", str(images)]
    if is_panorama_rig:
        feature_command += ["--ImageReader.single_camera_per_folder", "1"]
    else:
        feature_command += ["--ImageReader.single_camera", "1"]
    _run(feature_command, "特征提取")
    if is_panorama_rig:
        rig_config_path = write_rig_config(out / "rig_config.json")
        _run([binary, "rig_configurator", "--database_path", str(database),
              "--rig_config_path", str(rig_config_path)], "配置全景虚拟相机 Rig/Frame")
    _run([binary, "exhaustive_matcher", "--database_path", str(database)], "多视图特征匹配")
    # Rig metadata makes all six views share one estimated pose per source frame.
    # Same-frame correspondences are not depth baselines and are removed explicitly.
    if is_panorama_rig:
        _remove_same_capture_panorama_pairs(database)
    mapper_command = [binary, "mapper", "--database_path", str(database),
                      "--image_path", str(images), "--output_path", str(sparse)]
    if is_panorama_rig:
        mapper_command += ["--Mapper.ba_refine_sensor_from_rig", "0"]
    _run(mapper_command, "SfM 稀疏重建", timeout=3600)
    models = sorted((p for p in sparse.iterdir() if p.is_dir() and (p / "images.bin").exists()),
                    key=lambda p: int(p.name) if p.name.isdigit() else 10**9)
    if not models:
        raise ReconstructionError("COLMAP 未恢复出可用的相机/稀疏点云。请增加相邻视角重叠、静止目标表面纹理和相机视差；不要只拍目标自身旋转。")
    registered_txt = out / "registered_model_txt"
    registered_txt.mkdir(parents=True, exist_ok=True)
    _run([binary, "model_converter", "--input_path", str(models[0]), "--output_path", str(registered_txt),
          "--output_type", "TXT"], "导出稀疏相机模型")
    registered_images_file = registered_txt / "images.txt"
    registered_images = 0
    if registered_images_file.is_file():
        registered_images = sum(
            1 for line in registered_images_file.read_text(errors="replace").splitlines()
            if (lambda parts: len(parts) >= 10 and parts[0].isdigit()
                and parts[8].isdigit() and ('.' in parts[9] or '/' in parts[9]))(line.split())
            and not line.lstrip().startswith("#")
        )
    if registered_images < 6:
        raise ReconstructionError(f"COLMAP 仅注册 {registered_images} 张相机图像，少于 6 张；视角重叠或特征不足")
    dense.mkdir(exist_ok=True)
    _run([binary, "image_undistorter", "--image_path", str(images), "--input_path", str(models[0]),
          "--output_path", str(dense), "--output_type", "COLMAP"], "图像去畸变", timeout=1800)
    fused = dense / "fused.ply"
    mesh = dense / "mesh.ply"
    method = "COLMAP SfM + MVS + Poisson meshing"
    texture_status: dict[str, Any] = {"available": False, "success": False, "note": "COLMAP Poisson output is not UV-textured by this pipeline."}
    try:
        _run([binary, "patch_match_stereo", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
              "--PatchMatchStereo.geom_consistency", "true"], "MVS 深度估计", timeout=7200)
        _run([binary, "stereo_fusion", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
              "--input_type", "geometric", "--output_path", str(fused)], "多视图深度融合", timeout=3600)
        if not fused.exists() or fused.stat().st_size < 128:
            raise ReconstructionError("COLMAP 未生成有效的融合点云；请检查素材纹理、视差和遮挡")
        _run([binary, "poisson_mesher", "--input_path", str(fused), "--output_path", str(mesh)], "表面网格生成", timeout=3600)
    except ReconstructionError as colmap_error:
        details = str(colmap_error).lower()
        cuda_missing = "requires cuda" in details or "cuda, which is not available" in details
        if not cuda_missing:
            raise
        interface = shutil.which("InterfaceCOLMAP")
        densify = shutil.which("DensifyPointCloud")
        reconstruct = shutil.which("ReconstructMesh")
        if not (interface and densify and reconstruct):
            raise ReconstructionError(
                "COLMAP 的稠密重建需要 CUDA，但当前系统没有可用 CUDA。"
                "稀疏重建已保留；如需在 Mac 上继续，请安装带 macOS arm64 支持的 OpenMVS "
                "(InterfaceCOLMAP、DensifyPointCloud、ReconstructMesh)，然后重新运行。"
                "也可在支持 NVIDIA CUDA 的 Linux 机器上运行。原始错误：" + str(colmap_error)
            ) from colmap_error
        scene = dense / "scene.mvs"
        _run([interface, "-i", str(dense), "-o", str(scene), "--image-folder", str(dense / "images")],
             "OpenMVS 导入 COLMAP 稀疏模型", timeout=1800)
        if not scene.is_file() or scene.stat().st_size < 128:
            raise ReconstructionError("OpenMVS InterfaceCOLMAP 未生成有效的 scene.mvs；请检查输入目录和 OpenMVS 日志")
        _validate_openmvs_scene_image_paths(scene, dense / "images")
        # OpenMVS 2.4 mode 0 computes/fuses depth maps. Mode -2 only fuses
        # disparity maps and produced zero points on the earlier 33-image sample.
        dense_scene = dense / "scene_dense.mvs"
        fused = dense / "scene_dense.ply"
        openmvs_mesh = dense / "scene_dense_mesh.ply"
        # Remove stale outputs so a previous partial run cannot be mistaken for
        # the result of this attempt.
        for artifact in (dense_scene, fused, openmvs_mesh):
            artifact.unlink(missing_ok=True)
        attempts = [
            ("default", _openmvs_densify_command(densify, scene)),
            # Full-resolution depth maps can recover detail lost by OpenMVS's
            # default half-resolution level. This is intentionally a single
            # bounded retry because it can use substantially more RAM/time.
            ("full_resolution", _openmvs_densify_command(densify, scene, resolution_level=0)),
        ]
        densify_diagnostics: list[str] = []
        for label, command in attempts:
            # Ensure each attempt starts without a prior PLY that could be stale.
            fused.unlink(missing_ok=True)
            try:
                output = _run(command, f"OpenMVS 深度图稠密重建（{label}）", timeout=14400, cwd=dense)
            except ReconstructionError as exc:
                output = str(exc)
                densify_diagnostics.append(f"[{label}] {output}")
                (dense / f"openmvs_densify_{label}.log").write_text(output, errors="replace")
                continue
            densify_diagnostics.append(f"[{label}] {output}")
            (dense / f"openmvs_densify_{label}.log").write_text(output, errors="replace")
            if fused.is_file() and fused.stat().st_size >= 128:
                try:
                    _validate_point_cloud(fused)
                except ReconstructionError as exc:
                    densify_diagnostics.append(f"[{label}] 点云验收失败：{exc}")
                    (dense / f"openmvs_densify_{label}.log").write_text("\\n".join(densify_diagnostics), errors="replace")
                    fused.unlink(missing_ok=True)
                    continue
                break
        if not dense_scene.is_file() or dense_scene.stat().st_size < 128:
            tail = "\n".join(densify_diagnostics)[-1800:]
            raise ReconstructionError("OpenMVS 稠密重建未生成有效 scene_dense.mvs。诊断日志已保存到 dense/openmvs_densify_*.log。\\n" + tail)
        if not fused.is_file() or fused.stat().st_size < 128:
            tail = "\n".join(densify_diagnostics)[-3000:]
            raise ReconstructionError(
                "OpenMVS 在默认分辨率和全分辨率重试后仍未生成有效 scene_dense.ply 点云；"
                "不会伪造成功。诊断日志已保存到 dense/openmvs_densify_*.log。\\n" + tail
            )
        point_cloud_quality = _validate_point_cloud(fused)
        _run([reconstruct, str(dense_scene), "-p", str(fused)], "OpenMVS 表面网格生成", timeout=7200, cwd=dense)
        openmvs_mesh = dense / "scene_dense_mesh.ply"
        if not openmvs_mesh.is_file() or openmvs_mesh.stat().st_size < 128:
            raise ReconstructionError("OpenMVS 未生成预期的 scene_dense_mesh.ply；请查看 OpenMVS 的 LOG 文件")

        # Refine geometry before texturing when the optional OpenMVS tools exist.
        refine = shutil.which("RefineMesh")
        if refine:
            try:
                _run([refine, str(dense_scene), "-m", str(openmvs_mesh), "-o",
                      str(dense / "scene_dense_mesh_refine.mvs")],
                     "OpenMVS 网格细化", timeout=7200, cwd=dense)
            except ReconstructionError as exc:
                # Refinement is optional; preserve the valid raw mesh and report the limitation.
                (dense / "openmvs_refine.log").write_text(str(exc), errors="replace")

        # TextureMesh is the critical missing stage for colored, photorealistic assets.
        # OpenMVS CLI output naming differs slightly across packaged builds, so discover
        # the actual OBJ/MTL/texture artifacts after running the supported scene input.
        texture = shutil.which("TextureMesh")
        textured_obj = dense / "scene_textured_mesh.obj"
        texture_status = {"available": bool(texture), "success": False}
        if texture:
            try:
                texture_log = _run(
                    [texture, str(dense_scene), "--export-type", "obj"],
                    "OpenMVS 真实纹理贴图", timeout=7200, cwd=dense,
                )
                (dense / "openmvs_texture.log").write_text(texture_log, errors="replace")
                candidates = [textured_obj, dense / "scene_dense_mesh_texture.obj",
                              dense / "scene_dense_mesh_refine_texture.obj"]
                existing = next((p for p in candidates if p.is_file() and p.stat().st_size > 128), None)
                if existing is None:
                    existing = next((p for p in dense.glob("*.obj") if p.is_file() and p.stat().st_size > 128), None)
                if existing:
                    if existing != textured_obj:
                        shutil.copy2(existing, textured_obj)
                    texture_status.update({"success": True, "obj": str(textured_obj)})
                    mtl_candidates = list(dense.glob("*.mtl"))
                    texture_status["mtl_files"] = [p.name for p in mtl_candidates]
                    texture_status["texture_files"] = [p.name for p in dense.glob("*.png")] + [p.name for p in dense.glob("*.jpg")]
            except ReconstructionError as exc:
                texture_status["error"] = str(exc)
                (dense / "openmvs_texture.log").write_text(str(exc), errors="replace")
        else:
            texture_status["error"] = "未找到 TextureMesh；当前结果只能保证几何网格，不能声称具有真实纹理。"

        # Normalize OpenMVS outputs to the same API asset names used by COLMAP.
        normalized_mesh = dense / "mesh.ply"
        normalized_fused = dense / "fused.ply"
        shutil.copy2(openmvs_mesh, normalized_mesh)
        shutil.copy2(fused, normalized_fused)
        mesh = normalized_mesh
        fused = normalized_fused
        method = "COLMAP SfM + OpenMVS depth-map fusion + mesh reconstruction"

    quality = inspect_mesh(mesh)
    return {
        "success": True,
        "method": method,
        "registered_images": registered_images,
        "input_images": len(image_files),
        "registered_model": str(models[0]),
        "dense_point_cloud": str(fused),
        **({"dense_point_cloud_quality": point_cloud_quality} if method.endswith("mesh reconstruction") else {}),
        "mesh": str(mesh),
        "mesh_bytes": mesh.stat().st_size,
        "mesh_quality": quality,
        **({"texturing": texture_status} if method.endswith("mesh reconstruction") else {"texturing": {"available": False, "success": False, "note": "COLMAP native Poisson output is not UV-textured by this pipeline."}}),
        "quality_checks": {
            "geometry_valid": True,
            "texture_baked": bool(method.endswith("mesh reconstruction") and texture_status.get("success")),
            "textured_obj": str(dense / "scene_textured_mesh.obj") if method.endswith("mesh reconstruction") and texture_status.get("success") else None,
        },
        "note": "基础几何检查通过不代表照片级质量。请以 texturing.success、OBJ/MTL/贴图文件和实际预览为准；未成功贴图时不会报告彩色纹理模型。",
    }
