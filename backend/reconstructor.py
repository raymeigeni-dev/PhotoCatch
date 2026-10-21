import numpy as np
import cv2
from typing import Dict, List, Tuple


class Reconstructor3D:
    def __init__(self):
        self.mesh_quality = "high"
        self.max_vertices = 10000

    def reconstruct(self, image: np.ndarray) -> Dict:
        if not isinstance(image, np.ndarray) or image.size == 0 or image.ndim != 3:
            raise ValueError("image must be a non-empty color image")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return self._create_default_cube()

        main_contour = max(contours, key=cv2.contourArea)
        epsilon = 0.02 * cv2.arcLength(main_contour, True)
        approx = cv2.approxPolyDP(main_contour, epsilon, True)
        if len(approx) < 3:
            return self._create_default_cube()

        vertices, faces, colors = self._generate_mesh_from_contour(approx, image)
        return {
            "vertices": vertices,
            "faces": faces,
            "colors": colors,
            "vertex_count": len(vertices),
            "face_count": len(faces),
        }

    @staticmethod
    def _triangulate_polygon(points: np.ndarray) -> List[List[int]]:
        """Ear-clip a simple 2D polygon, returning triangle indices."""
        points = np.asarray(points, dtype=float)
        count = len(points)
        if count < 3:
            return []

        area2 = sum(
            points[i, 0] * points[(i + 1) % count, 1]
            - points[(i + 1) % count, 0] * points[i, 1]
            for i in range(count)
        )
        if abs(area2) < 1e-12:
            return []
        orientation = 1.0 if area2 > 0 else -1.0
        remaining = list(range(count))
        triangles = []

        def cross(a, b, c):
            return ((b[0] - a[0]) * (c[1] - a[1])
                    - (b[1] - a[1]) * (c[0] - a[0]))

        def inside_triangle(p, a, b, c):
            eps = 1e-10
            c1 = cross(a, b, p) * orientation
            c2 = cross(b, c, p) * orientation
            c3 = cross(c, a, p) * orientation
            return c1 >= -eps and c2 >= -eps and c3 >= -eps

        guard = count * count
        while len(remaining) > 3 and guard > 0:
            guard -= 1
            ear_found = False
            for pos, current in enumerate(remaining):
                prev_idx = remaining[pos - 1]
                next_idx = remaining[(pos + 1) % len(remaining)]
                a, b, c = points[prev_idx], points[current], points[next_idx]
                if cross(a, b, c) * orientation <= 1e-12:
                    continue
                if any(
                    inside_triangle(points[idx], a, b, c)
                    for idx in remaining
                    if idx not in (prev_idx, current, next_idx)
                ):
                    continue
                triangles.append([prev_idx, current, next_idx])
                del remaining[pos]
                ear_found = True
                break
            if not ear_found:
                # Remove a collinear vertex if floating-point contour coordinates
                # prevent ear detection; never silently emit an invalid fan.
                removed = False
                for pos, current in enumerate(remaining):
                    prev_idx = remaining[pos - 1]
                    next_idx = remaining[(pos + 1) % len(remaining)]
                    if abs(cross(points[prev_idx], points[current], points[next_idx])) <= 1e-10:
                        del remaining[pos]
                        removed = True
                        break
                if not removed:
                    return []

        if len(remaining) == 3:
            triangles.append(remaining[:])
        return triangles

    def _generate_mesh_from_contour(self, contour: np.ndarray, image: np.ndarray) -> Tuple[List, List, List]:
        h, w = image.shape[:2]
        normalized_contour = contour.reshape(-1, 2).astype(float)
        normalized_contour[:, 0] /= w
        normalized_contour[:, 1] /= h
        points = np.column_stack((normalized_contour[:, 0] - 0.5,
                                  0.5 - normalized_contour[:, 1]))
        n_verts = len(points)

        # Front and back contour rings.
        vertices = [[float(x), float(y), 0.5] for x, y in points]
        vertices.extend([[float(x), float(y), -0.5] for x, y in points])
        faces = []

        # Each contour edge is emitted once and forms two side triangles.
        for i in range(n_verts):
            next_i = (i + 1) % n_verts
            faces.append([i, next_i, n_verts + next_i])
            faces.append([i, n_verts + next_i, n_verts + i])

        # Cap both ends using ear clipping so concave silhouettes are supported.
        cap_triangles = self._triangulate_polygon(points)
        signed_area2 = sum(
            points[i, 0] * points[(i + 1) % n_verts, 1]
            - points[(i + 1) % n_verts, 0] * points[i, 1]
            for i in range(n_verts)
        )
        for tri in cap_triangles:
            front = tri[:] if signed_area2 > 0 else [tri[0], tri[2], tri[1]]
            faces.append(front)
            faces.append([n_verts + front[0], n_verts + front[2], n_verts + front[1]])

        # One RGB color per triangle; the frontend expands indexed geometry
        # before assigning these per-face colors to its three vertices.
        colors = []
        for face in faces:
            cx = sum(vertices[index][0] for index in face) / 3
            cy = sum(vertices[index][1] for index in face) / 3
            sample_x = max(0, min(w - 1, int((cx + 0.5) * w)))
            sample_y = max(0, min(h - 1, int((0.5 - cy) * h)))
            b, g, r = image[sample_y, sample_x][:3]
            colors.append([float(r / 255.0), float(g / 255.0), float(b / 255.0)])

        return vertices, faces, colors

    def _create_default_cube(self) -> Dict:
        vertices = [
            [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5],
            [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
            [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5],
            [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5],
        ]
        faces = [
            [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
            [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
        ]
        colors = [[0.5, 0.5, 0.5] for _ in faces]
        return {
            "vertices": vertices,
            "faces": faces,
            "colors": colors,
            "vertex_count": len(vertices),
            "face_count": len(faces),
        }
