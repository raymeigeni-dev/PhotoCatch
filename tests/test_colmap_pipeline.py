from pathlib import Path

import numpy as np
import pytest
import trimesh

from backend.colmap_pipeline import ReconstructionError, inspect_mesh, run_colmap_mvs


def _write_mesh(path: Path, *, duplicate: bool = False, degenerate: bool = False) -> Path:
    vertices = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)
    faces = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ], dtype=int)
    if duplicate:
        faces = np.vstack([faces, faces[0]])
    if degenerate:
        faces = np.vstack([faces, [0, 0, 1]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.export(path)
    return path


def test_colmap_pipeline_reports_missing_executable(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    for i in range(8):
        (images / f"frame{i}.jpg").write_bytes(b"placeholder")
    with pytest.raises(ReconstructionError, match="未找到 COLMAP"):
        run_colmap_mvs(images, tmp_path / "output", executable="photocatch-colmap-not-installed")


def test_colmap_pipeline_rejects_empty_image_directory(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    with pytest.raises(ReconstructionError, match="至少需要 8 张"):
        run_colmap_mvs(images, tmp_path / "output", executable="colmap")


def test_mesh_quality_reports_watertight_cube(tmp_path):
    report = inspect_mesh(_write_mesh(tmp_path / "cube.ply"))
    assert report["vertices"] == 8
    assert report["faces"] == 12
    assert report["watertight"] is True
    assert report["duplicate_faces"] == 0
    assert report["degenerate_faces"] == 0
    assert report["connected_components"] == 1


def test_mesh_quality_rejects_duplicate_faces(tmp_path):
    with pytest.raises(ReconstructionError, match="重复三角面"):
        inspect_mesh(_write_mesh(tmp_path / "duplicate.ply", duplicate=True))


def test_mesh_quality_rejects_degenerate_faces(tmp_path):
    with pytest.raises(ReconstructionError, match="退化三角面"):
        inspect_mesh(_write_mesh(tmp_path / "degenerate.ply", degenerate=True))


def test_mesh_quality_reports_disconnected_components(tmp_path):
    first = trimesh.creation.box()
    second = trimesh.creation.box()
    second.apply_translation([3, 0, 0])
    combined = trimesh.util.concatenate([first, second])
    path = tmp_path / "two_components.ply"
    combined.export(path)
    report = inspect_mesh(path)
    assert report["connected_components"] == 2
    assert any("多个独立连通组件" in warning for warning in report["warnings"])
