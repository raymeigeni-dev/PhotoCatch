"""Evidence-preserving three-fixed-camera rotational visual-hull reconstruction.

This stage computes a silhouette visual hull and observed surface colors. It is
not a substitute for dense multi-view stereo or hidden-surface reconstruction.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import trimesh

from backend.rotational_capture.geometry import project_object_points
from backend.rotational_capture.schema import (
    CaptureSequence, CaptureValidationError, RigCalibration,
    load_calibration, load_capture_sequence,
)


class RotationalCaptureError(RuntimeError):
    """A capture cannot produce a defensible rotational reconstruction."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_observation_pixels(observation, camera):
    image = cv2.imread(str(observation.image_path), cv2.IMREAD_COLOR)
    mask = cv2.imread(str(observation.mask_path), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None:
        raise RotationalCaptureError(
            f"{observation.capture_id}/{observation.camera_id} 图像或 mask 无法解码。"
        )
    expected = (camera.image_height, camera.image_width)
    if image.shape[:2] != expected or mask.shape[:2] != expected:
        raise RotationalCaptureError(
            f"{observation.capture_id}/{observation.camera_id} 图像/mask 尺寸与标定尺寸不一致。"
        )
    return image, mask > 0


def _surface_indices(indices: np.ndarray) -> np.ndarray:
    occupied = {tuple(int(v) for v in row) for row in indices}
    surface = []
    neighbors = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    for row in indices:
        key = tuple(int(v) for v in row)
        if any(tuple(key[i] + delta[i] for i in range(3)) not in occupied for delta in neighbors):
            surface.append(row)
    return np.asarray(surface, dtype=np.int64).reshape(-1, 3)


def _validate_camera_coverage(sequence: CaptureSequence, rig: RigCalibration) -> None:
    expected = set(rig.cameras)
    for capture_id in sorted({item.capture_id for item in sequence.observations}):
        found = {item.camera_id for item in sequence.observations if item.capture_id == capture_id}
        if found != expected:
            raise RotationalCaptureError(
                f"{capture_id} 相机集合不匹配：expected={sorted(expected)}, found={sorted(found)}"
            )


def reconstruct_visual_hull(
    calibration_path: str | Path,
    capture_manifest_path: str | Path,
    output_dir: str | Path,
    *,
    bounds_min: list[float],
    bounds_max: list[float],
    voxel_size: float,
    min_observations: int = 6,
    max_candidate_voxels: int = 2_000_000,
) -> dict[str, Any]:
    """Carve a conservative silhouette visual hull and color visible surface voxels.

    Bounds and voxel_size use the unit declared in the calibration. The object
    reference frame is the zero-angle object frame. Encoder angles are measured
    at exposure time. A point is rejected if any in-frame observation sees it
    outside the supplied foreground mask.
    """
    try:
        rig = load_calibration(calibration_path)
        sequence = load_capture_sequence(capture_manifest_path)
    except CaptureValidationError as exc:
        raise RotationalCaptureError(str(exc)) from exc
    _validate_camera_coverage(sequence, rig)

    lower = np.asarray(bounds_min, dtype=np.float64)
    upper = np.asarray(bounds_max, dtype=np.float64)
    if lower.shape != (3,) or upper.shape != (3,) or not np.isfinite(lower).all() or not np.isfinite(upper).all():
        raise RotationalCaptureError("bounds_min / bounds_max 必须是有限的三维坐标。")
    if np.any(upper <= lower):
        raise RotationalCaptureError("每个 bounds_max 分量都必须大于 bounds_min。")
    if not np.isfinite(voxel_size) or voxel_size <= 0:
        raise RotationalCaptureError("voxel_size 必须是正的有限值。")
    if min_observations < 1 or max_candidate_voxels < 1:
        raise RotationalCaptureError("min_observations 和 max_candidate_voxels 必须为正整数。")

    axes = [
        np.arange(lower[i] + voxel_size / 2, upper[i], voxel_size, dtype=np.float64)
        for i in range(3)
    ]
    if any(len(axis) == 0 for axis in axes):
        raise RotationalCaptureError("边界盒小于一个体素。")
    shape = tuple(len(axis) for axis in axes)
    candidate_count = int(np.prod(shape, dtype=np.int64))
    if candidate_count > max_candidate_voxels:
        raise RotationalCaptureError(
            f"候选体素数 {candidate_count} 超过限制 {max_candidate_voxels}。"
        )
    xx, yy, zz = np.meshgrid(*axes, indexing="ij")
    candidates = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))

    rejected = np.zeros(len(candidates), dtype=bool)
    seen = np.zeros(len(candidates), dtype=np.uint32)
    decoded: list[tuple[Any, Any, np.ndarray, np.ndarray]] = []
    for observation in sequence.observations:
        camera = rig.cameras.get(observation.camera_id)
        if camera is None:
            raise RotationalCaptureError(f"未标定的相机：{observation.camera_id}")
        image, mask = _load_observation_pixels(observation, camera)
        pixels, depth = project_object_points(candidates, camera, rig, observation.angle_deg)
        finite_pixels = np.isfinite(pixels).all(axis=1)
        safe_pixels = np.where(finite_pixels[:, None], pixels, -1e9)
        u = np.rint(safe_pixels[:, 0]).astype(np.int64)
        v = np.rint(safe_pixels[:, 1]).astype(np.int64)
        in_frame = (
            (depth > 0)
            & (u >= 0) & (u < camera.image_width)
            & (v >= 0) & (v < camera.image_height)
        )
        ids = np.flatnonzero(in_frame)
        seen[ids] += 1
        foreground = np.zeros(len(candidates), dtype=bool)
        foreground[ids] = mask[v[ids], u[ids]]
        rejected |= in_frame & ~foreground
        decoded.append((observation, image, mask, depth))

    occupied_mask = (~rejected) & (seen >= min_observations)
    occupied = candidates[occupied_mask]
    if len(occupied) == 0:
        raise RotationalCaptureError(
            "没有体素通过多视角轮廓约束。请检查相机外参、旋转角、前景 mask 和物体边界盒。"
        )

    grid_indices = np.floor((occupied - lower) / voxel_size).astype(np.int64)
    surface_indices = _surface_indices(grid_indices)
    surface_centers = lower + (surface_indices.astype(np.float64) + 0.5) * voxel_size
    color_sum = np.zeros((len(surface_centers), 3), dtype=np.float64)
    color_count = np.zeros(len(surface_centers), dtype=np.uint16)

    for observation, image, mask, _ in decoded:
        camera = rig.cameras[observation.camera_id]
        pixels, depth = project_object_points(surface_centers, camera, rig, observation.angle_deg)
        finite_pixels = np.isfinite(pixels).all(axis=1)
        safe_pixels = np.where(finite_pixels[:, None], pixels, -1e9)
        u = np.rint(safe_pixels[:, 0]).astype(np.int64)
        v = np.rint(safe_pixels[:, 1]).astype(np.int64)
        valid = (
            finite_pixels
            & np.isfinite(depth)
            & (depth > 0)
            & (u >= 0) & (u < camera.image_width)
            & (v >= 0) & (v < camera.image_height)
        )
        ids = np.flatnonzero(valid)
        if len(ids) == 0:
            continue
        flat = v[ids] * camera.image_width + u[ids]
        zbuffer = np.full(camera.image_width * camera.image_height, np.inf, dtype=np.float64)
        np.minimum.at(zbuffer, flat, depth[ids])
        visible = depth[ids] <= zbuffer[flat] + voxel_size * 0.75
        ids = ids[visible]
        if len(ids) == 0:
            continue
        valid_mask = mask[v[ids], u[ids]]
        ids = ids[valid_mask]
        if len(ids) == 0:
            continue
        rgb = image[v[ids], u[ids], ::-1].astype(np.float64)
        np.add.at(color_sum, ids, rgb)
        np.add.at(color_count, ids, 1)

    colored = color_count > 0
    if not colored.any():
        raise RotationalCaptureError(
            "视觉外壳已生成，但没有可追溯的表面颜色观测；拒绝生成伪彩色结果。"
        )
    observed_rgb = np.zeros((len(surface_centers), 3), dtype=np.uint8)
    observed_rgb[colored] = np.clip(
        np.rint(color_sum[colored] / color_count[colored, None]), 0, 255
    ).astype(np.uint8)

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    occupancy_path = destination / "rotational_visual_hull.npz"
    cloud_path = destination / "rotational_surface_observed_rgb.ply"
    manifest_path = destination / "rotational_reconstruction.manifest.json"

    np.savez_compressed(
        occupancy_path,
        occupied_centers=occupied,
        occupied_grid_indices=grid_indices,
        surface_centers=surface_centers,
        surface_grid_indices=surface_indices,
        surface_rgb=observed_rgb,
        surface_color_observed=colored,
        surface_color_observation_count=color_count,
        voxel_size=np.float64(voxel_size),
        unit=np.asarray(rig.unit),
    )
    cloud = trimesh.points.PointCloud(surface_centers[colored], colors=observed_rgb[colored])
    cloud.export(cloud_path)

    calibration_file = Path(calibration_path).expanduser().resolve()
    capture_file = Path(capture_manifest_path).expanduser().resolve()
    manifest = {
        "schema_version": 1,
        "algorithm": "three_fixed_camera_rotational_silhouette_visual_hull",
        "status": "visual_hull_with_observed_surface_rgb",
        "source_calibration_sha256": _sha256(calibration_file),
        "source_capture_manifest_sha256": _sha256(capture_file),
        "camera_ids": sorted(rig.cameras),
        "capture_groups": len({item.capture_id for item in sequence.observations}),
        "observation_count": len(sequence.observations),
        "max_sync_skew_ns": sequence.max_sync_skew_ns,
        "candidate_voxel_count": candidate_count,
        "occupied_visual_hull_voxel_count": int(len(occupied)),
        "surface_voxel_count": int(len(surface_centers)),
        "surface_voxels_with_observed_rgb": int(colored.sum()),
        "surface_voxels_without_rgb": int((~colored).sum()),
        "voxel_size": float(voxel_size),
        "unit": rig.unit,
        "scale_status": rig.scale_status,
        "scale_source": rig.scale_source,
        "scale_uncertainty": rig.scale_uncertainty,
        "outputs": {
            "occupancy_npz": occupancy_path.name,
            "colored_surface_ply": cloud_path.name,
        },
        "limitations": [
            "This output is a silhouette visual hull, not dense multi-view stereo.",
            "Silhouette visual hulls cannot recover concavities that do not affect silhouettes.",
            "Unobserved/internal surfaces are not reconstructed.",
            "RGB is emitted only where source image pixels and foreground masks provide evidence.",
            "Metric dimensions are valid only when the input calibration scale is independently calibrated.",
            "No physical camera, turntable or real-object acceptance test is implied by this software result.",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "status": manifest["status"],
        "occupied_voxels": int(len(occupied)),
        "surface_voxels": int(len(surface_centers)),
        "colored_surface_voxels": int(colored.sum()),
        "occupancy_path": str(occupancy_path),
        "point_cloud_path": str(cloud_path),
        "manifest_path": str(manifest_path),
        "scale_status": rig.scale_status,
    }


def reconstruct_from_files(
    calibration_path: str | Path,
    capture_manifest_path: str | Path,
    output_dir: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Stable public entry point for CLI/API adapters."""
    return reconstruct_visual_hull(
        calibration_path, capture_manifest_path, output_dir, **kwargs
    )
