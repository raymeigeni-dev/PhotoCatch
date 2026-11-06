from pathlib import Path
import json

import numpy as np
import pytest
import trimesh

from backend.voxelization import VoxelizationError, voxelize_colored_asset


def _write_colored_cloud(path: Path, points=None, colors=None):
    points = np.asarray(points if points is not None else [
        [0.1, 0.1, 0.1], [0.2, 0.1, 0.1], [1.2, 0.1, 0.1]
    ], dtype=float)
    colors = np.asarray(colors if colors is not None else [
        [255, 0, 0], [0, 0, 255], [0, 255, 0]
    ], dtype=np.uint8)
    trimesh.points.PointCloud(points, colors=colors).export(path)


def test_voxelize_groups_points_and_averages_observed_color(tmp_path):
    source = tmp_path / "source.ply"
    _write_colored_cloud(source)
    result = voxelize_colored_asset(
        source, tmp_path / "out", voxel_size=1.0, unit="m"
    )

    assert result["success"] is True
    assert result["source_vertex_count"] == 3
    assert result["voxel_count"] == 2
    output = trimesh.load(result["point_cloud_path"], process=False)
    assert len(output.vertices) == 2
    colors = np.asarray(output.colors)[:, :3]
    assert any(np.array_equal(color, [128, 0, 128]) for color in colors)
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["unit"] == "m"
    assert manifest["color_source"] == "source_vertex_rgb"
    assert manifest["source_sha256"] == result["source_sha256"]


def test_voxelization_rejects_missing_vertex_colors(tmp_path):
    source = tmp_path / "uncolored.ply"
    trimesh.points.PointCloud([[0, 0, 0], [1, 0, 0]]).export(source)
    with pytest.raises(VoxelizationError, match="缺少逐顶点 RGB"):
        voxelize_colored_asset(source, tmp_path / "out", voxel_size=1, unit="m")


@pytest.mark.parametrize("unit", ["", "inch", "unknown"])
def test_voxelization_requires_explicit_supported_unit(tmp_path, unit):
    source = tmp_path / "source.ply"
    _write_colored_cloud(source)
    with pytest.raises(VoxelizationError, match="必须明确指定单位"):
        voxelize_colored_asset(source, tmp_path / "out", voxel_size=1, unit=unit)


def test_voxelization_rejects_invalid_voxel_size(tmp_path):
    source = tmp_path / "source.ply"
    _write_colored_cloud(source)
    with pytest.raises(VoxelizationError, match="voxel_size"):
        voxelize_colored_asset(source, tmp_path / "out", voxel_size=0, unit="m")


def test_voxelization_enforces_voxel_count_limit(tmp_path):
    source = tmp_path / "source.ply"
    _write_colored_cloud(source)
    with pytest.raises(VoxelizationError, match="超过上限"):
        voxelize_colored_asset(
            source, tmp_path / "out", voxel_size=0.01, unit="m", max_voxels=1
        )


def test_voxelization_does_not_modify_source_asset(tmp_path):
    source = tmp_path / "source.ply"
    _write_colored_cloud(source)
    before = source.read_bytes()
    voxelize_colored_asset(source, tmp_path / "out", voxel_size=1, unit="m")
    assert source.read_bytes() == before
