"""Rigid transforms and camera projection for a rotating object."""
from __future__ import annotations

import cv2
import numpy as np

from backend.rotational_capture.schema import CameraCalibration, RigCalibration


def rotation_z(degrees: float) -> np.ndarray:
    angle = np.deg2rad(float(degrees))
    c, s = np.cos(angle), np.sin(angle)
    return np.array([
        [c, -s, 0.0, 0.0],
        [s, c, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float64)


def camera_from_object(
    camera: CameraCalibration, rig: RigCalibration, angle_deg: float
) -> np.ndarray:
    """T_camera_object for object-reference coordinates at measured encoder angle."""
    return (
        camera.camera_from_rig
        @ rig.rig_from_turntable
        @ rotation_z(angle_deg)
        @ rig.turntable_from_object
    )


def project_object_points(
    points_object: np.ndarray,
    camera: CameraCalibration,
    rig: RigCalibration,
    angle_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points_object, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("points_object 必须是有限的 Nx3 数组。")
    transform = camera_from_object(camera, rig, angle_deg)
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    rvec, _ = cv2.Rodrigues(rotation)
    projected, _ = cv2.projectPoints(
        points.reshape(-1, 1, 3),
        rvec,
        translation.reshape(3, 1),
        camera.intrinsics,
        camera.distortion,
    )
    camera_points = points @ rotation.T + translation
    return projected.reshape(-1, 2), camera_points[:, 2]
