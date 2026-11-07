"""Timestamped rotary encoder ingestion and angle interpolation."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class EncoderError(ValueError):
    """Invalid or insufficient rotary encoder evidence."""


@dataclass(frozen=True)
class EncoderSample:
    timestamp_ns: int
    angle_deg: float


class EncoderTrack:
    def __init__(self, samples: list[EncoderSample], *, max_gap_ns: int = 100_000_000):
        if len(samples) < 2:
            raise EncoderError("编码器至少需要两个采样点。")
        if max_gap_ns <= 0:
            raise EncoderError("max_gap_ns 必须为正数。")
        times = np.asarray([s.timestamp_ns for s in samples], dtype=np.int64)
        angles = np.asarray([s.angle_deg for s in samples], dtype=np.float64)
        if np.any(times < 0) or np.any(np.diff(times) <= 0):
            raise EncoderError("编码器时间戳必须非负且严格递增。")
        if not np.isfinite(angles).all():
            raise EncoderError("编码器角度必须是有限数值。")
        unwrapped = np.rad2deg(np.unwrap(np.deg2rad(angles)))
        delta = np.diff(unwrapped)
        if np.any(np.abs(delta) < 1e-9):
            raise EncoderError("编码器存在重复角度采样。")
        signs = np.sign(delta)
        if np.any(signs != signs[0]):
            raise EncoderError("编码器记录到旋转方向反转；请检查摆动、回弹或编码器噪声。")
        if np.any(np.diff(times) > max_gap_ns):
            raise EncoderError("编码器采样间隔过大，不能安全插值。")
        self._times = times
        self._angles = unwrapped
        self.max_gap_ns = int(max_gap_ns)

    @classmethod
    def from_csv(cls, path: str | Path, *, max_gap_ns: int = 100_000_000) -> "EncoderTrack":
        try:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not {"timestamp_ns", "angle_deg"}.issubset(reader.fieldnames or []):
                    raise EncoderError("编码器 CSV 必须包含 timestamp_ns,angle_deg。")
                samples = [
                    EncoderSample(int(row["timestamp_ns"]), float(row["angle_deg"]))
                    for row in reader
                ]
        except (OSError, ValueError) as exc:
            if isinstance(exc, EncoderError):
                raise
            raise EncoderError(f"无法读取编码器 CSV：{exc}") from exc
        return cls(samples, max_gap_ns=max_gap_ns)

    def angle_at(self, timestamp_ns: int) -> float:
        timestamp_ns = int(timestamp_ns)
        if timestamp_ns < self._times[0] or timestamp_ns > self._times[-1]:
            raise EncoderError("目标时间超出编码器记录范围，禁止外推角度。")
        right = int(np.searchsorted(self._times, timestamp_ns, side="left"))
        if right < len(self._times) and self._times[right] == timestamp_ns:
            return float(self._angles[right] % 360.0)
        left = right - 1
        gap = int(self._times[right] - self._times[left])
        if gap > self.max_gap_ns:
            raise EncoderError("目标时间跨越编码器数据缺口，禁止插值。")
        fraction = (timestamp_ns - int(self._times[left])) / gap
        return float((self._angles[left] + fraction * (self._angles[right] - self._angles[left])) % 360.0)
