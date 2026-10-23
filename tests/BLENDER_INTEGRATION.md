# Blender GLB round-trip integration test

This test is intentionally run by Blender's own Python runtime because it uses
`bpy` and the same import/export operators as the repair adapter.

From the repository root, run:

```sh
blender --background --python tests/blender_roundtrip_integration.py -- tools/blender_repair.py
```

The test creates a disposable GLB fixture with a UV layer containing per-loop
coordinates, two material slots and face assignments, two mesh objects, a
parent-child relationship, non-identity transforms, and a zero-area face. It
runs the production adapter in a separate Blender process, imports the output,
and checks object presence, hierarchy, transforms, UV data, material slots and
material indices. A JSON repair report is required.

## What this test does not prove

- Blender/BMesh's current adapter does not implement a general self-intersection
  detector or a guaranteed self-intersection repair algorithm.
- A passing synthetic fixture does not establish compatibility with every GLB
  exporter or arbitrary production asset.
- Boundary and non-manifold edge counts are emitted by the adapter's report;
  this test currently checks that the report exists, not that every defect class
  has been eliminated. Some boundaries are intentional and should not be blindly
  filled.
- The adapter does not yet guarantee preservation of every possible glTF
  extension, skinning, morph target, custom attribute, animation or instancing.

Do not interpret process exit code 0 alone as proof of successful repair. Inspect
the before/after metrics and review any remaining defects.
