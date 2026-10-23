#!/usr/bin/env python3
"""Conservative Blender/BMesh repair adapter for PhotoCatch.

Run with Blender's bundled Python, not system Python:
  blender --background --python tools/blender_repair.py -- input.glb output.glb

This is deliberately conservative and reports each operation. It is NOT a
mathematical guarantee that arbitrary self-intersections or invalid shells can
be repaired. Always keep the source file and inspect the output.
"""
import bpy
import bmesh
import json
import os
import sys
from mathutils import Vector
from mesh_intersections import count_self_intersections


def arguments():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) != 2:
        raise SystemExit("Usage: blender --background --python tools/blender_repair.py -- INPUT OUTPUT")
    return os.path.abspath(argv[0]), os.path.abspath(argv[1])


def import_scene(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        raise ValueError("Unsupported repair input format: " + ext)


def export_scene(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in {".glb", ".gltf"}:
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB" if ext == ".glb" else "GLTF_SEPARATE")
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_export"):
            bpy.ops.wm.obj_export(filepath=path, export_materials=True)
        else:
            bpy.ops.export_scene.obj(filepath=path, use_materials=True)
    elif ext == ".ply":
        bpy.ops.wm.ply_export(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_export(filepath=path)
    else:
        raise ValueError("Unsupported repair output format: " + ext)


def repair_mesh_object(obj, report, merge_distance=1e-5, hole_sides=0):
    if obj.type != "MESH":
        return
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    before = {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
        "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
        "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
    }
    item = {"object": obj.name, "before": before, "operations": []}
    # Independent triangle-triangle count on the original topology.
    item["before"]["self_intersections"] = count_self_intersections(
        [tuple(v.co) for v in bm.verts], [tuple(v.index for v in f.verts) for f in bm.faces]
    )

    # Remove only near-coincident vertices within a small explicit tolerance.
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=merge_distance)
    item["operations"].append({"name": "merge_nearby_vertices", "distance": merge_distance})

    # Delete zero-area/degenerate geometry; do not automatically delete loose
    # geometry or aggressively dissolve boundaries.
    degenerate = [f for f in bm.faces if f.calc_area() <= 1e-12]
    if degenerate:
        bmesh.ops.delete(bm, geom=degenerate, context="FACES")
    item["operations"].append({"name": "remove_zero_area_faces", "count": len(degenerate)})

    # Recalculate consistent normals on connected face regions.
    faces = list(bm.faces)
    if faces:
        bmesh.ops.recalc_face_normals(bm, faces=faces)
    item["operations"].append({"name": "recalculate_face_normals", "count": len(faces)})

    # Hole filling is opt-in: automatically filling every boundary can close
    # intentional openings. The default (0) leaves boundaries unchanged.
    filled = 0
    if hole_sides and hole_sides >= 3:
        boundary = [e for e in bm.edges if e.is_boundary]
        result = bmesh.ops.holes_fill(bm, edges=boundary, sides=hole_sides)
        filled = len(result.get("faces", []))
    item["operations"].append({"name": "fill_boundary_holes", "enabled": bool(hole_sides), "faces_added": filled})

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    bm_check = bmesh.new()
    bm_check.from_mesh(mesh)
    item["after"] = {
        "vertices": len(bm_check.verts),
        "edges": len(bm_check.edges),
        "faces": len(bm_check.faces),
        "boundary_edges": sum(1 for e in bm_check.edges if e.is_boundary),
        "non_manifold_edges": sum(1 for e in bm_check.edges if not e.is_manifold),
        "zero_area_faces": sum(1 for f in bm_check.faces if f.calc_area() <= 1e-12),
        "self_intersections": count_self_intersections(
            [tuple(v.co) for v in bm_check.verts], [tuple(v.index for v in f.verts) for f in bm_check.faces]
        ),
    }
    bm_check.free()
    report.append(item)


def main():
    input_path, output_path = arguments()
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)
    # Clear scene to avoid accidentally modifying unrelated startup objects.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    import_scene(input_path)
    report = []
    for obj in list(bpy.context.scene.objects):
        repair_mesh_object(obj, report)
    export_scene(output_path)
    sidecar = output_path + ".repair-report.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump({"input": input_path, "output": output_path, "objects": report,
                   "self_intersections": {"status": "completed", "count_before": sum(x["before"]["self_intersections"]["count"] for x in report), "count_after": sum(x["after"]["self_intersections"]["count"] for x in report), "count_delta": sum(x["after"]["self_intersections"]["count"] for x in report) - sum(x["before"]["self_intersections"]["count"] for x in report), "repair_status": "unresolved" if sum(x["after"]["self_intersections"]["count"] for x in report) > 0 else "clear", "per_object": [{"object": x["object"], "before": x["before"]["self_intersections"], "after": x["after"]["self_intersections"]} for x in report], "policy": "Independent AABB sweep and triangle-triangle narrow phase; shared-vertex adjacency excluded. Detector completion does not imply intersection repair."},
                   "warning": "Conservative BMesh operations; not a guarantee of repairing all self-intersections or arbitrary topology."},
                  f, ensure_ascii=False, indent=2)
    print("PHOTOCATCH_REPAIR_REPORT=" + json.dumps({"report": sidecar, "objects": len(report)}))


if __name__ == "__main__":
    main()
