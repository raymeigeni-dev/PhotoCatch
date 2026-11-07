"""Suspended-garment capture protocol and manifest assembly."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from backend.rotational_capture.encoder import EncoderTrack
from backend.rotational_capture.sync_bridge import SynchronizedGroup


class HangingCaptureError(ValueError):
    """Invalid suspended garment capture setup."""


@dataclass(frozen=True)
class HangingCaptureConfig:
    camera_ids: tuple[str, str, str]
    camera_azimuth_deg: tuple[float, float, float]
    rotation_axis: str = "Z"
    suspension: str = "overhead_hanger"
    target_rpm: float = 1.0
    sample_step_deg: float = 2.0
    max_camera_skew_ns: int = 5_000_000
    max_encoder_skew_ns: int = 5_000_000
    shutter_models: dict[str, str] | None = None

    def validate(self) -> None:
        if len(set(self.camera_ids)) != 3 or any(not value for value in self.camera_ids):
            raise HangingCaptureError("必须配置三个不同且非空的 camera_id。")
        if len(self.camera_azimuth_deg) != 3:
            raise HangingCaptureError("必须配置三个相机方位角。")
        angles = sorted(float(value) % 360.0 for value in self.camera_azimuth_deg)
        gaps = [(angles[(i + 1) % 3] - angles[i]) % 360.0 for i in range(3)]
        if any(abs(gap - 120.0) > 15.0 for gap in gaps):
            raise HangingCaptureError("三台相机应近似均匀环绕，方位间隔建议 120°±15°。")
        if self.rotation_axis != "Z" or self.suspension != "overhead_hanger":
            raise HangingCaptureError("本协议要求顶部悬挂、绕垂直 Z 轴旋转。")
        if not 0.1 <= self.target_rpm <= 3.0:
            raise HangingCaptureError("建议旋转速度限制在 0.1–3 RPM。")
        if not 0.25 <= self.sample_step_deg <= 10.0:
            raise HangingCaptureError("sample_step_deg 必须在 0.25°–10°。")
        if self.max_camera_skew_ns < 0 or self.max_encoder_skew_ns < 0:
            raise HangingCaptureError("同步误差阈值不能为负数。")
        if self.shutter_models:
            unknown = set(self.shutter_models) - set(self.camera_ids)
            if unknown:
                raise HangingCaptureError(f"快门模型包含未知相机：{sorted(unknown)}")
            if any(value not in {"global", "rolling", "unknown"} for value in self.shutter_models.values()):
                raise HangingCaptureError("shutter_models 只允许 global、rolling 或 unknown。")

    def target_angles(self) -> list[float]:
        self.validate()
        count = int(round(360.0 / self.sample_step_deg))
        return [index * 360.0 / count for index in range(count)]


def write_capture_manifest(
    groups: list[SynchronizedGroup],
    encoder: EncoderTrack,
    output_path: str | Path,
    *,
    max_camera_skew_ns: int = 5_000_000,
    max_encoder_skew_ns: int = 5_000_000,
) -> dict:
    """Convert synchronized video frames + encoder evidence to pipeline schema v1."""
    if not groups:
        raise HangingCaptureError("没有同步采集组。")
    records = []
    for group in groups:
        frame_times = [frame.reference_time_ns for frame in group.frames]
        if max(frame_times) - min(frame_times) > max_camera_skew_ns:
            raise HangingCaptureError(f"{group.capture_id} 相机帧同步误差超限。")
        reference_time = group.reference_time_ns
        angle = encoder.angle_at(reference_time)
        nearest_encoder_skew = min(
            abs(reference_time - frame_time) for frame_time in frame_times
        )
        if nearest_encoder_skew > max_encoder_skew_ns:
            raise HangingCaptureError(f"{group.capture_id} 编码器时间与曝光时间误差超限。")
        records.append({
            "capture_id": group.capture_id,
            "angle_deg": angle,
            "encoder_timestamp_ns": reference_time,
            "frames": [
                {
                    "camera_id": frame.camera_id,
                    "timestamp_ns": frame.reference_time_ns,
                    "image_path": frame.image_path,
                    "mask_path": frame.mask_path,
                }
                for frame in group.frames
            ],
        })
    payload = {
        "schema_version": 1,
        "max_sync_skew_ns": max(max_camera_skew_ns, max_encoder_skew_ns),
        "capture_groups": records,
        "capture_mode": "suspended_garment_rotation",
        "sync_method": "optical_timecode_clock_mapping",
        "angle_source": "timestamped_rotary_encoder_interpolation",
        "limitations": [
            "Rolling-shutter row-time compensation is not yet applied by the current visual-hull projector.",
            "Garment swing/deformation must be measured or controlled; rigid rotation is assumed by the current geometry solver.",
            "This manifest is not evidence of real camera or physical rig acceptance.",
        ],
    }
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
