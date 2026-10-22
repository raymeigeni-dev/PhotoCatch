"""Optional COLMAP SfM/MVS runner for genuine multi-view reconstruction.

Requires a system COLMAP executable. Runs in a per-job temporary directory and reports
failure stages explicitly; it never substitutes a silhouette extrusion when COLMAP fails.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


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


def run_colmap_mvs(images_dir: str | Path, output_dir: str | Path, *, executable: str = "colmap") -> dict[str, Any]:
    """Run feature extraction, matching, sparse mapping and dense meshing on prepared images."""
    binary = shutil.which(executable)
    if not binary:
        raise ReconstructionError("未找到 COLMAP 可执行文件。请安装 COLMAP 并确保 colmap 在 PATH 中。")
    images = Path(images_dir).resolve()
    out = Path(output_dir).resolve()
    if not images.is_dir() or not any(p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"} for p in images.iterdir() if p.is_file()):
        raise ReconstructionError("没有可用于摄影测量的图像。请先提取足够清晰、视角不同的帧。")
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
        raise ReconstructionError("COLMAP 未恢复出可用的相机/稀疏点云。请增加相邻视角重叠、纹理和视差，并避免只拍目标自身旋转。")
    dense.mkdir(exist_ok=True)
    _run([binary, "image_undistorter", "--image_path", str(images), "--input_path", str(models[0]),
          "--output_path", str(dense), "--output_type", "COLMAP"], "图像去畸变", timeout=1800)
    _run([binary, "patch_match_stereo", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
          "--PatchMatchStereo.geom_consistency", "true"], "MVS 深度估计", timeout=7200)
    fused = dense / "fused.ply"
    _run([binary, "stereo_fusion", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
          "--input_type", "geometric", "--output_path", str(fused)], "多视图深度融合", timeout=3600)
    mesh = dense / "mesh.ply"
    _run([binary, "poisson_mesher", "--input_path", str(fused), "--output_path", str(mesh)], "表面网格生成", timeout=3600)
    if not fused.exists() or fused.stat().st_size < 128 or not mesh.exists() or mesh.stat().st_size < 128:
        raise ReconstructionError("COLMAP 返回成功但没有生成有效的点云/网格文件；请检查素材和 COLMAP 版本")
    return {
        "success": True,
        "method": "COLMAP SfM + MVS + Poisson meshing",
        "registered_model": str(models[0]),
        "dense_point_cloud": str(fused),
        "mesh": str(mesh),
        "mesh_bytes": mesh.stat().st_size,
        "note": "已生成摄影测量网格文件；尚需独立检查网格连通性、比例、纹理质量和浏览器渲染。"
    }
