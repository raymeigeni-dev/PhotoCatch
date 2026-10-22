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


class ReconstructionError(RuntimeError):
    pass


def _run(command: list[str], stage: str, timeout: int = 1800) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ReconstructionError(f"{stage} 超时；素材过长或计算资源不足") from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()[-2500:]
        raise ReconstructionError(f"{stage} 失败（退出码 {result.returncode}）。{details}")
    return result.stdout


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
    return {
        "vertices": int(len(vertices)),
        "faces": int(len(faces)),
        "duplicate_faces": duplicate_faces,
        "degenerate_faces": degenerate_faces,
        "connected_components": int(component_count),
        "largest_component_face_ratio": round(float(max(component_sizes.values(), default=0) / len(faces)), 5),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "surface_area": round(float(areas.sum()), 6),
        "bounds": [[round(float(n), 6) for n in row] for row in bounds],
        "extent": [round(float(n), 6) for n in extent],
        "has_vertex_colors": bool(getattr(mesh.visual, "kind", None) == "vertex" and getattr(mesh.visual, "vertex_colors", None) is not None),
        "textured": bool(getattr(mesh.visual, "kind", None) == "texture"),
        "warnings": [
            *(["网格不是水密封闭表面，存在孔洞或开放边界风险"] if not mesh.is_watertight else []),
            *(["网格包含多个独立连通组件；需检查漂浮碎片"] if component_count > 1 else []),
            *(["输出不包含真实 UV 纹理贴图"] if getattr(mesh.visual, "kind", None) != "texture" else []),
            "几何指标不能判断模型是否为正确目标；请在浏览器中人工核验",
        ],
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
        pattern = re.compile(r"(?:^|/)frame_(\\d+)_([a-z]+)\\.(?:jpg|jpeg|png)$", re.IGNORECASE)
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
    _run([binary, "feature_extractor", "--database_path", str(database), "--image_path", str(images),
          "--ImageReader.single_camera", "1"], "特征提取")
    _run([binary, "exhaustive_matcher", "--database_path", str(database)], "多视图特征匹配")
    # In 360 mode, virtual crops from the same source frame share one optical
    # center. Remove their pairwise matches before mapper can triangulate them.
    _remove_same_capture_panorama_pairs(database)
    _run([binary, "mapper", "--database_path", str(database), "--image_path", str(images),
          "--output_path", str(sparse)], "SfM 稀疏重建", timeout=3600)
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
        # OpenMVS documents fusion-mode -2 as CPU Semi-Global Matching (SGM).
        _run([densify, str(scene), "--fusion-mode", "-2"], "OpenMVS CPU SGM 稠密重建", timeout=14400)
        dense_scene = dense / "scene_dense.mvs"
        fused = dense / "scene_dense.ply"
        if not dense_scene.is_file() or dense_scene.stat().st_size < 128:
            raise ReconstructionError("OpenMVS 稠密重建未生成 scene_dense.mvs；请检查 OpenMVS 日志和输入图像")
        if not fused.is_file() or fused.stat().st_size < 128:
            raise ReconstructionError("OpenMVS 稠密重建未生成有效 scene_dense.ply 点云；不能继续宣称稠密重建成功")
        _run([reconstruct, str(dense_scene), "-p", str(fused)], "OpenMVS 表面网格生成", timeout=7200)
        openmvs_mesh = dense / "scene_dense_mesh.ply"
        if not openmvs_mesh.is_file() or openmvs_mesh.stat().st_size < 128:
            raise ReconstructionError("OpenMVS 未生成预期的 scene_dense_mesh.ply；请查看 OpenMVS 的 LOG 文件")
        mesh = openmvs_mesh
        method = "COLMAP SfM + OpenMVS CPU SGM + mesh reconstruction"
    quality = inspect_mesh(mesh)
    return {
        "success": True,
        "method": method,
        "registered_images": registered_images,
        "input_images": len(image_files),
        "registered_model": str(models[0]),
        "dense_point_cloud": str(fused),
        "mesh": str(mesh),
        "mesh_bytes": mesh.stat().st_size,
        "mesh_quality": quality,
        "note": "网格已通过基础几何完整性检查；水密性、连通组件、真实纹理及目标身份仍须查看质量报告并在浏览器中人工确认。",
    }
