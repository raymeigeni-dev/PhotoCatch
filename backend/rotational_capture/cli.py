"""Command-line entry point for fixed-camera rotational capture."""
from __future__ import annotations

import argparse
import json

from backend.rotational_capture.pipeline import reconstruct_visual_hull


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a three-camera rotational silhouette visual hull from calibrated captures."
    )
    parser.add_argument("--calibration", required=True, help="Path to calibrated rig JSON.")
    parser.add_argument("--capture-manifest", required=True, help="Path to synchronized capture JSON.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--bounds-min", required=True, nargs=3, type=float, metavar=("X", "Y", "Z"))
    parser.add_argument("--bounds-max", required=True, nargs=3, type=float, metavar=("X", "Y", "Z"))
    parser.add_argument("--voxel-size", required=True, type=float)
    parser.add_argument("--min-observations", type=int, default=6)
    parser.add_argument("--max-candidate-voxels", type=int, default=2_000_000)
    args = parser.parse_args()

    result = reconstruct_visual_hull(
        args.calibration,
        args.capture_manifest,
        args.output,
        bounds_min=args.bounds_min,
        bounds_max=args.bounds_max,
        voxel_size=args.voxel_size,
        min_observations=args.min_observations,
        max_candidate_voxels=args.max_candidate_voxels,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
