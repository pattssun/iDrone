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

        self.obstacles = []

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

        # --- Obstacles ---
        self._draw_obstacles()

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

    # ---- Obstacle rendering ----

    def _draw_obstacles(self):
        """Draw all obstacles in the world."""
        from obstacles import ObstacleType
        for obs in self.obstacles:
            if obs.type == ObstacleType.BOX:
                self._draw_box_obstacle(obs)
            elif obs.type == ObstacleType.CYLINDER:
                self._draw_cylinder_obstacle(obs)
            elif obs.type == ObstacleType.TREE:
                self._draw_tree_obstacle(obs)
            elif obs.type == ObstacleType.HOOP:
                self._draw_hoop_obstacle(obs)

    def _draw_box_obstacle(self, obs):
        """Draw an axis-aligned box (building) with shaded faces and edges."""
        hw, hh, hd = obs.width / 2, obs.height, obs.depth / 2
        x, z = obs.x, obs.z

        v = [
            (x - hw, 0,  z - hd),   # 0: bottom-left-back
            (x + hw, 0,  z - hd),   # 1: bottom-right-back
            (x + hw, 0,  z + hd),   # 2: bottom-right-front
            (x - hw, 0,  z + hd),   # 3: bottom-left-front
            (x - hw, hh, z - hd),   # 4: top-left-back
            (x + hw, hh, z - hd),   # 5: top-right-back
            (x + hw, hh, z + hd),   # 6: top-right-front
            (x - hw, hh, z + hd),   # 7: top-left-front
        ]

        # Side faces with per-face shading for depth
        faces = [
            (0, 1, 5, 4, 0.85),  # back (darker)
            (2, 3, 7, 6, 1.0),   # front (lighter)
            (0, 3, 7, 4, 0.90),  # left
            (1, 2, 6, 5, 0.95),  # right
        ]
        base = config.OBSTACLE_BUILDING_COLOR
        for i0, i1, i2, i3, shade in faces:
            glColor3f(base[0] * shade, base[1] * shade, base[2] * shade)
            glBegin(GL_QUADS)
            glVertex3f(*v[i0]); glVertex3f(*v[i1])
            glVertex3f(*v[i2]); glVertex3f(*v[i3])
            glEnd()

        # Roof
        glColor3f(*config.OBSTACLE_BUILDING_ROOF_COLOR)
        glBegin(GL_QUADS)
        glVertex3f(*v[4]); glVertex3f(*v[5])
        glVertex3f(*v[6]); glVertex3f(*v[7])
        glEnd()

        # Edges
        glColor4f(*config.OBSTACLE_BUILDING_EDGE_COLOR)
        glLineWidth(1.0)
        for ib, it in [(0, 4), (1, 5), (2, 6), (3, 7)]:
            glBegin(GL_LINES)
            glVertex3f(*v[ib]); glVertex3f(*v[it])
            glEnd()
        glBegin(GL_LINE_LOOP)
        for i in [4, 5, 6, 7]:
            glVertex3f(*v[i])
        glEnd()
        glBegin(GL_LINE_LOOP)
        for i in [0, 1, 2, 3]:
            glVertex3f(*v[i])
        glEnd()
        glLineWidth(2.0)

        # Ground shadow
        glColor4f(0.0, 0.0, 0.0, config.OBSTACLE_SHADOW_ALPHA)
        glBegin(GL_QUADS)
        glVertex3f(x - hw, 0.004, z - hd)
        glVertex3f(x + hw, 0.004, z - hd)
        glVertex3f(x + hw, 0.004, z + hd)
        glVertex3f(x - hw, 0.004, z + hd)
        glEnd()

    def _draw_cylinder_obstacle(self, obs):
        """Draw a vertical cylinder (pole/tower) with top cap and optional beacon."""
        segments = 12
        cx, cz = obs.x, obs.z
        r, h = obs.radius, obs.height
        color = config.OBSTACLE_POLE_COLOR

        # Side faces
        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            nx = math.cos(angle)
            nz = math.sin(angle)
            shade = 0.8 + 0.2 * max(0, nz)
            glColor3f(color[0] * shade, color[1] * shade, color[2] * shade)
            px = cx + r * nx
            pz = cz + r * nz
            glVertex3f(px, h, pz)
            glVertex3f(px, 0, pz)
        glEnd()

        # Top cap
        glColor3f(color[0] * 0.9, color[1] * 0.9, color[2] * 0.9)
        self._draw_filled_circle(cx, h, cz, r, segments)

        # Red beacon on tall poles
        if h > 4.0:
            beacon_r = max(r * 1.5, 0.06)
            glColor3f(*config.OBSTACLE_POLE_LIGHT_COLOR)
            self._draw_filled_circle(cx, h + 0.02, cz, beacon_r, 8)

    def _draw_tree_obstacle(self, obs):
        """Draw tree: brown trunk cylinder + green canopy sphere."""
        segments = 8
        cx, cz = obs.x, obs.z
        tr, th = obs.radius, obs.height

        # Trunk
        trunk_color = config.OBSTACLE_TREE_TRUNK_COLOR
        glColor3f(*trunk_color)
        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            px = cx + tr * math.cos(angle)
            pz = cz + tr * math.sin(angle)
            glVertex3f(px, th, pz)
            glVertex3f(px, 0, pz)
        glEnd()

        # Canopy sphere (latitude slices)
        canopy_r = obs.canopy_radius
        if canopy_r <= 0:
            return
        canopy_cy = th + canopy_r * 0.7
        canopy_color = config.OBSTACLE_TREE_CANOPY_COLOR
        lat_segs = 8
        lon_segs = 12

        for j in range(lat_segs):
            lat0 = math.pi * (j / lat_segs - 0.5)
            lat1 = math.pi * ((j + 1) / lat_segs - 0.5)
            y0 = canopy_cy + canopy_r * math.sin(lat0)
            y1 = canopy_cy + canopy_r * math.sin(lat1)
            r0 = canopy_r * math.cos(lat0)
            r1 = canopy_r * math.cos(lat1)
            shade = 0.7 + 0.3 * (j / lat_segs)
            glColor3f(canopy_color[0] * shade, canopy_color[1] * shade, canopy_color[2] * shade)

            glBegin(GL_QUAD_STRIP)
            for i in range(lon_segs + 1):
                angle = 2.0 * math.pi * i / lon_segs
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                glVertex3f(cx + r1 * cos_a, y1, cz + r1 * sin_a)
                glVertex3f(cx + r0 * cos_a, y0, cz + r0 * sin_a)
            glEnd()

    def _draw_hoop_obstacle(self, obs):
        """Draw a ring/hoop (torus) to fly through."""
        cx, cz = obs.x, obs.z
        ring_r = obs.radius
        tube_r = obs.ring_thickness
        ring_y = obs.height
        color = config.OBSTACLE_HOOP_COLOR

        ring_segs = 24
        tube_segs = 8

        for i in range(ring_segs):
            theta0 = 2.0 * math.pi * i / ring_segs
            theta1 = 2.0 * math.pi * (i + 1) / ring_segs

            glBegin(GL_QUAD_STRIP)
            for j in range(tube_segs + 1):
                phi = 2.0 * math.pi * j / tube_segs
                for theta in [theta1, theta0]:
                    r = ring_r + tube_r * math.cos(phi)
                    px = cx + r * math.cos(theta)
                    py = ring_y + tube_r * math.sin(phi)
                    pz = cz + r * math.sin(theta)
                    shade = 0.7 + 0.3 * math.cos(phi)
                    glColor3f(color[0] * shade, color[1] * shade, color[2] * shade)
                    glVertex3f(px, py, pz)
            glEnd()

    def resize(self, width: int, height: int):
        """Handle window resize."""
        self.width = width
        self.height = height
        glViewport(0, 0, width, height)
