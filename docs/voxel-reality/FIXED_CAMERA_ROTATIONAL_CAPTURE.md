# Voxel Reality — Fixed-Camera Rotational Capture (FCRC)

## Engineering objective

Capture an object rotating about the rig Z axis while three calibrated cameras remain stationary at distinct azimuths. Convert every synchronized observation into the same object-reference coordinate system using the measured turntable angle. Fuse observations into a conservative colored voxel visual hull, retaining provenance and explicit limitations.

This is a new acquisition/reconstruction path. It does not replace or modify the legacy PhotoCatch reconstruction pipeline.

## Coordinate convention

Right-handed rig frame: +Z is the turntable axis. Angles are radians internally and degrees in capture manifests. Matrices use column-vector convention and are named `T_destination_from_source`.

For object-reference point `p_object` at measured turntable angle theta:

`p_camera = T_camera_from_rig * T_rig_from_turntable * Rz(theta) * T_turntable_from_object * p_object`

Each camera has fixed intrinsics and fixed `T_camera_from_rig`. The measured angle is sampled at exposure time from an encoder or a hardware-synchronized controller. Host wall-clock estimates are not accepted as encoder data.

## Acquisition requirements

- Three fixed cameras with unique IDs and calibrated intrinsics, distortion and extrinsics.
- Global-shutter sensors are strongly preferred. Rolling-shutter requires row-time compensation and is not accepted by this first implementation.
- Common hardware trigger or measured exposure timestamps. Per-capture camera skew is bounded by a configurable nanosecond limit.
- Encoder angle sampled at exposure time; monotonic rotation direction; no guessed angle from commanded motor speed.
- Fixed focus, exposure, white balance and lighting after calibration.
- Object rigidly attached to a calibrated turntable; no slipping, deformation or articulation during a scan.
- Foreground masks generated from actual source frames by a segmentation model or reviewed operator. This package consumes masks; it does not fabricate them.

## Implemented first-stage pipeline

1. Validate exactly three camera calibrations and one observation per camera per capture group.
2. Validate image/mask existence, dimensions, timestamps, synchronization skew, encoder angle and transform matrices.
3. Transform object-reference voxel candidates into each fixed camera using the measured turntable angle.
4. Intersect silhouette constraints to form a **visual hull**.
5. Extract the hull's surface voxels and project them back into observations.
6. Use per-observation nearest-depth pixel arbitration before sampling RGB; preserve only observed colors.
7. Write an occupancy NPZ, colored surface PLY, and JSON provenance/quality manifest.

## What visual hull means — and does not mean

Silhouette carving produces an outer visual hull. It cannot recover concavities that never affect silhouettes, hidden internal geometry, or exact depth from a single silhouette. The result is not a dense photogrammetric mesh and must never be labeled as a complete or exact reconstruction. Subsequent milestones must add calibrated feature correspondence, multi-view triangulation / COLMAP pose priors, dense stereo or measured depth, occlusion reasoning, texture atlas generation and metric validation.

## Hardware geometry

The initial three-camera azimuth proposal is 0°, 120°, 240° around Z. These are mounting targets, not calibration values. The actual calibrated extrinsics are authoritative. Camera optical axes must converge on the calibrated object volume; lens field of view and object envelope determine camera elevation and distance. A second elevated camera tier or depth sensor may be needed for top/bottom coverage.

Recommended capture:
- rigid optical bench / enclosed light-controlled booth;
- encoder-equipped direct-drive turntable;
- common trigger generator with per-camera exposure timestamps;
- three matched global-shutter cameras, fixed focal-length lenses;
- diffuse cross-polarized lighting and color checker;
- scale artifact and calibration target captured at the object origin;
- emergency stop and interlocked guard around moving hardware.

## Acceptance gates

- Calibration reprojection error recorded per camera and below a project-defined threshold.
- Camera synchronization skew measured from trigger/exposure metadata.
- Encoder angular error and repeatability measured against an independent reference.
- Real calibration target dimensions reconstructed within a declared tolerance.
- Real physical object scanned twice; repeatability and coverage compared.
- Surface color error measured against a color chart under controlled lighting.
- Unobserved regions and uncertainty surfaced in the UI.
- No fixture-based unit test counts as a real-camera or real-object acceptance test.

## Package layout

- `backend/rotational_capture/schema.py`: calibration and capture manifest contracts.
- `backend/rotational_capture/geometry.py`: rigid transforms and projection.
- `backend/rotational_capture/pipeline.py`: synchronization, visual-hull carving, observed-color fusion and provenance.
- `tests/test_rotational_capture.py`: deterministic mathematical and validation tests.

## Explicit non-goals of this milestone

No camera SDK driver, motor controller, hardware trigger firmware, segmentation model, dense MVS mesh, texture atlas, Android/iOS AR client, or light-field display driver is claimed implemented. Those are separate deliverables with hardware-specific acceptance tests.


## File contract and invocation

The calibration JSON uses `schema_version: 1`, `unit`, exactly three camera records (`camera_id`, 3x3 `intrinsics`, distortion coefficients, 4x4 `camera_from_rig`, image dimensions), 4x4 `rig_from_turntable` and `turntable_from_object`, and a `scale_calibration` object. Matrices are rigid transforms; camera extrinsics are measured, never inferred from the proposed 0/120/240 degree mounting labels.

The capture manifest contains at least two `capture_groups`. Every group must include:
- unique `capture_id`;
- `angle_deg` measured by the encoder at exposure time;
- `encoder_timestamp_ns`;
- exactly one frame record for each calibrated camera;
- each frame's `timestamp_ns`, `image_path` and `mask_path`.

The encoder timestamp and all three camera exposure timestamps must fall within `max_sync_skew_ns`. Paths are relative to the capture manifest. Masks must be real per-frame foreground masks aligned to the original images.

Run from the repository root:

```bash
python -m backend.rotational_capture.cli \
  --calibration /path/to/calibration.json \
  --capture-manifest /path/to/capture.json \
  --output /path/to/output \
  --bounds-min -0.15 -0.15 0.00 \
  --bounds-max 0.15 0.15 0.40 \
  --voxel-size 0.002 \
  --min-observations 6
```

The command intentionally requires the user to supply measured bounds and voxel size. It does not generate a default object, assume a scale, or claim an uncalibrated unit is metric.
