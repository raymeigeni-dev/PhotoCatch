# PhotoCatch cloud reconstruction adapter

## Status and honesty

The code provides a provider-neutral HTTP adapter seam. It does **not** claim to connect directly to RealityCapture or any cloud service until a compatible gateway and credentials are configured. RealityCapture deployments may require a provider-specific workflow, licensing, storage setup, and credentials.

## Required gateway contract

Set these environment variables in the backend process:

- `PHOTOCATCH_CLOUD_API_BASE_URL=https://your-gateway.example/api/`
- `PHOTOCATCH_CLOUD_API_TOKEN=...`
- Optional `PHOTOCATCH_CLOUD_PROVIDER=realitycapture` (label only; this does not create compatibility).

The configured gateway must implement:

1. `POST /jobs`: multipart field `video`; return JSON with non-empty `job_id`.
2. `GET /jobs/{job_id}`: return JSON status `queued`, `running`, `succeeded`, or `failed`.
3. `GET /jobs/{job_id}/result`: return a JSON object containing an `assets` list or object. The API exposes this manifest; the assets themselves are not downloaded to the Mac automatically yet.

API endpoints:
- `GET /api/reconstruction/engines`: reports local tool availability and cloud configuration.
- `POST /api/video/reconstruct/cloud`: submits a video and returns the remote job ID.
- `GET /api/video/reconstruct/cloud/<job_id>`: polls remote status.
- `GET /api/video/reconstruct/cloud/<job_id>/result`: fetches the provider result manifest; it does not download remote assets to local storage.

## Local paths

- OpenMVS: local CPU dense reconstruction, mesh reconstruction, optional refinement, and TextureMesh UV bake when those binaries are installed. The API reports whether texture bake actually produced assets.
- Apple Object Capture: macOS-native helper, using the existing `/api/video/reconstruct/apple` route; the helper must be built and real input-tested on the target Mac.

## Texture and quality

A geometrically valid PLY is not proof of photo-realistic texture. Review the response `texturing.success`, the OBJ/MTL/texture files, and a visual preview. A cloud job submission is not a successful reconstruction; poll until `succeeded` and verify the result separately.
