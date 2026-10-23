# Mesh attribute inheritance contract

This contract is the required behavior for topology-editing work in PhotoCatch. The current position/face-only core does **not** yet satisfy this contract; the workspace must keep its fail-closed guard until the implementation and tests do.

## Attribute domains

- **Vertex domain**: position, vertex color/weights and other values attached to a geometric vertex.
- **Face domain**: material index, face labels and face-level custom values.
- **Corner/loop domain**: UV coordinates, split normals, tangent data and values that can differ at each face corner. UVs must never be collapsed to one value per welded position.
- **Edge domain**: crease/sharpness and other edge-associated values, where present.
- **Object domain**: transforms, parent links, object identity and material-slot order.

Every mesh edit must return both the edited mesh and a structured attribute report: preserved, interpolated, inherited, regenerated, dropped, or unsupported. Silent loss is a test failure.

## Required inheritance rules

| Operation | Required rule |
|---|---|
| Move vertex | Preserve all attributes and corner identity; only position changes. |
| Delete face | Remove that face's face-domain values and its corner values; retain values on surviving faces. |
| Extrude face | Cap inherits source face material/face attributes; new side faces inherit from the source boundary face by a documented deterministic rule. New vertex attributes interpolate from source vertices. Corner UVs are derived per source corner and extrusion side; seams remain split. |
| Merge vertices | Merge only when position tolerance **and all merge-critical discontinuities** are compatible. Otherwise preserve separate vertices. Corner attributes remain per-corner regardless of vertex merge. Conflicting vertex/edge custom values must be reported, never silently averaged. |
| Rebuild/triangulate face | Each generated face inherits the source face material and face attributes. Corner values are copied/interpolated using the generated corner's barycentric coordinates in the source face. |
| Recalculate normals | Recompute geometric normals only when explicitly requested. Preserve or regenerate split/corner normals according to a declared policy; report regenerated values. |
| Unsupported custom attribute | Abort the destructive operation by default, or require explicit user confirmation to drop it; emit attribute name, domain and reason. |

## Repair acceptance and self-intersections

Before/after reports must compare per object: vertex/edge/face counts, boundary edges, non-manifold edges, degenerate/zero-area faces, duplicate faces, loose vertices/edges, and material/UV/custom-attribute preservation. Metrics are not all defects in every asset: boundary edges may be intentional, and a lower non-manifold count does not prove that self-intersections decreased.

Self-intersection is a separate metric. A detector must use triangle-triangle intersection tests with spatial acceleration (for example, BVH broad-phase plus robust triangle-triangle narrow-phase), ignore only pairs that are adjacent by a shared mesh edge/vertex according to the declared policy, and report candidate pairs, confirmed pairs, coplanar/near-degenerate ambiguities and tolerance. The report must say `not_run` or `unsupported` until such a detector actually runs. It must not infer an intersection count from edge manifoldness.

## Acceptance gates

1. GLB fixture round-trip preserves per-corner UV seam values, material slots and per-face material indices, object hierarchy, and transforms within tolerance.
2. Tests exercise extrusion, face deletion, vertex merge, and face rebuild on seams and multiple material groups.
3. Each operation checks all supported attribute domains and asserts explicit reporting for unsupported attributes.
4. Blender repair integration compares each metric before/after and independently runs the self-intersection detector; missing detector results fail acceptance rather than defaulting to zero.
5. Run the Blender integration workflow and retain its real CI result before calling the repair path verified.
