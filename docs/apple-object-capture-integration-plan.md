# PhotoCatch: Apple RealityKit Object Capture integration plan

Status: proposal/implementation plan; **not yet runtime-verified on the user's Mac or iPhone**.

## Decision

Use Apple's RealityKit Object Capture as a first-class reconstruction backend, while keeping COLMAP/OpenMVS as a selectable fallback for existing workflows. Do not silently replace the existing backend until a real chair test demonstrates a better result.

- **macOS reconstruction:** `PhotogrammetrySession` consumes a directory of overlapping photographs and can write a USDZ model. It reports `isSupported`; PhotoCatch must check this at runtime rather than assume every Mac is supported.
- **iPhone capture:** Apple's `ObjectCaptureSession` + `ObjectCaptureView` provide a guided capture workflow on supported physical LiDAR devices (Apple's sample lists LiDAR, A14 or later, and iOS/iPadOS 18+). Capture and reconstruction are separate phases.
- **Input constraint:** a MOV file is not directly a `PhotogrammetrySession` image directory. Video import must extract well-spaced, sharp frames, reject duplicates/blur, and save them into a job-local image directory first. A video-derived frame set may be worse than photos taken around the object.
- **Output constraint:** USDZ is the first native output target because it can carry a renderable asset with materials. Verify texture/material content and model quality after export; file extension alone is not acceptance.

Official references:
- https://developer.apple.com/documentation/RealityKit/PhotogrammetrySession
- https://developer.apple.com/documentation/RealityKit/creating-3d-objects-from-photographs
- https://developer.apple.com/documentation/RealityKit/ObjectCaptureSession
- https://developer.apple.com/documentation/RealityKit/scanning-objects-using-object-capture

## Implementation sequence

### Phase 0 — capability probe (required before enabling)
1. Add a native Swift command-line helper under `native/apple-object-capture/`.
2. At startup, check `PhotogrammetrySession.isSupported`; return a machine-readable unsupported result and non-zero exit code if false.
3. Record macOS version, architecture, supported status, input image count, processing status, elapsed time, output size, and errors. Never log image pixels or upload media.
4. Build and run the helper on the target Mac. A source file or green CI is not evidence that this machine supports reconstruction.

### Phase 1 — image preparation
1. Reuse PhotoCatch's existing video upload/job boundary.
2. Extract a configurable set of temporally distributed frames into an isolated job directory (never overwrite the uploaded original).
3. Reject near-duplicates and low-sharpness frames; retain a diagnostic contact sheet and a JSON manifest.
4. Keep image count bounded and report whether the capture has enough viewpoints. The threshold must be calibrated against real chair footage, not presented as a universal guarantee.

### Phase 2 — native reconstruction adapter
1. Add an adapter that invokes the helper with explicit input/output paths and a timeout.
2. Use an explicit backend setting: `apple_object_capture`, `colmap_openmvs`, or `auto`. Initially `auto` must choose Apple only when the helper is installed and reports supported; otherwise it may use the existing backend with the selected fallback clearly reported.
3. Preserve subprocess stdout/stderr, exit code, elapsed time, and generated files in the job diagnostics.
4. Return a distinct error when Apple reconstruction is unsupported or fails; do not label a sparse cloud, silhouette extrusion, or empty file as a successful textured model.

### Phase 3 — asset validation and UI
1. Validate file existence/size and parse the USDZ archive; record material/texture evidence when it can be inspected reliably.
2. Apply the existing topology/fragmentation gates to formats that can be inspected, and add USDZ-specific checks rather than assuming PLY checks apply unchanged.
3. Show the backend used, source-frame count, model preview, texture/material status, and all quality warnings in the result panel.
4. Preserve PLY export for the legacy path. Treat USDZ as the Apple-native deliverable and add conversion only if a reliable local converter is available.

### Phase 4 — iPhone LiDAR capture (separate deliverable)
1. Add a small iOS companion target based on Apple's Object Capture sample APIs.
2. Capture guided multi-angle images with `ObjectCaptureSession`; export the image set and metadata to the Mac/local PhotoCatch job.
3. Do not claim LiDAR alone reconstructs fine fabric, thin chair legs, reflective surfaces, or hidden geometry. Test those failure modes explicitly.
4. Keep this out of the first macOS adapter PR unless an iOS app target and signing/build pipeline already exist.

## Acceptance gates

- Unit tests cover unsupported hardware, helper missing, timeout, non-zero exit, absent/empty output, and path safety.
- Input frames are written only beneath a per-job working directory; original video checksum remains unchanged.
- Native helper builds with the repository's documented Xcode/Swift toolchain.
- On the user's Mac, `PhotogrammetrySession.isSupported == true` is recorded before claiming Apple reconstruction works.
- Reconstruct the same `IMG_0096.MOV` with the current COLMAP/OpenMVS path and the Apple path using equivalent input frames. Compare visual fidelity to the chair, connected components, holes, geometry completeness, material/texture evidence, runtime, and output size.
- No backend is marked production-ready until real-video comparison passes. Automated tests alone are insufficient.

## Current scope boundary

This document records the proposed route and acceptance contract. The existing PhotoCatch backend has **not** yet been switched to Apple Object Capture; the native helper and adapter still require implementation, build, and real-device verification.
