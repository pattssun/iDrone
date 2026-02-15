"""Hand-Drone: Hand-controlled drone simulator. Entry point and main loop."""

import sys
import time

import cv2
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *

import config
from tracker import Tracker, TrackingResult, draw_landmarks
from controls import ControlMapper, DroneCommand
from drone_interface import SimulatorAdapter
from renderer import Renderer
from dashboard import Dashboard


def main():
    # --- Initialize webcam ---
    cap = cv2.VideoCapture(config.WEBCAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.WEBCAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.WEBCAM_HEIGHT)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        sys.exit(1)

    # --- Initialize Pygame + OpenGL ---
    pygame.init()
    display = pygame.display.set_mode(
        (config.WINDOW_WIDTH, config.WINDOW_HEIGHT),
        DOUBLEBUF | OPENGL | RESIZABLE,
    )
    pygame.display.set_caption("Hand-Drone Simulator")

    # --- Initialize components ---
    tracker = Tracker()
    control_mapper = ControlMapper()
    drone = SimulatorAdapter()
    renderer = Renderer(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
    dashboard = Dashboard(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

    renderer.init_gl()
    dashboard.init()
    drone.connect()

    clock = pygame.time.Clock()
    prev_time = time.perf_counter()
    fps = 0.0
    running = True

    # State
    webcam_frame = None
    tracking_result = TrackingResult()
    command = DroneCommand()

    print("Hand-Drone Simulator")
    print("  Controls:")
    print("    Rock sign (index + pinky) = takeoff / hover")
    print("    Release gesture = land")
    print("    Hand roll = drone roll")
    print("    Hand pitch (tilt forward/back) = drone pitch")
    print("    Head tilt = yaw")
    print("  Keys:")
    print("    ESC = quit")
    print("    R = reset drone")
    print("    C = calibrate neutral hand position")

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
                    print("Drone reset.")
                elif event.key == K_c:
                    ret, frame = cap.read()
                    if ret:
                        frame = cv2.flip(frame, 1)
                        if tracker.calibrate_neutral(frame):
                            print("Pitch calibrated to current hand position.")
                        else:
                            print("Calibration failed — no hand detected.")
            elif event.type == VIDEORESIZE:
                w, h = event.size
                renderer.resize(w, h)
                dashboard.resize(w, h)

        # --- Capture webcam frame ---
        ret, frame = cap.read()
        if ret:
            frame = cv2.flip(frame, 1)  # mirror for natural interaction
            webcam_frame = frame.copy()

            # --- Run tracking ---
            tracking_result = tracker.process(frame)

            # Draw landmarks on the webcam frame for thumbnail
            webcam_frame = draw_landmarks(webcam_frame, tracking_result)

        # --- Map controls ---
        command = control_mapper.map(tracking_result, dt)

        # --- Step physics ---
        drone.send_command(command)
        drone.step(dt)

        # --- Render 3D scene ---
        state = drone.get_state()
        renderer.render(state)

        # --- Render HUD overlay ---
        dashboard.render(state, command, tracking_result, webcam_frame, fps)

        # --- Swap buffers ---
        pygame.display.flip()
        clock.tick(config.FPS_TARGET)

    # --- Cleanup ---
    tracker.close()
    drone.disconnect()
    cap.release()
    pygame.quit()
    print("Goodbye.")


if __name__ == "__main__":
    main()
