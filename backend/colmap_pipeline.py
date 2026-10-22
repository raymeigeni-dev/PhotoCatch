"""COLMAP SfM/MVS execution plus explicit mesh-quality gates.

This module never substitutes a silhouette extrusion when photogrammetry fails.
"""
from __future__ import annotations

import shutil
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
    components = mesh.split(only_watertight=False)
    areas = np.asarray(mesh.area_faces)
    bounds = np.asarray(mesh.bounds, dtype=float)
    extent = bounds[1] - bounds[0]
    if not np.isfinite(extent).all() or float(extent.max()) <= 1e-9:
        raise ReconstructionError("模型包围盒尺寸无效或退化")
    # Reject obvious topology corruption. A mesh can still have holes or be the
    # wrong object, so report watertightness and component counts separately.
    if duplicate_faces:
        raise ReconstructionError(f"网格质量检查失败：发现 {duplicate_faces} 个重复三角面")
    if degenerate_faces:
        raise ReconstructionError(f"网格质量检查失败：发现 {degenerate_faces} 个退化三角面")
    if not np.isfinite(areas).all() or float(areas.sum()) <= 1e-10:
        raise ReconstructionError("网格表面积无效")
    return {
        "vertices": int(len(vertices)),
        "faces": int(len(faces)),
        "duplicate_faces": duplicate_faces,
        "degenerate_faces": degenerate_faces,
        "connected_components": int(len(components)),
        "largest_component_face_ratio": round(float(max((len(part.faces) for part in components), default=0) / len(faces)), 5),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "surface_area": round(float(areas.sum()), 6),
        "bounds": [[round(float(n), 6) for n in row] for row in bounds],
        "extent": [round(float(n), 6) for n in extent],
        "has_vertex_colors": bool(getattr(mesh.visual, "kind", None) == "vertex" and getattr(mesh.visual, "vertex_colors", None) is not None),
        "textured": bool(getattr(mesh.visual, "kind", None) == "texture"),
        "warnings": [
            *(["网格不是水密封闭表面，存在孔洞或开放边界风险"] if not mesh.is_watertight else []),
            *(["网格包含多个独立连通组件；需检查漂浮碎片"] if len(components) > 1 else []),
            *(["输出不包含真实 UV 纹理贴图"] if getattr(mesh.visual, "kind", None) != "texture" else []),
            "几何指标不能判断模型是否为正确目标；请在浏览器中人工核验",
        ],
    }


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
    _run([binary, "mapper", "--database_path", str(database), "--image_path", str(images),
          "--output_path", str(sparse)], "SfM 稀疏重建", timeout=3600)
    models = sorted((p for p in sparse.iterdir() if p.is_dir() and (p / "images.bin").exists()),
                    key=lambda p: int(p.name) if p.name.isdigit() else 10**9)
    if not models:
        raise ReconstructionError("COLMAP 未恢复出可用的相机/稀疏点云。请增加相邻视角重叠、静止目标表面纹理和相机视差；不要只拍目标自身旋转。")
    registered_txt = out / "registered_model_txt"
    _run([binary, "model_converter", "--input_path", str(models[0]), "--output_path", str(registered_txt),
          "--output_type", "TXT"], "导出稀疏相机模型")
    registered_images_file = registered_txt / "images.txt"
    registered_images = 0
    if registered_images_file.is_file():
        registered_images = sum(1 for line in registered_images_file.read_text(errors="replace").splitlines()
                                if line.strip() and not line.lstrip().startswith("#") and len(line.split()) >= 10)
    if registered_images < 6:
        raise ReconstructionError(f"COLMAP 仅注册 {registered_images} 张相机图像，少于 6 张；视角重叠或特征不足")
    dense.mkdir(exist_ok=True)
    _run([binary, "image_undistorter", "--image_path", str(images), "--input_path", str(models[0]),
          "--output_path", str(dense), "--output_type", "COLMAP"], "图像去畸变", timeout=1800)
    _run([binary, "patch_match_stereo", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
          "--PatchMatchStereo.geom_consistency", "true"], "MVS 深度估计", timeout=7200)
    fused = dense / "fused.ply"
    _run([binary, "stereo_fusion", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
          "--input_type", "geometric", "--output_path", str(fused)], "多视图深度融合", timeout=3600)
    if not fused.exists() or fused.stat().st_size < 128:
        raise ReconstructionError("COLMAP 未生成有效的融合点云；请检查素材纹理、视差和遮挡")
    mesh = dense / "mesh.ply"
    _run([binary, "poisson_mesher", "--input_path", str(fused), "--output_path", str(mesh)], "表面网格生成", timeout=3600)
    quality = inspect_mesh(mesh)
    return {
        "success": True,
        "method": "COLMAP SfM + MVS + Poisson meshing",
        "registered_images": registered_images,
        "input_images": len(image_files),
        "registered_model": str(models[0]),
        "dense_point_cloud": str(fused),
        "mesh": str(mesh),
        "mesh_bytes": mesh.stat().st_size,
        "mesh_quality": quality,
        "note": "网格已通过基础几何完整性检查；水密性、连通组件、真实纹理及目标身份仍须查看质量报告并在浏览器中人工确认。",
    }
