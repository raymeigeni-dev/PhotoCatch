from __future__ import annotations

import json

import pytest

from backend.rotational_capture.encoder import EncoderError, EncoderSample, EncoderTrack
from backend.rotational_capture.hanging import HangingCaptureConfig, HangingCaptureError, write_capture_manifest
from backend.rotational_capture.sync_bridge import (
    OpticalPulse, SyncBridgeError, VideoFrame, fit_camera_clock,
    group_nearest_frames, map_video_frames,
)


def test_optical_pulse_clock_mapping_handles_independent_camera_clock():
    pulses = [
        OpticalPulse("phone_a", 1_000_000_000, 1, 5_000_000_000),
        OpticalPulse("phone_a", 2_000_000_000, 2, 6_000_000_100),
        OpticalPulse("phone_a", 3_000_000_000, 3, 7_000_000_200),
    ]
    clock = fit_camera_clock(pulses, max_residual_ns=1_000)
    assert clock.map_pts(2_000_000_000) == 6_000_000_100


def test_clock_mapping_rejects_bad_led_fit():
    pulses = [
        OpticalPulse("cam", 0, 1, 0),
        OpticalPulse("cam", 1_000_000_000, 2, 1_000_000_000),
        OpticalPulse("cam", 2_000_000_000, 3, 3_000_000_000),
    ]
    with pytest.raises(SyncBridgeError, match="残差"):
        fit_camera_clock(pulses, max_residual_ns=10)


def test_video_frame_mapping_rejects_wrong_camera():
    clock = fit_camera_clock([
        OpticalPulse("a", 0, 1, 100),
        OpticalPulse("a", 100, 2, 200),
    ])
    with pytest.raises(SyncBridgeError, match="不一致"):
        map_video_frames([VideoFrame("b", 10, "i.png", "m.png")], clock)


def test_three_camera_grouping_enforces_sync_tolerance():
    mapped = {}
    for camera, offset in (("a", 0), ("b", 100), ("c", 200)):
        clock = fit_camera_clock([
            OpticalPulse(camera, 0, 1, offset),
            OpticalPulse(camera, 1_000, 2, 1_000 + offset),
        ])
        mapped[camera] = map_video_frames(
            [VideoFrame(camera, 500, f"{camera}.png", f"{camera}_mask.png")], clock
        )
    groups = group_nearest_frames(mapped, [600], max_skew_ns=500)
    assert len(groups) == 1
    assert groups[0].max_skew_ns == 200
    with pytest.raises(SyncBridgeError, match="超过"):
        group_nearest_frames(mapped, [600], max_skew_ns=100)


def test_encoder_interpolates_across_zero_degrees():
    track = EncoderTrack([
        EncoderSample(0, 359.0),
        EncoderSample(10_000_000, 1.0),
        EncoderSample(20_000_000, 3.0),
    ])
    assert track.angle_at(5_000_000) == pytest.approx(0.0)
    assert track.angle_at(15_000_000) == pytest.approx(2.0)


def test_encoder_refuses_extrapolation_and_reversal():
    track = EncoderTrack([EncoderSample(0, 0), EncoderSample(10, 10)])
    with pytest.raises(EncoderError, match="超出"):
        track.angle_at(11)
    with pytest.raises(EncoderError, match="反转"):
        EncoderTrack([EncoderSample(0, 0), EncoderSample(10, 10), EncoderSample(20, 5)])


def test_hanging_capture_configuration_and_2_degree_sampling():
    config = HangingCaptureConfig(("a", "b", "c"), (0, 120, 240), sample_step_deg=2)
    assert len(config.target_angles()) == 180
    with pytest.raises(HangingCaptureError, match="120"):
        HangingCaptureConfig(("a", "b", "c"), (0, 90, 180)).validate()


def test_manifest_uses_encoder_angle_and_records_limitations(tmp_path):
    config = HangingCaptureConfig(("a", "b", "c"), (0, 120, 240))
    config.validate()
    frames = []
    from backend.rotational_capture.sync_bridge import MappedFrame, SynchronizedGroup
    for camera in ("a", "b", "c"):
        frames.append(MappedFrame(camera, 5_000_000, 5_000_000, f"{camera}.png", f"{camera}_mask.png", 0))
    group = SynchronizedGroup("capture_000001", 5_000_000, tuple(frames), 0)
    encoder = EncoderTrack([EncoderSample(0, 359), EncoderSample(10_000_000, 1)])
    output = tmp_path / "capture.json"
    payload = write_capture_manifest([group], encoder, output)
    saved = json.loads(output.read_text())
    assert saved["capture_groups"][0]["angle_deg"] == pytest.approx(0)
    assert saved["angle_source"] == "timestamped_rotary_encoder_interpolation"
    assert any("Rolling-shutter" in item for item in payload["limitations"])
