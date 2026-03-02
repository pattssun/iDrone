"""HUD overlay: DJI Fly-style card-based telemetry instruments."""

import math

import numpy as np
import pygame
from OpenGL.GL import *
from OpenGL.GLU import *

import config
from physics import DroneState
from controls import DroneCommand
from tracker import TrackingResult


class Dashboard:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._font_large = None
        self._font_medium = None
        self._font_small = None

    def init(self):
        """Initialize after pygame + OpenGL context exists."""
        pygame.font.init()
        self._font_large = pygame.font.SysFont("Helvetica", config.HUD_FONT_LARGE)
        self._font_medium = pygame.font.SysFont("Helvetica", config.HUD_FONT_MEDIUM)
        self._font_small = pygame.font.SysFont("Helvetica", config.HUD_FONT_SMALL)

    def render(self, state: DroneState, command: DroneCommand, tracking: TrackingResult,
               fps: float):
        """Render full HUD overlay on top of 3D scene."""
        self._begin_2d()

        margin = config.HUD_MARGIN

        # --- Compass heading bar (top center) ---
        compass_w = int(self.width * config.HUD_COMPASS_WIDTH_FRAC)
        compass_x = (self.width - compass_w) // 2
        compass_y = self.height - margin - config.HUD_COMPASS_HEIGHT - 10
        self._draw_compass(compass_x, compass_y, compass_w, config.HUD_COMPASS_HEIGHT, state.yaw)

        # --- Telemetry strip: Alt | V.Speed | H.Speed | THR (below compass) ---
        tel_w = compass_w
        tel_h = 46
        tel_x = compass_x
        tel_y = compass_y - tel_h - 4
        h_speed = math.sqrt(state.vx ** 2 + state.vz ** 2)
        thr_pct = command.throttle * 100
        self._draw_telemetry_strip(tel_x, tel_y, tel_w, tel_h,
                                   state.y, state.vy, h_speed, thr_pct)

        # --- Attitude indicator (left side, center) ---
        att_r = config.HUD_ATTITUDE_RADIUS_NEW
        att_cx = margin + att_r + 10
        att_cy = self.height // 2
        self._draw_attitude_indicator(att_cx, att_cy, att_r, state.roll, state.pitch)

        # --- Connection status (top-left) ---
        connected = tracking.gesture_active
        dot_color = config.THEME_STATUS_GREEN if connected else config.THEME_STATUS_RED
        dot_y = self.height - margin - 12
        self._draw_filled_circle_2d(margin + 12, dot_y, config.HUD_STATUS_DOT_RADIUS, 12, dot_color)
        label = "Connected" if connected else "Disconnected"
        self._draw_text(label, margin + 22, dot_y - 7, config.THEME_TEXT_SECONDARY, self._font_small)

        # --- FLIP indicator (centered) ---
        if state.is_flipping:
            self._draw_text("FLIP", self.width // 2, self.height // 2 + 40,
                            config.THEME_STATUS_ORANGE, self._font_large, center=True)

        # --- FPS (top-right) ---
        self._draw_text(f"{fps:.0f} FPS", self.width - margin - 55, self.height - margin - 12,
                        config.THEME_TEXT_SECONDARY, self._font_small)

        self._end_2d()

    # ---- Helpers ----

    def _draw_card(self, x, y, w, h):
        """Semi-transparent filled card with 1px border."""
        # Fill
        glColor4f(*config.THEME_CARD_BG)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()
        # Border
        glColor4f(*config.THEME_CARD_BORDER)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

    def _draw_filled_circle_2d(self, cx, cy, radius, segments, color):
        """Filled circle in 2D."""
        glColor3f(*color)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, cy)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        glEnd()

    def _draw_text(self, text, x, y, color=(255, 255, 255), font=None, center=False):
        """Render text using pygame font onto OpenGL quad."""
        if font is None:
            font = self._font_medium
        if not font:
            return

        # Normalize color to 0-255 int tuples
        if isinstance(color[0], float) and color[0] <= 1.0:
            draw_color = tuple(int(c * 255) for c in color[:3])
        else:
            draw_color = color[:3]

        surface = font.render(text, True, draw_color)
        text_data = pygame.image.tostring(surface, "RGBA", True)
        w, h = surface.get_size()

        draw_x = x - w // 2 if center else x

        tex = glGenTextures(1)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)

        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(draw_x, y)
        glTexCoord2f(1, 0); glVertex2f(draw_x + w, y)
        glTexCoord2f(1, 1); glVertex2f(draw_x + w, y + h)
        glTexCoord2f(0, 1); glVertex2f(draw_x, y + h)
        glEnd()

        glDisable(GL_TEXTURE_2D)
        glDeleteTextures([tex])

    # ---- Instrument components ----

    def _draw_compass(self, x, y, w, h, heading_deg):
        """Compass heading bar with tick marks and cardinal labels."""
        self._draw_card(x, y, w, h)

        # Visible range: heading +/- 45 degrees
        cx = x + w / 2
        cy = y + h / 2
        deg_range = 90.0  # total visible degrees
        px_per_deg = w / deg_range

        # Normalize heading to 0-360
        hdg = heading_deg % 360
        if hdg < 0:
            hdg += 360

        # Draw ticks and labels
        cardinals = {0: 'N', 45: 'NE', 90: 'E', 135: 'SE', 180: 'S', 225: 'SW', 270: 'W', 315: 'NW'}
        for deg_offset in range(-50, 51):
            world_deg = (round(hdg) + deg_offset) % 360
            if world_deg % 10 != 0:
                continue
            px_x = cx + deg_offset * px_per_deg
            if px_x < x or px_x > x + w:
                continue

            # Tick mark
            if world_deg % 90 == 0:
                tick_h = h * 0.5
                glColor4f(0.9, 0.9, 0.9, 0.9)
            elif world_deg % 45 == 0:
                tick_h = h * 0.35
                glColor4f(0.7, 0.7, 0.7, 0.7)
            else:
                tick_h = h * 0.2
                glColor4f(0.5, 0.5, 0.5, 0.5)

            glLineWidth(1.0)
            glBegin(GL_LINES)
            glVertex2f(px_x, y)
            glVertex2f(px_x, y + tick_h)
            glEnd()

            # Cardinal/intercardinal labels
            if world_deg in cardinals:
                self._draw_text(cardinals[world_deg], px_x, y + tick_h + 1,
                                config.THEME_TEXT_PRIMARY, self._font_small, center=True)

        # Center pointer triangle (top of bar)
        ptr_size = 5
        glColor4f(*config.THEME_STATUS_BLUE, 1.0)
        glBegin(GL_TRIANGLES)
        glVertex2f(cx, y + h)
        glVertex2f(cx - ptr_size, y + h + ptr_size)
        glVertex2f(cx + ptr_size, y + h + ptr_size)
        glEnd()

        # Heading value at center top
        self._draw_text(f"{hdg:.0f}\u00b0", cx, y + h + 6, config.THEME_TEXT_ACCENT, self._font_small, center=True)

    def _draw_telemetry_strip(self, x, y, w, h, altitude, vert_speed, h_speed, thr_pct):
        """4-column telemetry strip: Alt | V.Speed | H.Speed | THR."""
        self._draw_card(x, y, w, h)

        col_w = w / 4
        label_y = y + h - 16  # label near top of card
        value_y = y + 8       # value near bottom of card

        # Column dividers
        glColor4f(1.0, 1.0, 1.0, 0.04)
        glLineWidth(1.0)
        for i in range(1, 4):
            dx = x + col_w * i
            glBegin(GL_LINES)
            glVertex2f(dx, y + 6)
            glVertex2f(dx, y + h - 6)
            glEnd()

        # Col 1: Alt
        c1 = x + col_w * 0.5
        self._draw_text("Alt", c1, label_y, config.THEME_TEXT_SECONDARY, self._font_small, center=True)
        self._draw_text(f"{altitude:.1f}", c1, value_y, config.THEME_TEXT_ACCENT, self._font_medium, center=True)

        # Col 2: V.Speed
        c2 = x + col_w * 1.5
        self._draw_text("V.Speed", c2, label_y, config.THEME_TEXT_SECONDARY, self._font_small, center=True)
        if abs(vert_speed) > 0.05:
            vs_color = config.THEME_STATUS_BLUE if vert_speed > 0 else config.THEME_STATUS_ORANGE
            sign = "+" if vert_speed > 0 else ""
            self._draw_text(f"{sign}{vert_speed:.1f}", c2, value_y, vs_color, self._font_medium, center=True)
        else:
            self._draw_text("0.0", c2, value_y, config.THEME_TEXT_PRIMARY, self._font_medium, center=True)

        # Col 3: H.Speed
        c3 = x + col_w * 2.5
        self._draw_text("H.Speed", c3, label_y, config.THEME_TEXT_SECONDARY, self._font_small, center=True)
        self._draw_text(f"{h_speed:.1f}", c3, value_y, config.THEME_TEXT_PRIMARY, self._font_medium, center=True)

        # Col 4: THR
        c4 = x + col_w * 3.5
        self._draw_text("THR", c4, label_y, config.THEME_TEXT_SECONDARY, self._font_small, center=True)
        # Color-code throttle: blue above 50%, orange below 50%, white at ~50%
        if thr_pct > 55:
            thr_color = config.THEME_STATUS_BLUE
        elif thr_pct < 45:
            thr_color = config.THEME_STATUS_ORANGE
        else:
            thr_color = config.THEME_TEXT_PRIMARY
        self._draw_text(f"{thr_pct:.0f}%", c4, value_y, thr_color, self._font_medium, center=True)

    def _draw_attitude_indicator(self, cx, cy, r, roll_deg, pitch_deg):
        """Small attitude indicator with sky/ground halves."""
        roll_rad = math.radians(-roll_deg)
        pitch_offset = -pitch_deg / 45.0 * r

        cos_r = math.cos(roll_rad)
        sin_r = math.sin(roll_rad)

        # Clipping: draw within circle by using stencil-like approach with many segments
        segments = 48

        # Sky half (upper) — blue (matches phone gradient midpoint)
        sky_color = (0.31, 0.50, 0.70)
        self._draw_half_circle(cx, cy, r, roll_rad, pitch_offset, upper=True, color=sky_color, segments=segments)

        # Ground half (lower) — brown (matches phone gradient midpoint)
        ground_color = (0.39, 0.30, 0.07)
        self._draw_half_circle(cx, cy, r, roll_rad, pitch_offset, upper=False, color=ground_color, segments=segments)

        # Horizon line
        offset_x = -pitch_offset * sin_r
        offset_y = pitch_offset * cos_r
        lx1 = cx + (-r * cos_r) + offset_x
        ly1 = cy + (-r * sin_r) + offset_y
        lx2 = cx + (r * cos_r) + offset_x
        ly2 = cy + (r * sin_r) + offset_y

        glColor4f(1.0, 1.0, 1.0, 0.9)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex2f(lx1, ly1)
        glVertex2f(lx2, ly2)
        glEnd()

        # Center crosshair — white (matches phone 20px span)
        glColor4f(1.0, 1.0, 1.0, 0.85)
        ch = 10
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex2f(cx - ch, cy)
        glVertex2f(cx + ch, cy)
        glVertex2f(cx, cy - ch)
        glVertex2f(cx, cy + ch)
        glEnd()

        # Outer ring — subtle white (matches phone box-shadow)
        glColor4f(1.0, 1.0, 1.0, 0.12)
        glLineWidth(1.5)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            glVertex2f(cx + r * math.cos(angle), cy + r * math.sin(angle))
        glEnd()

    def _draw_half_circle(self, cx, cy, r, roll_rad, pitch_offset, upper, color, segments=48):
        """Draw either the sky (upper) or ground (lower) half of the attitude circle."""
        cos_r = math.cos(roll_rad)
        sin_r = math.sin(roll_rad)
        offset_x = -pitch_offset * sin_r
        offset_y = pitch_offset * cos_r

        # Horizon line center
        hcx = cx + offset_x
        hcy = cy + offset_y

        # Normal pointing "up" from the horizon line (perpendicular, into sky)
        nx = -sin_r
        ny = cos_r

        glColor3f(*color)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(hcx, hcy)

        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)

            # Determine which side of the horizon this point is on
            dx = px - hcx
            dy = py - hcy
            dot = dx * nx + dy * ny

            if upper and dot >= 0:
                glVertex2f(px, py)
            elif not upper and dot <= 0:
                glVertex2f(px, py)
        glEnd()

    # ---- 2D projection ----

    def _begin_2d(self):
        """Switch to 2D orthographic projection for overlay."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)

    def _end_2d(self):
        """Restore 3D projection."""
        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def resize(self, width, height):
        self.width = width
        self.height = height
