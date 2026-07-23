import cv2
import numpy as np
import mediapipe as mp
from typing import List, Dict

class ObjectDetector:
    
    def __init__(self):
        self.mp_selfie = mp.solutions.selfie_segmentation
        self.selfie_segmentation = self.mp_selfie.SelfieSegmentation(model_selection=1)
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5
        )
        
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.colors = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (255, 255, 0), (255, 0, 255), (0, 255, 255),
        ]
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        detections = []
        h, w, c = frame.shape
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        hand_results = self.hands.process(rgb_frame)
        if hand_results.multi_hand_landmarks:
            for hand_idx, landmarks in enumerate(hand_results.multi_hand_landmarks):
                bbox = self._get_bbox_from_landmarks(landmarks, w, h)
                detections.append({
                    'type': 'hand',
                    'id': hand_idx,
                    'bbox': bbox,
                    'confidence': 0.95,
                    'label': f'Hand {hand_idx+1}'
                })
        
        pose_results = self.pose.process(rgb_frame)
        if pose_results.pose_landmarks:
            bbox = self._get_bbox_from_landmarks(pose_results.pose_landmarks, w, h)
            detections.append({
                'type': 'person',
                'id': 0,
                'bbox': bbox,
                'confidence': 0.90,
                'label': 'Person'
            })
        
        segmentation_results = self.selfie_segmentation.process(rgb_frame)
        if segmentation_results.segmentation_mask is not None:
            mask = segmentation_results.segmentation_mask
            binary_mask = (mask > 0.5).astype(np.uint8) * 255
            
            contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for idx, contour in enumerate(contours[:5]):
                if cv2.contourArea(contour) > 500:
                    x, y, w_box, h_box = cv2.boundingRect(contour)
                    detections.append({
                        'type': 'object',
                        'id': idx,
                        'bbox': [x, y, w_box, h_box],
                        'confidence': 0.85,
                        'label': f'Object {idx+1}',
                        'area': int(cv2.contourArea(contour))
                    })
        
        return detections
    
    def _get_bbox_from_landmarks(self, landmarks, frame_w: int, frame_h: int) -> List[int]:
        xs = [lm.x for lm in landmarks.landmark]
        ys = [lm.y for lm in landmarks.landmark]
        
        x_min = max(0, int(min(xs) * frame_w) - 10)
        y_min = max(0, int(min(ys) * frame_h) - 10)
        x_max = min(frame_w, int(max(xs) * frame_w) + 10)
        y_max = min(frame_h, int(max(ys) * frame_h) + 10)
        
        return [x_min, y_min, x_max - x_min, y_max - y_min]
    
    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        for idx, det in enumerate(detections):
            bbox = det['bbox']
            x, y, w, h = bbox
            color = self.colors[idx % len(self.colors)]
            
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            label = f"{det['label']} ({det['confidence']:.2f})"
            cv2.putText(frame, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame
