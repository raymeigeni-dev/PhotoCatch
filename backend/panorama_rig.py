"""COLMAP rig metadata for virtual cameras projected from a single 360 frame."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Must stay synchronized with panorama.equirectangular_to_perspective_views.
# R_rig_from_camera maps camera-local rays into the panorama rig coordinate system.
VIEW_ORIENTATIONS_DEGREES = {
    "front": (0.0, 0.0),
    "right": (90.0, 0.0),
    "back": (180.0, 0.0),
    "left": (270.0, 0.0),
    "up": (0.0, 55.0),
    "down": (0.0, -55.0),
}


def _rotation_matrix(yaw_degrees: float, pitch_degrees: float) -> np.ndarray:
    yaw, pitch = np.deg2rad(yaw_degrees), np.deg2rad(pitch_degrees)
    # Exact convention used by panorama.py: R_y(yaw) @ R_x(-pitch).
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rx_minus_pitch = np.array([[1.0, 0.0, 0.0], [0.0, cp, sp], [0.0, -sp, cp]])
    return ry @ rx_minus_pitch


def _matrix_to_quaternion_wxyz(matrix: np.ndarray) -> list[float]:
    """Convert a proper 3x3 rotation matrix to normalized COLMAP [w,x,y,z]."""
    m = np.asarray(matrix, dtype=float)
    trace = float(np.trace(m))
    if trace > 0:
        s = np.sqrt(trace + 1.0) * 2.0
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s,
             (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s,
             (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s,
             0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s,
             (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.asarray(q, dtype=float)
    q /= np.linalg.norm(q)
    return [float(v) for v in q]


def view_cam_from_rig_quaternion(view_name: str) -> list[float]:
    """COLMAP's cam_from_rig rotation; all virtual camera translations are zero."""
    if view_name not in VIEW_ORIENTATIONS_DEGREES:
        raise ValueError(f"Unknown panorama view: {view_name}")
    yaw, pitch = VIEW_ORIENTATIONS_DEGREES[view_name]
    # panorama.py maps a camera ray into rig/world axes. COLMAP needs the inverse.
    return _matrix_to_quaternion_wxyz(_rotation_matrix(yaw, pitch).T)


def build_rig_config() -> list[dict]:
    cameras = []
    for name in VIEW_ORIENTATIONS_DEGREES:
        camera = {"image_prefix": f"{name}/"}
        if name == "front":
            camera["ref_sensor"] = True
        else:
            camera["cam_from_rig_rotation"] = view_cam_from_rig_quaternion(name)
            camera["cam_from_rig_translation"] = [0.0, 0.0, 0.0]
        cameras.append(camera)
    return [{"cameras": cameras}]


def write_rig_config(path: str | Path) -> Path:
    target = Path(path)
    target.write_text(json.dumps(build_rig_config(), indent=2) + "\n", encoding="utf-8")
    return target
