# Suspended garment capture protocol

This document defines the first executable capture-ingestion layer for Voxel Reality.
It separates recorder synchronization, encoder angle measurement, and reconstruction.
A successful manifest proves timestamp/angle consistency only; it does not prove that
a physical garment has been reconstructed correctly.

## Physical layout

- Suspend the garment from an overhead hanger; no turntable/tabletop is required.
- Place three fixed cameras around the vertical Z axis, nominal azimuths 0/120/240 degrees.
- Keep cameras stationary and calibrate intrinsics/extrinsics in the capture volume.
- Rotate the hanger/garment at a conservative nominal 0.1–3 RPM; begin at 1 RPM.
- Nominal sampling is every 2 degrees (180 groups per revolution). At 1 RPM this is
  one group every 333 ms. Each group contains one selected frame from each camera.
- The encoder measures actual hanger angle. Nominal RPM and nominal angle are not
  substituted for measured values.

## Indirect synchronization

The three recorders need not share a clock or provide Genlock. A visible optical
timecode/LED device is included in all camera views. A camera-specific detector emits
OpticalPulse(camera_id, pts_ns, pulse_id, reference_time_ns) observations. The sync
bridge fits an affine mapping from each camera's media PTS clock to a shared reference
clock and rejects insufficient, non-monotonic, or high-residual pulse evidence.

The current bridge is the decoded-pulse ingestion and clock-mapping API. LED hardware,
optical pattern generation, and image-level LED detection are not yet implemented.
The bridge does not infer synchronization from file creation time or device wall clocks.

group_nearest_frames selects one unique frame per camera for each requested reference
time and enforces a maximum inter-camera timestamp skew. It refuses to silently reuse
a single frame for multiple capture groups.

## Encoder interface

The encoder adapter consumes CSV rows with these columns:

    timestamp_ns,angle_deg
    0,359.0
    10000000,0.0
    20000000,1.0

Angles are unwrapped before interpolation, so crossing 359 -> 0 degrees remains
continuous. The adapter rejects time reversal, direction reversal, long sampling gaps,
and extrapolation outside measured encoder coverage. The output angle is interpolated
at the synchronized exposure reference time.

## Manifest contract

write_capture_manifest emits the existing rotational capture schema v1:
exactly three frame observations per capture group, shared-clock timestamps, and the
encoder-interpolated angle. Image and mask paths are relative to the manifest location
and must exist before the reconstruction pipeline consumes the manifest.

## Phone / DJI video constraints

Ordinary phones and many compact DJI cameras use rolling shutters. The current
visual-hull camera calibration contract still requires global shutter; this is an
intentional safety gate, not a claim that phones have global shutters. Before
phone/DJI footage can be accepted for metric reconstruction, add calibrated
row-readout duration/direction and row-time pose compensation (or demonstrate a
conservative angular readout bound under the selected slow rotation speed). Do not
change the shutter declaration to global merely to bypass this gate.

The optical sync bridge maps frame PTS clocks; it does not by itself correct rolling
shutter, exposure blur, autofocus breathing, electronic stabilization, lens switching,
or camera-specific image warping. Those need per-device metadata/validation.

## Suspended fabric constraints

A hanger rotation does not guarantee that fabric is rigid. Sleeves and hems can lag,
flutter, or twist relative to the hanger. The current reconstruction assumes a rigid
object pose derived from the encoder. Before accepting a scan, inspect repeated passes
and use garment-feature motion / silhouette consistency to quantify swing. If the
garment deforms materially during the scan, reject the rigid scan or use a non-rigid
capture/reconstruction model.

## Verification boundary

Unit tests use synthetic clocks, timestamps, angles, and file paths. They validate
clock fitting, skew rejection, angle interpolation, and manifest assembly only.
They are not camera footage, physical encoder, hanger, or garment acceptance tests.
