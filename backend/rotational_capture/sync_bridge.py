"""Indirect synchronization for three independent video recorders.

The bridge consumes decoded optical timecode observations. It does not assume
shared device clocks, camera SDK support, or hardware genlock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


class SyncBridgeError(ValueError):
    """Synchronization evidence is missing, ambiguous, or out of tolerance."""


@dataclass(frozen=True)
class OpticalPulse:
    camera_id: str
    pts_ns: int
    pulse_id: int
    reference_time_ns: int


@dataclass(frozen=True)
class VideoFrame:
    camera_id: str
    pts_ns: int
    image_path: str
    mask_path: str


@dataclass(frozen=True)
class MappedFrame:
    camera_id: str
    pts_ns: int
    reference_time_ns: int
    image_path: str
    mask_path: str
    clock_residual_ns: float


@dataclass(frozen=True)
class SynchronizedGroup:
    capture_id: str
    reference_time_ns: int
    frames: tuple[MappedFrame, ...]
    max_skew_ns: int


@dataclass(frozen=True)
class ClockMap:
    camera_id: str
    slope: float
    intercept_ns: float
    max_abs_residual_ns: float
    pulse_count: int

    def map_pts(self, pts_ns: int) -> int:
        return int(round(self.slope * int(pts_ns) + self.intercept_ns))


def fit_camera_clock(pulses: Iterable[OpticalPulse], *, max_residual_ns: int = 5_000_000) -> ClockMap:
    """Fit camera PTS -> shared reference time from decoded LED pulse IDs."""
    items = list(pulses)
    if len(items) < 2:
        raise SyncBridgeError("每台相机至少需要两个不同时间的光学同步脉冲。")
    camera_ids = {p.camera_id for p in items}
    if len(camera_ids) != 1:
        raise SyncBridgeError("一次时钟拟合只能包含一台相机。")
    if any(p.pts_ns < 0 or p.reference_time_ns < 0 or p.pulse_id < 0 for p in items):
        raise SyncBridgeError("同步脉冲时间和编号必须为非负整数。")
    if len({p.pulse_id for p in items}) != len(items):
        raise SyncBridgeError("同一相机的光学 pulse_id 必须唯一。")
    items.sort(key=lambda p: p.pts_ns)
    x = np.asarray([p.pts_ns for p in items], dtype=np.float64)
    y = np.asarray([p.reference_time_ns for p in items], dtype=np.float64)
    if np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0):
        raise SyncBridgeError("同步脉冲必须按时间严格递增。")
    x0, y0 = x[0], y[0]
    slope, relative_intercept = np.polyfit(x - x0, y - y0, 1)
    intercept = y0 + relative_intercept - slope * x0
    residuals = y - (slope * x + intercept)
    maximum = float(np.max(np.abs(residuals)))
    if not np.isfinite(slope) or slope <= 0:
        raise SyncBridgeError("相机时钟映射斜率无效。")
    if maximum > max_residual_ns:
        raise SyncBridgeError(
            f"光学同步时钟拟合残差 {maximum:.0f} ns 超过 {max_residual_ns} ns。"
        )
    return ClockMap(next(iter(camera_ids)), float(slope), float(intercept), maximum, len(items))


def map_video_frames(frames: Iterable[VideoFrame], clock: ClockMap) -> list[MappedFrame]:
    mapped = []
    for frame in frames:
        if frame.camera_id != clock.camera_id:
            raise SyncBridgeError("视频帧 camera_id 与时钟映射不一致。")
        if frame.pts_ns < 0 or not frame.image_path or not frame.mask_path:
            raise SyncBridgeError("视频帧必须有有效 PTS、图像路径和 mask 路径。")
        mapped.append(MappedFrame(
            frame.camera_id, frame.pts_ns, clock.map_pts(frame.pts_ns),
            frame.image_path, frame.mask_path, clock.max_abs_residual_ns,
        ))
    return sorted(mapped, key=lambda item: item.reference_time_ns)


def group_nearest_frames(
    frames_by_camera: dict[str, list[MappedFrame]],
    target_times_ns: Iterable[int],
    *,
    max_skew_ns: int = 5_000_000,
) -> list[SynchronizedGroup]:
    """Select one unique nearest frame per camera for each reference time."""
    if len(frames_by_camera) != 3 or any(not values for values in frames_by_camera.values()):
        raise SyncBridgeError("必须提供三台相机各自非空的视频帧序列。")
    if max_skew_ns < 0:
        raise SyncBridgeError("max_skew_ns 不能为负数。")
    result = []
    used: dict[str, set[int]] = {camera: set() for camera in frames_by_camera}
    for index, target in enumerate(target_times_ns):
        selected = []
        for camera_id, values in sorted(frames_by_camera.items()):
            candidates = [
                (abs(frame.reference_time_ns - int(target)), pos, frame)
                for pos, frame in enumerate(values) if pos not in used[camera_id]
            ]
            if not candidates:
                raise SyncBridgeError(f"{camera_id} 没有剩余视频帧可匹配 capture_{index:06d}。")
            _, pos, frame = min(candidates, key=lambda item: (item[0], item[1]))
            used[camera_id].add(pos)
            selected.append(frame)
        times = [frame.reference_time_ns for frame in selected]
        skew = max(times) - min(times)
        if skew > max_skew_ns:
            raise SyncBridgeError(
                f"capture_{index:06d} 三机位帧时间差 {skew} ns 超过 {max_skew_ns} ns。"
            )
        result.append(SynchronizedGroup(
            f"capture_{index:06d}", int(round(sum(times) / 3)), tuple(selected), skew
        ))
    return result
