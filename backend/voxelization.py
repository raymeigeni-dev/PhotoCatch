"""Evidence-preserving conversion of colored point clouds/mesh vertices to voxels.

This module does not reconstruct geometry from video. It converts an existing asset's
measured vertices into occupied voxels and refuses to invent missing vertex colors.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


class VoxelizationError(ValueError):
    """Raised when a source asset cannot be safely voxelized."""


SUPPORTED_UNITS = {"m", "cm", "mm"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_colored_vertices(source: Path) -> tuple[np.ndarray, np.ndarray, str]:
    try:
        asset = trimesh.load(source, process=False)
    except Exception as exc:
        raise VoxelizationError(f"无法读取三维资产：{exc}") from exc

    if isinstance(asset, trimesh.Scene):
        raise VoxelizationError("暂不接受包含多个节点的 Scene；请先显式合并并保留坐标变换。")

    if isinstance(asset, trimesh.Trimesh):
        points = np.asarray(asset.vertices, dtype=np.float64)
        colors = np.asarray(asset.visual.vertex_colors)
        asset_kind = "mesh_vertices"
    elif isinstance(asset, trimesh.points.PointCloud):
        points = np.asarray(asset.vertices, dtype=np.float64)
        colors = np.asarray(asset.colors)
        asset_kind = "point_cloud"
    else:
        raise VoxelizationError(f"不支持的资产类型：{type(asset).__name__}")

    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise VoxelizationError("源资产没有有效的 Nx3 三维顶点/点数据。")
    if not np.isfinite(points).all():
        raise VoxelizationError("源资产包含 NaN 或无穷坐标。")
    if colors.ndim != 2 or colors.shape[0] != len(points) or colors.shape[1] < 3:
        raise VoxelizationError("源资产缺少逐顶点 RGB 颜色；拒绝猜测或生成颜色。")

    rgb = np.asarray(colors[:, :3], dtype=np.float64)
    if not np.isfinite(rgb).all():
        raise VoxelizationError("源资产颜色包含 NaN 或无穷值。")
    if rgb.size and rgb.max() <= 1.0 and rgb.min() >= 0.0:
        rgb = rgb * 255.0
    if rgb.min() < 0.0 or rgb.max() > 255.0:
        raise VoxelizationError("源资产 RGB 颜色超出 [0, 255] 范围。")

    return points, np.rint(rgb).astype(np.uint8), asset_kind


def voxelize_colored_asset(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    voxel_size: float,
    unit: str,
    max_voxels: int = 2_000_000,
) -> dict[str, Any]:
    """Voxelize measured vertices, averaging position and observed RGB per occupied cell.

    voxel_size is expressed in the explicitly declared source unit (m, cm, or mm).
    The output PLY contains voxel centers as colored points; it is not a watertight
    surface mesh and does not imply recovery of unobserved/internal geometry.
    """
    source = Path(source_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise VoxelizationError("源资产不存在或为空。")
    if destination == source.parent or source in destination.parents:
        raise VoxelizationError("输出目录不能覆盖源资产或位于源资产文件内部。")
    if unit not in SUPPORTED_UNITS:
        raise VoxelizationError("必须明确指定单位：m、cm 或 mm。")
    if not np.isfinite(voxel_size) or voxel_size <= 0:
        raise VoxelizationError("voxel_size 必须是大于 0 的有限数值。")
    if not isinstance(max_voxels, int) or max_voxels < 1:
        raise VoxelizationError("max_voxels 必须是正整数。")

    points, colors, asset_kind = _load_colored_vertices(source)
    origin = points.min(axis=0)
    grid = np.floor((points - origin) / float(voxel_size)).astype(np.int64)
    unique_grid, inverse, counts = np.unique(
        grid, axis=0, return_inverse=True, return_counts=True
    )
    voxel_count = len(unique_grid)
    if voxel_count > max_voxels:
        raise VoxelizationError(
            f"体素数量 {voxel_count} 超过上限 {max_voxels}；请增大 voxel_size 或提高明确配置的上限。"
        )

    position_sums = np.zeros((voxel_count, 3), dtype=np.float64)
    color_sums = np.zeros((voxel_count, 3), dtype=np.float64)
    np.add.at(position_sums, inverse, points)
    np.add.at(color_sums, inverse, colors.astype(np.float64))
    centers = position_sums / counts[:, None]
    mean_colors = np.clip(np.rint(color_sums / counts[:, None]), 0, 255).astype(np.uint8)

    destination.mkdir(parents=True, exist_ok=True)
    point_path = destination / "voxels.ply"
    manifest_path = destination / "voxels.manifest.json"
    if point_path == source or manifest_path == source:
        raise VoxelizationError("输出文件路径与源资产冲突。")

    cloud = trimesh.points.PointCloud(centers, colors=mean_colors)
    cloud.export(point_path)

    bounds_min = points.min(axis=0).tolist()
    bounds_max = points.max(axis=0).tolist()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "operation": "colored_vertex_voxelization",
        "source_file": source.name,
        "source_sha256": _sha256(source),
        "source_asset_kind": asset_kind,
        "source_vertex_count": int(len(points)),
        "voxel_count": int(voxel_count),
        "voxel_size": float(voxel_size),
        "unit": unit,
        "grid_origin": origin.tolist(),
        "bounds": {"min": bounds_min, "max": bounds_max},
        "color_source": "source_vertex_rgb",
        "color_aggregation": "arithmetic_mean_per_occupied_voxel",
        "position_aggregation": "arithmetic_centroid_per_occupied_voxel",
        "output": point_path.name,
        "limitations": [
            "This is a representation conversion, not video reconstruction.",
            "Only source vertices are voxelized; no unseen or internal geometry is inferred.",
            "Output is a colored point cloud of voxel centers, not a watertight mesh.",
            "Metric scale is only as reliable as the source asset and its declared unit.",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "success": True,
        "point_cloud_path": str(point_path),
        "manifest_path": str(manifest_path),
        "voxel_count": int(voxel_count),
        "source_vertex_count": int(len(points)),
        "voxel_size": float(voxel_size),
        "unit": unit,
        "source_sha256": manifest["source_sha256"],
    }
