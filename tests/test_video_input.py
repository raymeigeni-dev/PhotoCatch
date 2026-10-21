from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.video_input import analyze_video


def _make_test_video(path: Path, *, frame_count: int = 12, moving: bool = True) -> Path:
    width, height = 320, 240
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12.0, (width, height)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG video writer is unavailable in this environment")
    rng = np.random.default_rng(42)
    texture = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    for idx in range(frame_count):
        frame = texture.copy()
        x = 20 + (idx * 9 if moving else 0)
        cv2.rectangle(frame, (x % 250, 50), (min(width - 1, (x % 250) + 50), 110), (0, 0, 255), -1)
        cv2.putText(frame, f"frame {idx}", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    return path


def test_video_analysis_extracts_frames_and_returns_quality_report(tmp_path):
    video = _make_test_video(tmp_path / "sample.avi")
    report = analyze_video(str(video), max_frames=8)

    assert report["success"] is True
    assert report["analysis_only"] is True
    assert report["video"]["frame_count"] >= 8
    assert report["sampling"]["extracted_frames"] >= 2
    assert report["quality"]["sharpness_median"] >= 0
    assert report["previews"]
    assert all(item["image"].startswith("data:image/jpeg;base64,") for item in report["previews"])
    assert isinstance(report["reconstruction_ready"], bool)


def test_video_analysis_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        analyze_video(str(tmp_path / "missing.mp4"))


def test_video_analysis_rejects_non_video_file(tmp_path):
    path = tmp_path / "broken.avi"
    path.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="无法解码"):
        analyze_video(str(path))
