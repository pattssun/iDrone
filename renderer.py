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
        # Match sky bottom (horizon haze) color
        glClearColor(*config.SKY_BOTTOM_COLOR, 1.0)

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

        # --- Ground surface + grid ---
        self._draw_ground(state)

        # --- Ground shadow ---
        self._draw_shadow(state)

        # --- Drone ---
        self._draw_drone(state)

    def _draw_sky(self):
        """Draw 3-band sky gradient as fullscreen quads in ortho mode."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, 1, 0, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glBegin(GL_QUADS)
        # Bottom quad: horizon haze → mid sky (y 0 → 0.45)
        glColor3f(*config.SKY_BOTTOM_COLOR)
        glVertex2f(0, 0)
        glVertex2f(1, 0)
        glColor3f(*config.SKY_MID_COLOR)
        glVertex2f(1, 0.45)
        glVertex2f(0, 0.45)
        # Top quad: mid sky → deep sky (y 0.45 → 1.0)
        glColor3f(*config.SKY_MID_COLOR)
        glVertex2f(0, 0.45)
        glVertex2f(1, 0.45)
        glColor3f(*config.SKY_TOP_COLOR)
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

    def _draw_ground(self, state: DroneState):
        """Draw solid ground surface with subtle grid overlay."""
        grid_size = config.GROUND_GRID_SIZE
        spacing = config.GROUND_GRID_SPACING

        # Snap grid center to nearest grid line
        cx = round(state.x / spacing) * spacing
        cz = round(state.z / spacing) * spacing
        extent = grid_size * spacing

        # Pass A: Large filled dark quad
        glColor3f(*config.GROUND_COLOR)
        glBegin(GL_QUADS)
        glVertex3f(cx - extent, 0.001, cz - extent)
        glVertex3f(cx + extent, 0.001, cz - extent)
        glVertex3f(cx + extent, 0.001, cz + extent)
        glVertex3f(cx - extent, 0.001, cz + extent)
        glEnd()

        # Pass B: Grid lines
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(-grid_size, grid_size + 1):
            # Every 5th line uses accent color
            if i % 5 == 0:
                glColor4f(*config.GROUND_GRID_ACCENT)
            else:
                glColor4f(*config.GROUND_GRID_COLOR)

            x = cx + i * spacing
            glVertex3f(x, 0.002, cz - extent)
            glVertex3f(x, 0.002, cz + extent)

            z = cz + i * spacing
            glVertex3f(cx - extent, 0.002, z)
            glVertex3f(cx + extent, 0.002, z)
        glEnd()
        glLineWidth(2.0)

    def _draw_shadow(self, state: DroneState):
        """Draw dark elliptical shadow on ground below drone."""
        base_r = config.DRONE_SHADOW_RADIUS
        # Radius grows slightly with altitude, alpha fades
        altitude = max(state.y, 0.0)
        radius = base_r + altitude * 0.03
        alpha = config.DRONE_SHADOW_ALPHA * max(0.0, 1.0 - altitude / 20.0)
        if alpha < 0.01:
            return

        segments = 24
        glColor4f(0.0, 0.0, 0.0, alpha)
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(state.x, 0.003, state.z)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            x = state.x + radius * math.cos(angle)
            z = state.z + radius * 0.6 * math.sin(angle)  # 0.6 Z-squish for ellipse
            glVertex3f(x, 0.003, z)
        glEnd()

    def _draw_drone(self, state: DroneState):
        """Draw solid drone model with arms, body, LEDs, and prop discs."""
        glPushMatrix()
        glTranslatef(state.x, state.y, state.z)

        # Apply rotation (yaw, then pitch, then roll — extrinsic)
        glRotatef(state.yaw, 0, 1, 0)
        glRotatef(state.pitch, 1, 0, 0)
        glRotatef(state.roll, 0, 0, 1)

        arm = config.DRONE_ARM_LENGTH
        prop_r = config.DRONE_PROP_RADIUS
        hw = config.DRONE_ARM_WIDTH  # arm half-width

        # Four arm endpoints (X configuration)
        arms = [
            (-arm, 0, arm),   # front-left
            (arm, 0, arm),    # front-right
            (-arm, 0, -arm),  # back-left
            (arm, 0, -arm),   # back-right
        ]
        arm_colors = [
            (0.8, 0.15, 0.15),  # front-left: red
            (0.15, 0.7, 0.15),  # front-right: green
            (0.4, 0.4, 0.42),   # back-left: gray
            (0.4, 0.4, 0.42),   # back-right: gray
        ]

        # Draw arms as flat quads (rectangles)
        for i, (ax, ay, az) in enumerate(arms):
            glColor3f(*arm_colors[i])
            # Arm direction vector
            length = math.sqrt(ax * ax + az * az)
            if length < 0.001:
                continue
            dx, dz = ax / length, az / length
            # Perpendicular for width
            px, pz = -dz * hw, dx * hw

            glBegin(GL_QUADS)
            glVertex3f(0 - px, ay + 0.005, 0 - pz)
            glVertex3f(0 + px, ay + 0.005, 0 + pz)
            glVertex3f(ax + px, ay + 0.005, az + pz)
            glVertex3f(ax - px, ay + 0.005, az - pz)
            glEnd()

        # Draw center body — filled charcoal square
        body = arm * 0.25
        glColor3f(*config.DRONE_BODY_COLOR)
        glBegin(GL_QUADS)
        glVertex3f(-body, 0.01, -body)
        glVertex3f(body, 0.01, -body)
        glVertex3f(body, 0.01, body)
        glVertex3f(-body, 0.01, body)
        glEnd()

        # Thin gray border outline on body
        glColor4f(0.5, 0.5, 0.52, 0.8)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        glVertex3f(-body, 0.011, -body)
        glVertex3f(body, 0.011, -body)
        glVertex3f(body, 0.011, body)
        glVertex3f(-body, 0.011, body)
        glEnd()

        # Front LEDs — small filled circles at front arm roots
        led_r = 0.015
        led_offset = body * 0.8
        # Red LED (front-left)
        glColor3f(1.0, 0.1, 0.1)
        self._draw_filled_circle(-led_offset, 0.012, led_offset, led_r, 12)
        # Green LED (front-right)
        glColor3f(0.1, 1.0, 0.1)
        self._draw_filled_circle(led_offset, 0.012, led_offset, led_r, 12)

        # Prop discs at arm tips — semi-transparent filled circles + outline ring
        for i, (ax, ay, az) in enumerate(arms):
            # Filled disc
            glColor4f(*arm_colors[i], config.DRONE_PROP_DISC_ALPHA)
            self._draw_filled_circle(ax, ay + 0.02, az, prop_r, 24)
            # Outline ring
            glColor4f(*arm_colors[i], 0.5)
            self._draw_circle_outline_3d(ax, ay + 0.02, az, prop_r, 24)

        glLineWidth(2.0)
        glPopMatrix()

    def _draw_filled_circle(self, cx, cy, cz, radius, segments):
        """Draw a filled circle in the XZ plane using GL_TRIANGLE_FAN."""
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(cx, cy, cz)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            z = cz + radius * math.sin(angle)
            glVertex3f(x, cy, z)
        glEnd()

    def _draw_circle_outline_3d(self, cx, cy, cz, radius, segments):
        """Draw a circle outline in the XZ plane."""
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
