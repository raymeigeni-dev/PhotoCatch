import numpy as np
import pytest

from backend.rotational_capture.benchmark import (
    BenchmarkValidationError,
    evaluate_preregistered_gate,
    summarize_signed_errors,
    symmetric_surface_distance,
)


def test_signed_error_summary_reports_bias_mae_rmse_and_percentiles():
    result = summarize_signed_errors([-2.0, 0.0, 2.0, 4.0])
    assert result.count == 4
    assert result.bias == pytest.approx(1.0)
    assert result.mae == pytest.approx(2.0)
    assert result.rmse == pytest.approx(np.sqrt(6.0))
    assert result.p95_absolute == pytest.approx(3.7)
    assert result.max_absolute == pytest.approx(4.0)


def test_surface_distance_is_zero_for_identical_point_sets():
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    result = symmetric_surface_distance(points, points.copy(), chunk_size=2)
    assert result["symmetric"]["mae"] == pytest.approx(0.0)
    assert result["symmetric"]["max_absolute"] == pytest.approx(0.0)


def test_surface_distance_is_symmetric_and_reports_both_directions():
    reference = np.array([[0, 0, 0], [2, 0, 0]], dtype=float)
    predicted = np.array([[1, 0, 0]], dtype=float)
    result = symmetric_surface_distance(reference, predicted)
    assert result["reference_to_prediction"]["mae"] == pytest.approx(1.0)
    assert result["prediction_to_reference"]["mae"] == pytest.approx(1.0)
    assert result["symmetric"]["mae"] == pytest.approx(1.0)


def test_gate_fails_when_any_preregistered_limit_is_exceeded():
    result = evaluate_preregistered_gate(
        {"dimension_p95_mm": 3.2, "surface_mae_mm": 0.8},
        {"dimension_p95_mm": 3.0, "surface_mae_mm": 1.0},
        sample_count=30,
        minimum_samples=30,
    )
    assert result.status == "FAIL"
    assert result.violations["dimension_p95_mm"]["observed"] == pytest.approx(3.2)


def test_gate_is_not_tested_when_reference_metric_or_samples_are_missing():
    result = evaluate_preregistered_gate(
        {"dimension_p95_mm": 1.0},
        {"dimension_p95_mm": 2.0, "surface_mae_mm": 1.0},
        sample_count=4,
        minimum_samples=5,
    )
    assert result.status == "NOT_TESTED"
    assert result.missing_metrics == ("surface_mae_mm",)


def test_gate_passes_only_when_every_metric_and_sample_requirement_passes():
    result = evaluate_preregistered_gate(
        {"dimension_p95_mm": 1.0, "surface_mae_mm": 0.5},
        {"dimension_p95_mm": 2.0, "surface_mae_mm": 1.0},
        sample_count=30,
        minimum_samples=30,
    )
    assert result.status == "PASS"


@pytest.mark.parametrize("bad", [[], [[0, 0]], [[0, 0, float("nan")]]])
def test_surface_distance_rejects_invalid_point_clouds(bad):
    with pytest.raises(BenchmarkValidationError):
        symmetric_surface_distance(bad, [[0, 0, 0]])


def test_gate_rejects_empty_or_invalid_threshold_protocol():
    with pytest.raises(BenchmarkValidationError):
        evaluate_preregistered_gate({}, {}, sample_count=10, minimum_samples=1)
    with pytest.raises(BenchmarkValidationError):
        evaluate_preregistered_gate({}, {"metric": -1}, sample_count=10, minimum_samples=1)
