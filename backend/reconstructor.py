import numpy as np
import cv2
from typing import Dict, List, Tuple

class Reconstructor3D:
    
    def __init__(self):
        self.mesh_quality = 'high'
        self.max_vertices = 10000
    
    def reconstruct(self, image: np.ndarray) -> Dict:
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
        
        vertices, faces, colors = self._generate_mesh_from_contour(approx, image)
        
        return {
            'vertices': vertices,
            'faces': faces,
            'colors': colors,
            'vertex_count': len(vertices),
            'face_count': len(faces)
        }
    
    def _generate_mesh_from_contour(self, contour: np.ndarray, image: np.ndarray) -> Tuple[List, List, List]:
        h, w = image.shape[:2]
        vertices = []
        faces = []
        colors = []
        
        normalized_contour = contour.reshape(-1, 2).astype(float)
        normalized_contour[:, 0] /= w
        normalized_contour[:, 1] /= h
        
        for pt in normalized_contour:
            x, y = pt
            vertices.append([x - 0.5, 0.5 - y, 0.5])
        
        for pt in normalized_contour:
            x, y = pt
            vertices.append([x - 0.5, 0.5 - y, -0.5])
        
        n_verts = len(normalized_contour)
        
        for i in range(n_verts - 1):
            faces.append([i, i + 1, n_verts + i + 1])
            faces.append([i, n_verts + i + 1, n_verts + i])
        
        for i in range(n_verts):
            next_i = (i + 1) % n_verts
            faces.append([i, next_i, n_verts + next_i])
            faces.append([i, n_verts + next_i, n_verts + i])
        
        for i in range(len(faces)):
            sample_x = int((normalized_contour[i % n_verts][0] + 0.5) * w)
            sample_y = int((0.5 - normalized_contour[i % n_verts][1]) * h)
            sample_x = max(0, min(w - 1, sample_x))
            sample_y = max(0, min(h - 1, sample_y))
            
            bgr = image[sample_y, sample_x]
            rgb = [float(bgr[2] / 255.0), float(bgr[1] / 255.0), float(bgr[0] / 255.0)]
            colors.append(rgb)
        
        return vertices, faces, colors
    
    def _create_default_cube(self) -> Dict:
        vertices = [
            [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5],
            [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
            [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5],
            [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5]
        ]
        
        faces = [
            [0, 1, 2], [0, 2, 3],
            [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1],
            [2, 6, 7], [2, 7, 3],
            [0, 3, 7], [0, 7, 4],
            [1, 5, 6], [1, 6, 2]
        ]
        
        colors = [[0.5, 0.5, 0.5] for _ in range(len(faces))]
        
        return {
            'vertices': vertices,
            'faces': faces,
            'colors': colors,
            'vertex_count': len(vertices),
            'face_count': len(faces)
        }
