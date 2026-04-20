"""
Hand Tracking Throttle — Zone Control
Webcam divided into top/bottom zones. Fist = hover. Open hand in top half
= climb, bottom half = descend. Intensity by distance from midline.
No calibration needed — start flying immediately.

Controls:
  K - killswitch (immediate throttle 0)
  Q / ESC - quit

Usage:
  python hand_throttle.py                            # with Pico + joystick
  python hand_throttle.py --no-serial                # no Pico hardware
  python hand_throttle.py --no-joystick              # neutral yaw/pitch/roll
  python hand_throttle.py --no-serial --no-joystick  # prototype mode

Requires: pip install mediapipe opencv-python pyserial pygame
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
import random

EMA_ALPHA = 0.3
NEUTRAL = 2048
DAC_MAX = 4095
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "hand_landmarker.task")

# Zone control
FIST_THRESHOLD = 1.3      # raw openness below this = fist → hover
DEADZONE_HALF = 0.08      # ±8% of frame height around midline
PARTICLE_COUNT = 50        # drifting HUD particles

# Joystick axis mapping (common gamepad layout)
JOY_AXIS_ROLL = 0     # left stick X
JOY_AXIS_PITCH = 1    # left stick Y
JOY_AXIS_YAW = 3      # right stick X
JOYSTICK_DEADZONE = 0.08

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


# Zone colors (BGR)
CLIMB_COLOR = (0, 200, 80)
DESCEND_COLOR = (60, 60, 220)
HOVER_COLOR = (60, 220, 220)


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


def palm_centroid(landmarks):
    """Mean x, y of all 21 landmarks in normalized [0,1] coords."""
    cx = sum(lm.x for lm in landmarks) / len(landmarks)
    cy = sum(lm.y for lm in landmarks) / len(landmarks)
    return cx, cy


def is_fist(landmarks):
    return compute_raw_openness(landmarks) < FIST_THRESHOLD


def compute_zone_dac(palm_cy, fist):
    """Map palm y-position + fist state to (dac_value, zone, intensity).
    zone: 'climb'|'descend'|'hover'|'deadzone'. intensity: 0..1."""
    if fist:
        return NEUTRAL, "hover", 0.0

    top_edge = 0.5 - DEADZONE_HALF
    bot_edge = 0.5 + DEADZONE_HALF

    if palm_cy < top_edge:
        intensity = min(1.0, (top_edge - palm_cy) / top_edge)
        dac = int(NEUTRAL + intensity * (DAC_MAX - NEUTRAL))
        return min(DAC_MAX, dac), "climb", intensity
    elif palm_cy > bot_edge:
        intensity = min(1.0, (palm_cy - bot_edge) / (1.0 - bot_edge))
        dac = int(NEUTRAL - intensity * NEUTRAL)
        return max(0, dac), "descend", intensity
    else:
        return NEUTRAL, "deadzone", 0.0


def _init_particles():
    """Create a pool of particles for the drifting effect."""
    return [{"x": random.random(), "y": random.random(), "r": random.uniform(1.5, 3.5)}
            for _ in range(PARTICLE_COUNT)]


def _step_particles(particles, zone, intensity, dt=0.033):
    """Advance particle positions. Drift up in top zone, down in bottom zone."""
    base_speed = intensity * 0.6
    for p in particles:
        if zone == "climb":
            p["y"] -= base_speed * dt * random.uniform(0.5, 1.5)
            if p["y"] < 0:
                p["y"] = 1.0
                p["x"] = random.random()
        elif zone == "descend":
            p["y"] += base_speed * dt * random.uniform(0.5, 1.5)
            if p["y"] > 1:
                p["y"] = 0.0
                p["x"] = random.random()


def init_joystick():
    """Initialize pygame joystick subsystem, return first joystick or None."""
    import pygame
    if not pygame.get_init():
        pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        return None
    joy = pygame.joystick.Joystick(0)
    joy.init()
    print(f"Joystick: {joy.get_name()} ({joy.get_numaxes()} axes, {joy.get_numbuttons()} buttons)")
    return joy


def apply_deadzone(value, deadzone=JOYSTICK_DEADZONE):
    """Apply deadzone and rescale axis value from -1..1."""
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def axis_to_dac(value):
    """Map axis (-1..1) to DAC (0..4095) centered on NEUTRAL."""
    clamped = max(-1.0, min(1.0, value))
    return max(0, min(DAC_MAX, int(NEUTRAL + clamped * NEUTRAL)))


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


def send_to_pico(ser, throttle_dac, yaw_dac=NEUTRAL, pitch_dac=NEUTRAL, roll_dac=NEUTRAL):
    """Send throttle,yaw,pitch,roll to Pico. Drain read buffer."""
    cmd = f"{throttle_dac},{yaw_dac},{pitch_dac},{roll_dac}\n"
    ser.write(cmd.encode())
    ser.flush()
    while ser.in_waiting:
        ser.read(ser.in_waiting)


def draw_zone_overlay(frame, dac_value, throttle_pct, hand_found, zone, intensity,
                      particles, palm_pos=None, fist_state=False):
    """Draw zone-based HUD: tints, midline, particles, arrow, status, DAC arc."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    mid_y = h // 2
    dz_top = int(h * (0.5 - DEADZONE_HALF))
    dz_bot = int(h * (0.5 + DEADZONE_HALF))

    # --- Zone tints ---
    green_tint = overlay[:dz_top].copy()
    green_tint[:] = (green_tint * 0.85 + [0, 25, 0]).clip(0, 255).astype("uint8")
    overlay[:dz_top] = green_tint
    red_tint = overlay[dz_bot:].copy()
    red_tint[:] = (red_tint * 0.85 + [0, 0, 25]).clip(0, 255).astype("uint8")
    overlay[dz_bot:] = red_tint

    # Midline
    cv2.line(overlay, (0, mid_y), (w, mid_y), (255, 255, 255), 1, cv2.LINE_AA)
    # Deadzone boundary dashes
    for x in range(0, w, 20):
        cv2.line(overlay, (x, dz_top), (min(x + 10, w), dz_top), (120, 120, 120), 1)
        cv2.line(overlay, (x, dz_bot), (min(x + 10, w), dz_bot), (120, 120, 120), 1)

    # --- Drifting particles ---
    for p in particles:
        px = int(p["x"] * w)
        py = int(p["y"] * h)
        pr = int(p["r"])
        if zone == "climb" and p["y"] < 0.5:
            brightness = min(255, int(80 + 175 * intensity))
            color = (0, brightness, int(brightness * 0.4))
        elif zone == "descend" and p["y"] > 0.5:
            brightness = min(255, int(80 + 175 * intensity))
            color = (int(brightness * 0.3), int(brightness * 0.3), brightness)
        else:
            color = (50, 50, 50)
        cv2.circle(overlay, (px, py), pr, color, -1, cv2.LINE_AA)

    # --- Direction arrow (near hand) ---
    if palm_pos and zone in ("climb", "descend"):
        ax = int(palm_pos[0] * w) + 60
        ay = int(palm_pos[1] * h)
        arrow_size = int(15 + 25 * intensity)
        arrow_color = CLIMB_COLOR if zone == "climb" else DESCEND_COLOR
        if zone == "climb":
            pts = [(ax, ay - arrow_size), (ax - arrow_size // 2, ay), (ax + arrow_size // 2, ay)]
        else:
            pts = [(ax, ay + arrow_size), (ax - arrow_size // 2, ay), (ax + arrow_size // 2, ay)]
        import numpy as np
        cv2.fillPoly(overlay, [np.array(pts)], arrow_color)

    # --- Status badge (top-left) ---
    if not hand_found:
        badge_color = (60, 60, 220)
        badge_text = "NO HAND"
    elif fist_state:
        badge_color = HOVER_COLOR
        badge_text = "FIST  HOVER"
    elif zone == "climb":
        badge_color = CLIMB_COLOR
        badge_text = "CLIMB"
    elif zone == "descend":
        badge_color = DESCEND_COLOR
        badge_text = "DESCEND"
    else:
        badge_color = HOVER_COLOR
        badge_text = "HOVER"

    badge_w = 160
    badge_h = 32
    cv2.rectangle(overlay, (12, 10), (12 + badge_w, 10 + badge_h), badge_color, -1)
    cv2.rectangle(overlay, (12, 10), (12 + badge_w, 10 + badge_h), (255, 255, 255), 1)
    (btw, bth), _ = cv2.getTextSize(badge_text, font, 0.55, 2)
    cv2.putText(overlay, badge_text,
                (12 + (badge_w - btw) // 2, 10 + (badge_h + bth) // 2),
                font, 0.55, (255, 255, 255), 2)

    # --- DAC readout (top-right) ---
    cv2.putText(overlay, f"DAC {dac_value}", (w - 150, 32), font, 0.6, (0, 255, 255), 2)

    # --- Throttle arc (bottom-right) ---
    arc_cx = w - 80
    arc_cy = h - 80
    arc_r = 55
    arc_t = 12
    cv2.ellipse(overlay, (arc_cx, arc_cy), (arc_r, arc_r), 0, 135, 405, (40, 40, 40), arc_t)
    if throttle_pct > 0.01:
        fill_angle = 135 + int(270 * throttle_pct)
        arc_color = CLIMB_COLOR if zone == "climb" else DESCEND_COLOR if zone == "descend" else HOVER_COLOR
        cv2.ellipse(overlay, (arc_cx, arc_cy), (arc_r, arc_r), 0, 135, fill_angle, arc_color, arc_t)
    pct_text = f"{int(throttle_pct * 100)}"
    (tw, th), _ = cv2.getTextSize(pct_text, font, 1.2, 3)
    cv2.putText(overlay, pct_text, (arc_cx - tw // 2, arc_cy + th // 3), font, 1.2, (255, 255, 255), 3)
    cv2.putText(overlay, "%", (arc_cx - 8, arc_cy + th // 3 + 22), font, 0.5, (180, 180, 180), 1)

    # Blend
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)


def draw_joystick_overlay(frame, yaw_dac, pitch_dac, roll_dac, joy_connected):
    """Draw joystick channel readouts on the webcam frame."""
    if not joy_connected:
        return
    font = cv2.FONT_HERSHEY_SIMPLEX
    y0 = 55
    cv2.putText(frame, "JOYSTICK", (15, y0), font, 0.45, (0, 200, 255), 1)
    cv2.putText(frame, f"YAW  {yaw_dac:4d}", (15, y0 + 18), font, 0.4, (180, 180, 180), 1)
    cv2.putText(frame, f"PTCH {pitch_dac:4d}", (15, y0 + 36), font, 0.4, (180, 180, 180), 1)
    cv2.putText(frame, f"ROLL {roll_dac:4d}", (15, y0 + 54), font, 0.4, (180, 180, 180), 1)


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
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            result_callback=on_result,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

        self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            raise RuntimeError("Cannot open webcam")

        self._smoothed_dac = float(NEUTRAL)
        self._zone = "hover"
        self._intensity = 0.0
        self._particles = _init_particles()
        self._killed = False

        import threading
        self._lock = threading.Lock()
        self._throttle = 0.5       # 0.0=descent, 0.5=hover, 1.0=climb
        self._hand_found = False
        self._latest_frame = None
        self._running = False

    def process_frame(self):
        """Grab one frame, run zone-based throttle. Returns (frame, hand_found, throttle_pct, dac_value) or None."""
        ret, frame = self._cap.read()
        if not ret:
            return None

        frame = cv2.flip(frame, 1)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        self._landmarker.detect_async(mp_image, int(time.time() * 1000))

        # Find right hand only
        hand_found = False
        landmarks = None
        result = self._latest_result[0]
        if result and result.hand_landmarks:
            for lm in result.hand_landmarks:
                if lm[0].x >= 0.5:
                    landmarks = lm
                    break

        fist_state = False
        palm_pos = None

        if landmarks is not None:
            hand_found = True
            fist_state = is_fist(landmarks)
            palm_pos = palm_centroid(landmarks)

            # Draw skeleton with zone-appropriate color
            skel_color = HOVER_COLOR if fist_state else (
                CLIMB_COLOR if self._zone == "climb" else
                DESCEND_COLOR if self._zone == "descend" else HOVER_COLOR)
            h, w = frame.shape[:2]
            for connection in HAND_CONNECTIONS:
                a, b = landmarks[connection[0]], landmarks[connection[1]]
                pt1 = (int(a.x * w), int(a.y * h))
                pt2 = (int(b.x * w), int(b.y * h))
                cv2.line(frame, pt1, pt2, skel_color, 2, cv2.LINE_AA)
            for idx in FINGERTIPS:
                lm = landmarks[idx]
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 7, skel_color, -1, cv2.LINE_AA)
                cv2.circle(frame, (cx, cy), 7, (255, 255, 255), 1, cv2.LINE_AA)
            wx, wy = int(landmarks[WRIST].x * w), int(landmarks[WRIST].y * h)
            cv2.circle(frame, (wx, wy), 6, (255, 180, 0), -1, cv2.LINE_AA)

        # Compute DAC
        if self._killed:
            dac_value = 0
            zone = "hover"
            intensity = 0.0
        elif not hand_found:
            dac_value = NEUTRAL
            zone = "hover"
            intensity = 0.0
        elif fist_state:
            dac_value = NEUTRAL
            zone = "hover"
            intensity = 0.0
        else:
            dac_value, zone, intensity = compute_zone_dac(palm_pos[1], False)

        # EMA smooth
        self._smoothed_dac = EMA_ALPHA * dac_value + (1 - EMA_ALPHA) * self._smoothed_dac
        dac_value = int(self._smoothed_dac)
        dac_value = max(0, min(DAC_MAX, dac_value))
        throttle_pct = dac_value / DAC_MAX

        self._zone = zone
        self._intensity = intensity

        # Animate particles
        _step_particles(self._particles, zone, intensity)

        # Draw zone HUD
        draw_zone_overlay(frame, dac_value, throttle_pct, hand_found, zone, intensity,
                          self._particles, palm_pos, fist_state)

        with self._lock:
            self._throttle = throttle_pct
            self._hand_found = hand_found
            self._latest_frame = frame.copy()

        return frame, hand_found, throttle_pct, dac_value

    def killswitch(self):
        self._smoothed_dac = 0.0
        self._killed = True
        with self._lock:
            self._throttle = 0.0

    def get_throttle(self):
        """Thread-safe. Returns (throttle_pct, hand_found). throttle_pct: 0.0=descent, 0.5=hover, 1.0=climb."""
        with self._lock:
            return self._throttle, self._hand_found

    def get_frame(self):
        with self._lock:
            return self._latest_frame

    def get_status(self):
        """Returns (throttle, hand_found, zone, intensity)."""
        with self._lock:
            return self._throttle, self._hand_found, self._zone, self._intensity

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


def read_joystick(joy):
    """Read joystick axes and return (yaw_dac, pitch_dac, roll_dac)."""
    import pygame
    pygame.event.pump()

    raw_roll = joy.get_axis(JOY_AXIS_ROLL)
    raw_pitch = joy.get_axis(JOY_AXIS_PITCH)
    raw_yaw = 0.0
    if joy.get_numaxes() > JOY_AXIS_YAW:
        raw_yaw = joy.get_axis(JOY_AXIS_YAW)
    elif joy.get_numaxes() > 2:
        raw_yaw = joy.get_axis(2)

    roll_dac = axis_to_dac(apply_deadzone(raw_roll))
    pitch_dac = axis_to_dac(apply_deadzone(-raw_pitch))  # invert Y axis
    yaw_dac = axis_to_dac(apply_deadzone(raw_yaw))
    return yaw_dac, pitch_dac, roll_dac


def main():
    parser = argparse.ArgumentParser(description="Hand tracking throttle control")
    parser.add_argument("--no-serial", action="store_true", help="Run without Pico hardware")
    parser.add_argument("--no-joystick", action="store_true",
                        help="Skip joystick, send neutral yaw/pitch/roll")
    args = parser.parse_args()

    ser = None
    if not args.no_serial:
        ser = connect_pico()

    # Joystick init (pygame subsystem only, no display window)
    joy = None
    if not args.no_joystick:
        joy = init_joystick()
        if joy is None:
            print("No joystick found — yaw/pitch/roll will stay at neutral")

    tracker = HandTracker()

    serial_status = "CONNECTED" if ser else "OFF (--no-serial)"
    joy_status = joy.get_name() if joy else "NONE"
    print(f"Hand Throttle (Zone Control) — Serial: {serial_status}, Joystick: {joy_status}")
    print("Fist = hover | Open hand top half = climb | Open hand bottom half = descend")
    print("Right hand only. Press K to kill, Q/ESC to quit")
    print("-" * 65)

    frame_idx = 0
    try:
        while True:
            result = tracker.process_frame()
            if result is None:
                break
            frame, hand_found, throttle_pct, dac_value = result

            # Read joystick for yaw/pitch/roll
            yaw_dac = NEUTRAL
            pitch_dac = NEUTRAL
            roll_dac = NEUTRAL
            if joy:
                yaw_dac, pitch_dac, roll_dac = read_joystick(joy)

            if ser:
                send_to_pico(ser, dac_value, yaw_dac, pitch_dac, roll_dac)

            # Draw joystick overlay on frame
            draw_joystick_overlay(frame, yaw_dac, pitch_dac, roll_dac, joy is not None)

            # Serial badge
            if ser:
                cv2.putText(frame, "SERIAL", (frame.shape[1] - 100, 32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            if frame_idx % 5 == 0:
                serial_tag = " [TX]" if ser else ""
                _, _, zone, intensity = tracker.get_status()
                sys.stdout.write(
                    f"\rzone={zone:<8} i={intensity:.2f} T={dac_value:4d} Y={yaw_dac:4d} P={pitch_dac:4d} R={roll_dac:4d}{serial_tag}   "
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
                        send_to_pico(ser, 0, NEUTRAL, NEUTRAL, NEUTRAL)
                print("\n  *** KILLSWITCH ***")

    finally:
        print("\nShutting down...")
        if ser:
            for _ in range(5):
                send_to_pico(ser, 0, NEUTRAL, NEUTRAL, NEUTRAL)
            ser.close()
            print("Serial closed. Safe defaults sent.")
        tracker.stop()
        if joy:
            import pygame
            pygame.quit()


if __name__ == "__main__":
    main()
