"""Independent-reference metrics and preregistered acceptance gates.

These utilities calculate errors; they do not acquire or certify physical ground truth.
Synthetic inputs are suitable for unit tests only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import numpy as np


class BenchmarkValidationError(ValueError):
    """Invalid benchmark inputs or acceptance protocol."""


@dataclass(frozen=True)
class ErrorSummary:
    count: int
    bias: float
    mae: float
    rmse: float
    p95_absolute: float
    max_absolute: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class GateResult:
    status: str
    sample_count: int
    minimum_samples: int
    violations: dict[str, dict[str, float]]
    missing_metrics: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "sample_count": self.sample_count,
            "minimum_samples": self.minimum_samples,
            "violations": self.violations,
            "missing_metrics": list(self.missing_metrics),
        }


def _finite_vector(values, label: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise BenchmarkValidationError(f"{label} 必须是非空一维数组。")
    if not np.isfinite(array).all():
        raise BenchmarkValidationError(f"{label} 包含 NaN 或无穷值。")
    return array


def summarize_signed_errors(errors) -> ErrorSummary:
    """Summarize signed prediction-minus-reference errors in a single unit."""
    values = _finite_vector(errors, "errors")
    absolute = np.abs(values)
    return ErrorSummary(
        count=int(values.size),
        bias=float(np.mean(values)),
        mae=float(np.mean(absolute)),
        rmse=float(np.sqrt(np.mean(np.square(values)))),
        p95_absolute=float(np.percentile(absolute, 95)),
        max_absolute=float(np.max(absolute)),
    )


def _points(values, label: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3 or array.shape[0] == 0:
        raise BenchmarkValidationError(f"{label} 必须是形状为 (N, 3) 的非空点云。")
    if not np.isfinite(array).all():
        raise BenchmarkValidationError(f"{label} 包含 NaN 或无穷值。")
    return array


def _directed_nearest_distances(source: np.ndarray, target: np.ndarray, chunk_size: int) -> np.ndarray:
    result = np.empty(source.shape[0], dtype=np.float64)
    target_norm = np.einsum("ij,ij->i", target, target)
    for start in range(0, source.shape[0], chunk_size):
        block = source[start:start + chunk_size]
        squared = (
            np.einsum("ij,ij->i", block, block)[:, None]
            + target_norm[None, :]
            - 2.0 * block @ target.T
        )
        np.maximum(squared, 0.0, out=squared)
        result[start:start + len(block)] = np.sqrt(np.min(squared, axis=1))
    return result


def symmetric_surface_distance(reference_xyz, predicted_xyz, *, chunk_size: int = 1024) -> dict:
    """Return symmetric point-cloud nearest-neighbour distances in input units.

    This is a sampled point-to-point surface metric, not an exact mesh
    point-to-triangle distance. Use independently scanned, consistently sampled
    reference and prediction surfaces; record sampling density in the protocol.
    """
    reference = _points(reference_xyz, "reference_xyz")
    predicted = _points(predicted_xyz, "predicted_xyz")
    if isinstance(chunk_size, bool) or int(chunk_size) != chunk_size or chunk_size < 1:
        raise BenchmarkValidationError("chunk_size 必须是正整数。")
    ref_to_pred = _directed_nearest_distances(reference, predicted, int(chunk_size))
    pred_to_ref = _directed_nearest_distances(predicted, reference, int(chunk_size))
    combined = np.concatenate((ref_to_pred, pred_to_ref))
    summary = summarize_signed_errors(combined)
    return {
        "metric": "symmetric_point_to_point_nearest_neighbour",
        "unit": "same_as_input_coordinates",
        "reference_to_prediction": summarize_signed_errors(ref_to_pred).to_dict(),
        "prediction_to_reference": summarize_signed_errors(pred_to_ref).to_dict(),
        "symmetric": summary.to_dict(),
        "note": "Sampled point-to-point distance; not exact point-to-triangle mesh distance.",
    }


def evaluate_preregistered_gate(
    observed: Mapping[str, float] | None,
    thresholds: Mapping[str, float],
    *,
    sample_count: int,
    minimum_samples: int,
) -> GateResult:
    """Evaluate max-error limits frozen before a held-out benchmark run.

    Missing observations/protocol limits or insufficient independent samples
    yield NOT TESTED. Any exceeded mandatory limit yields FAIL.
    """
    if isinstance(sample_count, bool) or int(sample_count) != sample_count or sample_count < 0:
        raise BenchmarkValidationError("sample_count 必须是非负整数。")
    if isinstance(minimum_samples, bool) or int(minimum_samples) != minimum_samples or minimum_samples < 1:
        raise BenchmarkValidationError("minimum_samples 必须是正整数。")
    if not isinstance(thresholds, Mapping) or not thresholds:
        raise BenchmarkValidationError("必须预先登记至少一个数值阈值。")

    normalized_thresholds: dict[str, float] = {}
    for name, limit in thresholds.items():
        value = float(limit)
        if not name or not np.isfinite(value) or value < 0:
            raise BenchmarkValidationError(f"阈值 {name!r} 必须是非负有限数值。")
        normalized_thresholds[str(name)] = value

    if observed is None:
        return GateResult("NOT_TESTED", int(sample_count), int(minimum_samples), {}, tuple(sorted(normalized_thresholds)))

    missing = []
    violations: dict[str, dict[str, float]] = {}
    for name, limit in normalized_thresholds.items():
        if name not in observed:
            missing.append(name)
            continue
        value = float(observed[name])
        if not np.isfinite(value) or value < 0:
            missing.append(name)
            continue
        if value > limit:
            violations[name] = {"observed": value, "maximum_allowed": limit}

    if violations:
        status = "FAIL"
    elif missing or sample_count < minimum_samples:
        status = "NOT_TESTED"
    else:
        status = "PASS"
    return GateResult(
        status,
        int(sample_count),
        int(minimum_samples),
        violations,
        tuple(sorted(missing)),
    )
