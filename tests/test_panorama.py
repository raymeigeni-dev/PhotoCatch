import cv2
import numpy as np
import pytest

from backend.panorama import equirectangular_to_perspective_views, is_equirectangular


def test_detects_standard_equirectangular_aspect_ratio():
    assert is_equirectangular(3840, 1920)
    assert is_equirectangular(1920, 960)
    assert not is_equirectangular(1920, 1080)
    assert not is_equirectangular(0, 0)


def test_projects_panorama_to_six_same_sized_perspective_views():
    height, width = 128, 256
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :width // 2] = (0, 0, 255)
    frame[:, width // 2:] = (0, 255, 0)
    views = equirectangular_to_perspective_views(frame, output_size=96)
    assert [name for name, _ in views] == ["front", "right", "back", "left", "up", "down"]
    assert all(view.shape == (96, 96, 3) for _, view in views)
    assert all(view.dtype == np.uint8 for _, view in views)
    assert len({view.tobytes() for _, view in views}) > 1


def test_up_and_down_views_use_correct_poles():
    frame = np.zeros((128, 256, 3), dtype=np.uint8)
    frame[:64, :] = (0, 0, 255)      # north/top of equirectangular image
    frame[64:, :] = (0, 255, 0)      # south/bottom
    views = dict(equirectangular_to_perspective_views(frame, output_size=96))
    up_center = views["up"][48, 48]
    down_center = views["down"][48, 48]
    assert up_center[2] > up_center[1]
    assert down_center[1] > down_center[2]


def test_rejects_non_panorama_and_invalid_options():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="2:1"):
        equirectangular_to_perspective_views(frame)
    pano = np.zeros((100, 200, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="至少为 64"):
        equirectangular_to_perspective_views(pano, output_size=32)
    with pytest.raises(ValueError, match="视场角"):
        equirectangular_to_perspective_views(pano, horizontal_fov_degrees=140)
