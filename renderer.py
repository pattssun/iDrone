"""3D renderer using Pygame + OpenGL: drone model, ground grid, chase cam."""

import math

import numpy as np
import pygame
from OpenGL.GL import *
from OpenGL.GLU import *

import config
from physics import DroneState


class Renderer:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

        # Chase cam state
        self._cam_x = 0.0
        self._cam_y = config.CHASE_CAM_HEIGHT
        self._cam_z = -config.CHASE_CAM_DISTANCE

    def init_gl(self):
        """Initialize OpenGL state. Call after pygame display is created."""
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glLineWidth(2.0)
        glClearColor(0.4, 0.6, 0.9, 1.0)  # sky blue

    def render(self, state: DroneState):
        """Render the full 3D scene."""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # --- Sky gradient (draw as background quad) ---
        self._draw_sky()

        # --- 3D perspective setup ---
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(60.0, self.width / self.height, 0.1, 200.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # --- Chase camera ---
        self._update_camera(state)
        gluLookAt(
            self._cam_x, self._cam_y, self._cam_z,
            state.x, state.y, state.z,
            0.0, 1.0, 0.0,
        )

        # --- Ground grid ---
        self._draw_ground_grid(state)

        # --- Drone ---
        self._draw_drone(state)

    def _draw_sky(self):
        """Draw sky gradient as fullscreen quad in ortho mode."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, 1, 0, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glBegin(GL_QUADS)
        # Bottom: lighter blue
        glColor3f(0.6, 0.8, 1.0)
        glVertex2f(0, 0)
        glVertex2f(1, 0)
        # Top: deeper blue
        glColor3f(0.2, 0.4, 0.8)
        glVertex2f(1, 1)
        glVertex2f(0, 1)
        glEnd()
        glEnable(GL_DEPTH_TEST)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def _update_camera(self, state: DroneState):
        """Smooth chase camera following drone."""
        yaw_rad = math.radians(state.yaw)
        # Target camera position: behind and above drone
        target_x = state.x - math.sin(yaw_rad) * config.CHASE_CAM_DISTANCE
        target_y = state.y + config.CHASE_CAM_HEIGHT
        target_z = state.z - math.cos(yaw_rad) * config.CHASE_CAM_DISTANCE

        # Smooth follow
        s = config.CHASE_CAM_SMOOTHING
        self._cam_x += (target_x - self._cam_x) * s
        self._cam_y += (target_y - self._cam_y) * s
        self._cam_z += (target_z - self._cam_z) * s

    def _draw_ground_grid(self, state: DroneState):
        """Draw ground grid centered roughly on drone position."""
        grid_size = config.GROUND_GRID_SIZE
        spacing = config.GROUND_GRID_SPACING

        # Snap grid center to nearest grid line for seamless scrolling
        cx = round(state.x / spacing) * spacing
        cz = round(state.z / spacing) * spacing

        glBegin(GL_LINES)
        for i in range(-grid_size, grid_size + 1):
            # Color by distance from origin for altitude zone feel
            dist = abs(i * spacing)
            if dist < 5:
                glColor4f(0.3, 0.8, 0.3, 0.6)  # green near center
            elif dist < 15:
                glColor4f(0.5, 0.5, 0.5, 0.4)  # gray
            else:
                glColor4f(0.4, 0.4, 0.4, 0.2)  # faded

            x = cx + i * spacing
            glVertex3f(x, 0.0, cz - grid_size * spacing)
            glVertex3f(x, 0.0, cz + grid_size * spacing)

            z = cz + i * spacing
            glVertex3f(cx - grid_size * spacing, 0.0, z)
            glVertex3f(cx + grid_size * spacing, 0.0, z)
        glEnd()

    def _draw_drone(self, state: DroneState):
        """Draw wireframe X-frame drone with colored front arms."""
        glPushMatrix()
        glTranslatef(state.x, state.y, state.z)

        # Apply rotation (yaw, then pitch, then roll — extrinsic)
        glRotatef(state.yaw, 0, 1, 0)
        glRotatef(state.pitch, 1, 0, 0)
        glRotatef(state.roll, 0, 0, 1)

        arm = config.DRONE_ARM_LENGTH
        prop_r = config.DRONE_PROP_RADIUS

        # Four arm endpoints (X configuration)
        # Front-left, front-right, back-left, back-right
        arms = [
            (-arm, 0, arm),   # front-left
            (arm, 0, arm),    # front-right
            (-arm, 0, -arm),  # back-left
            (arm, 0, -arm),   # back-right
        ]
        colors = [
            (1.0, 0.2, 0.2),  # front-left: red
            (0.2, 1.0, 0.2),  # front-right: green
            (0.6, 0.6, 0.6),  # back-left: gray
            (0.6, 0.6, 0.6),  # back-right: gray
        ]

        # Draw arms
        glLineWidth(3.0)
        for i, (ax, ay, az) in enumerate(arms):
            glColor3f(*colors[i])
            glBegin(GL_LINES)
            glVertex3f(0, 0, 0)
            glVertex3f(ax, ay, az)
            glEnd()

            # Draw prop circle at arm tip
            self._draw_circle(ax, ay + 0.02, az, prop_r, 16, colors[i])

        # Draw center body (small square)
        body = arm * 0.2
        glColor3f(0.9, 0.9, 0.2)  # yellow
        glLineWidth(2.0)
        glBegin(GL_LINE_LOOP)
        glVertex3f(-body, 0, -body)
        glVertex3f(body, 0, -body)
        glVertex3f(body, 0, body)
        glVertex3f(-body, 0, body)
        glEnd()

        # Draw front indicator (small triangle)
        glColor3f(1.0, 1.0, 1.0)
        glBegin(GL_LINE_LOOP)
        glVertex3f(-body * 0.5, 0.01, body)
        glVertex3f(body * 0.5, 0.01, body)
        glVertex3f(0, 0.01, body + body * 0.8)
        glEnd()

        glLineWidth(2.0)
        glPopMatrix()

    def _draw_circle(self, cx, cy, cz, radius, segments, color):
        """Draw a circle in the XZ plane at given center."""
        glColor3f(*color)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            z = cz + radius * math.sin(angle)
            glVertex3f(x, cy, z)
        glEnd()

    def resize(self, width: int, height: int):
        """Handle window resize."""
        self.width = width
        self.height = height
        glViewport(0, 0, width, height)
