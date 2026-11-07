# Garment reconstruction and measurement-driven virtual fitting

## Product requirement

Voxel Reality must not treat every wrinkle visible in a hanging video as part of the garment design. The required output is a **design-structure garment model** that can be fitted to a different measured body and then physically draped. The captured hanging appearance is evidence about the garment, not the final garment surface.

The pipeline has two separate latent states:

1. **Garment design state**: panel boundaries, seams, darts, pleats, gathers, intended ease, hems, collars, cuffs, closures, lining/construction where observable, and material constitutive properties.
2. **Capture/wear state**: gravity folds, hanger deformation, temporary compression, sleeve/hem swing, camera/lighting artefacts, pose-dependent folds and occlusions.

Only design-state geometry and intentionally designed folds should be preserved as garment structure. Capture/wear-state folds must be estimated as nuisance deformation and removed or marginalized before fitting. After fitting, new natural folds are generated from the target body, pose, gravity, contact and fabric simulation.

## 1. Why a raw video surface is not the pattern

A single 3D drape does not uniquely determine the 2D sewing pattern. Different panel shapes, seam placement, darts, fabric stretch, lining, and internal construction can produce very similar observed outer surfaces. Hidden surfaces and covered seams are not observable from a finite set of camera views.

Therefore, the system must not claim to recover an exact manufacturing pattern from video alone. It should return:
- measured visible 3D surface with uncertainty;
- detected seam/panel/edge hypotheses with confidence;
- design-fold hypotheses separated from transient folds;
- garment measurements and known construction facts;
- alternative plausible pattern parameterizations where the evidence is ambiguous;
- explicit missing-evidence flags.

Where exact pattern recovery is required, collect additional evidence: flat-lay front/back/inside images, seam and label close-ups, a relaxed garment scan, manual tape measurements, known size label, or the original pattern/CAD. These are evidence inputs, not optional magic inference.

## 2. Garment capture and reconstruction

### 2.1 Geometry acquisition
Use synchronized calibrated multi-view video and encoder poses to reconstruct a metric, colorized outer surface. Require:
- measured camera intrinsics, distortion and extrinsics;
- per-mode shutter/readout calibration and original PTS;
- measured encoder angle and timestamp;
- stable exposure/focus/zoom and documented stabilization;
- verified foreground masks and scale reference;
- multi-view reprojection and silhouette residual reports.

The visual hull is only a conservative silhouette-bounded volume. It cannot recover concavities or unseen internal surfaces by itself. For detailed garment shape, add calibrated multi-view stereo / depth evidence and fuse it with the visual hull. Do not describe a visual hull as a fully accurate mesh.

### 2.2 Design folds versus transient folds
Build a garment-specific evidence graph over time and views:
- **Design fold candidates**: repeat at the same garment-relative location across independent captures, remain spatially anchored to panel/seam landmarks, show consistent fold direction, and are supported by construction cues (pleat edges, stitching, darts, gathers, pressed creases).
- **Transient fold candidates**: change with gravity/orientation, hanger contact, sleeve swing, motion, local compression or capture sequence; lack seam/construction support; or disappear in relaxed/flat evidence.
- **Unknown**: insufficient evidence. Preserve the uncertainty and request more views/evidence rather than silently classifying.

A fold classifier must not rely on one frame or on temporal persistence alone: a gravity fold can persist during a short turn, while a designed fold can be partly occluded. Use repeated captures in multiple orientations, seam/panel topology and, where possible, flat-lay/inside evidence. The output should contain a per-fold label, confidence, supporting observations and provenance.

### 2.3 Canonical garment representation
Store separate layers:
- canonical panel/mesh geometry in garment-local coordinates;
- panel boundaries and seam graph;
- design pleat/gather/dart constraints;
- material zones and measured fabric parameters;
- transient capture deformation fields, retained only as evidence;
- texture/color maps and surface details;
- measurement table with units and uncertainty.

The canonical mesh must not bake transient hanger/gravity wrinkles into its rest shape. The rest shape is a pattern- and construction-constrained garment state, not a smoothed copy of one draped frame. Smoothing alone is unacceptable because it can erase intended pleats, darts and gathers.

## 3. Learn garment construction and patternmaking as explicit constraints

The model should encode actual garment-making knowledge rather than learn only pixel-to-mesh correlations:
- body measurements and ease allowances;
- pattern panels and grain direction;
- seam correspondence and stitch length/allowance;
- darts, pleats, gathers, tucks and shaping;
- collar, sleeve-cap, armhole, cuff, waistband and hem construction;
- fabric warp/weft stretch, shear, bending and thickness;
- grading rules and size increments.

A pattern representation should be parameterized by panel outlines, seam graph, darts/pleats, and construction constraints. The fitting stage changes body-dependent dimensions and ease while preserving the design intent and manufacturing constraints. It must not non-uniformly stretch an arbitrary finished surface without respecting seams and panel construction.

