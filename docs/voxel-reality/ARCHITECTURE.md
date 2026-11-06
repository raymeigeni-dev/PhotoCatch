# Voxel Reality — Engineering Architecture

Status: foundation specification. This document defines interfaces and acceptance boundaries; it does not claim the complete product exists.

## Product contract

Voxel Reality accepts a user-selected object from a real video or image sequence, reconstructs geometry and appearance from measured evidence, optionally decomposes the resulting surface/point cloud into colored spatial voxels, and displays the validated asset on supported AR or spatial-display devices.

The system must distinguish:
- **Observed**: directly measured from source images/depth.
- **Reconstructed**: estimated by a named reconstruction backend.
- **Calibrated**: metric scale established from a documented reference or sensor.
- **Inferred / unknown**: not observed or not reliably recoverable.

Never fill missing geometry, color, texture, scale, or hidden surfaces with fabricated values while labeling the result as a faithful reconstruction.

## Architecture boundaries

1. **Capture & ingestion**
   - Video/image import, timestamps, camera metadata, optional depth/LiDAR.
   - Immutable source asset, SHA-256, media metadata, per-job workspace.
   - Capture quality report is advisory; it is not a reconstruction result.

2. **Object selection & temporal tracking**
   - Per-frame instance masks and stable track identity.
   - Mask confidence, occlusion, lost-track and re-identification events.
   - Preserve original frame coordinates and camera calibration.

3. **Reconstruction adapters**
   - Apple Object Capture (supported Apple platforms only).
   - COLMAP + compatible dense reconstruction backend.
   - Future platform-neutral photogrammetry/depth adapters.
   - Each adapter declares input requirements, coordinate frame, units, outputs, limitations and provenance.
   - No silent fallback to silhouette extrusion or a synthetic mesh.

4. **Canonical geometry & appearance**
   - Canonical asset manifest with coordinate frame, unit declaration, transform, bounds and provenance.
   - Geometry: point cloud, triangle mesh and optional Gaussian splat representations.
   - Appearance: vertex colors, UV textures, material parameters and texture evidence.
   - Validate topology, connected components, holes, normals, texture/material presence and finite coordinates.

5. **Voxel decomposition**
   - Convert an existing measured point cloud or colored mesh vertices into a voxel representation.
   - Each occupied voxel records integer grid coordinate, center, occupancy count and aggregated observed color.
   - Voxel size is explicit in the declared source unit.
   - Missing source color is a hard error; do not invent color.
   - Voxelization is a representation conversion, not a way to recover unseen geometry.

6. **Metric scale & calibration**
   - Scale sources: calibrated depth/LiDAR, known physical reference, or calibrated camera reconstruction.
   - Store scale source, reference measurement, uncertainty and transform.
   - If no metric reference exists, label scale as arbitrary/uncalibrated; do not claim original physical dimensions.

7. **Spatial presentation**
   - Cross-platform core asset formats: GLB/glTF, PLY and USDZ where supported.
   - Mobile AR adapters: ARKit/RealityKit and ARCore; desktop viewer for Windows/macOS.
   - Air/light-medium presentation is a hardware adapter boundary (light-field, volumetric display or projection medium), not a software-only promise.
   - Presentation transforms must not mutate canonical geometry or its metric dimensions.

8. **Quality, provenance & test harness**
   - Every job emits machine-readable diagnostics, source hash, backend/version, calibration provenance, outputs and quality gates.
   - Unit tests may use explicitly labeled fixtures; fixtures never count as real capture acceptance.
   - Real acceptance requires a physical object, real capture, measured dimensions, reconstructed output and independent visual/metric review.

## Proposed repository layout

- `backend/capture/`: media ingestion and frame selection
- `backend/selection/`: object masks and temporal tracking adapters
- `backend/reconstruction/`: backend contracts and Apple/COLMAP adapters
- `backend/assets/`: canonical asset manifest and validation
- `backend/voxelization.py`: first isolated voxel conversion primitive
- `backend/calibration/`: metric scale and uncertainty
- `backend/spatial/`: AR and spatial-display adapters
- `frontend/`: cross-platform workspace and viewer
- `native/ios/`, `native/android/`, `native/spatial-display/`: device-specific bridges
- `tests/fixtures/`: small deterministic test assets, never presented as reconstructed customer objects

Migration is incremental. Existing PhotoCatch modules remain intact while proven functionality is wrapped behind explicit interfaces.

## First implementation milestone

Implement a strict colored-point-cloud-to-voxel conversion primitive with:
- explicit input units and voxel size;
- finite-coordinate and color validation;
- deterministic voxel indexing and per-voxel centroid/color aggregation;
- bounded output size;
- source hash and metadata manifest;
- no synthetic geometry or default colors;
- tests for correctness and failure behavior.

This milestone proves only the conversion stage. It does not prove video segmentation, photogrammetry, metric scale recovery, AR tracking, or holographic display.
