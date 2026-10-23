import json

import numpy as np
import pytest

from backend.panorama_rig import (
    VIEW_ORIENTATIONS_DEGREES,
    _rotation_matrix,
    build_rig_config,
    view_cam_from_rig_quaternion,
    write_rig_config,
)


def _quaternion_matrix_wxyz(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ])


def test_all_six_view_rotations_are_valid_and_orthonormal():
    assert list(VIEW_ORIENTATIONS_DEGREES) == ["front", "right", "back", "left", "up", "down"]
    for name, (yaw, pitch) in VIEW_ORIENTATIONS_DEGREES.items():
        rotation = _rotation_matrix(yaw, pitch)
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-7)
        assert np.linalg.det(rotation) == pytest.approx(1.0, abs=1e-7)
        q = view_cam_from_rig_quaternion(name)
        assert len(q) == 4
        assert np.linalg.norm(q) == pytest.approx(1.0, abs=1e-7)
        # COLMAP cam_from_rig must be the inverse of the camera-local-to-rig rotation.
        np.testing.assert_allclose(_quaternion_matrix_wxyz(q), rotation.T, atol=1e-6)


def test_front_is_reference_and_other_sensor_translations_are_zero():
    config = build_rig_config()
    assert len(config) == 1
    cameras = config[0]["cameras"]
    assert [camera["image_prefix"] for camera in cameras] == [
        "front/", "right/", "back/", "left/", "up/", "down/"
    ]
    assert cameras[0]["ref_sensor"] is True
    assert "cam_from_rig_rotation" not in cameras[0]
    for camera in cameras[1:]:
        assert len(camera["cam_from_rig_rotation"]) == 4
        assert camera["cam_from_rig_translation"] == [0.0, 0.0, 0.0]


def test_rig_config_is_written_as_valid_json(tmp_path):
    path = write_rig_config(tmp_path / "rig_config.json")
    assert json.loads(path.read_text()) == build_rig_config()


def test_unknown_view_rotation_is_rejected():
    with pytest.raises(ValueError, match="Unknown panorama view"):
        view_cam_from_rig_quaternion("northeast")
