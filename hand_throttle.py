"""
Hand Tracking Throttle — Phase 1 Prototype
Opens MacBook webcam, tracks hand openness via MediaPipe, displays throttle.
No serial/hardware — visual output only.

Controls:
  C - calibrate (fist first, then spread)
  Q / ESC - quit

Requires: pip install mediapipe opencv-python
"""

import math
import os
import sys
import time

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision

# --- Constants ---
EMA_ALPHA = 0.3
CLOSED_FIST_THRESHOLD = 0.05
THROTTLE_CAP = 3000
CALIBRATION_FRAMES = 30
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "hand_landmarker.task")

# Landmark indices
WRIST = 0
FINGERTIPS = [8, 12, 16, 20]   # index, middle, ring, pinky
MCPS = [5, 9, 13, 17]

# Hand skeleton connections for drawing
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),        # thumb
    (0,5),(5,6),(6,7),(7,8),        # index
    (0,9),(9,10),(10,11),(11,12),   # middle  (wrist to MCP9 added)
    (0,13),(13,14),(14,15),(15,16), # ring    (wrist to MCP13 added)
    (0,17),(17,18),(18,19),(19,20), # pinky
    (5,9),(9,13),(13,17),           # palm
]

# Calibration states
CAL_NONE = 0
CAL_WAITING_CLOSED = 1
CAL_SAMPLING_CLOSED = 2
CAL_WAITING_OPEN = 3
CAL_SAMPLING_OPEN = 4
CAL_DONE = 5


