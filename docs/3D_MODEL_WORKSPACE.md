# PhotoCatch 3D Model Workspace

## Purpose

`frontend/3d-workspace.html` is a browser-based, local-first workspace for inspecting and assembling multiple 3D assets. It is separate from the video reconstruction test bench and does not claim to improve or repair scan quality automatically.

## Launch

From the repository root, start a local static server:

```bash
python3 -m http.server 8000
```

Open `http://127.0.0.1:8000/frontend/3d-workspace.html`.

The workspace imports Three.js modules from jsDelivr, so the first launch requires browser network access to that CDN. Model files are read in the browser and are not uploaded to the PhotoCatch backend.

## Supported import and export

- Import: GLB, glTF, OBJ, STL, PLY, USDZ/USD/USDA/USDC (USD loader via Three.js r180).
- Export: GLB scene assembly, plus a separate JSON scene manifest containing object names and transforms.
- The JSON manifest does not contain geometry. Export GLB to preserve the assembled model geometry and supported materials.
- A glTF file that references external texture/image files may not load correctly when imported as a single standalone file. Prefer self-contained GLB when possible.
- FBX, 3MF and DAE are not implemented by this initial workspace. USDZ files containing binary USDC and large texture payloads can be memory-intensive; material/texture fidelity, including EXR displacement maps, must be checked after import.

## Editing features

- Orbit, pan and zoom the 3D view; select imported objects in the scene or object list.
- Translate, rotate and scale with a transform gizmo, or enter exact position/rotation/scale values in the inspector.
- Duplicate/delete objects, toggle visibility, focus selected/all visible objects, reset transforms, center an object, and place the selected object's bounding-box bottom on the ground plane.
- Align other visible objects to the active object's bounding-box center along X/Y/Z; distribute visible objects approximately along X.
- The grid and axes are editor helpers and are excluded from the GLB export.

## Important limitations

- Alignment is based on axis-aligned bounding-box centers, not semantic part recognition, mesh surface fitting, CAD constraints, contact detection, or automatic mating. Users must visually inspect and adjust assemblies.
- Imported models retain their source units and coordinate conventions; the workspace does not infer whether units are meters, millimeters, or centimeters.
- This initial version does not provide boolean unions, watertight mesh repair, UV editing, material painting, rigging, parametric CAD, or reliable round-trip editing of arbitrary CAD formats.
- GLB export and actual browser/WebGL interaction still need manual testing on the target Mac. A successful page load or file import is not proof of manufacturing-grade geometry.
