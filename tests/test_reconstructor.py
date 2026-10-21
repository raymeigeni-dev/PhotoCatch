import numpy as np

from backend.reconstructor import Reconstructor3D


def _edge_use_counts(faces):
    counts = {}
    for face in faces:
        assert len(face) == 3
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = tuple(sorted((a, b)))
            counts[edge] = counts.get(edge, 0) + 1
    return counts


def _assert_valid_triangles(result):
    vertices = result["vertices"]
    faces = result["faces"]
    assert len(vertices) == result["vertex_count"]
    assert len(faces) == result["face_count"]
    assert len(vertices) > 0 and len(faces) > 0
    assert all(len(face) == 3 for face in faces)
    assert all(0 <= index < len(vertices) for face in faces for index in face)
    assert len(result["colors"]) == len(faces)
    assert all(np.isfinite(component) for vertex in vertices for component in vertex)


def test_blank_image_returns_valid_fallback_mesh():
    result = Reconstructor3D().reconstruct(np.zeros((64, 64, 3), dtype=np.uint8))
    _assert_valid_triangles(result)
    assert all(count == 2 for count in _edge_use_counts(result["faces"]).values())


def test_reconstruction_output_has_finite_vertices():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:80, 25:75] = 255
    result = Reconstructor3D().reconstruct(image)
    _assert_valid_triangles(result)


def test_contour_mesh_is_closed_and_manifold():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:80, 25:75] = 255
    result = Reconstructor3D().reconstruct(image)
    _assert_valid_triangles(result)

    canonical_faces = [tuple(sorted(face)) for face in result["faces"]]
    assert len(canonical_faces) == len(set(canonical_faces)), "duplicate triangle faces found"

    edge_counts = _edge_use_counts(result["faces"])
    assert edge_counts, "mesh has no edges"
    assert all(count == 2 for count in edge_counts.values()), (
        f"mesh must be closed and manifold; edge-use counts: {sorted(set(edge_counts.values()))}"
    )


def test_concave_polygon_triangulation_preserves_area():
    # A simple concave "arrow" polygon with known area 3.0.
    points = np.array(
        [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [1.0, 1.0], [0.0, 2.0]]
    )
    triangles = Reconstructor3D._triangulate_polygon(points)

    assert len(triangles) == len(points) - 2
    assert all(len(set(triangle)) == 3 for triangle in triangles)
    assert all(0 <= index < len(points) for triangle in triangles for index in triangle)

    triangle_area = 0.0
    for a, b, c in triangles:
        pa, pb, pc = points[[a, b, c]]
        cross = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0])
        assert abs(cross) > 1e-12, "triangulation emitted a degenerate triangle"
        triangle_area += abs(cross) / 2

    assert np.isclose(triangle_area, 3.0)
