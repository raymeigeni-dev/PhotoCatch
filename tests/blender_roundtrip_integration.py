#!/usr/bin/env python3
"""Blender end-to-end GLB round-trip test for PhotoCatch.

Run with:
  blender --background --python tests/blender_roundtrip_integration.py -- tools/blender_repair.py

Creates a synthetic scene containing a UV seam, two materials, two mesh objects,
a parent-child relationship, non-identity transforms, and a degenerate triangle.
Exports it to GLB, invokes the production repair adapter in a second Blender
process, reimports the result, and checks preservation plus repair metrics.
"""
import bpy
import json
import math
import os
import subprocess
import sys
import tempfile


def fail(message):
    raise AssertionError(message)


def args():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(values) != 1:
        fail("Usage: blender --background --python tests/blender_roundtrip_integration.py -- tools/blender_repair.py")
    return os.path.abspath(values[0])


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def make_fixture():
    mat_a = bpy.data.materials.new("Material_Red")
    mat_a.diffuse_color = (0.8, 0.05, 0.05, 1)
    mat_b = bpy.data.materials.new("Material_Blue")
    mat_b.diffuse_color = (0.05, 0.1, 0.8, 1)

    # Two triangles share positions but have distinct loop UVs at the shared
    # edge, deliberately exercising per-corner UV seam preservation.
    verts = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(2,1,0),(3,0,0),(4,0,0),(5,0,0),(6,0,0)]
    # Three distinct collinear vertices make a valid-index but zero-area face.
    faces = [(0,1,2),(0,2,3),(1,4,5),(1,5,2),(7,8,9)]
    mesh = bpy.data.meshes.new("UVSeamMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Fixture_Main", mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat_a)
    mesh.materials.append(mat_b)
    for poly in mesh.polygons:
        poly.material_index = 0 if poly.index < 2 else 1
    uv = mesh.uv_layers.new(name="UVMap")
    coords = [
      [(0,0),(1,0),(1,1)], [(0.2,0.2),(0.8,0.8),(0,1)],
      [(0,0),(1,0),(1,1)], [(0.1,0.1),(0.9,0.9),(0,1)],
      [(0,0),(0,0),(0,0)]
    ]
    for poly in mesh.polygons:
        for li, uvco in zip(poly.loop_indices, coords[poly.index]):
            uv.data[li].uv = uvco
    obj.location = (1.25, -2.0, 0.5)
    obj.rotation_euler = (0.1, 0.2, 0.3)
    obj.scale = (1.2, 0.9, 1.1)

    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0,0,2))
    child = bpy.context.object
    child.name = "Fixture_Child"
    child.parent = obj
    child.location = (0.4, 0.5, 1.5)
    child.rotation_euler = (0.0, 0.25, 0.0)
    child.data.name = "ChildMesh"
    return obj, child


def snapshot():
    scene_objects = {o.name: o for o in bpy.context.scene.objects}
    data = {}
    for name, obj in scene_objects.items():
        entry = {
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
            "location": tuple(round(float(v), 5) for v in obj.location),
            "rotation": tuple(round(float(v), 5) for v in obj.rotation_euler),
            "scale": tuple(round(float(v), 5) for v in obj.scale),
        }
        if obj.type == "MESH":
            mesh = obj.data
            entry["vertices"] = len(mesh.vertices)
            entry["polygons"] = len(mesh.polygons)
            entry["materials"] = [m.name for m in mesh.materials]
            entry["material_indices"] = sorted(set(p.material_index for p in mesh.polygons))
            entry["uv_layers"] = [layer.name for layer in mesh.uv_layers]
            entry["uv_loop_count"] = len(mesh.uv_layers[0].data) if mesh.uv_layers else 0
            entry["uv_samples"] = [
                tuple(round(float(v), 5) for v in mesh.uv_layers[0].data[i].uv)
                for i in range(min(12, len(mesh.uv_layers[0].data)))
            ] if mesh.uv_layers else []
            entry["degenerate_faces"] = sum(1 for p in mesh.polygons if p.area <= 1e-12)
        data[name] = entry
    return data


def main():
    repair_script = args()
    blender = bpy.app.binary_path
    with tempfile.TemporaryDirectory(prefix="photocatch-blender-it-") as tmp:
        source = os.path.join(tmp, "fixture.glb")
        output = os.path.join(tmp, "repaired.glb")
        clear_scene()
        make_fixture()
        bpy.ops.export_scene.gltf(filepath=source, export_format="GLB")
        pre = snapshot()
        assert "Fixture_Main" in pre and "Fixture_Child" in pre, "fixture objects missing"
        assert pre["Fixture_Main"]["uv_layers"], "fixture UV layer was not created"
        assert len(pre["Fixture_Main"]["materials"]) == 2, "fixture needs two material slots"
        assert pre["Fixture_Child"]["parent"] == "Fixture_Main", "fixture parent link missing"

        proc = subprocess.run(
            [blender, "--background", "--python", repair_script, "--", source, output],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300
        )
        if proc.returncode != 0 or not os.path.isfile(output):
            fail("repair subprocess failed; exit=%s output=%s" % (proc.returncode, proc.stdout[-6000:]))
        report_path = output + ".repair-report.json"
        if not os.path.isfile(report_path):
            fail("repair report sidecar missing")
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)

        clear_scene()
        bpy.ops.import_scene.gltf(filepath=output)
        post = snapshot()
        for name in ("Fixture_Main", "Fixture_Child"):
            assert name in post, "object lost after round-trip: " + name
            assert post[name]["type"] == pre[name]["type"], "object type changed: " + name
            assert post[name]["parent"] == pre[name]["parent"], "parent hierarchy changed: " + name
            for field in ("location", "rotation", "scale"):
                for a, b in zip(pre[name][field], post[name][field]):
                    assert abs(a-b) < 2e-4, "%s transform changed for %s: %s -> %s" % (field, name, pre[name][field], post[name][field])
        main_obj = post["Fixture_Main"]
        assert main_obj["uv_layers"], "UV layer lost after round-trip"
        assert main_obj["uv_loop_count"] > 0, "UV loop data missing after round-trip"
        assert len(main_obj["materials"]) == 2, "material slots lost after round-trip"
        assert set(main_obj["material_indices"]) >= {0, 1}, "material assignments lost after round-trip"
        assert main_obj["uv_samples"] == pre["Fixture_Main"]["uv_samples"], "sampled UV coordinates changed"
        assert report.get("objects"), "repair report contains no mesh objects"
        repair_items = {item.get("object"): item for item in report["objects"]}
        assert "Fixture_Main" in repair_items, "main mesh metrics missing from report"
        metrics = repair_items["Fixture_Main"]
        assert "before" in metrics and "after" in metrics, "before/after metrics missing"
        assert metrics["before"].get("faces", 0) > metrics["after"].get("faces", 0), "degenerate face was not removed"
        assert metrics["after"].get("zero_area_faces", 0) == 0, "zero-area faces remain after repair"
        assert report.get("self_intersections", {}).get("status") in ("not_run", "unsupported"), "self-intersection status must be explicit until independent detector is implemented"

        print("PHOTOCATCH_BLENDER_ROUNDTRIP=" + json.dumps({
            "status": "PASS",
            "objects_before": sorted(pre),
            "objects_after": sorted(post),
            "uv_layers": main_obj["uv_layers"],
            "material_slots": main_obj["materials"],
            "material_indices": main_obj["material_indices"],
            "parent": post["Fixture_Child"]["parent"],
            "repair_report": report,
            "note": "This test validates fixture round-trip attributes and basic BMesh metrics. It does not claim general self-intersection detection."
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