def dist(a, b):
    """Euclidean distance between two landmarks."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def compute_raw_openness(landmarks):
    """Average ratio of fingertip-to-wrist / MCP-to-wrist across 4 fingers."""
    wrist = landmarks[WRIST]
    ratios = []
    for tip_idx, mcp_idx in zip(FINGERTIPS, MCPS):
        tip_dist = dist(landmarks[tip_idx], wrist)
        mcp_dist = dist(landmarks[mcp_idx], wrist)
        if mcp_dist > 1e-6:
            ratios.append(tip_dist / mcp_dist)
    return sum(ratios) / len(ratios) if ratios else 0.0


def draw_throttle_bar(frame, throttle_pct, dac_value, hand_found):
    """Draw vertical throttle bar and readout on left side of frame."""
    h, w = frame.shape[:2]
    bar_x = 30
    bar_w = 40
    bar_top = 60
    bar_bottom = h - 60
    bar_h = bar_bottom - bar_top

    # Background
    cv2.rectangle(frame, (bar_x, bar_top), (bar_x + bar_w, bar_bottom), (50, 50, 50), -1)
    cv2.rectangle(frame, (bar_x, bar_top), (bar_x + bar_w, bar_bottom), (200, 200, 200), 2)

    # Fill
    fill_h = int(bar_h * throttle_pct)
    if fill_h > 0:
        color = (0, 220, 0) if hand_found else (0, 100, 0)
        cv2.rectangle(frame, (bar_x, bar_bottom - fill_h), (bar_x + bar_w, bar_bottom), color, -1)

    # Labels
    cv2.putText(frame, "THR", (bar_x - 2, bar_top - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"{int(throttle_pct * 100)}%", (bar_x - 5, bar_bottom + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # Readout on right of bar
    text_x = bar_x + bar_w + 15
    cv2.putText(frame, f"DAC: {dac_value}", (text_x, bar_top + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    hand_str = "HAND" if hand_found else "NO HAND"
    hand_color = (0, 255, 0) if hand_found else (0, 0, 255)
    cv2.putText(frame, hand_str, (text_x, bar_top + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, hand_color, 2)


def draw_calibration_prompt(frame, cal_state):
    """Draw calibration instructions on frame."""
    h, w = frame.shape[:2]
    if cal_state == CAL_WAITING_CLOSED:
        text = "Make a FIST, then press C"
    elif cal_state == CAL_SAMPLING_CLOSED:
        text = "Sampling fist... hold still"
    elif cal_state == CAL_WAITING_OPEN:
        text = "SPREAD fingers wide, then press C"
    elif cal_state == CAL_SAMPLING_OPEN:
        text = "Sampling open... hold still"
    else:
        return

    cv2.putText(frame, text, (w // 2 - 200, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)


def main():
    # --- MediaPipe setup (LIVE_STREAM mode) ---
    latest_result = [None]
    latest_timestamp = [0]

    def on_result(result, image, timestamp_ms):
        latest_result[0] = result
        latest_timestamp[0] = timestamp_ms

    options = vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.LIVE_STREAM,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        result_callback=on_result,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    # --- Webcam ---
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam")
        sys.exit(1)

    # --- State ---
    cal_state = CAL_WAITING_CLOSED
    closed_baseline = 1.0
    open_baseline = 2.0
    cal_samples = []

    smoothed_openness = 0.0
    frame_idx = 0

    print("Hand Throttle Phase 1 — Prototype")
    print("Press C to calibrate, Q/ESC to quit")
    print("-" * 40)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)  # mirror
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

            timestamp_ms = int(time.time() * 1000)
            landmarker.detect_async(mp_image, timestamp_ms)

            # Process latest result
            hand_found = False
            raw_openness = 0.0

            result = latest_result[0]
            if result and result.hand_landmarks:
                hand_found = True
                landmarks = result.hand_landmarks[0]
                raw_openness = compute_raw_openness(landmarks)

                # Draw landmarks
                # Convert normalized landmarks to pixel coords for drawing
                h, w = frame.shape[:2]
                for connection in HAND_CONNECTIONS:
                    start = landmarks[connection[0]]
                    end = landmarks[connection[1]]
                    pt1 = (int(start.x * w), int(start.y * h))
                    pt2 = (int(end.x * w), int(end.y * h))
                    cv2.line(frame, pt1, pt2, (0, 255, 0), 2)
                for lm in landmarks:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (255, 0, 0), -1)

            # --- Calibration logic ---
            if cal_state == CAL_SAMPLING_CLOSED:
                if hand_found:
                    cal_samples.append(raw_openness)
                if len(cal_samples) >= CALIBRATION_FRAMES:
                    closed_baseline = sum(cal_samples) / len(cal_samples)
                    cal_samples.clear()
                    cal_state = CAL_WAITING_OPEN
                    print(f"  Closed baseline: {closed_baseline:.3f}")

            elif cal_state == CAL_SAMPLING_OPEN:
                if hand_found:
                    cal_samples.append(raw_openness)
                if len(cal_samples) >= CALIBRATION_FRAMES:
                    open_baseline = sum(cal_samples) / len(cal_samples)
                    cal_samples.clear()
                    cal_state = CAL_DONE
                    print(f"  Open baseline: {open_baseline:.3f}")
                    print("  Calibration complete!")

            # --- Compute throttle ---
            if not hand_found or cal_state != CAL_DONE:
                smoothed_openness = 0.0
                dac_value = 0
                throttle_pct = 0.0
            else:
                # Normalize
                spread = open_baseline - closed_baseline
                if spread > 1e-6:
                    normalized = (raw_openness - closed_baseline) / spread
                else:
                    normalized = 0.0
                normalized = max(0.0, min(1.0, normalized))

                # Safety: fist closed → instant 0
                if normalized < CLOSED_FIST_THRESHOLD:
                    smoothed_openness = 0.0
                else:
                    smoothed_openness = EMA_ALPHA * normalized + (1 - EMA_ALPHA) * smoothed_openness

                dac_value = int(smoothed_openness * THROTTLE_CAP)
                throttle_pct = smoothed_openness

            # --- Draw UI ---
            draw_throttle_bar(frame, throttle_pct, dac_value, hand_found)
            if cal_state != CAL_DONE:
                draw_calibration_prompt(frame, cal_state)

            # Console output
            if frame_idx % 5 == 0:  # throttle console spam
                sys.stdout.write(
                    f"\ropenness={smoothed_openness:.2f} dac={dac_value:4d} hand_found={hand_found}   "
                )
                sys.stdout.flush()

            cv2.imshow("Hand Throttle", frame)
            frame_idx += 1

            # --- Key handling ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # Q or ESC
                break
            elif key == ord('c') or key == ord('C'):
                if cal_state == CAL_WAITING_CLOSED:
                    cal_state = CAL_SAMPLING_CLOSED
                    cal_samples.clear()
                    print("\n  Sampling fist...")
                elif cal_state == CAL_WAITING_OPEN:
                    cal_state = CAL_SAMPLING_OPEN
                    cal_samples.clear()
                    print("  Sampling open hand...")
                elif cal_state == CAL_DONE:
                    # Re-calibrate
                    cal_state = CAL_WAITING_CLOSED
                    smoothed_openness = 0.0
                    print("\n  Re-calibrating...")

    finally:
        print("\nShutting down...")
        landmarker.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
