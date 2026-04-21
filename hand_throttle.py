"""
Hand Tracking Throttle — Finger Direction Control
All fingers pointing up = climb. All pointing down = descend.
Fist = hover. Neon ray beams shoot from fingertips.
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
import random
import sys
import time

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision

# --- Constants ---

EMA_ALPHA = 0.3
NEUTRAL = 2048
DAC_MAX = 4095
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "hand_landmarker.task")

# Gesture detection
FIST_THRESHOLD = 1.3
FINGER_ANGLE_THRESHOLD = 45  # degrees from vertical

# Ray visuals (BGR)
RAY_CORE_WIDTH = 2
RAY_GLOW_WIDTH = 12
RAY_PULSE_HZ = 2.0
FLARE_RADIUS = 10
RAY_CORE_CLIMB = (0, 255, 120)
RAY_GLOW_CLIMB = (0, 180, 60)
RAY_CORE_DESCEND = (80, 120, 255)
RAY_GLOW_DESCEND = (40, 60, 200)
RAY_CORE_IDLE = (120, 120, 120)
RAY_GLOW_IDLE = (60, 60, 60)

# Joystick axis mapping (common gamepad layout)
JOY_AXIS_ROLL = 0     # left stick X
JOY_AXIS_PITCH = 1    # left stick Y
JOY_AXIS_YAW = 3      # right stick X
JOYSTICK_DEADZONE = 0.08

# Keyboard control (fallback when no joystick)
KB_STEP = 0.5         # axis deflection per key tap
KB_DECAY = 0.85       # per-frame decay toward neutral
ARROW_KEYS = {
    63232: 'up', 65362: 'up',      # macOS, Linux
    63233: 'down', 65364: 'down',
    63234: 'left', 65361: 'left',
    63235: 'right', 65363: 'right',
}

# Landmark indices
WRIST = 0
FIST_TIPS = [8, 12, 16, 20]       # index, middle, ring, pinky (for fist detection)
FIST_MCPS = [5, 9, 13, 17]
ALL_TIPS = [8, 12, 16, 20]         # index, middle, ring, pinky
ALL_BASES = [5, 9, 13, 17]        # MCPs for each

# Hand skeleton connections for drawing
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # index
    (0, 9), (9, 10), (10, 11), (11, 12),   # middle
    (0, 13), (13, 14), (14, 15), (15, 16), # ring
    (0, 17), (17, 18), (18, 19), (19, 20), # pinky
    (5, 9), (9, 13), (13, 17),             # palm
]

# Particle trails
MAX_PARTICLES = 200
PARTICLE_LIFETIME = 0.5
PARTICLE_SPEED = 150       # pixels per second
PARTICLES_PER_TIP = 3

# Palm-locked throttle arc
PALM_POP_DURATION = 0.3    # scale-pop entrance animation
PALM_ARC_RADIUS = 70
PALM_ARC_THICKNESS = 10

# Skeleton color wave
WAVE_DURATION = 0.4



# Zone colors (BGR)
CLIMB_COLOR = (0, 200, 80)
DESCEND_COLOR = (60, 60, 220)
HOVER_COLOR = (60, 220, 220)


def dist(a, b):
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def compute_raw_openness(landmarks):
    wrist = landmarks[WRIST]
    ratios = []
    for tip_idx, mcp_idx in zip(FIST_TIPS, FIST_MCPS):
        tip_dist = dist(landmarks[tip_idx], wrist)
        mcp_dist = dist(landmarks[mcp_idx], wrist)
        if mcp_dist > 1e-6:
            ratios.append(tip_dist / mcp_dist)
    return sum(ratios) / len(ratios) if ratios else 0.0


def palm_centroid(landmarks):
    """Center of palm — average of wrist + 4 MCP joints (not fingertips)."""
    palm_indices = [0, 5, 9, 13, 17]
    cx = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    cy = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)
    return cx, cy


def is_fist(landmarks):
    return compute_raw_openness(landmarks) < FIST_THRESHOLD


def fingers_direction(landmarks):
    """Check if all 5 fingers point up, all point down, or mixed.
    Returns 'up', 'down', or 'mixed'."""
    threshold_rad = math.radians(FINGER_ANGLE_THRESHOLD)
    ups = 0
    downs = 0

    for tip_idx, base_idx in zip(ALL_TIPS, ALL_BASES):
        tip = landmarks[tip_idx]
        base = landmarks[base_idx]
        dx = tip.x - base.x
        dy = tip.y - base.y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            return "mixed"

        angle_from_up = math.atan2(abs(dx), -dy)
        angle_from_down = math.atan2(abs(dx), dy)

        if angle_from_up < threshold_rad:
            ups += 1
        elif angle_from_down < threshold_rad:
            downs += 1

    if ups == 4:
        return "up"
    if downs == 4:
        return "down"
    return "mixed"


def compute_direction_dac(direction):
    """Map finger direction to (dac_value, zone, intensity)."""
    if direction == "up":
        return DAC_MAX, "climb", 1.0
    elif direction == "down":
        return 0, "descend", 1.0
    else:
        return NEUTRAL, "hover", 0.0


def _ray_segments(landmarks, w, h):
    """Precompute ray start/end points for all 5 fingers."""
    rays = []
    for tip_idx, base_idx in zip(ALL_TIPS, ALL_BASES):
        tip = landmarks[tip_idx]
        base = landmarks[base_idx]
        tx, ty = int(tip.x * w), int(tip.y * h)
        bx, by = int(base.x * w), int(base.y * h)
        dx, dy = tx - bx, ty - by
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            continue
        ndx, ndy = dx / length, dy / length

        t_x = ((w - tx) / ndx) if ndx > 0 else ((-tx / ndx) if ndx < 0 else float('inf'))
        t_y = ((h - ty) / ndy) if ndy > 0 else ((-ty / ndy) if ndy < 0 else float('inf'))
        ray_t = max(0, min(t_x, t_y))

        ex, ey = int(tx + ndx * ray_t), int(ty + ndy * ray_t)
        rays.append(((tx, ty), (ex, ey)))
    return rays


def draw_finger_rays(frame, landmarks, zone, t):
    """Draw neon ray beams from all 5 fingertips in their pointing direction."""
    h, w = frame.shape[:2]

    if zone == "climb":
        core_color, glow_color = RAY_CORE_CLIMB, RAY_GLOW_CLIMB
    elif zone == "descend":
        core_color, glow_color = RAY_CORE_DESCEND, RAY_GLOW_DESCEND
    else:
        core_color, glow_color = RAY_CORE_IDLE, RAY_GLOW_IDLE

    pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi * RAY_PULSE_HZ)
    glow_alpha = 0.25 + 0.35 * pulse

    rays = _ray_segments(landmarks, w, h)

    # Glow pass (blended overlay)
    overlay = frame.copy()
    for start, end in rays:
        cv2.line(overlay, start, end, glow_color, RAY_GLOW_WIDTH, cv2.LINE_AA)
        cv2.circle(overlay, start, FLARE_RADIUS, glow_color, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, glow_alpha, frame, 1 - glow_alpha, 0, frame)

    # Core pass (full brightness, drawn directly)
    for start, end in rays:
        cv2.line(frame, start, end, core_color, RAY_CORE_WIDTH, cv2.LINE_AA)
        cv2.circle(frame, start, 5, core_color, -1, cv2.LINE_AA)
        cv2.circle(frame, start, 7, (255, 255, 255), 1, cv2.LINE_AA)


def _zone_color(zone):
    if zone == "climb":
        return CLIMB_COLOR
    elif zone == "descend":
        return DESCEND_COLOR
    return HOVER_COLOR


def _lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def spawn_particles(particles, landmarks, zone, w, h):
    """Spawn spark particles from each fingertip."""
    color = _zone_color(zone)
    for tip_idx, base_idx in zip(ALL_TIPS, ALL_BASES):
        tip = landmarks[tip_idx]
        base = landmarks[base_idx]
        tx, ty = tip.x * w, tip.y * h
        dx, dy = tip.x - base.x, tip.y - base.y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            continue
        ndx, ndy = dx / length, dy / length
        base_angle = math.atan2(ndy, ndx)
        for _ in range(PARTICLES_PER_TIP):
            spread = math.radians(random.uniform(-15, 15))
            angle = base_angle + spread
            speed = PARTICLE_SPEED * random.uniform(0.6, 1.0)
            particles.append({
                'x': tx, 'y': ty,
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed,
                'life': PARTICLE_LIFETIME,
                'max_life': PARTICLE_LIFETIME,
                'size': random.uniform(2.0, 4.0),
                'color': color,
            })
    # Cap pool
    if len(particles) > MAX_PARTICLES:
        del particles[:len(particles) - MAX_PARTICLES]


def update_and_draw_particles(frame, particles, dt):
    """Update particle physics and draw them."""
    alive = []
    for p in particles:
        p['life'] -= dt
        if p['life'] <= 0:
            continue
        p['x'] += p['vx'] * dt
        p['y'] += p['vy'] * dt
        alive.append(p)

    particles[:] = alive

    for p in particles:
        frac = p['life'] / p['max_life']
        r = max(1, int(p['size'] * frac))
        c = tuple(int(v * frac) for v in p['color'])
        cv2.circle(frame, (int(p['x']), int(p['y'])), r, c, -1, cv2.LINE_AA)


def _pop_scale(t, duration):
    """Scale pop easing: 0 -> 1.1 -> 1.0 over duration."""
    if t >= duration:
        return 1.0
    p = t / duration
    if p < 0.6:
        return (p / 0.6) * 1.1
    else:
        return 1.1 - 0.1 * ((p - 0.6) / 0.4)


def draw_palm_throttle(overlay, landmarks, zone, throttle_pct, w, h, scale=1.0):
    """Draw 360° throttle ring with % text locked to palm centroid."""
    if scale < 0.01:
        return
    cx_n, cy_n = palm_centroid(landmarks)
    cx, cy = int(cx_n * w), int(cy_n * h)
    color = _zone_color(zone)
    r = max(1, int(PALM_ARC_RADIUS * scale))
    t = max(1, int(PALM_ARC_THICKNESS * scale))
    font = cv2.FONT_HERSHEY_SIMPLEX

    # Solid white disc inside the ring
    disc_r = max(1, r - t // 2)
    cv2.circle(overlay, (cx, cy), disc_r, (255, 255, 255), -1, cv2.LINE_AA)

    # Background ring (dim gray, full 360°)
    cv2.ellipse(overlay, (cx, cy), (r, r), 0, 0, 360, (40, 40, 40), t, cv2.LINE_AA)

    # Fill arc — deviation from neutral, sweeps clockwise from 12 o'clock
    deviation = abs(throttle_pct - 0.5) * 2.0
    if deviation > 0.01:
        sweep = int(360 * deviation)
        cv2.ellipse(overlay, (cx, cy), (r, r), -90, 0, sweep, color, t, cv2.LINE_AA)

    # % text centered inside ring (skip when too small to read)
    if scale >= 0.3:
        font_scale = 1.2 * scale
        font_thick = max(1, int(3 * scale))
        pct_text = f"{int(throttle_pct * 100)}"
        (tw, th), _ = cv2.getTextSize(pct_text, font, font_scale, font_thick)
        cv2.putText(overlay, pct_text, (cx - tw // 2, cy + th // 3), font, font_scale, (0, 0, 0), font_thick)
        pct_font_scale = 0.5 * scale
        pct_font_thick = max(1, int(1 * scale))
        (pw, ph), _ = cv2.getTextSize("%", font, pct_font_scale, pct_font_thick)
        cv2.putText(overlay, "%", (cx - pw // 2, cy + th // 3 + int(22 * scale)), font, pct_font_scale, (100, 100, 100), pct_font_thick)



def draw_skeleton_with_wave(frame, landmarks, zone, prev_zone, wave_progress, w, h):
    """Draw hand skeleton with color wave transition."""
    new_color = _zone_color(zone)
    old_color = _zone_color(prev_zone)

    # Precompute wrist position for distance calc
    wx, wy = landmarks[WRIST].x, landmarks[WRIST].y

    for connection in HAND_CONNECTIONS:
        a, b = landmarks[connection[0]], landmarks[connection[1]]
        pt1 = (int(a.x * w), int(a.y * h))
        pt2 = (int(b.x * w), int(b.y * h))

        if wave_progress >= 1.0:
            seg_color = new_color
        else:
            # Midpoint distance from wrist (normalized 0-1)
            mid_x = (a.x + b.x) / 2
            mid_y = (a.y + b.y) / 2
            bone_dist = math.sqrt((mid_x - wx) ** 2 + (mid_y - wy) ** 2)
            # Normalize: max hand span is roughly 0.3 in landmark coords
            bone_norm = min(1.0, bone_dist / 0.3)
            # Wave front: bones closer to wrist change first
            t = max(0.0, min(1.0, (wave_progress * 1.5 - bone_norm)))
            seg_color = _lerp_color(old_color, new_color, t)

        cv2.line(frame, pt1, pt2, seg_color, 2, cv2.LINE_AA)

    # Draw landmark dots with new color (always current)
    dot_color = new_color if wave_progress >= 1.0 else _lerp_color(old_color, new_color, wave_progress)
    for idx in ALL_TIPS + [4]:
        lm = landmarks[idx]
        cx, cy = int(lm.x * w), int(lm.y * h)
        cv2.circle(frame, (cx, cy), 7, dot_color, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 7, (255, 255, 255), 1, cv2.LINE_AA)
    # Wrist dot
    wx_px, wy_px = int(landmarks[WRIST].x * w), int(landmarks[WRIST].y * h)
    cv2.circle(frame, (wx_px, wy_px), 6, (255, 180, 0), -1, cv2.LINE_AA)



def draw_hud_overlay(frame, dac_value, throttle_pct, hand_found, zone, fist_state):
    """Draw HUD: status badge, DAC readout, throttle arc."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX

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

    # Blend
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)


