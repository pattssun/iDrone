"""Control mapping: gesture angles → drone commands with smoothing and deadzone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

import config

if TYPE_CHECKING:
    from tracker import TrackingResult


@dataclass
class DroneCommand:
    roll_rate: float = 0.0     # degrees/sec
    pitch_rate: float = 0.0    # degrees/sec
    yaw_rate: float = 0.0      # degrees/sec


class ControlMapper:
    def __init__(self):
        self._smoothed_roll = 0.0
        self._prev_roll_rate = 0.0
        self._smoothed_pitch = 0.0
        self._prev_pitch_rate = 0.0
        self._smoothed_yaw = 0.0
        self._prev_yaw_rate = 0.0

    def map(self, tracking: TrackingResult, dt: float) -> DroneCommand:
        """Convert TrackingResult to DroneCommand with smoothing."""
        cmd = DroneCommand()

        if tracking.gesture_active:
            # --- Roll pipeline ---
            roll_in = self._deadzone(tracking.roll_angle, config.CONTROL_DEADZONE_DEG)

            alpha = config.CONTROL_EMA_ALPHA
            self._smoothed_roll = alpha * roll_in + (1 - alpha) * self._smoothed_roll

            roll_rate = self._smoothed_roll * config.CONTROL_ROLL_SENSITIVITY
            roll_rate = np.clip(roll_rate, -config.CONTROL_MAX_ROLL_RATE, config.CONTROL_MAX_ROLL_RATE)

            max_change = config.CONTROL_MAX_RATE_CHANGE * dt
            roll_rate = self._rate_limit(roll_rate, self._prev_roll_rate, max_change)

            cmd.roll_rate = float(roll_rate)
            self._prev_roll_rate = cmd.roll_rate

            # --- Pitch pipeline ---
            pitch_in = self._deadzone(tracking.pitch_angle, config.CONTROL_DEADZONE_DEG)

            self._smoothed_pitch = alpha * pitch_in + (1 - alpha) * self._smoothed_pitch

            pitch_rate = self._smoothed_pitch * config.CONTROL_PITCH_SENSITIVITY
            pitch_rate = np.clip(pitch_rate, -config.CONTROL_MAX_PITCH_RATE, config.CONTROL_MAX_PITCH_RATE)

            pitch_rate = self._rate_limit(pitch_rate, self._prev_pitch_rate, max_change)

            cmd.pitch_rate = float(pitch_rate)
            self._prev_pitch_rate = cmd.pitch_rate

            # --- Yaw pipeline (rate-based, like roll/pitch) ---
            yaw_in = self._deadzone(tracking.yaw_angle, config.CONTROL_DEADZONE_DEG)
            self._smoothed_yaw = alpha * yaw_in + (1 - alpha) * self._smoothed_yaw

            yaw_rate = self._smoothed_yaw * config.CONTROL_YAW_SENSITIVITY
            yaw_rate = np.clip(yaw_rate, -config.CONTROL_MAX_YAW_RATE, config.CONTROL_MAX_YAW_RATE)

            yaw_rate = self._rate_limit(yaw_rate, self._prev_yaw_rate, max_change)

            cmd.yaw_rate = float(yaw_rate)
            self._prev_yaw_rate = cmd.yaw_rate

        else:
            # No gesture — zero out smoothly
            self._smoothed_roll *= 0.9
            self._prev_roll_rate *= 0.9
            self._smoothed_pitch *= 0.9
            self._prev_pitch_rate *= 0.9
            self._smoothed_yaw *= 0.9
            self._prev_yaw_rate *= 0.9

        return cmd

    @staticmethod
    def _deadzone(value: float, threshold: float) -> float:
        if abs(value) < threshold:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - threshold)

    @staticmethod
    def _rate_limit(current: float, previous: float, max_change: float) -> float:
        delta = current - previous
        if abs(delta) > max_change:
            return previous + max_change * (1.0 if delta > 0 else -1.0)
        return current

    def reset(self):
        """Reset all state."""
        self._smoothed_roll = 0.0
        self._prev_roll_rate = 0.0
        self._smoothed_pitch = 0.0
        self._prev_pitch_rate = 0.0
        self._smoothed_yaw = 0.0
        self._prev_yaw_rate = 0.0
