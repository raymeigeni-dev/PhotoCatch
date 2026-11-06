from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.rotational_capture.geometry import camera_from_object, rotation_z
from backend.rotational_capture.pipeline import (
    RotationalCaptureError,
    reconstruct_visual_hull,
)
from backend.rotational_capture.schema import (
    CaptureValidationError,
    load_calibration,
    load_capture_sequence,
)


def _write_rig(root: Path, *, unit: str = "cm") -> Path:
    identity = np.eye(4).tolist()
    rig_from_turntable = np.eye(4)
    rig_from_turntable[2, 3] = 2.0
    cameras = []
    for camera_id in ("cam_a", "cam_b", "cam_c"):
        cameras.append({
            "camera_id": camera_id,
            "intrinsics": [[100.0, 0.0, 32.0], [0.0, 100.0, 32.0], [0.0, 0.0, 1.0]],
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
            "camera_from_rig": identity,
            "image_width": 64,
            "image_height": 64,
            "shutter_type": "global",
        })
    path = root / "calibration.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "unit": unit,
        "rig_from_turntable": rig_from_turntable.tolist(),
        "turntable_from_object": identity,
        "scale_calibration": {"status": "uncalibrated"},
        "cameras": cameras,
    }), encoding="utf-8")
    return path


def _write_capture(root: Path, *, skew_ns: int = 100, missing_camera: bool = False) -> Path:
    groups = []
    for group_index, angle in enumerate((0.0, 10.0)):
        frames = []
        ids = ("cam_a", "cam_b") if missing_camera else ("cam_a", "cam_b", "cam_c")
        for camera_index, camera_id in enumerate(ids):
            image_name = f"g{group_index}_{camera_id}.png"
            mask_name = f"g{group_index}_{camera_id}_mask.png"
            image = np.zeros((64, 64, 3), dtype=np.uint8)
            image[:, :] = (20 + camera_index * 30, 80, 180)
            mask = np.full((64, 64), 255, dtype=np.uint8)
            assert cv2.imwrite(str(root / image_name), image)
            assert cv2.imwrite(str(root / mask_name), mask)
            frames.append({
                "camera_id": camera_id,
                "timestamp_ns": group_index * 10_000_000 + camera_index * skew_ns,
                "image_path": image_name,
                "mask_path": mask_name,
            })
        groups.append({
            "capture_id": f"capture_{group_index}",
            "angle_deg": angle,
            "encoder_timestamp_ns": group_index * 10_000_000 + skew_ns,
            "frames": frames,
        })
    path = root / "capture.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "max_sync_skew_ns": max(1000, skew_ns * 3),
        "capture_groups": groups,
    }), encoding="utf-8")
    return path


def test_rotation_z_is_right_handed_and_90_degrees_maps_x_to_y():
    transformed = rotation_z(90) @ np.array([1.0, 0.0, 0.0, 1.0])
    np.testing.assert_allclose(transformed[:3], [0.0, 1.0, 0.0], atol=1e-7)


def test_camera_from_object_uses_measured_encoder_angle(tmp_path):
    calibration_path = _write_rig(tmp_path)
    rig = load_calibration(calibration_path)
    camera = rig.cameras["cam_a"]
    transform = camera_from_object(camera, rig, 90)
    np.testing.assert_allclose(transform[:3, 3], [0, 0, 2])
    point = transform @ np.array([1.0, 0.0, 0.0, 1.0])
    np.testing.assert_allclose(point[:3], [0.0, 1.0, 2.0], atol=1e-7)


def test_calibration_requires_exactly_three_cameras(tmp_path):
    path = _write_rig(tmp_path)
    raw = json.loads(path.read_text())
    raw["cameras"] = raw["cameras"][:2]
    path.write_text(json.dumps(raw))
    with pytest.raises(CaptureValidationError, match="恰好三台"):
        load_calibration(path)


def test_calibration_rejects_non_rigid_extrinsic(tmp_path):
    path = _write_rig(tmp_path)
    raw = json.loads(path.read_text())
    raw["cameras"][0]["camera_from_rig"][0][0] = 2.0
    path.write_text(json.dumps(raw))
    with pytest.raises(CaptureValidationError, match="正交矩阵"):
        load_calibration(path)


def test_capture_manifest_rejects_camera_sync_skew(tmp_path):
    _write_rig(tmp_path)
    path = _write_capture(tmp_path, skew_ns=2_000_000)
    raw = json.loads(path.read_text())
    raw["max_sync_skew_ns"] = 100
    path.write_text(json.dumps(raw))
    with pytest.raises(CaptureValidationError, match="不同步"):
        load_capture_sequence(path)


