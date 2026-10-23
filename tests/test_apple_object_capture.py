from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import apple_object_capture as apple


def test_missing_input_directory_is_rejected(tmp_path):
    with pytest.raises(apple.AppleCaptureError, match="does not exist"):
        apple.run_apple_capture(tmp_path / "missing", tmp_path / "out.usdz")


def test_output_inside_input_directory_is_rejected(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    monkeypatch.setattr(apple, "resolve_apple_capture_binary", lambda: Path("/unused"))
    with pytest.raises(apple.AppleCaptureError, match="outside"):
        apple.run_apple_capture(images, images / "model.usdz")


def test_missing_native_binary_has_build_instructions(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    monkeypatch.setattr(apple, "resolve_apple_capture_binary", lambda: None)
    with pytest.raises(apple.AppleCaptureError, match="swift build -c release"):
        apple.run_apple_capture(images, tmp_path / "model.usdz")


def test_success_requires_nonempty_usdz(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    binary = tmp_path / "capture"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setattr(apple, "resolve_apple_capture_binary", lambda: binary)
    with pytest.raises(apple.AppleCaptureError, match="no non-empty USDZ"):
        apple.run_apple_capture(images, tmp_path / "model.usdz")
