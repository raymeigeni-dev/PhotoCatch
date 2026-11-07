# Independent reference dataset and reproducible measurement baseline

**Status: NOT TESTED / NOT ACCEPTED.** This protocol is a data-acquisition and evaluation contract. No physical reference garment, body, calibrated scan, pattern, or independently measured result is being claimed as collected by this commit.

## 1. Purpose and independence rule

The benchmark compares Voxel Reality outputs with ground truth acquired independently of the Voxel Reality reconstruction and inference pipeline. The system under test must not create, edit, register, clean, or choose the reference measurements used to score itself.

A reference is independent only when:
- it comes from a separately calibrated instrument or documented manual metrology procedure;
- the reference operator does not use the Voxel Reality prediction to place or adjust reference landmarks;
- raw reference data are retained before alignment or filtering;
- instrument identity, calibration certificate/verification, operator, date, environment, uncertainty and procedure are recorded;
- the reference data are held out from model training, tuning, threshold selection and manual correction.

A reference scan may be rigidly registered for evaluation only with a predeclared registration method and independently defined fiducials. Report results both before and after any allowed registration. Do not use non-rigid registration to conceal shape error.

## 2. Reference cohorts to acquire

Acquire and track these as separate cohorts. Do not substitute synthetic geometry or rendered people for physical references.

| Cohort | Physical reference | Required raw evidence | What it validates |
|---|---|---|---|
| R0 — metrology / rig | Traceably measured scale bars and calibration artefacts spanning the capture volume; independent angle reference for encoder | Calibration certificates or documented traceable checks, raw target images, independent target coordinates, encoder reference log | Metric scale, camera calibration, angle and timing |
| R1 — rigid geometry | Physical rigid artefacts with independently measured dimensions and independently scanned surfaces, including concave and convex features | Original images, independent scan point cloud/mesh, measured dimensions, scale artefact record | Capture and 3D geometry before fabric ambiguity is introduced |
| R2 — garment surface | Real garments scanned independently in documented states; include front/back/inside/flat-lay and suspended orientations where possible | Original multi-camera videos, masks, independent reference scans, garment ID, state, material and size metadata | Metric outer-surface reconstruction and occlusion |
| R3 — garment construction | Physical paper/CAD patterns or panels measured on a calibrated digitizer/table; seams, darts, pleats, gathers and design folds labelled by qualified patternmaking reviewers | Original pattern files/images, panel coordinates, seam graph, construction notes, reviewer labels and adjudication | Pattern topology, panel dimensions, construction and design-fold classification |
| R4 — body | Human subjects or calibrated anthropometric forms measured independently; metric body scan plus standardized tape measurements | Consent/usage record where human subjects are involved, raw scan, tape sheet, landmark definitions, operator and repeatability readings | Body dimensions and uncertainty |
| R5 — physical try-on | Same physical garment worn by the same independently measured subject/form in a documented pose; independent scan of the actual worn state | Garment/body IDs linking R2/R3/R4, pose protocol, independent worn scan, fabric test data, pressure/contact evidence if claimed | Pattern-aware fit and cloth simulation |

R0 and R1 establish metrology and geometry baselines before attempting complex cloth. R2–R5 are required before claims about garment structure, body measurement or actual try-on accuracy.

## 3. Physical acquisition procedure

### 3.1 Rig and scale
1. Verify each camera/lens configuration independently; lock focus, zoom, stabilization, exposure and image mode.
2. Measure intrinsics, distortion and extrinsics using a calibrated target at multiple depths and positions across the complete capture volume.
3. Place at least one traceable length artefact in the garment capture volume and capture it at multiple orientations and locations.
4. Compare the encoder against an independent angular reference over the complete rotation range and at the actual operating speeds.
5. Measure trigger/exposure timing independently. Retain raw trigger, exposure and encoder logs.
6. Repeat calibration at the start and end of each acquisition session. If drift exceeds the pre-registered calibration limit, quarantine that session.

