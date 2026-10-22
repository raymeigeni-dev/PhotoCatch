from pathlib import Path

import pytest

from backend.colmap_pipeline import ReconstructionError, run_colmap_mvs


def test_colmap_pipeline_reports_missing_executable(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "frame.jpg").write_bytes(b"placeholder")
    with pytest.raises(ReconstructionError, match="未找到 COLMAP"):
        run_colmap_mvs(images, tmp_path / "output", executable="photocatch-colmap-not-installed")


def test_colmap_pipeline_rejects_empty_image_directory(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    with pytest.raises(ReconstructionError, match="没有可用于摄影测量"):
        run_colmap_mvs(images, tmp_path / "output", executable="colmap")
