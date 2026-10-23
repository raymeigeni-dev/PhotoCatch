import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
import cv2
import numpy as np
from flask_cors import CORS

try:
    from backend.detector import ObjectDetector
    from backend.reconstructor import Reconstructor3D
    from backend.utils import encode_image, decode_image
    from backend.video_input import analyze_video
    from backend.colmap_pipeline import run_colmap_mvs, ReconstructionError
    from backend.panorama import equirectangular_to_perspective_views, is_equirectangular
    from backend.apple_object_capture import run_apple_capture, AppleCaptureError
    from backend.cloud_reconstruction import cloud_provider_status, submit_video, get_job, CloudReconstructionError
except ModuleNotFoundError:
    # Also support the documented "python backend/server.py" launch command.
    from detector import ObjectDetector
    from reconstructor import Reconstructor3D
    from utils import encode_image, decode_image
    from video_input import analyze_video
    from colmap_pipeline import run_colmap_mvs, ReconstructionError
    from panorama import equirectangular_to_perspective_views, is_equirectangular
    from apple_object_capture import run_apple_capture, AppleCaptureError
    from cloud_reconstruction import cloud_provider_status, submit_video, get_job, CloudReconstructionError

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


@app.route('/api/reconstruction/engines', methods=['GET'])
def reconstruction_engines():
    """Report available engines/tools without implying that unavailable ones work."""
    def available(name):
        return shutil.which(name) is not None
    apple_binary = os.getenv("PHOTOCATCH_APPLE_CAPTURE_BIN")
    apple_candidates = [
        Path(apple_binary).expanduser() if apple_binary else None,
        Path(__file__).resolve().parents[1] / "native" / "apple-object-capture" / ".build" / "release" / "photocatch-apple-capture",
    ]
    apple_ready = any(p and p.is_file() and os.access(p, os.X_OK) for p in apple_candidates)
    return jsonify({
        "engines": [
            {"id": "openmvs", "type": "local", "ready": all(available(x) for x in ("InterfaceCOLMAP", "DensifyPointCloud", "ReconstructMesh")),
             "texture_ready": available("TextureMesh"), "refinement_ready": available("RefineMesh"),
             "note": "本地 CPU 稠密重建；真实纹理贴图需要 TextureMesh。"},
            {"id": "apple-object-capture", "type": "local", "ready": apple_ready,
             "platform_supported": __import__("platform").system() == "Darwin",
             "note": "需要 macOS、已编译原生 helper，并用真实素材验证。"},
            {"id": "realitycapture-cloud", "type": "cloud-adapter", **cloud_provider_status()},
        ],
        "cuda_available": available("nvidia-smi"),
        "warning": "工具存在性不是重建质量证明；每次任务仍需检查输出资产和视觉质量。",
    })


@app.route('/api/video/reconstruct/cloud', methods=['POST'])
def reconstruct_uploaded_video_cloud():
    """Submit a video to a configured provider gateway; submission is not completion."""
    upload = request.files.get('video')
    if upload is None or not upload.filename:
        return jsonify({"success": False, "error": "请先选择一个视频文件"}), 400
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}:
        return jsonify({"success": False, "error": "不支持该视频格式"}), 400
    job_id = uuid.uuid4().hex
    root = Path(app.instance_path) / "reconstructions" / job_id
    root.mkdir(parents=True, exist_ok=False)
    upload_path = root / ("upload" + suffix)
    try:
        upload.save(upload_path)
        result = submit_video(str(upload_path), upload.filename)
        result.update({
            "job_id": job_id,
            "status_url": f"/api/video/reconstruct/cloud/{result['cloud_job_id']}",
            "message": "视频已提交到已配置的云端网关；请轮询状态，不能将提交成功视为模型已生成。",
        })
        return jsonify(result), 202
    except CloudReconstructionError as exc:
        logger.warning("Cloud reconstruction not submitted: %s", exc)
        return jsonify({"success": False, "error": str(exc), "job_id": job_id}), 503
    finally:
        upload_path.unlink(missing_ok=True)


