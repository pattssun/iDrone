"""iDrone: Phone-controlled drone simulator. Entry point and main loop.

Usage:
  python main.py          # phone gyro control
  python main.py --hand   # hand tracking throttle + joystick pitch/roll/yaw
"""

import argparse
import sys
import time

import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

import config
from tracker import TrackingResult
from controls import ControlMapper, DroneCommand
from drone_interface import SimulatorAdapter
from renderer import Renderer
from dashboard import Dashboard
from phone_server import PhoneServer
from obstacles import create_world


_pip_texture = [None]
_hand_fonts = {}


def _get_hand_font(size):
    if size not in _hand_fonts:
        _hand_fonts[size] = pygame.font.SysFont("Helvetica", size)
    return _hand_fonts[size]


def _draw_gl_text(text, x, y, win_w, win_h, size=24, color=(255, 255, 255), center=False):
    """Render text with pygame font as an OpenGL textured quad."""
    font = _get_hand_font(size)
    surface = font.render(text, True, color)
    text_data = pygame.image.tostring(surface, "RGBA", True)
    tw, th = surface.get_size()

    draw_x = x - tw // 2 if center else x

    tex = glGenTextures(1)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tw, th, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)

    glColor4f(1, 1, 1, 1)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(draw_x, y)
    glTexCoord2f(1, 0); glVertex2f(draw_x + tw, y)
    glTexCoord2f(1, 1); glVertex2f(draw_x + tw, y + th)
    glTexCoord2f(0, 1); glVertex2f(draw_x, y + th)
    glEnd()

    glDisable(GL_TEXTURE_2D)
    glDeleteTextures([tex])


def draw_hand_hud(frame_bgr, win_w, win_h, throttle, hand_found, joy_connected=False):
    """Draw webcam PiP overlay on the simulator window."""

    # --- Enter 2D mode ---
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, win_w, 0, win_h, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)

    # =============================================
    # WEBCAM PiP — bottom-right corner
    # =============================================
    if frame_bgr is not None:
        import cv2
        pip_w = win_w // 4
        pip_h = int(pip_w * frame_bgr.shape[0] / frame_bgr.shape[1])
        small = cv2.resize(frame_bgr, (pip_w, pip_h))
        rgba = cv2.cvtColor(small, cv2.COLOR_BGR2RGBA)
        rgba = np.flipud(rgba).copy()

        if _pip_texture[0] is None:
            _pip_texture[0] = glGenTextures(1)
        tex_id = _pip_texture[0]

        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, pip_w, pip_h, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, rgba.tobytes())

        margin = 12
        x0 = win_w - pip_w - margin
        y0 = margin
        x1 = x0 + pip_w
        y1 = y0 + pip_h

        # Drop shadow
        glDisable(GL_TEXTURE_2D)
        glColor4f(0, 0, 0, 0.5)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glBegin(GL_QUADS)
        glVertex2f(x0 + 3, y0 - 3)
        glVertex2f(x1 + 3, y0 - 3)
        glVertex2f(x1 + 3, y1 - 3)
        glVertex2f(x0 + 3, y1 - 3)
        glEnd()

        # Border
        border_color = (0.0, 0.85, 0.35) if hand_found else (0.8, 0.2, 0.2)
        glColor3f(*border_color)
        glLineWidth(3.0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x0 - 1, y0 - 1)
        glVertex2f(x1 + 1, y0 - 1)
        glVertex2f(x1 + 1, y1 + 1)
        glVertex2f(x0 - 1, y1 + 1)
        glEnd()

        # Webcam texture
        glEnable(GL_TEXTURE_2D)
        glColor3f(1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x0, y0)
        glTexCoord2f(1, 0); glVertex2f(x1, y0)
        glTexCoord2f(1, 1); glVertex2f(x1, y1)
        glTexCoord2f(0, 1); glVertex2f(x0, y1)
        glEnd()
        glDisable(GL_TEXTURE_2D)

        # PiP label
        _draw_gl_text("HAND CAM", x0 + 6, y1 - 22, win_w, win_h,
                       size=14, color=(200, 200, 200))

        # Joystick badge
        if joy_connected:
            _draw_gl_text("JOYSTICK", x0 + 6, y0 + 4, win_w, win_h,
                           size=12, color=(0, 200, 255))

    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()


