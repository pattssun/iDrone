"""
Hand Tracking Throttle — Phase 2
Opens MacBook webcam, tracks hand openness via MediaPipe, sends throttle
to Pico over USB serial. Yaw/pitch/roll stay at neutral (2048) for
physical joystick control.

Controls:
  C - calibrate (fist first, then spread)
  K - killswitch (immediate throttle 0)
  Q / ESC - quit

Usage:
  python hand_throttle.py              # with Pico connected
  python hand_throttle.py --no-serial  # prototype mode, no hardware

Requires: pip install mediapipe opencv-python pyserial
"""

import argparse
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
NEUTRAL = 2048
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


def find_pico_port():
    """Auto-detect Pico serial port."""
    import serial.tools.list_ports
    for port in serial.tools.list_ports.comports():
        if "usbmodem" in port.device.lower() or "pico" in port.description.lower():
            return port.device
    print("Available ports:")
    for port in serial.tools.list_ports.comports():
        print(f"  {port.device} - {port.description}")
    return None


def connect_pico():
    """Connect to Pico, wait for READY signal."""
    import serial
    port_name = find_pico_port()
    if port_name is None:
        print("Could not auto-detect Pico. Enter port manually:")
        port_name = input("> ").strip()

    print(f"Connecting to {port_name}...")
    ser = serial.Serial(port_name, 115200, timeout=0.1)
    time.sleep(1)

    print("Waiting for Pico...")
    start = time.time()
    while time.time() - start < 5:
        line = ser.readline().decode().strip()
        if line == "READY":
            print("Pico is ready!")
            return ser
        if line:
            print(f"  Pico: {line}")

    print("Warning: didn't get READY signal, continuing anyway...")
    return ser


def send_to_pico(ser, throttle_dac):
    """Send throttle,neutral,neutral,neutral to Pico. Drain read buffer."""
    cmd = f"{throttle_dac},{NEUTRAL},{NEUTRAL},{NEUTRAL}\n"
    ser.write(cmd.encode())
    ser.flush()
    while ser.in_waiting:
        ser.read(ser.in_waiting)


