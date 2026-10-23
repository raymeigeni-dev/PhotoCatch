from pathlib import Path
import sqlite3

import numpy as np
import pytest
import trimesh

from backend.colmap_pipeline import (ReconstructionError, _openmvs_densify_command,
                                     _remove_same_capture_panorama_pairs, _validate_openmvs_scene_image_paths,
                                     _validate_point_cloud, inspect_mesh, run_colmap_mvs)


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


def test_panorama_filter_removes_only_same_source_frame_pairs(tmp_path):
    database = tmp_path / "database.db"
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE images (image_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE matches (pair_id INTEGER PRIMARY KEY);
            CREATE TABLE two_view_geometries (pair_id INTEGER PRIMARY KEY);
        """)
        db.executemany("INSERT INTO images VALUES (?, ?)", [
            (1, "front/frame_0000.jpg"),
            (2, "right/frame_0000.jpg"),
            (3, "front/frame_0001.jpg"),
        ])
        same_frame_pair = 2147483647 * 1 + 2
        different_frame_pair = 2147483647 * 1 + 3
        db.executemany("INSERT INTO matches VALUES (?)", [(same_frame_pair,), (different_frame_pair,)])
        db.executemany("INSERT INTO two_view_geometries VALUES (?)", [(same_frame_pair,), (different_frame_pair,)])
    removed = _remove_same_capture_panorama_pairs(database)
    assert removed == 1
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT pair_id FROM matches ORDER BY pair_id").fetchall() == [(different_frame_pair,)]
        assert db.execute("SELECT pair_id FROM two_view_geometries ORDER BY pair_id").fetchall() == [(different_frame_pair,)]


def test_panorama_filter_is_noop_for_regular_video_names(tmp_path):
    database = tmp_path / "database.db"
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE images (image_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE matches (pair_id INTEGER PRIMARY KEY);
            CREATE TABLE two_view_geometries (pair_id INTEGER PRIMARY KEY);
        """)
        db.executemany("INSERT INTO images VALUES (?, ?)", [(1, "frame_0000.jpg"), (2, "frame_0001.jpg")])
    assert _remove_same_capture_panorama_pairs(database) == 0



def test_openmvs_densify_uses_depth_map_fusion_mode():
    assert _openmvs_densify_command("DensifyPointCloud", "/tmp/scene.mvs") == [
        "DensifyPointCloud", "/tmp/scene.mvs", "--fusion-mode", "0"
    ]


def test_openmvs_densify_can_retry_at_full_resolution():
    assert _openmvs_densify_command(
        "DensifyPointCloud", "/tmp/scene.mvs", resolution_level=0
    ) == [
        "DensifyPointCloud", "/tmp/scene.mvs", "--fusion-mode", "0",
        "--resolution-level", "0",
    ]



def test_openmvs_scene_rejects_stale_absolute_image_paths(tmp_path):
    images = tmp_path / "dense" / "images"
    images.mkdir(parents=True)
    (images / "frame_0000.jpg").write_bytes(b"placeholder")
    scene = tmp_path / "scene.mvs"
    scene.write_bytes(b"OpenMVS scene /old/PhotoCatch/images/frame_0000.jpg\\x00" + b"x" * 256)
    with pytest.raises(ReconstructionError, match="引用了不存在的图片路径"):
        _validate_openmvs_scene_image_paths(scene, images)


def test_openmvs_scene_accepts_existing_image_directory_without_stale_paths(tmp_path):
    images = tmp_path / "dense" / "images"
    images.mkdir(parents=True)
    (images / "frame_0000.jpg").write_bytes(b"placeholder")
    scene = tmp_path / "scene.mvs"
    scene.write_bytes(b"OpenMVS scene" + b"x" * 256)
    _validate_openmvs_scene_image_paths(scene, images)


def test_point_cloud_validation_rejects_corrupt_ply(tmp_path):
    path = tmp_path / "corrupt.ply"
    path.write_bytes(b"not a ply file" + b"x" * 200)
    with pytest.raises(ReconstructionError, match="无法解析 PLY"):
        _validate_point_cloud(path)


def test_point_cloud_validation_accepts_real_ply_points(tmp_path):
    cloud = trimesh.points.PointCloud(np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 2.0, 0.0]
    ]))
    path = tmp_path / "points.ply"
    cloud.export(path)
    report = _validate_point_cloud(path)
    assert report["points"] == 3
    assert report["bytes"] == path.stat().st_size
