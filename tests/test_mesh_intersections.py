from tools.mesh_intersections import _segments2, count_self_intersections


def test_coplanar_segment_crossing_is_detected():
    assert _segments2((0, 0), (1, 1), (0, 1), (1, 0), 1e-8)


def test_disjoint_coplanar_segments_are_not_intersections():
    assert not _segments2((0, 0), (1, 0), (0, 1), (1, 1), 1e-8)


def test_triangle_intersection_counter_imports_and_reports_result():
    vertices = [
        (-1, 0, 0), (1, 0, 0), (0, 1, 0),
        (0, -1, -1), (0, -1, 1), (0, 1, 0.2),
    ]
    faces = [(0, 1, 2), (3, 4, 5)]
    result = count_self_intersections(vertices, faces)
    assert result["status"] == "completed"
    assert isinstance(result["count"], int)
