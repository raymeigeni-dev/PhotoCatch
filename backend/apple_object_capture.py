"""Safe subprocess adapter for the optional Apple Object Capture CLI."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


class AppleCaptureError(RuntimeError):
    """Raised when the native Object Capture helper is unavailable or fails."""


def resolve_apple_capture_binary() -> Path | None:
    configured = os.environ.get("PHOTOCATCH_APPLE_CAPTURE_BIN")
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path(__file__).resolve().parents[1] / "native" / "apple-object-capture" / ".build" / "release" / "photocatch-apple-capture",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def run_apple_capture(image_dir: str | Path, output_usdz: str | Path, timeout_seconds: int = 7200) -> dict[str, Any]:
    """Run the native CLI, preserve stdout/stderr, and require a non-empty USDZ."""
    images = Path(image_dir).resolve()
    output = Path(output_usdz).resolve()
    if not images.is_dir():
        raise AppleCaptureError("Apple Object Capture input image directory does not exist.")
    if output == images or images in output.parents:
        raise AppleCaptureError("USDZ output must be outside the input image directory.")
    binary = resolve_apple_capture_binary()
    if binary is None:
        raise AppleCaptureError(
            "Apple Object Capture helper is not built. Run: "
            "cd native/apple-object-capture && swift build -c release"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [str(binary), str(images), str(output)],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppleCaptureError(f"Apple Object Capture timed out after {timeout_seconds} seconds.") from exc
    parsed: dict[str, Any] = {}
    for line in reversed((proc.stdout or "").splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict) and ("ok" in value or "error" in value):
                parsed = value
                break
        except json.JSONDecodeError:
            continue
    if proc.returncode != 0 or not parsed.get("ok"):
        detail = parsed.get("error") or (proc.stderr or proc.stdout or "Native reconstruction failed").strip()
        raise AppleCaptureError(str(detail)[:2000])
    if not output.is_file() or output.stat().st_size <= 0:
        raise AppleCaptureError("Native helper reported success but no non-empty USDZ file exists.")
    return {
        "success": True, "engine": "apple-realitykit-object-capture",
        "model_path": str(output), "model_bytes": output.stat().st_size,
        "native_result": parsed, "stdout": (proc.stdout or "")[-12000:],
        "stderr": (proc.stderr or "")[-12000:],
    }
