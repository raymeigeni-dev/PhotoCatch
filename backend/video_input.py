"""Video ingestion and capture-quality assessment for multi-view reconstruction.

This module does not claim to reconstruct geometry. It extracts temporally distributed
frames and estimates whether the clip has enough sharpness and visual change to justify
attempting a photogrammetry pipeline.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import cv2
import numpy as np

from backend.utils import encode_image


def _frame_metrics(frame: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return {
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
        "brightness": round(float(gray.mean()), 2),
        "contrast": round(float(gray.std()), 2),
    }


def _feature_overlap(first: np.ndarray, second: np.ndarray) -> tuple[int, float]:
    """Return ORB good-match count and inlier ratio proxy, not camera pose."""
    gray_a = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=1200)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)
    if des_a is None or des_b is None or len(kp_a) < 8 or len(kp_b) < 8:
        return 0, 0.0
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_a, des_b, k=2)
    good = [m for pair in pairs if len(pair) == 2 for m, n in [pair] if m.distance < 0.72 * n.distance]
    return len(good), round(len(good) / max(1, min(len(kp_a), len(kp_b))), 4)


def analyze_video(path: str, max_frames: int = 24, max_dimension: int = 960) -> dict[str, Any]:
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise ValueError("上传的视频文件为空或不存在")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("无法解码该视频。请尝试 MP4/H.264 或转换为常见视频格式。")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        if frame_count < 2 or width < 32 or height < 32:
            raise ValueError("视频帧数或分辨率不足，至少需要两帧有效画面")

        sample_count = min(max_frames, frame_count)
        positions = np.linspace(0, frame_count - 1, num=sample_count, dtype=int)
        sampled: list[tuple[int, np.ndarray]] = []
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            scale = min(1.0, max_dimension / max(h, w))
            if scale < 1:
                frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            sampled.append((int(pos), frame))
    finally:
        cap.release()

    if len(sampled) < 2:
        raise ValueError("视频解码失败：成功提取的有效帧少于 2 帧")

    metrics = [_frame_metrics(frame) for _, frame in sampled]
    sharpness = [m["sharpness"] for m in metrics]
    brightness = [m["brightness"] for m in metrics]
    feature_counts, overlap = [], []
    for (_, a), (_, b) in zip(sampled, sampled[1:]):
        # Align image sizes for feature matching.
        target_h = min(a.shape[0], b.shape[0])
        target_w = min(a.shape[1], b.shape[1])
        a2 = cv2.resize(a, (target_w, target_h))
        b2 = cv2.resize(b, (target_w, target_h))
        count, ratio = _feature_overlap(a2, b2)
        feature_counts.append(count)
        overlap.append(ratio)

    blurry = sum(value < 35 for value in sharpness)
    dark = sum(value < 25 for value in brightness)
    useful_pairs = sum(count >= 20 for count in feature_counts)
    changed_pairs = sum(count >= 20 and ratio < 0.85 for count, ratio in zip(feature_counts, overlap))
    warnings = []
    if blurry / len(sharpness) > 0.35:
        warnings.append("多数采样帧清晰度偏低；请避免手抖、快速移动或失焦")
    if dark / len(brightness) > 0.5:
        warnings.append("视频整体偏暗；增加均匀光照")
    if useful_pairs < max(1, int(len(feature_counts) * 0.4)):
        warnings.append("相邻采样帧的可匹配特征不足；场景可能纹理少、模糊或变化过大")
    if changed_pairs < 2:
        warnings.append("暂未观察到足够的视角/画面变化证据；请绕目标缓慢移动拍摄，而非只让目标转动或使用静态单视角")
    eligible = (
        len(sampled) >= 8
        and blurry / len(sharpness) <= 0.35
        and useful_pairs >= max(1, int(len(feature_counts) * 0.4))
        and changed_pairs >= 2
    )
    if not eligible:
        warnings.append("当前素材不满足自动重建的初步输入门槛；本分析不会生成虚假的 3D 成功结果")

    # Return a small contact sheet of representative frames for UI review.
    preview_indices = sorted(set([0, len(sampled) // 3, (2 * len(sampled)) // 3, len(sampled) - 1]))
    previews = []
    for idx in preview_indices:
        frame_no, frame = sampled[idx]
        previews.append({
            "frame_index": frame_no,
            "time_seconds": round(frame_no / fps, 3) if fps > 0 else None,
            "image": encode_image(frame),
            **metrics[idx],
        })

    return {
        "success": True,
        "analysis_only": True,
        "reconstruction_ready": bool(eligible),
        "message": "输入初检完成；通过初检不代表已经完成三维重建。" if eligible else "输入初检未通过；请根据提示重新拍摄或选择其他视频。",
        "video": {"width": width, "height": height, "fps": round(fps, 3), "frame_count": frame_count, "duration_seconds": round(duration, 3)},
        "sampling": {"extracted_frames": len(sampled), "requested_frames": sample_count, "max_dimension": max_dimension},
        "quality": {
            "sharpness_median": round(float(np.median(sharpness)), 2),
            "sharp_frames": len(sharpness) - blurry,
            "dark_frames": dark,
            "feature_match_pairs": useful_pairs,
            "pairs_checked": len(feature_counts),
            "changed_view_pairs": changed_pairs,
            "feature_match_counts": feature_counts,
        },
        "warnings": warnings,
        "previews": previews,
        "next_step": "多视角摄影测量（例如 COLMAP SfM/MVS）" if eligible else "重新拍摄：稳定、清晰、光线均匀，绕目标走动并保持目标占画面主体",
    }