### 3.2 Garment reference
1. Assign a persistent physical garment ID. Record category, labeled size, measured fabric composition if known, weave/knit, lining, closures and construction details.
2. Capture front, back, left, right, inside and flat-lay evidence. Include close-ups of seams, darts, pleats, gathers, tucks, hems and pressed creases.
3. Acquire an independent metric 3D scan of the garment in a documented state. Record support/contact points, gravity direction, orientation, tension and whether the garment is relaxed, suspended or worn.
4. Repeat the garment capture after removing and remounting it. A repeated capture is a new session, not a duplicate frame.
5. Have two qualified reviewers independently label panel boundaries, seam paths, construction features and fold classes. Resolve disagreements through a documented adjudication; retain both original labels.
6. Keep hanger-, gravity-, pose- and motion-dependent folds in the transient-state annotations. Do not label them as design folds merely because they appear in multiple adjacent frames.

### 3.3 Body reference
1. Use a documented neutral stance, landmark definitions, minimal/known clothing and a controlled camera setup.
2. Acquire independent front/side/back metric scans and standardized tape measurements. Record repeated tape readings by independent operators where possible.
3. Record each dimension separately with unit, landmark definition, operator, instrument, repeat readings and uncertainty. Never infer an unmeasured circumference from a front photograph.
4. For human subjects, retain consent and access controls. Use pseudonymous subject IDs; do not commit identifiable raw body imagery to a public repository.

### 3.4 Physical try-on
1. Link the exact garment ID, body ID, garment size, fabric condition and pose.
2. Capture the physical garment on the measured body/form and independently scan the worn state.
3. Repeat after removing and redressing the garment to measure real-world repeatability.
4. Compare virtual and physical states using the same coordinate convention, pose and explicitly allowed rigid alignment. Record strain, penetration, gaps, contact, seam displacement and landmark errors where the relevant sensors/reference methods exist.

## 4. Immutable dataset manifest

Each physical item and capture session must have a manifest. Store raw files in controlled object storage or an access-controlled dataset location; do not put private human scans in this repository. The manifest must include at least:

```json
{
  "schema_version": 1,
  "dataset_id": "assigned-after-physical-acquisition",
  "cohort": "R0|R1|R2|R3|R4|R5",
  "split": "development|validation|blind_test",
  "physical_item_id": "pseudonymous-stable-id",
  "session_id": "unique-acquisition-session",
  "acquired_at_utc": "ISO-8601 timestamp",
  "operator_id": "pseudonymous-operator-id",
  "protocol_revision": "immutable-protocol-revision",
  "instrument_records": [
    {
      "instrument_id": "manufacturer-model-serial-or-controlled-id",
      "calibration_record_id": "certificate-or-verification-id",
      "calibration_valid_at_acquisition": true,
      "stated_uncertainty": 0.0,
      "unit": "mm"
    }
  ],
  "files": [
    {
      "role": "raw_capture|reference_scan|pattern|tape_measurements|encoder_log|calibration",
      "relative_path": "controlled-storage-object-key",
      "sha256": "64-character-content-hash",
      "unit": "mm",
      "coordinate_frame": "documented-frame-id"
    }
  ],
  "measurements": [
    {
      "name": "example_dimension_name",
      "value": 0.0,
      "unit": "mm",
      "method": "independent-reference-method",
      "uncertainty": 0.0,
      "operator_id": "pseudonymous-operator-id"
    }
  ],
  "exclusions": [],
  "notes": "No personally identifying data"
}
```

The JSON above is a schema example only; its placeholder IDs and zero values are not observations. A record is not benchmark evidence until every referenced file exists, every SHA-256 matches, units/coordinate frames are explicit, and instrument records are verified.

Never overwrite raw evidence. Corrections create a new manifest revision with a link to the superseded revision and a reason. Hash the raw data, calibration, labels, model, code revision, configuration, predictions and final report.

## 5. Dataset splitting and leakage prevention