@app.route('/api/video/reconstruct/cloud/<cloud_job_id>', methods=['GET'])
def poll_cloud_reconstruction(cloud_job_id):
    try:
        result = get_job(cloud_job_id)
        if result.get("status") == "succeeded":
            result["quality_verified"] = False
            result["note"] = "云端任务成功状态尚未验证下载文件、纹理、几何和视觉质量。"
        return jsonify(result)
    except CloudReconstructionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502


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
        mode = request.form.get('mode', 'ordinary')
        if mode == 'panorama360':
            width, height = report['video']['width'], report['video']['height']
            report['capture_mode'] = 'panorama360'
            report['panorama_dimensions_detected'] = is_equirectangular(width, height)
            report['reconstruction_ready'] = bool(report['panorama_dimensions_detected'])
            report['message'] = ('检测到接近 2:1 的全景画幅；将投影为重叠透视视图后尝试 SfM。' if report['panorama_dimensions_detected']
                                 else '所选 360°模式下，视频尺寸不像 2:1 等距柱状投影。请先在 Insta360/GoPro 软件中导出标准 360°全景视频。')
            report['warnings'] = list(report.get('warnings', [])) + [
                '全景透视投影只增加视野覆盖，不会产生新的相机基线；若设备仅原地旋转，真实深度重建仍可能失败。',
                '360°视频应优先使用设备官方软件导出的完整等距柱状投影文件；已拼接、裁切或防抖重构的文件可能不适合。'
            ]
            report['next_step'] = '全景帧透视投影 + COLMAP 稀疏重建；仍须验证真实相机平移视差'
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


@app.route('/api/video/reconstruct', methods=['POST'])
def reconstruct_uploaded_video():
    """Run actual COLMAP SfM/MVS on a video after conservative input preflight."""
    upload = request.files.get('video')
    if upload is None or not upload.filename:
        return jsonify({'error': '请先选择一个视频文件'}), 400
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}:
        return jsonify({'error': '不支持该视频格式'}), 400
    job_id = uuid.uuid4().hex
    root = Path(app.instance_path) / 'reconstructions' / job_id
    images_dir = root / 'images'
    upload_path = root / ('upload' + suffix)
    try:
        images_dir.mkdir(parents=True, exist_ok=False)
        upload.save(upload_path)
        mode = request.form.get('mode', 'ordinary')
        if mode not in {'ordinary', 'panorama360'}:
            return jsonify({'error': 'mode 仅支持 ordinary 或 panorama360'}), 400
        report = analyze_video(str(upload_path), max_frames=36, max_dimension=1200)
        if mode == 'ordinary' and not report.get('reconstruction_ready'):
            return jsonify({'error': '视频未通过保守的输入质量门槛，未启动重建。', 'analysis': report}), 422
        if mode == 'panorama360':
            if not is_equirectangular(report['video']['width'], report['video']['height']):
                return jsonify({'error': '全景模式需要接近 2:1 的标准等距柱状投影视频；请先从 Insta360/GoPro 官方软件导出 360°全景视频。', 'analysis': report}), 422

        cap = cv2.VideoCapture(str(upload_path))
        if not cap.isOpened():
            return jsonify({'error': '无法重新打开视频进行抽帧'}), 422
        try:
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            positions = np.unique(np.linspace(0, max(0, count - 1), num=min(36, count), dtype=int))
            saved = 0
            for source_frame_index, pos in enumerate(positions):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                h, w = frame.shape[:2]
                scale = min(1.0, 1200 / max(h, w))
                if scale < 1:
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                if mode == 'panorama360':
                    views = equirectangular_to_perspective_views(frame, output_size=640, horizontal_fov_degrees=100)
                    for direction, view in views:
                        view_dir = images_dir / direction
                        view_dir.mkdir(parents=True, exist_ok=True)
                        target = view_dir / f'frame_{source_frame_index:04d}.jpg'
                        if cv2.imwrite(str(target), view, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                            saved += 1
                elif cv2.imwrite(str(images_dir / f'frame_{saved:04d}.jpg'), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                    saved += 1
        finally:
            cap.release()
        if saved < 8:
            return jsonify({'error': f'有效重建图像仅 {saved} 张，至少需要 8 张；未启动重建。', 'analysis': report}), 422
        result = run_colmap_mvs(images_dir, root / 'colmap')
        result.update({
            'job_id': job_id,
            'mesh_url': f'/api/video/models/{job_id}/mesh.ply',
            'point_cloud_url': f'/api/video/models/{job_id}/pointcloud.ply',
            'input_images': saved,
            'capture_mode': mode,
            'input_analysis': report,
            'success': True,
        })
        return jsonify(result)
    except ReconstructionError as exc:
        logger.warning("COLMAP reconstruction rejected/failed: %s", exc)
        return jsonify({'error': str(exc), 'success': False, 'job_id': job_id}), 422
    except Exception:
        logger.exception("Video reconstruction failed")
        return jsonify({'error': '多视角重建失败；请检查后端日志和素材'}), 500
    finally:
        # Do not retain the uploaded original or raw sampled frames after the job.
        try:
            upload_path.unlink(missing_ok=True)
            shutil.rmtree(images_dir, ignore_errors=True)
        except OSError:
            logger.warning("Could not remove temporary video inputs for job %s", job_id)


@app.route('/api/video/reconstruct/apple', methods=['POST'])
def reconstruct_uploaded_video_apple():
    """Run Apple's native Object Capture on sampled overlapping video frames.
    This is an opt-in endpoint; the existing COLMAP route remains unchanged.
    """
    upload = request.files.get('video')
    if upload is None or not upload.filename:
        return jsonify({'error': '请先选择一个视频文件'}), 400
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}:
        return jsonify({'error': '不支持该视频格式'}), 400
    job_id = uuid.uuid4().hex
    root = Path(app.instance_path) / 'reconstructions' / job_id
    images_dir = root / 'apple-images'
    upload_path = root / ('upload' + suffix)
    output_path = root / 'apple-object-capture.usdz'
    try:
        root.mkdir(parents=True, exist_ok=False)
        images_dir.mkdir(parents=True, exist_ok=False)
        upload.save(upload_path)
        report = analyze_video(str(upload_path), max_frames=48, max_dimension=1600)
        if not report.get('reconstruction_ready'):
            return jsonify({
                'success': False, 'error': '视频未通过输入质量门槛，未启动苹果原生重建。',
                'analysis': report, 'job_id': job_id,
            }), 422
        cap = cv2.VideoCapture(str(upload_path))
        if not cap.isOpened():
            return jsonify({'success': False, 'error': '无法解码上传视频'}), 422
        saved = 0
        try:
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            positions = np.unique(np.linspace(0, max(0, count - 1), num=min(48, count), dtype=int))
            for pos in positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                h, w = frame.shape[:2]
                scale = min(1.0, 1600 / max(h, w))
                if scale < 1:
                    frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
                target = images_dir / f'frame_{int(pos):06d}.jpg'
                if cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 96]):
                    saved += 1
        finally:
            cap.release()
        if saved < 3:
            return jsonify({'success': False, 'error': f'有效图像仅 {saved} 张，至少需要 3 张。', 'job_id': job_id}), 422
        result = run_apple_capture(images_dir, output_path, timeout_seconds=int(os.getenv('PHOTOCATCH_APPLE_TIMEOUT', '7200')))
        result.update({
            'job_id': job_id, 'input_images': saved, 'input_analysis': report,
            'model_url': f'/api/video/apple-models/{job_id}',
            'message': '苹果原生重建完成；请检查 USDZ 的完整度、纹理和比例后再判定质量。',
        })
        return jsonify(result)
    except AppleCaptureError as exc:
        logger.warning("Apple Object Capture failed: %s", exc)
        return jsonify({'success': False, 'error': str(exc), 'job_id': job_id}), 422
    except Exception:
        logger.exception("Apple Object Capture endpoint failed")
        return jsonify({'success': False, 'error': '苹果原生重建失败；请检查后端日志。', 'job_id': job_id}), 500
    finally:
        # Retain the generated USDZ and diagnostics, but never retain the uploaded original or sampled frames.
        upload_path.unlink(missing_ok=True)
        shutil.rmtree(images_dir, ignore_errors=True)


