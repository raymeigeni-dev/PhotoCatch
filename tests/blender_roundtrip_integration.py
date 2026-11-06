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

# Use the same independent triangle-pair counter as the production repair adapter.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from mesh_intersections import count_self_intersections


def test_shared_vertex_crossing_policy():
    # The triangles share vertex index 0, but intersect again away from that
    # point. Default topology-aware mode excludes the pair; inclusive diagnostic
    # mode must reveal it rather than silently hiding the crossing.
    vertices = [(0,0,0), (2,0,0), (0,2,0), (0.5,0.5,-1), (0.5,0.5,1)]
    faces = [(0,1,2), (0,3,4)]
    conservative = count_self_intersections(vertices, faces)
    inclusive = count_self_intersections(vertices, faces, include_adjacent=True)
    assert conservative["status"] == "completed"
    assert conservative["count"] == 0, "default shared-vertex adjacency policy changed"
    assert inclusive["status"] == "completed"
    assert inclusive["count"] == 1, "shared-vertex crossing beyond the shared point was missed"


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
    verts = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(2,1,0),(3,0,0),(4,0,0),(5,0,0),(6,0,0),
             (0.2,0.2,-1),(0.2,0.2,1),(1.5,0.2,0)]
    # Three distinct collinear vertices make a valid-index but zero-area face.
    faces = [(0,1,2),(0,2,3),(1,4,5),(1,5,2),(7,8,9),(10,11,12)]
    mesh = bpy.data.meshes.new("UVSeamMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    # Point-domain vertex colors must survive GLB export -> repair -> import.
    color_attr = mesh.color_attributes.new(name="FixtureColor", type="FLOAT_COLOR", domain="POINT")
    for i, item in enumerate(color_attr.data):
        item.color = (0.15 + (i % 3) * 0.2, 0.25 + (i % 2) * 0.3, 0.65, 1.0)
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
      [(0,0),(0,0),(0,0)], [(0.2,0.2),(0.2,0.8),(0.8,0.2)]
    ]
    for poly in mesh.polygons:
        for li, uvco in zip(poly.loop_indices, coords[poly.index]):
            uv.data[li].uv = uvco
    obj.location = (1.25, -2.0, 0.5)
    obj.rotation_euler = (0.1, 0.2, 0.3)
    obj.scale = (1.2, 0.9, 1.1)

    # Real armature + vertex-group weights, exported through the same GLB path.
    rig_data = bpy.data.armatures.new("FixtureRigData")
    rig = bpy.data.objects.new("Fixture_Rig", rig_data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone = rig_data.edit_bones.new("Root")
    bone.head = (0, 0, 0)
    bone.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.select_set(False)
    group = obj.vertex_groups.new(name="Root")
    group.add(list(range(len(mesh.vertices))), 1.0, "REPLACE")
    modifier = obj.modifiers.new(name="FixtureArmature", type="ARMATURE")
    modifier.object = rig
    # glTF skins require the armature to be the skinned mesh's parent. Keep the
    # world transform unchanged while making the fixture structurally valid.
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()

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
            "world_matrix": tuple(
                tuple(round(float(value), 5) for value in row)
                for row in obj.matrix_world
            ),
        }
        if obj.type == "MESH":
            mesh = obj.data
            entry["mesh_data_name"] = mesh.name
            world_vertices = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
            entry["world_bounds"] = [
                tuple(round(float(min(vertex[axis] for vertex in world_vertices)), 5) for axis in range(3)),
                tuple(round(float(max(vertex[axis] for vertex in world_vertices)), 5) for axis in range(3)),
            ]
            entry["vertices"] = len(mesh.vertices)
            entry["polygons"] = len(mesh.polygons)
            entry["vertex_groups"] = [group.name for group in obj.vertex_groups]
            root_group = obj.vertex_groups.get("Root")
            entry["root_weights"] = [round(float(next((g.weight for g in v.groups if g.group == root_group.index), 0.0)), 4) for v in mesh.vertices[:3]] if root_group else []
            entry["materials"] = [m.name for m in mesh.materials]
            entry["material_indices"] = sorted(set(p.material_index for p in mesh.polygons))
            entry["uv_layers"] = [layer.name for layer in mesh.uv_layers]
            entry["color_attributes"] = [attr.name for attr in mesh.color_attributes]
            color_attr = mesh.color_attributes[0] if len(mesh.color_attributes) else None
            entry["color_samples"] = [tuple(round(float(v), 4) for v in color_attr.data[i].color) for i in range(min(3, len(color_attr.data)))] if color_attr else []
            entry["uv_loop_count"] = len(mesh.uv_layers[0].data) if mesh.uv_layers else 0
            entry["uv_samples"] = [
                tuple(round(float(v), 5) for v in mesh.uv_layers[0].data[i].uv)
                for i in range(min(12, len(mesh.uv_layers[0].data)))
            ] if mesh.uv_layers else []
            entry["degenerate_faces"] = sum(1 for p in mesh.polygons if p.area <= 1e-12)
        data[name] = entry
    return data


