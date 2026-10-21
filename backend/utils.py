import base64
import binascii

import cv2
import numpy as np


def encode_image(image: np.ndarray, format='jpeg') -> str:
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("image must be a non-empty NumPy array")
    if format not in ("jpeg", "png"):
        raise ValueError("format must be 'jpeg' or 'png'")
    extension = ".jpg" if format == "jpeg" else ".png"
    options = [cv2.IMWRITE_JPEG_QUALITY, 90] if format == "jpeg" else []
    ok, buffer = cv2.imencode(extension, image, options)
    if not ok:
        raise ValueError("image could not be encoded")
    mime = "jpeg" if format == "jpeg" else "png"
    b64_string = base64.b64encode(buffer).decode("utf-8")
    return f"data:image/{mime};base64,{b64_string}"


def decode_image(image_data: str) -> np.ndarray:
    if not isinstance(image_data, str) or not image_data.strip():
        raise ValueError("image data must be a non-empty base64 string")
    payload = image_data.strip()
    if payload.startswith("data:"):
        header, separator, payload = payload.partition(",")
        if not separator or ";base64" not in header:
            raise ValueError("image data URL must use base64 encoding")
    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image data is not valid base64") from exc
    if not image_bytes:
        raise ValueError("image payload is empty")
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError("payload does not contain a decodable image")
    return image


def resize_image(image: np.ndarray, max_width=640, max_height=480) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.ndim < 2 or image.size == 0:
        raise ValueError("image must be a non-empty NumPy array")
    if max_width <= 0 or max_height <= 0:
        raise ValueError("maximum dimensions must be positive")
    h, w = image.shape[:2]
    if w > max_width or h > max_height:
        scale = min(max_width / w, max_height / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        image = cv2.resize(image, (new_w, new_h))
    return image


def normalize_vertices(vertices: list, scale=1.0) -> list:
    vertices = np.asarray(vertices, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or vertices.shape[0] == 0:
        raise ValueError("vertices must be a non-empty list of 3D points")
    if not np.isfinite(vertices).all():
        raise ValueError("vertices must contain only finite numbers")
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be a finite positive number")
    vertices = vertices.copy()
    center = np.mean(vertices, axis=0)
    vertices -= center
    max_dist = np.max(np.linalg.norm(vertices, axis=1))
    if max_dist > 0:
        vertices = vertices / max_dist * scale
    return vertices.tolist()
