"""Video sampling and conservative photogrammetry input preflight.

The metrics here are heuristics only. They cannot prove camera motion or guarantee
that a clip is reconstructable; COLMAP's own sparse reconstruction is the next gate.
"""
from __future__ import annotations

import os
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


def _pair_geometry(first: np.ndarray, second: np.ndarray) -> dict[str, float | int | bool]:
    """Assess static-scene feature geometry; this is not a camera-pose estimator."""
    gray_a = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=2000)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)
    empty = {"keypoints_a": len(kp_a), "keypoints_b": len(kp_b), "good_matches": 0,
             "inliers": 0, "inlier_ratio": 0.0, "median_flow_px": 0.0,
             "fundamental_valid": False}
    if des_a is None or des_b is None or len(kp_a) < 8 or len(kp_b) < 8:
        return empty
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_a, des_b, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.72 * pair[1].distance]
    if len(good) < 8:
        return {**empty, "good_matches": len(good)}
    pts_a = np.float32([kp_a[m.queryIdx].pt for m in good])
    pts_b = np.float32([kp_b[m.trainIdx].pt for m in good])
    F, mask = cv2.findFundamentalMat(pts_a, pts_b, cv2.FM_RANSAC, 1.5, 0.99)
    inliers = mask.ravel().astype(bool) if F is not None and mask is not None else np.zeros(len(good), dtype=bool)
    flow = np.linalg.norm(pts_b - pts_a, axis=1)
    return {
        "keypoints_a": len(kp_a), "keypoints_b": len(kp_b), "good_matches": len(good),
        "inliers": int(inliers.sum()),
        "inlier_ratio": round(float(inliers.mean()), 4) if len(inliers) else 0.0,
        "median_flow_px": round(float(np.median(flow[inliers])) if inliers.any() else 0.0, 3),
        "fundamental_valid": bool(F is not None and F.shape == (3, 3) and inliers.sum() >= 8),
    }


def analyze_video(path: str, max_frames: int = 24, max_dimension: int = 960) -> dict[str, Any]:
    if max_frames < 2 or max_dimension < 64:
        raise ValueError("抽帧数量至少为 2，最大图像边长至少为 64")
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
        positions = np.unique(np.linspace(0, frame_count - 1, num=sample_count, dtype=int))
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
    pair_reports = []
    for (_, a), (_, b) in zip(sampled, sampled[1:]):
        target_h, target_w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        pair_reports.append(_pair_geometry(cv2.resize(a, (target_w, target_h)), cv2.resize(b, (target_w, target_h))))

    blurry = sum(value < 35 for value in sharpness)
    dark = sum(value < 25 for value in brightness)
    geometrically_supported = sum(p["fundamental_valid"] and p["inliers"] >= 20 and p["inlier_ratio"] >= 0.25 for p in pair_reports)
    parallax_pairs = sum(p["fundamental_valid"] and p["inliers"] >= 20 and p["median_flow_px"] >= 2.0 for p in pair_reports)
    warnings = []
    if blurry / len(sharpness) > 0.35:
        warnings.append("多数采样帧清晰度偏低；请避免手抖、快速移动或失焦")
    if dark / len(brightness) > 0.5:
        warnings.append("视频整体偏暗；增加均匀光照")
    if geometrically_supported < max(1, int(len(pair_reports) * 0.4)):
        warnings.append("满足几何一致性检验的特征帧对不足；可能是纹理少、模糊、运动模糊或视角变化不适合")
    if parallax_pairs < 2:
        warnings.append("没有足够的几何一致且有像素视差的帧对。普通画面变化、物体自身运动或静态相机不能证明有效相机运动")
    warnings.append("输入初检仅为启发式判断；最终可重建性必须由 COLMAP 稀疏重建是否成功来确认")
    eligible = (
        len(sampled) >= 8
        and blurry / len(sharpness) <= 0.35
        and geometrically_supported >= max(1, int(len(pair_reports) * 0.4))
        and parallax_pairs >= 2
    )
    if not eligible:
        warnings.append("当前素材未通过保守的输入门槛；不会因此生成或展示虚假的 3D 成功结果")

    preview_indices = sorted(set([0, len(sampled) // 3, (2 * len(sampled)) // 3, len(sampled) - 1]))
    previews = []
    for idx in preview_indices:
        frame_no, frame = sampled[idx]
        previews.append({"frame_index": frame_no, "time_seconds": round(frame_no / fps, 3) if fps > 0 else None,
                         "image": encode_image(frame), **metrics[idx]})
    return {
        "success": True, "analysis_only": True, "reconstruction_ready": bool(eligible),
        "message": "输入初检通过；仍需 COLMAP 稀疏重建确认。" if eligible else "输入初检未通过；请根据提示重新拍摄或选择其他视频。",
        "video": {"width": width, "height": height, "fps": round(fps, 3), "frame_count": frame_count, "duration_seconds": round(duration, 3)},
        "sampling": {"extracted_frames": len(sampled), "requested_frames": sample_count, "max_dimension": max_dimension},
        "quality": {
            "sharpness_median": round(float(np.median(sharpness)), 2), "sharp_frames": len(sharpness) - blurry,
            "dark_frames": dark, "geometrically_supported_pairs": int(geometrically_supported),
            "parallax_pairs": int(parallax_pairs), "pairs_checked": len(pair_reports),
            "pair_geometry": pair_reports,
        },
        "warnings": warnings, "previews": previews,
        "next_step": "COLMAP SfM 稀疏重建" if eligible else "重新拍摄：稳定清晰、光线均匀，绕静止目标走动并保持纹理可见",
    }
