import base64

import cv2
import numpy as np
import pytest

from backend.server import app


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def image_data_url():
    image = np.zeros((24, 32, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return "data:image/png;base64," + base64.b64encode(buffer).decode("ascii")


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


@pytest.mark.parametrize("body", [None, [], "text"])
def test_detect_rejects_non_object_json(client, body):
    response = client.post("/api/detect", json=body)
    assert response.status_code == 400


def test_detect_rejects_invalid_image(client):
    response = client.post("/api/detect", json={"image": "%%%not-an-image%%%"})
    assert response.status_code == 400
    assert "error" in response.get_json()


@pytest.mark.parametrize("bbox", [[1, 2, 3], [1, 2, -1, 4], [-1, 0, 3, 4], ["1", 2, 3, 4]])
def test_reconstruct_rejects_invalid_bbox(client, bbox):
    response = client.post("/api/reconstruct", json={"image": image_data_url(), "bbox": bbox})
    assert response.status_code == 400


def test_reconstruct_rejects_bbox_outside_image(client):
    response = client.post("/api/reconstruct", json={
        "image": image_data_url(), "bbox": [0, 0, 999, 999]
    })
    assert response.status_code == 400


def test_settings_does_not_claim_to_persist(client):
    response = client.post("/api/settings", json={"mesh_quality": "low"})
    assert response.status_code == 200
    assert "not persisted" in response.get_json()["message"]
