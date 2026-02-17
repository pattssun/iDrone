"""Drone orientation model — fixed position, roll + pitch for control testing."""

from dataclasses import dataclass

import numpy as np

import config
from controls import DroneCommand


@dataclass
class DroneState:
    # Fixed position
    x: float = 0.0
    y: float = 2.0  # hover height for visibility
    z: float = 0.0

    # Orientation (degrees)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    # Kept for interface compatibility
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    thrust: float = 0.0
    is_airborne: bool = True
    is_landing: bool = False


class DronePhysics:
    def __init__(self):
        self.state = DroneState()

    def step(self, command: DroneCommand, dt: float):
        """Apply roll and pitch rates, and yaw angle directly."""
        s = self.state

        # Roll
        s.roll += command.roll_rate * dt
        s.roll = float(np.clip(s.roll, -config.MAX_TILT_ANGLE, config.MAX_TILT_ANGLE))

        if abs(command.roll_rate) < 0.1:
            s.roll *= (1.0 - 3.0 * dt)

        # Pitch
        s.pitch += command.pitch_rate * dt
        s.pitch = float(np.clip(s.pitch, -config.MAX_TILT_ANGLE, config.MAX_TILT_ANGLE))

        if abs(command.pitch_rate) < 0.1:
            s.pitch *= (1.0 - 3.0 * dt)

        # Yaw (absolute angle, already smoothed by ControlMapper)
        s.yaw = command.yaw_angle
        if abs(command.yaw_angle) < 0.1:
            s.yaw *= (1.0 - 3.0 * dt)

    def reset(self):
        self.state = DroneState()


if __name__ == "__main__":
    """Standalone test: apply roll and pitch and print orientation."""
    physics = DronePhysics()
    dt = 1.0 / 60.0

    print("=== Roll right 2s ===")
    cmd = DroneCommand(roll_rate=20.0)
    for i in range(120):
        physics.step(cmd, dt)
        if i % 30 == 0:
            s = physics.state
            print(f"  t={i*dt:.1f}s  roll={s.roll:.1f}  pitch={s.pitch:.1f}")

    print(f"\nFinal: roll={physics.state.roll:.1f}  pitch={physics.state.pitch:.1f}")

    physics.reset()
    print("\n=== Pitch forward 2s ===")
    cmd = DroneCommand(pitch_rate=-20.0)
    for i in range(120):
        physics.step(cmd, dt)
        if i % 30 == 0:
            s = physics.state
            print(f"  t={i*dt:.1f}s  roll={s.roll:.1f}  pitch={s.pitch:.1f}")

    print(f"\nFinal: roll={physics.state.roll:.1f}  pitch={physics.state.pitch:.1f}")
