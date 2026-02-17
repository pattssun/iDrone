"""HUD overlay: attitude indicator (roll + pitch), altitude bar, control bars, webcam thumbnail."""

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
        self._font = None

    def init(self):
        """Initialize after pygame + OpenGL context exists."""
        pygame.font.init()
        self._font = pygame.font.SysFont("monospace", config.HUD_FONT_SIZE)

    def render(self, state: DroneState, command: DroneCommand, tracking: TrackingResult,
               fps: float):
        """Render full HUD overlay on top of 3D scene."""
        self._begin_2d()

        margin = config.HUD_MARGIN

        # Attitude indicator (center-left) — roll + pitch
        att_x = margin + config.HUD_ATTITUDE_RADIUS + 10
        att_y = self.height // 2
        self._draw_attitude_indicator(att_x, att_y, state.roll, state.pitch)

        # Altitude bar (right side)
        alt_x = self.width - margin - config.HUD_ALTITUDE_BAR_WIDTH - 10
        alt_y = self.height // 2
        self._draw_altitude_bar(alt_x, alt_y, state.y)

        # Control input (bottom left) — roll + pitch bar graphs
        bar_y = margin + 20
        self._draw_control_bars(margin + 10, bar_y, tracking, command)

        # Status (top left)
        status_y = self.height - margin - 50
        conn_color = (0, 255, 0) if tracking.gesture_active else (255, 60, 60)
        conn_text = "PHONE: CONNECTED" if tracking.gesture_active else "PHONE: WAITING"
        self._draw_text(conn_text, margin + 10, status_y, conn_color)

        # FPS (top right)
        self._draw_text(f"FPS: {fps:.0f}", self.width - margin - 80, status_y, (180, 180, 180))
        self._draw_text(f"CONF: {tracking.confidence:.0%}", self.width - margin - 100, status_y - 20,
                        (180, 180, 180))

        self._end_2d()

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

    def _draw_attitude_indicator(self, cx, cy, roll_deg, pitch_deg=0.0):
        """Artificial horizon circle showing roll and pitch."""
        r = config.HUD_ATTITUDE_RADIUS

        # Outer circle
        self._draw_circle_outline(cx, cy, r, (0, 255, 0, 180), 48)

        # Pitch offset: move horizon line up/down within the circle
        # Negative pitch (forward) moves horizon up, positive (back) moves it down
        pitch_offset = -pitch_deg / 45.0 * r

        # Horizon line (rotated by roll, offset by pitch)
        roll_rad = math.radians(roll_deg)

        cos_r = math.cos(roll_rad)
        sin_r = math.sin(roll_rad)

        # Horizon line endpoints with pitch offset perpendicular to roll
        offset_x = -pitch_offset * sin_r
        offset_y = pitch_offset * cos_r

        lx1 = cx + (-r * cos_r) + offset_x
        ly1 = cy + (-r * sin_r) + offset_y
        lx2 = cx + (r * cos_r) + offset_x
        ly2 = cy + (r * sin_r) + offset_y

        glColor4f(0.0, 0.8, 0.0, 0.9)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex2f(lx1, ly1)
        glVertex2f(lx2, ly2)
        glEnd()

        # Center crosshair
        glColor4f(1.0, 1.0, 0.0, 0.9)
        ch = 8
        glBegin(GL_LINES)
        glVertex2f(cx - ch, cy)
        glVertex2f(cx + ch, cy)
        glVertex2f(cx, cy - ch)
        glVertex2f(cx, cy + ch)
        glEnd()

        # Roll indicator (triangle at top of circle)
        tri_size = 8
        top_x = cx - r * math.sin(roll_rad)
        top_y = cy + r * math.cos(roll_rad)
        glColor4f(1.0, 0.5, 0.0, 0.9)
        glBegin(GL_TRIANGLES)
        glVertex2f(top_x, top_y)
        glVertex2f(top_x - tri_size * cos_r, top_y - tri_size * sin_r)
        glVertex2f(top_x + tri_size * cos_r, top_y + tri_size * sin_r)
        glEnd()

        # Labels
        self._draw_text(f"R:{roll_deg:+.0f}", cx - r - 30, cy + r + 5, (0, 200, 0))
        self._draw_text(f"P:{pitch_deg:+.0f}", cx - r - 30, cy + r + 22, (0, 200, 0))

    def _draw_altitude_bar(self, x, cy, altitude):
        """Vertical altitude gauge on right side."""
        bar_w = config.HUD_ALTITUDE_BAR_WIDTH
        bar_h = config.HUD_ALTITUDE_BAR_HEIGHT

        # Background
        glColor4f(0.0, 0.0, 0.0, 0.3)
        glBegin(GL_QUADS)
        glVertex2f(x, cy - bar_h // 2)
        glVertex2f(x + bar_w, cy - bar_h // 2)
        glVertex2f(x + bar_w, cy + bar_h // 2)
        glVertex2f(x, cy + bar_h // 2)
        glEnd()

        # Fill based on altitude (max display 10m)
        max_alt = 10.0
        fill_frac = min(altitude / max_alt, 1.0)
        fill_h = fill_frac * bar_h

        # Color gradient: green (low) → yellow → red (high)
        if fill_frac < 0.5:
            r, g = fill_frac * 2, 1.0
        else:
            r, g = 1.0, 1.0 - (fill_frac - 0.5) * 2

        glColor4f(r, g, 0.2, 0.7)
        glBegin(GL_QUADS)
        glVertex2f(x + 2, cy - bar_h // 2 + 2)
        glVertex2f(x + bar_w - 2, cy - bar_h // 2 + 2)
        glVertex2f(x + bar_w - 2, cy - bar_h // 2 + 2 + fill_h)
        glVertex2f(x + 2, cy - bar_h // 2 + 2 + fill_h)
        glEnd()

        # Altitude text
        self._draw_text(f"ALT", x - 5, cy + bar_h // 2 + 5, (200, 200, 200))
        self._draw_text(f"{altitude:.1f}m", x - 10, cy + bar_h // 2 - 15, (255, 255, 100))

        # Target altitude marker
        target_frac = min(config.ALTITUDE_HOLD_TARGET / max_alt, 1.0)
        target_y = cy - bar_h // 2 + 2 + target_frac * bar_h
        glColor4f(0.0, 1.0, 1.0, 0.8)
        glBegin(GL_LINES)
        glVertex2f(x - 5, target_y)
        glVertex2f(x + bar_w + 5, target_y)
        glEnd()

    def _draw_control_bars(self, x, y, tracking: TrackingResult, command: DroneCommand):
        """Show roll and pitch control inputs as bar graphs."""
        bar_width = 80
        bar_height = 8

        # Roll bar
        by = y

        self._draw_text("ROLL", x, by + bar_height + 2, (180, 180, 180))

        bx = x + 50
        self._draw_hbar(bx, by, bar_width, bar_height, tracking.roll_angle / 45.0, (100, 200, 100))

        bx2 = bx + bar_width + 10
        self._draw_hbar(bx2, by, bar_width, bar_height,
                        command.roll_rate / config.CONTROL_MAX_ROLL_RATE if config.CONTROL_MAX_ROLL_RATE else 0,
                        (100, 100, 255))

        # Pitch bar (below roll)
        by2 = y - bar_height - 10

        self._draw_text("PTCH", x, by2 + bar_height + 2, (180, 180, 180))

        self._draw_hbar(bx, by2, bar_width, bar_height, tracking.pitch_angle / 45.0, (100, 200, 100))

        self._draw_hbar(bx2, by2, bar_width, bar_height,
                        command.pitch_rate / config.CONTROL_MAX_PITCH_RATE if config.CONTROL_MAX_PITCH_RATE else 0,
                        (100, 100, 255))

    def _draw_hbar(self, x, y, w, h, frac, color):
        """Draw a horizontal bar centered on zero."""
        frac = max(-1.0, min(1.0, frac))

        # Background
        glColor4f(0.2, 0.2, 0.2, 0.5)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

        # Fill from center
        center_x = x + w / 2
        fill_w = frac * w / 2
        glColor4f(color[0] / 255, color[1] / 255, color[2] / 255, 0.8)
        glBegin(GL_QUADS)
        if frac >= 0:
            glVertex2f(center_x, y + 1)
            glVertex2f(center_x + fill_w, y + 1)
            glVertex2f(center_x + fill_w, y + h - 1)
            glVertex2f(center_x, y + h - 1)
        else:
            glVertex2f(center_x + fill_w, y + 1)
            glVertex2f(center_x, y + 1)
            glVertex2f(center_x, y + h - 1)
            glVertex2f(center_x + fill_w, y + h - 1)
        glEnd()

        # Center line
        glColor4f(0.8, 0.8, 0.8, 0.6)
        glBegin(GL_LINES)
        glVertex2f(center_x, y)
        glVertex2f(center_x, y + h)
        glEnd()

    def _draw_circle_outline(self, cx, cy, radius, color, segments):
        """Draw circle outline in 2D."""
        glColor4f(color[0] / 255, color[1] / 255, color[2] / 255, color[3] / 255 if len(color) > 3 else 1.0)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            glVertex2f(x, y)
        glEnd()

    def _draw_text(self, text, x, y, color=(255, 255, 255)):
        """Render text using pygame font onto OpenGL quad."""
        if not self._font:
            return

        surface = self._font.render(text, True, color)
        text_data = pygame.image.tostring(surface, "RGBA", True)
        w, h = surface.get_size()

        # Create temporary texture
        tex = glGenTextures(1)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)

        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 1); glVertex2f(x, y + h)
        glEnd()

        glDisable(GL_TEXTURE_2D)
        glDeleteTextures([tex])

    def resize(self, width, height):
        self.width = width
        self.height = height
