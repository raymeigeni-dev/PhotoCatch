import logging
import os
import tempfile
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    from backend.detector import ObjectDetector
    from backend.reconstructor import Reconstructor3D
    from backend.utils import encode_image, decode_image
    from backend.video_input import analyze_video
except ModuleNotFoundError:
    # Also support the documented "python backend/server.py" launch command.
    from detector import ObjectDetector
    from reconstructor import Reconstructor3D
    from utils import encode_image, decode_image
    from video_input import analyze_video

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024
CORS(app)

detector = ObjectDetector()
reconstructor = Reconstructor3D()


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running'})


@app.route('/api/video/analyze', methods=['POST'])
def analyze_uploaded_video():
    """Extract representative video frames and assess capture suitability.
    This endpoint is input analysis only; it does not claim to reconstruct 3D.
    """
    upload = request.files.get('video')
    if upload is None or not upload.filename:
        return jsonify({'error': '请先选择一个视频文件'}), 400
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}:
        return jsonify({'error': '不支持该视频扩展名。请使用 MP4、MOV、M4V、AVI、MKV 或 WebM'}), 400
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix='photocatch-video-', suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            upload.save(tmp)
        report = analyze_video(tmp_path)
        return jsonify(report)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 422
    except Exception:
        logger.exception("Video input analysis failed")
        return jsonify({'error': '视频分析失败；请检查文件是否完整且可解码'}), 500
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("Could not remove temporary upload %s", tmp_path)


@app.route('/api/detect', methods=['POST'])
def detect():
    data = _json_object()
    if data is None:
        return jsonify({'error': 'Request body must be a JSON object'}), 400
    image_data = data.get('image')
    if not isinstance(image_data, str) or not image_data.strip():
        return jsonify({'error': 'A base64 image is required'}), 400
    try:
        img_array = decode_image(image_data)
        detections = detector.detect(img_array)
        annotated_img = detector.draw_detections(img_array.copy(), detections)
        encoded_img = encode_image(annotated_img)
        return jsonify({
            'success': True, 'image': encoded_img,
            'detections': detections, 'count': len(detections)
        })
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        logger.exception("Detection request failed")
        return jsonify({'error': 'Image detection failed'}), 500


@app.route('/api/reconstruct', methods=['POST'])
def reconstruct():
    data = _json_object()
    if data is None:
        return jsonify({'error': 'Request body must be a JSON object'}), 400
    image_data, bbox = data.get('image'), data.get('bbox')
    if not isinstance(image_data, str) or not image_data.strip():
        return jsonify({'error': 'A base64 image is required'}), 400
    if (not isinstance(bbox, list) or len(bbox) != 4
            or any(isinstance(v, bool) or not isinstance(v, int) for v in bbox)):
        return jsonify({'error': 'bbox must be [x, y, width, height] integers'}), 400
    x, y, width, height = bbox
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return jsonify({'error': 'bbox coordinates must be non-negative and dimensions positive'}), 400
    try:
        img_array = decode_image(image_data)
        image_height, image_width = img_array.shape[:2]
        if x >= image_width or y >= image_height or x + width > image_width or y + height > image_height:
            return jsonify({'error': 'bbox must lie entirely within the image'}), 400
        roi = img_array[y:y + height, x:x + width]
        if roi.size == 0:
            return jsonify({'error': 'bbox selects an empty image region'}), 400
        model_data = reconstructor.reconstruct(roi)
        return jsonify({
            'success': True, 'model': model_data,
            'vertices': model_data['vertices'], 'faces': model_data['faces'],
            'colors': model_data['colors']
        })
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        logger.exception("Reconstruction request failed")
        return jsonify({'error': '3D reconstruction failed'}), 500


@app.route('/api/models', methods=['GET'])
def list_models():
    return jsonify({'models': [
        {'id': 1, 'name': 'General Object Detection', 'type': 'detection'},
        {'id': 2, 'name': '3D Mesh Reconstruction', 'type': 'reconstruction'}
    ]})


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        if _json_object() is None:
            return jsonify({'error': 'Request body must be a JSON object'}), 400
        return jsonify({'success': True, 'message': 'Settings accepted (not persisted)'})
    return jsonify({
        'detection_threshold': 0.5, 'mesh_quality': 'high',
        'ar_mode': 'webgl', 'max_objects': 10
    })


if __name__ == '__main__':
    print("\nPhotoCatch AR server: http://127.0.0.1:5000")
    app.run(debug=False, host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "5000")), threaded=True)