def draw_input_overlay(frame, yaw_dac, pitch_dac, roll_dac, label="KEYBOARD"):
    font = cv2.FONT_HERSHEY_SIMPLEX
    y0 = 55
    cv2.putText(frame, label, (15, y0), font, 0.45, (0, 200, 255), 1)
    cv2.putText(frame, f"YAW  {yaw_dac:4d}", (15, y0 + 18), font, 0.4, (180, 180, 180), 1)
    cv2.putText(frame, f"PTCH {pitch_dac:4d}", (15, y0 + 36), font, 0.4, (180, 180, 180), 1)
    cv2.putText(frame, f"ROLL {roll_dac:4d}", (15, y0 + 54), font, 0.4, (180, 180, 180), 1)


def init_joystick():
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
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def axis_to_dac(value):
    clamped = max(-1.0, min(1.0, value))
    return max(0, min(DAC_MAX, int(NEUTRAL + clamped * NEUTRAL)))


def find_pico_port():
    import serial.tools.list_ports
    for port in serial.tools.list_ports.comports():
        if "usbmodem" in port.device.lower() or "pico" in port.description.lower():
            return port.device
    print("Available ports:")
    for port in serial.tools.list_ports.comports():
        print(f"  {port.device} - {port.description}")
    return None


def connect_pico():
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
    cmd = f"{throttle_dac},{yaw_dac},{pitch_dac},{roll_dac}\n"
    ser.write(cmd.encode())
    ser.flush()
    while ser.in_waiting:
        ser.read(ser.in_waiting)


