import base64

import cv2
import numpy as np
import pytest

from backend.utils import decode_image, encode_image, normalize_vertices, resize_image


def sample_image(width=32, height=24):
    return np.full((height, width, 3), (20, 80, 160), dtype=np.uint8)


def test_encode_decode_round_trip_data_url():
    original = sample_image()
    encoded = encode_image(original)
    decoded = decode_image(encoded)
    assert decoded.shape == original.shape
    assert decoded.dtype == np.uint8
    assert np.mean(np.abs(decoded.astype(float) - original.astype(float))) < 8


@pytest.mark.parametrize("payload", ["", "not-base64", "data:image/png;base64,%%%"])
def test_decode_image_rejects_invalid_payload(payload):
    with pytest.raises((ValueError, TypeError)):
        decode_image(payload)


def test_resize_image_preserves_small_image():
    image = sample_image(20, 10)
    assert resize_image(image, 40, 40).shape == image.shape


def test_resize_image_respects_bounds():
    resized = resize_image(sample_image(640, 480), 160, 120)
    assert resized.shape[1] <= 160
    assert resized.shape[0] <= 120


def test_normalize_vertices_centers_and_scales():
    vertices = normalize_vertices([[0, 0, 0], [2, 0, 0]], scale=1)
    assert np.allclose(np.mean(vertices, axis=0), [0, 0, 0])
    assert np.isclose(max(np.linalg.norm(v) for v in vertices), 1)


def test_normalize_vertices_rejects_empty_input():
    with pytest.raises(ValueError):
        normalize_vertices([])
