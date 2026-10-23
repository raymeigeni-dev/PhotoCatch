from backend.cloud_reconstruction import cloud_provider_status, get_job, get_result, CloudReconstructionError


def test_cloud_adapter_reports_unconfigured_without_credentials(monkeypatch):
    monkeypatch.delenv("PHOTOCATCH_CLOUD_API_BASE_URL", raising=False)
    monkeypatch.delenv("PHOTOCATCH_CLOUD_API_TOKEN", raising=False)
    status = cloud_provider_status()
    assert status["configured"] is False
    assert status["requires_credentials"] is True


def test_cloud_job_id_rejects_path_traversal_before_network(monkeypatch):
    monkeypatch.setenv("PHOTOCATCH_CLOUD_API_BASE_URL", "https://example.invalid/api/")
    monkeypatch.setenv("PHOTOCATCH_CLOUD_API_TOKEN", "test-token")
    try:
        get_job("../secrets")
    except CloudReconstructionError as exc:
        assert "job_id" in str(exc)
    else:
        raise AssertionError("invalid job ID should be rejected")


def test_cloud_result_rejects_path_traversal_before_network(monkeypatch):
    monkeypatch.setenv("PHOTOCATCH_CLOUD_API_BASE_URL", "https://example.invalid/api/")
    monkeypatch.setenv("PHOTOCATCH_CLOUD_API_TOKEN", "test-token")
    try:
        get_result("../secrets")
    except CloudReconstructionError as exc:
        assert "job_id" in str(exc)
    else:
        raise AssertionError("invalid job ID should be rejected")