def main():
    test_shared_vertex_crossing_policy()
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
        assert "Root" in pre["Fixture_Main"]["vertex_groups"], "fixture skin-weight group was not created"
        assert all(abs(w-1.0)<1e-5 for w in pre["Fixture_Main"]["root_weights"]), "fixture skin weights invalid"

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
        print("BLENDER_ROUNDTRIP_PRE=" + json.dumps(pre, ensure_ascii=False))
        print("BLENDER_ROUNDTRIP_POST=" + json.dumps(post, ensure_ascii=False))
        for name in ("Fixture_Main", "Fixture_Child"):
            assert name in post, "object/node lost after round-trip: " + name
            assert post[name]["parent"] == pre[name]["parent"], "parent hierarchy changed: " + name
        # glTF represents an armature-skinned Blender object as a transform node
        # plus a separate mesh node named after its mesh datablock. Validate both
        # rather than incorrectly requiring Blender's pre-export object type/name.
        assert post["Fixture_Main"]["type"] in {"EMPTY", "MESH"}, "main glTF transform node missing"
        mesh_nodes = [
            name for name, item in post.items()
            if item["type"] == "MESH" and item.get("mesh_data_name") == "UVSeamMesh"
        ]
        assert len(mesh_nodes) == 1, "skinned main mesh node missing or duplicated"
        main_mesh_name = mesh_nodes[0]
        main_obj = post[main_mesh_name]
        for axis in range(3):
            assert abs(pre["Fixture_Main"]["world_bounds"][0][axis] - main_obj["world_bounds"][0][axis]) < 2e-4
            assert abs(pre["Fixture_Main"]["world_bounds"][1][axis] - main_obj["world_bounds"][1][axis]) < 2e-4
        for row_a, row_b in zip(pre["Fixture_Child"]["world_matrix"], post["Fixture_Child"]["world_matrix"]):
            for a, b in zip(row_a, row_b):
                assert abs(a-b) < 2e-4, "child world transform changed during GLB round-trip"
        assert "Fixture_Rig" in post and post["Fixture_Rig"]["type"] == "ARMATURE", "armature object lost after round-trip"
        assert "Root" in main_obj["vertex_groups"], "skin-weight vertex group lost after round-trip"
        assert all(abs(w-1.0)<2e-2 for w in main_obj["root_weights"]), "skin weights changed after round-trip: %s" % main_obj["root_weights"]
        # Count the exported GLB after it has been re-imported into this test process;
        # this is deliberately independent of the repair sidecar's before/after metrics.
        imported_main = bpy.data.objects.get(main_mesh_name)
        assert imported_main is not None and imported_main.type == "MESH", "re-imported main mesh missing"
        imported_mesh = imported_main.data
        intersections_after_reimport = count_self_intersections(
            [tuple(v.co) for v in imported_mesh.vertices],
            [tuple(p.vertices) for p in imported_mesh.polygons]
        )
        assert main_obj["uv_layers"], "UV layer lost after round-trip"
        assert main_obj["uv_loop_count"] > 0, "UV loop data missing after round-trip"
        assert len(main_obj["materials"]) == 2, "material slots lost after round-trip"
        assert set(main_obj["material_indices"]) >= {0, 1}, "material assignments lost after round-trip"
        assert main_obj["uv_samples"] == pre["Fixture_Main"]["uv_samples"], "sampled UV coordinates changed"
        assert main_obj["color_attributes"], "vertex color attribute lost after round-trip"
        assert len(main_obj["color_samples"]) == len(pre["Fixture_Main"]["color_samples"]), "vertex color samples missing after round-trip"
        for actual, expected in zip(main_obj["color_samples"], pre["Fixture_Main"]["color_samples"]):
            assert all(abs(a-b) < 2e-2 for a,b in zip(actual,expected)), "vertex color values changed: %s -> %s" % (expected, actual)
        assert report.get("objects"), "repair report contains no mesh objects"
        repair_items = {item.get("object"): item for item in report["objects"]}
        assert main_mesh_name in repair_items, "main mesh metrics missing from report"
        metrics = repair_items[main_mesh_name]
        assert "before" in metrics and "after" in metrics, "before/after metrics missing"
        assert metrics["before"].get("faces", 0) > metrics["after"].get("faces", 0), "degenerate face was not removed"
        assert metrics["after"].get("zero_area_faces", 0) == 0, "zero-area faces remain after repair"
        intersections = report.get("self_intersections", {})
        assert intersections.get("status") == "completed", "independent self-intersection detector did not run"
        assert intersections.get("count_before", 0) >= 1, "fixture crossing triangle was not detected before repair"
        assert intersections.get("count_after", -1) >= 1, "post-repair self-intersection count missing or unexpected"
        assert intersections.get("repair_status") == "unresolved", "remaining intersections must not be mislabeled as repaired"
        assert intersections_after_reimport.get("status") == "completed", "independent detector did not run on re-imported GLB"
        assert intersections_after_reimport.get("count", 0) >= 1, "crossing triangle was not detected after export and re-import"
        assert metrics["before"].get("self_intersections", {}).get("status") == "completed"
        assert metrics["after"].get("self_intersections", {}).get("status") == "completed"

        print("PHOTOCATCH_BLENDER_ROUNDTRIP=" + json.dumps({
            "status": "PASS",
            "objects_before": sorted(pre),
            "objects_after": sorted(post),
            "main_mesh_node": main_mesh_name,
            "uv_layers": main_obj["uv_layers"],
            "material_slots": main_obj["materials"],
            "material_indices": main_obj["material_indices"],
            "parent": post["Fixture_Child"]["parent"],
            "repair_report": report,
            "self_intersections_before": intersections.get("count_before"),
            "self_intersections_after_repair": intersections.get("count_after"),
            "self_intersections_after_reimport": intersections_after_reimport.get("count"),
            "note": "This test validates GLB round-trip attributes, topology metrics, and a known crossing-triangle self-intersection before/after repair."
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