def test_capture_manifest_requires_three_unique_cameras_per_group(tmp_path):
    _write_rig(tmp_path)
    path = _write_capture(tmp_path, missing_camera=True)
    with pytest.raises(CaptureValidationError, match="恰好包含三台"):
        load_capture_sequence(path)


def test_capture_manifest_rejects_rotation_direction_reversal(tmp_path):
    path = _write_capture(tmp_path)
    raw = json.loads(path.read_text())
    raw["capture_groups"][1]["angle_deg"] = 350.0
    raw["capture_groups"][0]["angle_deg"] = 10.0
    raw["capture_groups"].append({
        "capture_id": "capture_2",
        "angle_deg": 5.0,
        "encoder_timestamp_ns": 20_000_100,
        "frames": raw["capture_groups"][0]["frames"],
    })
    path.write_text(json.dumps(raw))
    with pytest.raises(CaptureValidationError, match="反转"):
        load_capture_sequence(path)


def test_visual_hull_writes_observed_rgb_and_provenance(tmp_path):
    calibration = _write_rig(tmp_path)
    capture = _write_capture(tmp_path)
    result = reconstruct_visual_hull(
        calibration,
        capture,
        tmp_path / "output",
        bounds_min=[-0.1, -0.1, -0.1],
        bounds_max=[0.1, 0.1, 0.1],
        voxel_size=0.1,
        min_observations=1,
    )

    assert result["status"] == "visual_hull_with_observed_surface_rgb"
    assert result["occupied_voxels"] == 8
    assert result["colored_surface_voxels"] > 0
    assert Path(result["occupancy_path"]).is_file()
    assert Path(result["point_cloud_path"]).is_file()
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["scale_status"] == "uncalibrated"
    assert "not dense multi-view stereo" in manifest["limitations"][0]
    occupancy = np.load(result["occupancy_path"])
    assert occupancy["occupied_centers"].shape == (8, 3)
    assert occupancy["surface_color_observed"].any()


def test_visual_hull_rejects_missing_camera_calibration(tmp_path):
    calibration = _write_rig(tmp_path)
    capture = _write_capture(tmp_path)
    raw = json.loads(calibration.read_text())
    raw["cameras"] = raw["cameras"][:2]
    calibration.write_text(json.dumps(raw))
    with pytest.raises(RotationalCaptureError, match="恰好三台"):
        reconstruct_visual_hull(
            calibration, capture, tmp_path / "out",
            bounds_min=[-0.1] * 3, bounds_max=[0.1] * 3, voxel_size=0.1,
        )


def test_visual_hull_rejects_bounds_exceeding_candidate_limit(tmp_path):
    calibration = _write_rig(tmp_path)
    capture = _write_capture(tmp_path)
    with pytest.raises(RotationalCaptureError, match="超过限制"):
        reconstruct_visual_hull(
            calibration, capture, tmp_path / "out",
            bounds_min=[-1.0] * 3, bounds_max=[1.0] * 3,
            voxel_size=0.01, max_candidate_voxels=100,
        )


def test_calibration_rejects_rolling_shutter_without_row_time_model(tmp_path):
    path = _write_rig(tmp_path)
    raw = json.loads(path.read_text())
    raw["cameras"][1]["shutter_type"] = "rolling"
    path.write_text(json.dumps(raw))
    with pytest.raises(CaptureValidationError, match="global shutter"):
        load_calibration(path)


def test_capture_manifest_rejects_encoder_angle_not_synchronized_to_exposure(tmp_path):
    path = _write_capture(tmp_path)
    raw = json.loads(path.read_text())
    raw["capture_groups"][0]["encoder_timestamp_ns"] += 50_000
    path.write_text(json.dumps(raw))
    with pytest.raises(CaptureValidationError, match="编码器角度采样与曝光时间不同步"):
        load_capture_sequence(path)


def test_visual_hull_rejects_empty_masks_instead_of_fabricating_geometry(tmp_path):
    calibration = _write_rig(tmp_path)
    capture = _write_capture(tmp_path)
    raw = json.loads(capture.read_text())
    for group in raw["capture_groups"]:
        for frame in group["frames"]:
            mask_path = tmp_path / frame["mask_path"]
            empty = np.zeros((64, 64), dtype=np.uint8)
            assert cv2.imwrite(str(mask_path), empty)
    with pytest.raises(RotationalCaptureError, match="没有体素通过"):
        reconstruct_visual_hull(
            calibration,
            capture,
            tmp_path / "out",
            bounds_min=[-0.1] * 3,
            bounds_max=[0.1] * 3,
            voxel_size=0.1,
            min_observations=1,
        )
