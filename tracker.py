"""Hand + face tracking using MediaPipe Tasks API. Detects rock sign gesture and extracts control angles."""

import math
import os
import time
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

import config

# Model paths (relative to this file)
_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
_HAND_MODEL = os.path.join(_MODEL_DIR, "hand_landmarker.task")
_FACE_MODEL = os.path.join(_MODEL_DIR, "face_landmarker.task")

BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode


@dataclass
class TrackingResult:
    gesture_active: bool = False
    roll_angle: float = 0.0   # degrees, positive = right
    pitch_angle: float = 0.0  # degrees, positive = forward
    yaw_angle: float = 0.0    # degrees, positive = right (from head)
    confidence: float = 0.0
    hand_landmarks: list = None  # list of NormalizedLandmark, for drawing
    face_landmarks: list = None  # list of NormalizedLandmark, for drawing


class Tracker:
    def __init__(self):
        hand_options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_HAND_MODEL),
            running_mode=VisionRunningMode.VIDEO,
            num_hands=config.MP_HAND_MAX_HANDS,
            min_hand_detection_confidence=config.MP_HAND_DETECTION_CONFIDENCE,
            min_tracking_confidence=config.MP_HAND_TRACKING_CONFIDENCE,
        )
        face_options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_FACE_MODEL),
            running_mode=VisionRunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=config.MP_FACE_DETECTION_CONFIDENCE,
            min_tracking_confidence=config.MP_FACE_TRACKING_CONFIDENCE,
        )

        self.hand_landmarker = HandLandmarker.create_from_options(hand_options)
        self.face_landmarker = FaceLandmarker.create_from_options(face_options)

        self._gesture_counter = 0
        self._gesture_state = False
        self._frame_timestamp_ms = 0

        # Calibration: neutral pitch reference (wrist-to-middle-MCP y-delta)
        self._pitch_neutral = None

    def calibrate_neutral(self, frame: np.ndarray):
        """Capture the current hand pose as the neutral pitch reference."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._frame_timestamp_ms += 1
        hand_result = self.hand_landmarker.detect_for_video(mp_image, self._frame_timestamp_ms)
        if hand_result.hand_landmarks:
            lm = hand_result.hand_landmarks[0]
            wrist = lm[0]
            mid_mcp = lm[9]
            self._pitch_neutral = mid_mcp.y - wrist.y
        return self._pitch_neutral is not None

    def process(self, frame: np.ndarray) -> TrackingResult:
        """Process a BGR frame and return tracking result."""
        result = TrackingResult()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        self._frame_timestamp_ms += 33  # ~30fps increment, must be monotonically increasing

        hand_result = self.hand_landmarker.detect_for_video(mp_image, self._frame_timestamp_ms)
        face_result = self.face_landmarker.detect_for_video(mp_image, self._frame_timestamp_ms)

        # --- Hand tracking ---
        if hand_result.hand_landmarks:
            lm = hand_result.hand_landmarks[0]  # list of NormalizedLandmark
            result.hand_landmarks = lm
            result.confidence = 0.8

            raw_gesture = self._detect_rock_sign(lm)
            result.gesture_active = self._apply_hysteresis(raw_gesture)

            if result.gesture_active:
                result.roll_angle = self._extract_roll(lm)
                result.pitch_angle = self._extract_pitch(lm)

        # --- Face tracking (yaw from head tilt) ---
        if face_result.face_landmarks:
            face_lm = face_result.face_landmarks[0]  # list of NormalizedLandmark
            result.face_landmarks = face_lm
            result.yaw_angle = self._extract_yaw(face_lm)

        return result

    def _detect_rock_sign(self, lm) -> bool:
        """Check if hand is making rock sign: index + pinky extended, middle + ring folded."""
        index_extended = lm[8].y < lm[6].y
        middle_folded = lm[12].y > lm[10].y
        ring_folded = lm[16].y > lm[14].y
        pinky_extended = lm[20].y < lm[18].y
        return index_extended and middle_folded and ring_folded and pinky_extended

    def _apply_hysteresis(self, raw: bool) -> bool:
        """Apply hysteresis to gesture detection to avoid flickering."""
        if raw == self._gesture_state:
            self._gesture_counter = 0
            return self._gesture_state

        self._gesture_counter += 1
        if self._gesture_counter >= config.GESTURE_HYSTERESIS_FRAMES:
            self._gesture_state = raw
            self._gesture_counter = 0

        return self._gesture_state

    def _extract_roll(self, lm) -> float:
        """Extract roll angle from index tip (8) to pinky tip (20) vector."""
        dx = lm[8].x - lm[20].x
        dy = lm[8].y - lm[20].y
        angle_rad = math.atan2(-dy, dx)
        angle_deg = math.degrees(angle_rad)
        return -angle_deg

    def _extract_pitch(self, lm) -> float:
        """Extract pitch from wrist (0) to middle MCP (9) vector y-component."""
        wrist = lm[0]
        mid_mcp = lm[9]
        current_delta = mid_mcp.y - wrist.y

        if self._pitch_neutral is None:
            self._pitch_neutral = current_delta

        diff = current_delta - self._pitch_neutral
        pitch_deg = diff * 200.0
        return float(np.clip(pitch_deg, -45.0, 45.0))

    def _extract_yaw(self, face_lm) -> float:
        """Extract yaw from face mesh: nose (1) vs ear landmarks (234, 454)."""
        nose = face_lm[1]
        left_ear = face_lm[234]
        right_ear = face_lm[454]

        dist_left = nose.x - left_ear.x
        dist_right = right_ear.x - nose.x

        if dist_left + dist_right < 0.001:
            return 0.0
        ratio = (dist_right - dist_left) / (dist_right + dist_left)
        # Negate because the webcam frame is mirrored (cv2.flip)
        yaw_deg = -ratio * 60.0
        return float(np.clip(yaw_deg, -45.0, 45.0))

    def close(self):
        self.hand_landmarker.close()
        self.face_landmarker.close()


# --- Drawing utilities ---
_draw_utils = mp.tasks.vision.drawing_utils
_draw_styles = mp.tasks.vision.drawing_styles
_HandConnections = mp.tasks.vision.HandLandmarksConnections
_FaceConnections = mp.tasks.vision.FaceLandmarksConnections


def draw_landmarks(frame: np.ndarray, result: TrackingResult) -> np.ndarray:
    """Draw hand and face landmarks on frame for visualization."""
    if result.hand_landmarks:
        _draw_utils.draw_landmarks(
            frame,
            result.hand_landmarks,
            _HandConnections.HAND_CONNECTIONS,
            _draw_styles.get_default_hand_landmarks_style(),
            _draw_styles.get_default_hand_connections_style(),
        )

    if result.face_landmarks:
        _draw_utils.draw_landmarks(
            frame,
            result.face_landmarks,
            _FaceConnections.FACE_LANDMARKS_CONTOURS,
            landmark_drawing_spec=None,
            connection_drawing_spec=_draw_styles.get_default_face_mesh_contours_style(),
            is_drawing_landmarks=False,
        )

    return frame


if __name__ == "__main__":
    """Standalone test: show webcam with landmarks and print tracking data."""
    cap = cv2.VideoCapture(config.WEBCAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.WEBCAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.WEBCAM_HEIGHT)

    tracker = Tracker()
    print("Tracker standalone test. Press 'c' to calibrate, 'q' to quit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        result = tracker.process(frame)
        frame = draw_landmarks(frame, result)

        status = "ROCK" if result.gesture_active else "---"
        cv2.putText(frame, f"Gesture: {status}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if result.gesture_active else (0, 0, 255), 2)
        cv2.putText(frame, f"Roll: {result.roll_angle:+.1f}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(frame, f"Pitch: {result.pitch_angle:+.1f}", (10, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(frame, f"Yaw: {result.yaw_angle:+.1f}", (10, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow("Tracker Test", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            ret2, frame2 = cap.read()
            if ret2:
                frame2 = cv2.flip(frame2, 1)
                if tracker.calibrate_neutral(frame2):
                    print("Calibrated pitch neutral.")
                else:
                    print("Calibration failed — no hand detected.")

    tracker.close()
    cap.release()
    cv2.destroyAllWindows()
