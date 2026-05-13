"""Tracking data types shared across input sources."""

from dataclasses import dataclass


@dataclass
class TrackingResult:
    gesture_active: bool = False
    roll_angle: float = 0.0    # degrees, positive = right
    pitch_angle: float = 0.0   # degrees, positive = back pitch, negative = front pitch
    yaw_angle: float = 0.0     # degrees, positive = clockwise from above
    throttle: float = 0.5      # 0.0 = full down, 1.0 = full up, 0.5 = hover
    confidence: float = 0.0
    flip_direction: str = ""   # "", "front", "back", "left", "right"