Training data must pair 2D patterns or panel geometry, sewing/construction labels, fabric properties, measured 3D garment scans and known body measurements. Without paired ground truth, a learned model can provide hypotheses but cannot establish exact pattern truth.

## 4. Human body measurement from imagery

A portrait alone is not a reliable source of absolute body measurements. Perspective, camera focal length, distance, pose, clothing, occlusion, body shape and image resizing all affect apparent dimensions. A single front image cannot reveal depth or circumference.

For accurate measurements, require a metric capture protocol:
- front, side and back views or a calibrated multi-camera/video capture;
- a known scale reference or calibrated depth/metric camera;
- controlled neutral pose, arms slightly separated from torso, feet positioned consistently;
- minimal/known clothing and clear visibility of landmarks;
- camera calibration and distortion correction;
- quality checks for occlusion, pose and scale.

Estimate a parametric 3D body mesh from the views, then fit measured landmarks and circumference constraints. Report each measurement with uncertainty and source evidence. If scale/depth is absent, report normalized proportions or an estimate range only; never label them as exact centimeters.

Required body outputs include stature, shoulder breadth, chest/bust, under-bust where relevant, waist, hip/seat, neck, arm length, upper-arm, wrist, inseam, outseam and torso lengths, with sex- and garment-category-appropriate measurement definitions. The system must allow manual tape-measure overrides and retain their provenance.

## 5. Pattern-aware fitting and cloth simulation

The fit process is not a 2D texture overlay and not a simple affine scaling of a mesh.

1. Build/validate a metric body mesh and body measurement vector.
2. Select a canonical garment pattern/mesh and its measured design parameters.
3. Compute target panel dimensions using body measurements plus explicit garment ease and grading rules.
4. Preserve seam correspondence, grain direction, darts, pleats, gathers and construction.
5. Initialize the garment around the body using semantic landmarks.
6. Simulate gravity, body collision, garment self-collision, seam constraints, anisotropic stretch/shear/bending, thickness and friction.
7. Separate designed folds from newly generated fit-dependent folds.
8. Evaluate fit using negative ease/strain, pressure/contact proxies, gap/penetration, seam stress, landmark alignment and silhouette error.
9. Render the resulting 3D garment and body together; support pose updates and reduced-order real-time simulation.

A cloth solver interface or a mesh alignment routine is not proof that physical fitting works. Production acceptance requires a real solver and measured validation against physical garments on known body forms.

## 6. Accuracy contract

Do not promise “100% accurate” from unconstrained video. Use evidence-based quality levels:

- **Level A — metric capture**: calibrated camera rig, measured scale, encoder, shutter timing and verified masks.
- **Level B — garment geometry**: multi-view reconstruction with measured reprojection/silhouette error and documented occluded regions.
- **Level C — design structure**: verified seams/panels/design folds, with unresolved hypotheses explicitly marked.
- **Level D — body measurements**: metric body capture cross-checked against tape measurements.
- **Level E — virtual fit**: pattern-aware solver validated against physical try-ons and known garment/body measurements.

Every output should include per-stage confidence, uncertainty and failure flags. A lower evidence level cannot be silently promoted to a higher one. For example, a single portrait may produce a body-shape estimate, not verified circumference measurements; a hanging scan may produce visible surface geometry, not a uniquely proven flat pattern.

## 7. Quantitative acceptance

Before claiming accurate reconstruction or fit, define and measure:
- camera reprojection error and independent calibration residual;
- metric scale error against a traceable ruler;
- multi-view silhouette intersection-over-union and boundary distance;
- mesh-to-reference surface distance (median, P95, maximum) on a scan with ground truth;
- seam/panel landmark precision and recall;
- design-fold classification precision/recall against expert labels;
- body measurement error against tape measurements per dimension;
- garment ease/strain and body-penetration statistics;
- fit silhouette and landmark error against physical try-on scans;
- repeatability across repeated captures and multiple garment/body sizes.

Acceptance thresholds must be set per garment class and capture protocol from a validation dataset. Never invent universal thresholds or report synthetic unit tests as physical accuracy evidence.

## 8. Implementation order

1. Preserve current capture and synchronization work as the acquisition layer.
2. Add metric multi-view geometry quality reports and an explicit uncertainty/occlusion model.
3. Add garment surface/edge/seam feature extraction and panel topology representation.
4. Add design-fold versus transient-fold classification using repeated multi-orientation captures and construction evidence.
5. Add patternmaking data model and body-measurement schema with units/provenance/uncertainty.
6. Add calibrated multi-view body measurement and tape-measure cross-check workflow.
7. Add pattern-aware garment grading and seam-constrained fitting.
8. Integrate a production cloth solver with collision and material calibration.
9. Validate against physical garments and bodies before any production-accuracy claim.

The target is a physically meaningful, pattern-aware 3D try-on system. It is not an image-to-image clothing filter.
