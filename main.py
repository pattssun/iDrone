"""iDrone: Phone-controlled drone simulator. Entry point and main loop."""

import sys
import time

import pygame
from pygame.locals import *
from OpenGL.GL import *

import config
from tracker import TrackingResult
from controls import ControlMapper, DroneCommand
from drone_interface import SimulatorAdapter
from renderer import Renderer
from dashboard import Dashboard
from phone_server import PhoneServer
from obstacles import create_world


def main():
    # --- Initialize Pygame + OpenGL ---
    pygame.init()
    display = pygame.display.set_mode(
        (config.WINDOW_WIDTH, config.WINDOW_HEIGHT),
        DOUBLEBUF | OPENGL | RESIZABLE,
    )
    pygame.display.set_caption("iDrone")

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

    print("iDrone Simulator")
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
                    print("Drone reset.")
                elif event.key == K_p:
                    print(f"Phone URL: {phone_server.url}")
            elif event.type == VIDEORESIZE:
                w, h = event.size
                renderer.resize(w, h)
                dashboard.resize(w, h)

        # --- Get phone input ---
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

        # --- Swap buffers ---
        pygame.display.flip()
        clock.tick(config.FPS_TARGET)

    # --- Cleanup ---
    phone_server.stop()
    drone.disconnect()
    pygame.quit()
    print("Goodbye.")


if __name__ == "__main__":
    main()
