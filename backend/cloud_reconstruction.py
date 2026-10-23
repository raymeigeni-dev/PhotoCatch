"""Provider-neutral cloud reconstruction adapter.

This is an integration contract, not a claim that RealityCapture is already connected.
A deployment must expose the documented HTTP job API and configure its URL/token.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import requests


class CloudReconstructionError(RuntimeError):
    pass


def cloud_provider_status() -> dict[str, Any]:
    base = os.getenv("PHOTOCATCH_CLOUD_API_BASE_URL", "").strip().rstrip("/") + "/"
    token = os.getenv("PHOTOCATCH_CLOUD_API_TOKEN", "").strip()
    return {
        "engine": "cloud-http-adapter",
        "configured": bool(base.strip("/") and token),
        "provider": os.getenv("PHOTOCATCH_CLOUD_PROVIDER", "custom"),
        "requires_credentials": True,
        "contract": {
            "submit": "POST /jobs multipart field 'video' -> JSON {job_id}",
            "status": "GET /jobs/{job_id} -> JSON {status: queued|running|succeeded|failed, ...}",
            "result": "GET /jobs/{job_id}/result -> provider-defined JSON with downloadable asset URLs",
        },
        "note": "RealityCapture is not connected unless a compatible gateway is configured; this adapter does not invent provider endpoints.",
    }


def _config() -> tuple[str, dict[str, str]]:
    base = os.getenv("PHOTOCATCH_CLOUD_API_BASE_URL", "").strip().rstrip("/") + "/"
    token = os.getenv("PHOTOCATCH_CLOUD_API_TOKEN", "").strip()
    if not base.strip("/") or not token:
        raise CloudReconstructionError(
            "云端重建未配置：需要 PHOTOCATCH_CLOUD_API_BASE_URL 和 PHOTOCATCH_CLOUD_API_TOKEN。"
            "这不是 RealityCapture 的即插即用官方连接；请先配置符合 docs/CLOUD_RECONSTRUCTION_ADAPTER.md 的服务端网关。"
        )
    return base, {"Authorization": f"Bearer {token}"}


def submit_video(path: str, filename: str, timeout_seconds: int = 120) -> dict[str, Any]:
    base, headers = _config()
    try:
        with open(path, "rb") as video:
            response = requests.post(
                urljoin(base, "jobs"),
                headers=headers,
                files={"video": (filename, video, "application/octet-stream")},
                timeout=timeout_seconds,
            )
        response.raise_for_status()
        data = response.json()
    except (OSError, requests.RequestException, ValueError) as exc:
        raise CloudReconstructionError(f"云端任务提交失败：{exc}") from exc
    if not isinstance(data, dict) or not data.get("job_id"):
        raise CloudReconstructionError("云端网关响应缺少 job_id，拒绝把任务标记为已提交。")
    return {"success": True, "engine": "cloud-http-adapter", "cloud_job_id": str(data["job_id"]), "provider_response": data}


def get_job(job_id: str) -> dict[str, Any]:
    if not job_id or len(job_id) > 200 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in job_id):
        raise CloudReconstructionError("云端 job_id 格式无效。")
    base, headers = _config()
    try:
        response = requests.get(urljoin(base, f"jobs/{job_id}"), headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CloudReconstructionError(f"读取云端任务状态失败：{exc}") from exc
    if not isinstance(data, dict) or data.get("status") not in {"queued", "running", "succeeded", "failed"}:
        raise CloudReconstructionError("云端网关返回了无效任务状态。")
    return {"success": True, "engine": "cloud-http-adapter", "cloud_job_id": job_id, **data}


def get_result(job_id: str) -> dict[str, Any]:
    """Fetch the provider's result manifest; actual asset URLs remain provider-owned."""
    if not job_id or len(job_id) > 200 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in job_id):
        raise CloudReconstructionError("云端 job_id 格式无效。")
    base, headers = _config()
    try:
        response = requests.get(urljoin(base, f"jobs/{job_id}/result"), headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CloudReconstructionError(f"读取云端结果清单失败：{exc}") from exc
    if not isinstance(data, dict):
        raise CloudReconstructionError("云端结果清单必须是 JSON 对象。")
    urls = data.get("assets")
    if not isinstance(urls, (list, dict)):
        raise CloudReconstructionError("云端结果清单缺少 assets；不能声称已取得模型文件。")
    return {"success": True, "engine": "cloud-http-adapter", "cloud_job_id": job_id,
            "result_manifest": data, "assets_downloaded_locally": False,
            "note": "已读取云端结果清单；资产 URL 仍由服务商提供，尚未下载到本机。"}