def draw_overlay(frame, throttle_pct, dac_value, hand_found, cal_state, cal_progress=0.0):
    """Draw full HUD overlay: throttle arc, status, calibration prompts."""
    h, w = frame.shape[:2]
    # Dim background slightly for contrast
    overlay = frame.copy()

    # --- Throttle arc gauge (bottom-right) ---
    arc_cx = w - 80
    arc_cy = h - 80
    arc_r = 55
    arc_thickness = 12

    # Background arc (270 degrees, from 135 to 405)
    cv2.ellipse(overlay, (arc_cx, arc_cy), (arc_r, arc_r), 0, 135, 405, (40, 40, 40), arc_thickness)
    # Filled arc
    if throttle_pct > 0.01:
        fill_angle = 135 + int(270 * throttle_pct)
        # Color gradient: green at low, yellow at mid, red at high
        if throttle_pct < 0.5:
            color = (0, 220, 50)
        elif throttle_pct < 0.8:
            color = (0, 220, 220)
        else:
            color = (0, 80, 255)
        cv2.ellipse(overlay, (arc_cx, arc_cy), (arc_r, arc_r), 0, 135, fill_angle, color, arc_thickness)

    # Percentage in center of arc
    pct_text = f"{int(throttle_pct * 100)}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(pct_text, font, 1.2, 3)
    cv2.putText(overlay, pct_text, (arc_cx - tw // 2, arc_cy + th // 3), font, 1.2, (255, 255, 255), 3)
    # Small % below
    cv2.putText(overlay, "%", (arc_cx - 8, arc_cy + th // 3 + 22), font, 0.5, (180, 180, 180), 1)

    # --- Status badge (top-left) ---
    if hand_found:
        badge_color = (0, 200, 80)
        badge_text = "TRACKING"
    else:
        badge_color = (60, 60, 220)
        badge_text = "NO HAND"

    badge_w = 140
    badge_h = 32
    # Rounded rect approximation
    cv2.rectangle(overlay, (12, 10), (12 + badge_w, 10 + badge_h), badge_color, -1)
    cv2.rectangle(overlay, (12, 10), (12 + badge_w, 10 + badge_h), (255, 255, 255), 1)
    (btw, bth), _ = cv2.getTextSize(badge_text, font, 0.55, 2)
    cv2.putText(overlay, badge_text,
                (12 + (badge_w - btw) // 2, 10 + (badge_h + bth) // 2),
                font, 0.55, (255, 255, 255), 2)

    # --- DAC readout (top-right) ---
    dac_text = f"DAC {dac_value}"
    cv2.putText(overlay, dac_text, (w - 150, 32), font, 0.6, (0, 255, 255), 2)

    # --- Calibration overlay ---
    if cal_state != CAL_DONE:
        # Semi-transparent dark banner across the middle
        banner_top = h // 2 - 60
        banner_bot = h // 2 + 60
        sub = overlay[banner_top:banner_bot, :]
        dark = (sub * 0.3).astype(sub.dtype)
        overlay[banner_top:banner_bot, :] = dark

        if cal_state == CAL_WAITING_CLOSED:
            line1 = "CALIBRATION"
            line2 = "Make a FIST"
            line3 = "Press [C] when ready"
            accent = (0, 200, 255)
        elif cal_state == CAL_SAMPLING_CLOSED:
            line1 = "SAMPLING FIST"
            line2 = f"Hold still... {int(cal_progress * 100)}%"
            line3 = ""
            accent = (0, 180, 255)
        elif cal_state == CAL_WAITING_OPEN:
            line1 = "CALIBRATION"
            line2 = "SPREAD fingers wide"
            line3 = "Press [C] when ready"
            accent = (0, 255, 200)
        elif cal_state == CAL_SAMPLING_OPEN:
            line1 = "SAMPLING OPEN"
            line2 = f"Hold still... {int(cal_progress * 100)}%"
            line3 = ""
            accent = (0, 255, 180)
        else:
            line1 = line2 = line3 = ""
            accent = (255, 255, 255)

        # Line 1 — title
        (t1w, t1h), _ = cv2.getTextSize(line1, font, 0.9, 2)
        cv2.putText(overlay, line1, (w // 2 - t1w // 2, h // 2 - 25), font, 0.9, accent, 2)

        # Line 2 — instruction
        (t2w, t2h), _ = cv2.getTextSize(line2, font, 0.7, 2)
        cv2.putText(overlay, line2, (w // 2 - t2w // 2, h // 2 + 10), font, 0.7, (255, 255, 255), 2)

        # Line 3 — hint
        if line3:
            (t3w, t3h), _ = cv2.getTextSize(line3, font, 0.5, 1)
            cv2.putText(overlay, line3, (w // 2 - t3w // 2, h // 2 + 40), font, 0.5, (160, 160, 160), 1)

        # Progress bar during sampling
        if cal_state in (CAL_SAMPLING_CLOSED, CAL_SAMPLING_OPEN) and cal_progress > 0:
            bar_margin = w // 4
            bar_y = h // 2 + 50
            cv2.rectangle(overlay, (bar_margin, bar_y), (w - bar_margin, bar_y + 6), (60, 60, 60), -1)
            fill_w = int((w - 2 * bar_margin) * cal_progress)
            cv2.rectangle(overlay, (bar_margin, bar_y), (bar_margin + fill_w, bar_y + 6), accent, -1)

    # Blend overlay
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)


class HandTracker:
    """Reusable hand tracker. Runs webcam + MediaPipe, exposes throttle value.

    Can be used standalone (run_standalone) or polled from another loop
    (start_threaded / get_throttle).
    """

    def __init__(self):
        self._latest_result = [None]

        def on_result(result, image, timestamp_ms):
            self._latest_result[0] = result

        options = vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.LIVE_STREAM,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            result_callback=on_result,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

        self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            raise RuntimeError("Cannot open webcam")

        self.cal_state = CAL_WAITING_CLOSED
        self._closed_baseline = 1.0
        self._open_baseline = 2.0
        self._cal_samples = []
        self._smoothed_openness = 0.0

        # Thread-safe output
        import threading
        self._lock = threading.Lock()
        self._throttle = 0.0       # 0.0–1.0
        self._hand_found = False
        self._latest_frame = None  # annotated BGR frame for PiP display
        self._running = False

    def process_frame(self):
        """Grab one frame, run detection, update throttle. Returns (frame, hand_found, throttle_pct, dac_value) or None if no frame."""
        ret, frame = self._cap.read()
        if not ret:
            return None

        frame = cv2.flip(frame, 1)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        self._landmarker.detect_async(mp_image, int(time.time() * 1000))

        hand_found = False
        raw_openness = 0.0

        result = self._latest_result[0]
        if result and result.hand_landmarks:
            hand_found = True
            landmarks = result.hand_landmarks[0]
            raw_openness = compute_raw_openness(landmarks)

            # Draw hand skeleton
            h, w = frame.shape[:2]
            for connection in HAND_CONNECTIONS:
                start = landmarks[connection[0]]
                end = landmarks[connection[1]]
                pt1 = (int(start.x * w), int(start.y * h))
                pt2 = (int(end.x * w), int(end.y * h))
                cv2.line(frame, pt1, pt2, (0, 230, 180), 2, cv2.LINE_AA)
            # Fingertips — larger bright dots
            for idx in FINGERTIPS:
                lm = landmarks[idx]
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 7, (0, 255, 100), -1, cv2.LINE_AA)
                cv2.circle(frame, (cx, cy), 7, (255, 255, 255), 1, cv2.LINE_AA)
            # Wrist — accent
            wx, wy = int(landmarks[WRIST].x * w), int(landmarks[WRIST].y * h)
            cv2.circle(frame, (wx, wy), 6, (255, 180, 0), -1, cv2.LINE_AA)
            # Other joints — small dots
            skip = set(FINGERTIPS + [WRIST])
            for i, lm in enumerate(landmarks):
                if i in skip:
                    continue
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 3, (200, 200, 200), -1, cv2.LINE_AA)

        # Calibration
        if self.cal_state == CAL_SAMPLING_CLOSED:
            if hand_found:
                self._cal_samples.append(raw_openness)
            if len(self._cal_samples) >= CALIBRATION_FRAMES:
                self._closed_baseline = sum(self._cal_samples) / len(self._cal_samples)
                self._cal_samples.clear()
                self.cal_state = CAL_WAITING_OPEN
                print(f"  Closed baseline: {self._closed_baseline:.3f}")
        elif self.cal_state == CAL_SAMPLING_OPEN:
            if hand_found:
                self._cal_samples.append(raw_openness)
            if len(self._cal_samples) >= CALIBRATION_FRAMES:
                self._open_baseline = sum(self._cal_samples) / len(self._cal_samples)
                self._cal_samples.clear()
                self.cal_state = CAL_DONE
                print(f"  Open baseline: {self._open_baseline:.3f}")
                print("  Calibration complete!")

        # Compute throttle
        if not hand_found or self.cal_state != CAL_DONE:
            self._smoothed_openness = 0.0
            dac_value = 0
            throttle_pct = 0.0
        else:
            spread = self._open_baseline - self._closed_baseline
            if spread > 1e-6:
                normalized = (raw_openness - self._closed_baseline) / spread
            else:
                normalized = 0.0
            normalized = max(0.0, min(1.0, normalized))

            if normalized < CLOSED_FIST_THRESHOLD:
                self._smoothed_openness = 0.0
            else:
                self._smoothed_openness = EMA_ALPHA * normalized + (1 - EMA_ALPHA) * self._smoothed_openness

            dac_value = int(self._smoothed_openness * THROTTLE_CAP)
            throttle_pct = self._smoothed_openness

        # Calibration progress for UI
        cal_progress = 0.0
        if self.cal_state in (CAL_SAMPLING_CLOSED, CAL_SAMPLING_OPEN):
            cal_progress = len(self._cal_samples) / CALIBRATION_FRAMES

        # Draw full HUD overlay
        draw_overlay(frame, throttle_pct, dac_value, hand_found, self.cal_state, cal_progress)

        with self._lock:
            self._throttle = throttle_pct
            self._hand_found = hand_found
            self._latest_frame = frame.copy()

        return frame, hand_found, throttle_pct, dac_value

    def start_calibration(self):
        """Advance calibration state machine on C press."""
        if self.cal_state == CAL_WAITING_CLOSED:
            self.cal_state = CAL_SAMPLING_CLOSED
            self._cal_samples.clear()
            print("\n  Sampling fist...")
        elif self.cal_state == CAL_WAITING_OPEN:
            self.cal_state = CAL_SAMPLING_OPEN
            self._cal_samples.clear()
            print("  Sampling open hand...")
        elif self.cal_state == CAL_DONE:
            self.cal_state = CAL_WAITING_CLOSED
            self._smoothed_openness = 0.0
            print("\n  Re-calibrating...")

    def killswitch(self):
        self._smoothed_openness = 0.0
        with self._lock:
            self._throttle = 0.0

    def get_throttle(self):
        """Thread-safe read of current throttle (0.0–1.0) and hand_found."""
        with self._lock:
            return self._throttle, self._hand_found

    def get_frame(self):
        """Thread-safe read of latest annotated webcam frame (BGR numpy array or None)."""
        with self._lock:
            return self._latest_frame

    def get_status(self):
        """Thread-safe read of full status for external HUD rendering.
        Returns (throttle, hand_found, cal_state, cal_progress)."""
        with self._lock:
            progress = 0.0
            if self.cal_state in (CAL_SAMPLING_CLOSED, CAL_SAMPLING_OPEN):
                progress = len(self._cal_samples) / CALIBRATION_FRAMES
            return self._throttle, self._hand_found, self.cal_state, progress

    def start_threaded(self):
        """Run hand tracking in a background thread with its own OpenCV window."""
        import threading
        self._running = True
        t = threading.Thread(target=self._thread_loop, daemon=True)
        t.start()

    def _thread_loop(self):
        """Background loop: process frames, no GUI (macOS requires GUI on main thread)."""
        while self._running:
            result = self.process_frame()
            if result is None:
                break
            time.sleep(0.01)  # ~100Hz cap to avoid spinning

    def stop(self):
        self._running = False
        self._landmarker.close()
        self._cap.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Hand tracking throttle control")
    parser.add_argument("--no-serial", action="store_true", help="Run without Pico hardware")
    args = parser.parse_args()

    ser = None
    if not args.no_serial:
        ser = connect_pico()

    tracker = HandTracker()

    serial_status = "CONNECTED" if ser else "OFF (--no-serial)"
    print(f"Hand Throttle — Serial: {serial_status}")
    print("Press C to calibrate, K to kill, Q/ESC to quit")
    print("-" * 40)

    frame_idx = 0
    try:
        while True:
            result = tracker.process_frame()
            if result is None:
                break
            frame, hand_found, throttle_pct, dac_value = result

            if ser:
                send_to_pico(ser, dac_value)

            # Overlay already drawn by process_frame; add serial badge
            if ser:
                cv2.putText(frame, "SERIAL", (frame.shape[1] - 100, 32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            if frame_idx % 5 == 0:
                serial_tag = " [TX]" if ser else ""
                sys.stdout.write(
                    f"\ropenness={throttle_pct:.2f} dac={dac_value:4d} hand_found={hand_found}{serial_tag}   "
                )
                sys.stdout.flush()

            cv2.imshow("Hand Throttle", frame)
            frame_idx += 1

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
            elif key == ord('k') or key == ord('K'):
                tracker.killswitch()
                if ser:
                    for _ in range(5):
                        send_to_pico(ser, 0)
                print("\n  *** KILLSWITCH ***")
            elif key == ord('c') or key == ord('C'):
                tracker.start_calibration()

    finally:
        print("\nShutting down...")
        if ser:
            for _ in range(5):
                send_to_pico(ser, 0)
            ser.close()
            print("Serial closed. Safe defaults sent.")
        tracker.stop()


if __name__ == "__main__":
    main()
