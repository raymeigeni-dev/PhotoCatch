from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
import numpy as np
import base64
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from detector import ObjectDetector
from reconstructor import Reconstructor3D
from utils import encode_image, decode_image

app = Flask(__name__)
CORS(app)

detector = ObjectDetector()
reconstructor = Reconstructor3D()

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running'})

@app.route('/api/detect', methods=['POST'])
def detect():
    try:
        data = request.json
        image_data = data.get('image')
        
        if not image_data:
            return jsonify({'error': 'No image provided'}), 400
        
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
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reconstruct', methods=['POST'])
def reconstruct():
    try:
        data = request.json
        image_data = data.get('image')
        bbox = data.get('bbox')
        
        if not image_data or not bbox:
            return jsonify({'error': 'Missing image or bbox'}), 400
        
        img_array = decode_image(image_data)
        x, y, w, h = bbox
        roi = img_array[y:y+h, x:x+w]
        model_data = reconstructor.reconstruct(roi)
        
        return jsonify({
            'success': True,
            'model': model_data,
            'vertices': model_data['vertices'],
            'faces': model_data['faces'],
            'colors': model_data['colors']
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models', methods=['GET'])
def list_models():
    models = [
        {'id': 1, 'name': 'General Object Detection', 'type': 'detection'},
        {'id': 2, 'name': '3D Mesh Reconstruction', 'type': 'reconstruction'}
    ]
    return jsonify({'models': models})

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        data = request.json
        return jsonify({'success': True, 'message': 'Settings saved'})
    else:
        return jsonify({
            'detection_threshold': 0.5,
            'mesh_quality': 'high',
            'ar_mode': 'webgl',
            'max_objects': 10
        })

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎬 PhotoCatch AR Server Starting...")
    print("="*60)
    print("📡 Server running at: http://localhost:5000")
    print("🌐 Open frontend/index.html in your browser")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