- Split by physical garment ID, person/form ID and acquisition session before extracting frames or patches.
- All frames from one physical garment/person/session remain in one split.
- A blind test item/person must not appear in training, feature selection, calibration tuning, threshold setting or manual post-processing.
- Keep blind reference files access-controlled until predictions and the evaluation configuration are frozen.
- Publish counts by garment construction, fabric type, size, body-size subgroup, session and operator.
- Report all exclusions and failed acquisitions. Do not silently remove difficult samples.

## 6. Metrics and frozen thresholds

For each gate, preregister a numeric maximum error (or minimum score where appropriate), units, sample count, subgroup coverage and confidence/reporting method before opening the blind test references.

| Gate | Required metrics | Threshold status |
|---|---|---|
| R0 capture | Reprojection RMS/P95 (px), scale MAE/P95 (mm and %), encoder angle error (deg), synchronization skew (ms) | NOT REGISTERED |
| R1/R2 geometry | Symmetric surface distance MAE/P95/max (mm), dimensional MAE/P95 (mm), silhouette IoU, boundary P95 (mm), coverage (%) | NOT REGISTERED |
| R3 construction | Panel/seam precision/recall/F1, seam location error (mm), panel outline/area error, fold-class precision/recall/F1 and abstention rate | NOT REGISTERED |
| R4 body | Per-measurement bias/MAE/RMSE/P95 (mm), repeatability (mm), invalid/abstained rate | NOT REGISTERED |
| R5 fit | Worn-surface MAE/P95 (mm), landmark/seam displacement (mm), penetration/gap/contact metrics, calibrated fabric strain error (%) | NOT REGISTERED |
| Repeatability | Between-session variance and subgroup pass/fail rates | NOT REGISTERED |

No universal numerical tolerance is invented in this protocol. The numeric limits must be approved and frozen in a separate versioned preregistration for each claimed garment class and capture configuration, using product requirements and instrument capability. They must be frozen before blind-test references are revealed. Limits may not be widened after results are seen.

A gate is:
- **PASS** only if every required metric and subgroup satisfies its frozen limit, sample requirements are met, independent reference uncertainty is acceptable under the protocol, and the run is reproducible.
- **FAIL** if any required metric exceeds its frozen limit.
- **NOT TESTED** if the physical reference, a threshold, a minimum sample count, an instrument record or required evidence is missing.

Until a threshold is preregistered, that gate cannot pass. A low error on a synthetic fixture does not change this status.

## 7. Reproducible metric tooling in this branch

`backend/rotational_capture/benchmark.py` currently provides:
- signed-error summaries: bias, MAE, RMSE, P95 absolute error and maximum absolute error;
- symmetric sampled point-cloud nearest-neighbour distances, including both directions;
- preregistered maximum-error gate evaluation with PASS / FAIL / NOT_TESTED semantics.

The point-cloud function is a sampled point-to-point nearest-neighbour metric, not exact point-to-triangle mesh distance. Sampling density and reference scan method must be recorded. Additional metric families (calibration, silhouette, topology, fold classification, anthropometry and physical fit) are not yet implemented in this module.

The unit tests use synthetic arrays to verify calculations and gate semantics only. They do not count as independent physical reference data or accuracy validation.

## 8. Current evidence ledger

| Evidence | Current state |
|---|---|
| Physical calibration artefact measurements | NOT ACQUIRED |
| Independent rigid-artefact reference scan | NOT ACQUIRED |
| Physical garment reference cohort | NOT ACQUIRED |
| Expert-verified patterns/seam/fold labels | NOT ACQUIRED |
| Independent body scans and tape measurements | NOT ACQUIRED |
| Matched physical try-on scans | NOT ACQUIRED |
| Per-gate numeric preregistration | NOT REGISTERED |
| Synthetic metric unit tests | Added; CI result pending for this commit |
| Physical accuracy acceptance | NOT TESTED |

This ledger is intentionally conservative. Do not change a row to PASS based on implementation progress, documentation, synthetic tests or visual inspection.