def main():
    parser = argparse.ArgumentParser(description="iDrone simulator")
    parser.add_argument("--hand", action="store_true",
                        help="Use webcam hand tracking for throttle")
    args = parser.parse_args()

    # --- Hand tracker (optional) ---
    hand_tracker = None
    joy = None
    if args.hand:
        from hand_throttle import HandTracker
        hand_tracker = HandTracker()
        hand_tracker.start_threaded()
        print("Hand tracking enabled — calibrate in the webcam window (C key)")

    # --- Initialize Pygame + OpenGL ---
    pygame.init()
    display = pygame.display.set_mode(
        (config.WINDOW_WIDTH, config.WINDOW_HEIGHT),
        DOUBLEBUF | OPENGL | RESIZABLE,
    )
    pygame.display.set_caption("iDrone")

    # --- Joystick for hand-tracking mode ---
    if hand_tracker:
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            joy = pygame.joystick.Joystick(0)
            joy.init()
            print(f"  Joystick: {joy.get_name()} ({joy.get_numaxes()} axes)")
        else:
            print("  No joystick — using keyboard for pitch/roll/yaw")

    # --- Initialize components ---
    control_mapper = ControlMapper()
    drone = SimulatorAdapter()
    renderer = Renderer(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
    dashboard = Dashboard(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
    phone_server = PhoneServer()

    renderer.init_gl()
    dashboard.init()
    drone.connect()
    phone_server.start()

    # --- Create obstacle world ---
    world_obstacles = create_world()
    drone._physics.obstacles = world_obstacles
    renderer.obstacles = world_obstacles

    clock = pygame.time.Clock()
    prev_time = time.perf_counter()
    fps = 0.0
    running = True

    # State
    tracking_result = TrackingResult()
    command = DroneCommand()

    # Keyboard-driven angles for --hand mode
    kb_pitch = 0.0
    kb_roll = 0.0
    kb_yaw = 0.0
    KB_RATE = 60.0  # degrees/sec for keyboard tilt
    win_w, win_h = config.WINDOW_WIDTH, config.WINDOW_HEIGHT

    print("iDrone Simulator")
    if hand_tracker:
        print("  Hand tracking: throttle from webcam")
        if joy:
            print(f"  Joystick: {joy.get_name()} for pitch/roll/yaw")
        else:
            print("  Keyboard: arrow keys = pitch/roll, A/D = yaw")
    else:
        print("  Phone gyro:")
        print(f"    Open on phone: {phone_server.url}")
        print("    Use phone orientation for roll, pitch, yaw")
    print("  Keys:")
    print("    P = print phone URL")
    print("    R = reset drone")
    print("    ESC = quit")

    while running:
        current_time = time.perf_counter()
        dt = current_time - prev_time
        prev_time = current_time
        if dt > 0:
            fps = fps * 0.95 + (1.0 / dt) * 0.05  # smoothed FPS

        # --- Event handling ---
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                elif event.key == K_r:
                    drone.reset()
                    control_mapper.reset()
                    kb_pitch = 0.0
                    kb_roll = 0.0
                    kb_yaw = 0.0
                    print("Drone reset.")
                elif event.key == K_p:
                    print(f"Phone URL: {phone_server.url}")
                elif hand_tracker and event.key == K_k:
                    hand_tracker.killswitch()
                    print("KILLSWITCH")
            elif event.type == VIDEORESIZE:
                w, h = event.size
                win_w, win_h = w, h
                renderer.resize(w, h)
                dashboard.resize(w, h)

        # --- Input ---
        if hand_tracker:
            if joy:
                # Joystick axes for pitch/roll/yaw
                from hand_throttle import apply_deadzone, JOY_AXIS_ROLL, JOY_AXIS_PITCH, JOY_AXIS_YAW
                raw_roll = joy.get_axis(JOY_AXIS_ROLL)
                raw_pitch = joy.get_axis(JOY_AXIS_PITCH)
                raw_yaw = 0.0
                if joy.get_numaxes() > JOY_AXIS_YAW:
                    raw_yaw = joy.get_axis(JOY_AXIS_YAW)
                elif joy.get_numaxes() > 2:
                    raw_yaw = joy.get_axis(2)

                kb_roll = apply_deadzone(raw_roll) * 45.0
                kb_pitch = apply_deadzone(-raw_pitch) * 45.0  # invert Y
                kb_yaw = apply_deadzone(raw_yaw) * 45.0
            else:
                # Keyboard fallback
                keys = pygame.key.get_pressed()
                if keys[K_UP]:
                    kb_pitch = min(45.0, kb_pitch + KB_RATE * dt)
                elif keys[K_DOWN]:
                    kb_pitch = max(-45.0, kb_pitch - KB_RATE * dt)
                else:
                    kb_pitch *= (1.0 - 3.0 * dt)  # auto-center

                if keys[K_RIGHT]:
                    kb_roll = min(45.0, kb_roll + KB_RATE * dt)
                elif keys[K_LEFT]:
                    kb_roll = max(-45.0, kb_roll - KB_RATE * dt)
                else:
                    kb_roll *= (1.0 - 3.0 * dt)

                if keys[K_d]:
                    kb_yaw = min(45.0, kb_yaw + KB_RATE * dt)
                elif keys[K_a]:
                    kb_yaw = max(-45.0, kb_yaw - KB_RATE * dt)
                else:
                    kb_yaw *= (1.0 - 3.0 * dt)

            hand_throttle, hand_found = hand_tracker.get_throttle()
            tracking_result = TrackingResult(
                gesture_active=True,
                roll_angle=kb_roll,
                pitch_angle=kb_pitch,
                yaw_angle=kb_yaw,
                throttle=hand_throttle,
            )
        else:
            tracking_result = phone_server.get_tracking_result()

        # --- Map controls ---
        command = control_mapper.map(tracking_result, dt)

        # --- Step physics ---
        drone.send_command(command)
        drone.step(dt)

        # --- Render 3D scene ---
        state = drone.get_state()
        phone_server.update_drone_state(state)
        renderer.render(state)

        # --- Render HUD overlay ---
        dashboard.render(state, command, tracking_result, fps)

        # --- Hand tracking overlay ---
        if hand_tracker:
            throttle_val, hand_found_val, _, _ = hand_tracker.get_status()
            draw_hand_hud(hand_tracker.get_frame(), win_w, win_h,
                          throttle_val, hand_found_val,
                          joy_connected=(joy is not None))

        # --- Swap buffers ---
        pygame.display.flip()
        clock.tick(config.FPS_TARGET)

    # --- Cleanup ---
    if hand_tracker:
        hand_tracker.stop()
    phone_server.stop()
    drone.disconnect()
    pygame.quit()
    print("Goodbye.")


if __name__ == "__main__":
    main()
