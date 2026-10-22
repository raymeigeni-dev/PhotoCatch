from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.video_input import analyze_video, _pair_geometry


def _make_test_video(path: Path, *, frame_count: int = 12, moving: bool = True, changing_text: bool = True) -> Path:
    width, height = 320, 240
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12.0, (width, height))
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG video writer is unavailable in this environment")
    rng = np.random.default_rng(42)
    texture = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    for idx in range(frame_count):
        frame = texture.copy()
        x = 20 + (idx * 9 if moving else 0)
        cv2.rectangle(frame, (x % 250, 50), (min(width - 1, (x % 250) + 50), 110), (0, 0, 255), -1)
        if changing_text:
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
    assert "parallax_pairs" in report["quality"]


def test_static_camera_scene_is_not_claimed_as_viewpoint_change(tmp_path):
    video = _make_test_video(tmp_path / "static.avi", moving=False, changing_text=False)
    report = analyze_video(str(video), max_frames=8)
    assert report["reconstruction_ready"] is False
    assert report["quality"]["parallax_pairs"] == 0
    assert any("不能证明有效相机运动" in warning for warning in report["warnings"])


def test_pair_geometry_rejects_identical_frames():
    rng = np.random.default_rng(7)
    frame = rng.integers(0, 255, (240, 320, 3), dtype=np.uint8)
    result = _pair_geometry(frame, frame.copy())
    assert result["median_flow_px"] < 0.1
    assert result["inliers"] >= 0


def test_video_analysis_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        analyze_video(str(tmp_path / "missing.mp4"))


def test_video_analysis_rejects_non_video_file(tmp_path):
    path = tmp_path / "broken.avi"
    path.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="无法解码"):
        analyze_video(str(path))
