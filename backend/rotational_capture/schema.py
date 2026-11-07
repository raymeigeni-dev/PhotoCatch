"""Strict data contracts for three-camera rotational capture."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import numpy as np


class CaptureValidationError(ValueError):
    """Invalid calibration or capture evidence."""


@dataclass(frozen=True)
class CameraCalibration:
    camera_id: str
    intrinsics: np.ndarray
    distortion: np.ndarray
    camera_from_rig: np.ndarray
    image_width: int
    image_height: int
    shutter_type: str


@dataclass(frozen=True)
class RigCalibration:
    cameras: dict[str, CameraCalibration]
    rig_from_turntable: np.ndarray
    turntable_from_object: np.ndarray
    unit: str
    scale_status: str
    scale_source: str | None
    scale_uncertainty: float | None


@dataclass(frozen=True)
class Observation:
    capture_id: str
    camera_id: str
    timestamp_ns: int
    angle_deg: float
    image_path: Path
    mask_path: Path


@dataclass(frozen=True)
class CaptureSequence:
    observations: tuple[Observation, ...]
    max_sync_skew_ns: int


def _rigid_transform(value: Any, label: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise CaptureValidationError(f"{label} 必须是有限的 4x4 矩阵。")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-7):
        raise CaptureValidationError(f"{label} 最后一行必须为 [0,0,0,1]。")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5):
        raise CaptureValidationError(f"{label} 旋转部分不是正交矩阵。")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5):
        raise CaptureValidationError(f"{label} 旋转行列式必须为 +1。")
    return matrix


def load_calibration(path: str | Path) -> RigCalibration:
    source = Path(path).expanduser().resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureValidationError(f"无法读取标定文件：{exc}") from exc

    if raw.get("schema_version") != 1:
        raise CaptureValidationError("不支持的标定 schema_version；当前要求为 1。")
    unit = raw.get("unit")
    if unit not in {"m", "cm", "mm"}:
        raise CaptureValidationError("必须明确声明单位 m、cm 或 mm。")

    camera_items = raw.get("cameras")
    if not isinstance(camera_items, list) or len(camera_items) != 3:
        raise CaptureValidationError("必须提供恰好三台固定相机的标定数据。")

    cameras: dict[str, CameraCalibration] = {}
    for item in camera_items:
        camera_id = str(item.get("camera_id", "")).strip()
        if not camera_id or camera_id in cameras:
            raise CaptureValidationError("camera_id 不能为空且必须唯一。")
        intrinsics = np.asarray(item.get("intrinsics"), dtype=np.float64)
        distortion = np.asarray(item.get("distortion", []), dtype=np.float64).reshape(-1)
        if intrinsics.shape != (3, 3) or not np.isfinite(intrinsics).all():
            raise CaptureValidationError(f"{camera_id} 内参必须是有限 3x3 矩阵。")
        if intrinsics[0, 0] <= 0 or intrinsics[1, 1] <= 0 or abs(intrinsics[2, 2] - 1) > 1e-6:
            raise CaptureValidationError(f"{camera_id} 焦距或内参矩阵无效。")
        if not np.isfinite(distortion).all():
            raise CaptureValidationError(f"{camera_id} 畸变参数包含非有限值。")
        width, height = int(item.get("image_width", 0)), int(item.get("image_height", 0))
        if width < 32 or height < 32:
            raise CaptureValidationError(f"{camera_id} 图像尺寸无效。")
        shutter_type = str(item.get("shutter_type", "unknown")).lower()
        if shutter_type != "global":
            raise CaptureValidationError(
                f"{camera_id} 必须声明 global shutter；当前流水线尚未实现 rolling-shutter 行时补偿。"
            )
        cameras[camera_id] = CameraCalibration(
            camera_id=camera_id,
            intrinsics=intrinsics,
            distortion=distortion,
            camera_from_rig=_rigid_transform(item.get("camera_from_rig"), f"{camera_id}.camera_from_rig"),
            image_width=width,
            image_height=height,
            shutter_type=shutter_type,
        )

    scale = raw.get("scale_calibration", {})
    status = scale.get("status", "uncalibrated")
    if status not in {"calibrated", "uncalibrated"}:
        raise CaptureValidationError("scale_calibration.status 必须是 calibrated 或 uncalibrated。")
    scale_source = scale.get("source")
    uncertainty = scale.get("uncertainty")
    if status == "calibrated":
        if not isinstance(scale_source, str) or not scale_source.strip():
            raise CaptureValidationError("已校准尺度必须记录可追溯的 scale_calibration.source。")
        if uncertainty is None or not np.isfinite(float(uncertainty)) or float(uncertainty) < 0:
            raise CaptureValidationError("已校准尺度必须记录非负有限 uncertainty。")

    return RigCalibration(
        cameras=cameras,
        rig_from_turntable=_rigid_transform(raw.get("rig_from_turntable"), "rig_from_turntable"),
        turntable_from_object=_rigid_transform(raw.get("turntable_from_object"), "turntable_from_object"),
        unit=unit,
        scale_status=status,
        scale_source=scale_source,
        scale_uncertainty=float(uncertainty) if uncertainty is not None else None,
    )


def load_capture_sequence(path: str | Path) -> CaptureSequence:
    manifest_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureValidationError(f"无法读取采集清单：{exc}") from exc
    if raw.get("schema_version") != 1:
        raise CaptureValidationError("不支持的采集清单 schema_version；当前要求为 1。")
    max_skew = int(raw.get("max_sync_skew_ns", 1_000_000))
    if max_skew < 0:
        raise CaptureValidationError("max_sync_skew_ns 不能小于 0。")
    groups = raw.get("capture_groups")
    if not isinstance(groups, list) or len(groups) < 2:
        raise CaptureValidationError("至少需要两个同步采集时刻。")

    observations: list[Observation] = []
    previous_angle: float | None = None
    direction: float | None = None
    for group in groups:
        capture_id = str(group.get("capture_id", "")).strip()
        angle = float(group.get("angle_deg", float("nan")))
        encoder_timestamp = int(group.get("encoder_timestamp_ns", -1))
        if not capture_id or not np.isfinite(angle) or encoder_timestamp < 0:
            raise CaptureValidationError(
                "每个采集组都必须具有 capture_id、有限 encoder angle_deg 和 encoder_timestamp_ns。"
            )
        if previous_angle is not None:
            delta = (angle - previous_angle + 180.0) % 360.0 - 180.0
            if abs(delta) < 1e-6:
                raise CaptureValidationError("相邻采集组旋转角度没有变化。")
            current_direction = 1.0 if delta > 0 else -1.0
            if direction is not None and current_direction != direction:
                raise CaptureValidationError("旋转方向发生反转；请拆分为独立扫描任务。")
            direction = current_direction
        previous_angle = angle

        frames = group.get("frames")
        if not isinstance(frames, list) or len(frames) != 3:
            raise CaptureValidationError(f"{capture_id} 必须恰好包含三台相机的帧。")
        ids = [str(frame.get("camera_id", "")) for frame in frames]
        if len(set(ids)) != 3:
            raise CaptureValidationError(f"{capture_id} 存在重复 camera_id。")
        timestamps = []
        for frame in frames:
            camera_id = str(frame.get("camera_id", ""))
            timestamp = int(frame.get("timestamp_ns", -1))
            if timestamp < 0:
                raise CaptureValidationError(f"{capture_id}/{camera_id} 缺少有效曝光时间戳。")
            timestamps.append(timestamp)
            image_path = (manifest_path.parent / str(frame.get("image_path", ""))).resolve()
            mask_path = (manifest_path.parent / str(frame.get("mask_path", ""))).resolve()
            if not image_path.is_file() or not mask_path.is_file():
                raise CaptureValidationError(f"{capture_id}/{camera_id} 原始图像或前景 mask 不存在。")
            observations.append(Observation(
                capture_id=capture_id,
                camera_id=camera_id,
                timestamp_ns=timestamp,
                angle_deg=angle,
                image_path=image_path,
                mask_path=mask_path,
            ))
        if max(timestamps) - min(timestamps) > max_skew:
            raise CaptureValidationError(
                f"{capture_id} 三台相机曝光不同步：skew={max(timestamps)-min(timestamps)} ns，"
                f"limit={max_skew} ns。"
            )
        exposure_midpoint = int(round(float(np.mean(timestamps))))
        encoder_skew = abs(encoder_timestamp - exposure_midpoint)
        if encoder_skew > max_skew:
            raise CaptureValidationError(
                f"{capture_id} 编码器角度采样与曝光时间不同步：skew={encoder_skew} ns，"
                f"limit={max_skew} ns。"
            )

    return CaptureSequence(tuple(observations), max_skew)
