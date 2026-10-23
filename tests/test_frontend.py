from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "index.html"


def test_frontend_entrypoint_exists_and_has_chinese_ui():
    assert FRONTEND.is_file(), "README points to a frontend entry point that must exist"
    html = FRONTEND.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert "PhotoCatch" in html
    assert "启动摄像头" in html


def test_frontend_has_camera_detection_and_reconstruction_controls():
    html = FRONTEND.read_text(encoding="utf-8")
    for element_id in (
        "video", "startCamera", "stopCamera", "detect",
        "detections", "reconstruct", "export", "viewer",
    ):
        assert f'id="{element_id}"' in html, f"missing frontend control: {element_id}"


def test_frontend_connects_to_backend_api():
    html = FRONTEND.read_text(encoding="utf-8")
    assert "'/api/health'" in html
    assert "'/api/detect'" in html
    assert "'/api/reconstruct'" in html
    assert "127.0.0.1:5000" in html


def test_frontend_uses_threejs_and_validates_mesh_indices():
    html = FRONTEND.read_text(encoding="utf-8")
    assert "three.module.js" in html
    assert "new THREE.WebGLRenderer" in html
    assert "i<data.vertices.length" in html
    assert "application/json" in html
