import logging
import os

import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

from backend.detector import ObjectDetector
from backend.reconstructor import Reconstructor3D
from backend.utils import encode_image, decode_image

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
CORS(app)

detector = ObjectDetector()
reconstructor = Reconstructor3D()


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running'})


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
            'success': True,
            'image': encoded_img,
            'detections': detections,
            'count': len(detections)
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
    image_data = data.get('image')
    bbox = data.get('bbox')
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
            'success': True,
            'model': model_data,
            'vertices': model_data['vertices'],
            'faces': model_data['faces'],
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
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Request body must be a JSON object'}), 400
        return jsonify({'success': True, 'message': 'Settings accepted (not persisted)'})
    return jsonify({
        'detection_threshold': 0.5,
        'mesh_quality': 'high',
        'ar_mode': 'webgl',
        'max_objects': 10
    })


if __name__ == '__main__':
    print("\\nPhotoCatch AR server: http://127.0.0.1:5000")
    app.run(debug=False, host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "5000")), threaded=True)
