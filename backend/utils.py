import base64
import numpy as np
import cv2

def encode_image(image: np.ndarray, format='jpeg') -> str:
    if format == 'jpeg':
        _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    else:
        _, buffer = cv2.imencode('.png', image)
    
    b64_string = base64.b64encode(buffer).decode('utf-8')
    return f'data:image/{format};base64,{b64_string}'

def decode_image(image_data: str) -> np.ndarray:
    if ',' in image_data:
        image_data = image_data.split(',')[1]
    
    image_bytes = base64.b64decode(image_data)
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    return image

def resize_image(image: np.ndarray, max_width=640, max_height=480) -> np.ndarray:
    h, w = image.shape[:2]
    
    if w > max_width or h > max_height:
        scale = min(max_width / w, max_height / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        image = cv2.resize(image, (new_w, new_h))
    
    return image

def normalize_vertices(vertices: list, scale=1.0) -> list:
    vertices = np.array(vertices)
    center = np.mean(vertices, axis=0)
    vertices -= center
    
    max_dist = np.max(np.linalg.norm(vertices, axis=1))
    if max_dist > 0:
        vertices = vertices / max_dist * scale
    
    return vertices.tolist()