@app.route('/api/video/apple-models/<job_id>', methods=['GET'])
def get_apple_reconstruction_asset(job_id):
    if not job_id.isalnum():
        return jsonify({'error': '模型文件路径无效'}), 400
    model_path = Path(app.instance_path) / 'reconstructions' / job_id / 'apple-object-capture.usdz'
    if not model_path.is_file():
        return jsonify({'error': 'USDZ 模型不存在；重建可能未完成'}), 404
    return send_from_directory(model_path.parent, model_path.name, mimetype='model/vnd.usdz+zip', as_attachment=True)


@app.route('/api/video/models/<job_id>/<asset_name>', methods=['GET'])
def get_reconstruction_asset(job_id, asset_name):
    fixed_names = {'mesh.ply': 'mesh.ply', 'pointcloud.ply': 'fused.ply',
                   'scene_textured_mesh.obj': 'scene_textured_mesh.obj'}
    # TextureMesh also emits MTL and image files. Permit only simple basenames with
    # known generated-asset extensions; send_from_directory confines access to base.
    generated_texture_asset = (
        Path(asset_name).name == asset_name
        and asset_name.startswith('scene_')
        and Path(asset_name).suffix.lower() in {'.mtl', '.png', '.jpg', '.jpeg'}
    )
    if not job_id.isalnum() or (asset_name not in fixed_names and not generated_texture_asset):
        return jsonify({'error': '模型文件路径无效'}), 400
    base = Path(app.instance_path) / 'reconstructions' / job_id / 'colmap' / 'dense'
    filename = fixed_names.get(asset_name, asset_name)
    if not (base / filename).is_file():
        return jsonify({'error': '模型文件不存在；重建可能未完成或当前引擎未生成该格式'}), 404
    import mimetypes
    mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return send_from_directory(base, filename, mimetype=mimetype, as_attachment=False)


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
