"""Perspective-view extraction for equirectangular 360-degree video frames.

The virtual views improve feature coverage; they do not create new camera baselines.
True depth still requires camera translation/parallax across source frames.
"""
from __future__ import annotations

import cv2
import numpy as np


def is_equirectangular(width: int, height: int, tolerance: float = 0.18) -> bool:
    """Return whether frame dimensions are consistent with a 2:1 equirectangular panorama."""
    if width <= 0 or height <= 0:
        return False
    return abs((width / height) - 2.0) <= tolerance


def equirectangular_to_perspective_views(
    frame: np.ndarray,
    *,
    output_size: int = 640,
    horizontal_fov_degrees: float = 100.0,
) -> list[tuple[str, np.ndarray]]:
    """Project a 2:1 equirectangular frame into six overlapping perspective views."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("全景帧必须是 H×W×3 的彩色图像")
    height, width = frame.shape[:2]
    if not is_equirectangular(width, height):
        raise ValueError("360°全景视频帧应接近 2:1 等距柱状投影；请检查设备导出格式")
    if output_size < 64:
        raise ValueError("透视视图尺寸至少为 64 像素")
    if not 60.0 <= horizontal_fov_degrees <= 120.0:
        raise ValueError("水平视场角必须在 60° 至 120° 之间")

    fov = np.deg2rad(horizontal_fov_degrees)
    focal = (output_size / 2.0) / np.tan(fov / 2.0)
    coords = np.arange(output_size, dtype=np.float32)
    xx, yy = np.meshgrid(coords, coords)
    x = (xx - (output_size - 1) / 2.0) / focal
    y = -((yy - (output_size - 1) / 2.0) / focal)
    z = np.ones_like(x)
    norm = np.sqrt(x * x + y * y + z * z)
    x, y, z = x / norm, y / norm, z / norm

    views: list[tuple[str, np.ndarray]] = []
    # Four horizontal views plus upward/downward views. Each view uses identical
    # intrinsics and output dimensions so the downstream SfM camera model is shared.
    orientations = [
        ("front", 0.0, 0.0), ("right", 90.0, 0.0),
        ("back", 180.0, 0.0), ("left", 270.0, 0.0),
        ("up", 0.0, 55.0), ("down", 0.0, -55.0),
    ]
    for name, yaw_deg, pitch_deg in orientations:
        yaw, pitch = np.deg2rad(yaw_deg), np.deg2rad(pitch_deg)
        # Camera-local ray -> world ray: yaw around vertical, then pitch.
        xp = x * np.cos(yaw) + z * np.sin(yaw)
        zp = -x * np.sin(yaw) + z * np.cos(yaw)
        yp = y * np.cos(pitch) - zp * np.sin(pitch)
        z_world = y * np.sin(pitch) + zp * np.cos(pitch)
        longitude = np.arctan2(xp, z_world)
        latitude = np.arcsin(np.clip(yp, -1.0, 1.0))
        map_x = ((longitude / (2.0 * np.pi)) + 0.5) * width
        map_y = (0.5 - latitude / np.pi) * height
        # Horizontal wrap is essential at the equirectangular seam.
        map_x = np.mod(map_x, width).astype(np.float32)
        map_y = np.clip(map_y, 0, height - 1).astype(np.float32)
        view = cv2.remap(frame, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_WRAP)
        views.append((name, view))
    return views
