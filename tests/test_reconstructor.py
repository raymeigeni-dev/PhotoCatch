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


def test_blank_image_returns_valid_fallback_mesh():
    result = Reconstructor3D().reconstruct(np.zeros((64, 64, 3), dtype=np.uint8))
    assert len(result["vertices"]) == result["vertex_count"]
    assert len(result["faces"]) == result["face_count"]
    assert len(result["vertices"]) > 0
    assert len(result["faces"]) > 0
    assert all(len(face) == 3 for face in result["faces"])
    assert all(0 <= index < len(result["vertices"]) for face in result["faces"] for index in face)
    assert len(result["colors"]) == len(result["faces"])


def test_reconstruction_output_has_finite_vertices():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:80, 25:75] = 255
    result = Reconstructor3D().reconstruct(image)
    assert all(np.isfinite(component) for vertex in result["vertices"] for component in vertex)
    assert all(len(face) == 3 for face in result["faces"])


def test_contour_mesh_has_no_duplicate_faces_or_nonmanifold_edges():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:80, 25:75] = 255
    result = Reconstructor3D().reconstruct(image)

    canonical_faces = [tuple(sorted(face)) for face in result["faces"]]
    assert len(canonical_faces) == len(set(canonical_faces)), "duplicate triangle faces found"

    edge_counts = _edge_use_counts(result["faces"])
    assert all(count <= 2 for count in edge_counts.values()), "non-manifold edge found"