def read_joystick(joy):
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
    pitch_dac = axis_to_dac(apply_deadzone(-raw_pitch))
    yaw_dac = axis_to_dac(apply_deadzone(raw_yaw))
    return yaw_dac, pitch_dac, roll_dac


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
        self._killed = False

        # Demo animation state
        self._particles = []
        self._prev_zone = "hover"
        self._zone_change_time = 0.0
        self._prev_frame_time = time.time()
        self._palm_appear_time = 0.0
        self._prev_hand_found = False

        import threading
        self._lock = threading.Lock()
        self._throttle = 0.5
        self._hand_found = False
        self._latest_frame = None
        self._running = False

    def process_frame(self):
        """Grab one frame, run finger-direction throttle. Returns (frame, hand_found, throttle_pct, dac_value) or None."""
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
        direction = "mixed"

        if landmarks is not None:
            hand_found = True
            fist_state = is_fist(landmarks)
            if not fist_state:
                direction = fingers_direction(landmarks)

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
            dac_value, zone, intensity = compute_direction_dac(direction)

        # EMA smooth
        self._smoothed_dac = EMA_ALPHA * dac_value + (1 - EMA_ALPHA) * self._smoothed_dac
        dac_value = int(self._smoothed_dac)
        dac_value = max(0, min(DAC_MAX, dac_value))
        throttle_pct = dac_value / DAC_MAX

        # Detect zone change
        now = time.time()
        dt = now - self._prev_frame_time
        self._prev_frame_time = now

        if zone != self._zone:
            self._prev_zone = self._zone
            self._zone_change_time = now
        self._zone = zone
        self._intensity = intensity

        # Detect hand entry edge for pop animation
        if hand_found and not self._prev_hand_found:
            self._palm_appear_time = now
        self._prev_hand_found = hand_found

        h, w = frame.shape[:2]

        if landmarks is not None:
            # 1. Skeleton with color wave
            wave_elapsed = now - self._zone_change_time
            wave_progress = min(1.0, wave_elapsed / WAVE_DURATION) if self._zone_change_time > 0 else 1.0
            if fist_state:
                # Fist: solid hover color, no wave
                draw_skeleton_with_wave(frame, landmarks, "hover", "hover", 1.0, w, h)
            else:
                draw_skeleton_with_wave(frame, landmarks, zone, self._prev_zone, wave_progress, w, h)

            # 2. Finger rays (existing — skip for fist)
            if not fist_state:
                draw_finger_rays(frame, landmarks, zone, now)

            # 3. Particle trails
            if not fist_state:
                spawn_particles(self._particles, landmarks, zone, w, h)
            update_and_draw_particles(frame, self._particles, dt)

            # 4. Palm throttle ring with scale-pop entrance (overlay pass)
            pop_elapsed = now - self._palm_appear_time
            scale = _pop_scale(pop_elapsed, PALM_POP_DURATION)
            overlay = frame.copy()
            draw_palm_throttle(overlay, landmarks, zone, throttle_pct, w, h, scale=scale)
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

        else:
            # No hand — still update particles (they fade out)
            update_and_draw_particles(frame, self._particles, dt)

        # 6. HUD overlay (always last)
        draw_hud_overlay(frame, dac_value, throttle_pct, hand_found, zone, fist_state)

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
        with self._lock:
            return self._throttle, self._hand_found

    def get_frame(self):
        with self._lock:
            return self._latest_frame

    def get_status(self):
        with self._lock:
            return self._throttle, self._hand_found, self._zone, self._intensity

    def start_threaded(self):
        import threading
        self._running = True
        t = threading.Thread(target=self._thread_loop, daemon=True)
        t.start()

    def _thread_loop(self):
        while self._running:
            result = self.process_frame()
            if result is None:
                break
            time.sleep(0.01)

    def stop(self):
        self._running = False
        self._landmarker.close()
        self._cap.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Hand tracking throttle control")
    parser.add_argument("--no-serial", action="store_true", help="Run without Pico hardware")
    parser.add_argument("--no-joystick", action="store_true",
                        help="Skip joystick, send neutral yaw/pitch/roll")
    args = parser.parse_args()

    ser = None
    if not args.no_serial:
        ser = connect_pico()

    joy = None
    if not args.no_joystick:
        joy = init_joystick()
        if joy is None:
            print("No joystick found — using keyboard for yaw/pitch/roll")

    tracker = HandTracker()

    serial_status = "CONNECTED" if ser else "OFF (--no-serial)"
    input_mode = joy.get_name() if joy else "KEYBOARD"
    print(f"Hand Throttle (Finger Direction) — Serial: {serial_status}, Input: {input_mode}")
    print("Fingers up = climb | Fingers down = descend | Fist = hover")
    if not joy:
        print("A/D = yaw | Up/Down = pitch | Left/Right = roll")
    print("K = killswitch | Q/ESC = quit")
    print("-" * 65)

    kb_yaw = 0.0
    kb_pitch = 0.0
    kb_roll = 0.0

    frame_idx = 0
    try:
        while True:
            result = tracker.process_frame()
            if result is None:
                break
            frame, hand_found, throttle_pct, dac_value = result

            kb_yaw *= KB_DECAY
            kb_pitch *= KB_DECAY
            kb_roll *= KB_DECAY

            if joy:
                yaw_dac, pitch_dac, roll_dac = read_joystick(joy)
            else:
                yaw_dac = axis_to_dac(kb_yaw)
                pitch_dac = axis_to_dac(kb_pitch)
                roll_dac = axis_to_dac(kb_roll)

            if ser:
                send_to_pico(ser, dac_value, yaw_dac, pitch_dac, roll_dac)

            draw_input_overlay(frame, yaw_dac, pitch_dac, roll_dac,
                               label="JOYSTICK" if joy else "KEYBOARD")

            if ser:
                cv2.putText(frame, "SERIAL", (frame.shape[1] - 100, 52),
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

            key = cv2.waitKeyEx(1)
            key_chr = key & 0xFF
            arrow = ARROW_KEYS.get(key)

            if key_chr == ord('q') or key_chr == 27:
                break
            elif key_chr == ord('k') or key_chr == ord('K'):
                tracker.killswitch()
                if ser:
                    for _ in range(5):
                        send_to_pico(ser, 0, NEUTRAL, NEUTRAL, NEUTRAL)
                print("\n  *** KILLSWITCH ***")
            elif not joy:
                if key_chr == ord('a'):
                    kb_yaw = max(-1.0, kb_yaw - KB_STEP)
                elif key_chr == ord('d'):
                    kb_yaw = min(1.0, kb_yaw + KB_STEP)
                elif arrow == 'up':
                    kb_pitch = min(1.0, kb_pitch + KB_STEP)
                elif arrow == 'down':
                    kb_pitch = max(-1.0, kb_pitch - KB_STEP)
                elif arrow == 'left':
                    kb_roll = max(-1.0, kb_roll - KB_STEP)
                elif arrow == 'right':
                    kb_roll = min(1.0, kb_roll + KB_STEP)

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
