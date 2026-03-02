"""Drone physics model — orientation + positional movement from tilt."""

import math
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
    is_flipping: bool = False


class FlipController:
    """Manages animated 360° flip with sine-eased rotation and parabolic altitude dip."""

    AXIS_ROLL = 0
    AXIS_PITCH = 1

    def __init__(self):
        self.active = False
        self.axis = self.AXIS_ROLL
        self.direction = 1        # +1 or -1
        self.elapsed = 0.0
        self.pre_flip_roll = 0.0
        self.pre_flip_pitch = 0.0
        self.pre_flip_altitude = 0.0
        self.last_flip_time = -config.FLIP_COOLDOWN

    def can_flip(self, state: DroneState, current_time: float) -> bool:
        if self.active:
            return False
        if state.y < config.FLIP_MIN_ALTITUDE:
            return False
        if current_time - self.last_flip_time < config.FLIP_COOLDOWN:
            return False
        return True

    def start(self, direction: str, state: DroneState, current_time: float):
        self.active = True
        self.elapsed = 0.0
        self.pre_flip_roll = state.roll
        self.pre_flip_pitch = state.pitch
        self.pre_flip_altitude = state.y

        if direction == "front":
            self.axis = self.AXIS_PITCH
            self.direction = -1   # negative pitch = nose down first
        elif direction == "back":
            self.axis = self.AXIS_PITCH
            self.direction = 1    # positive pitch = nose up first
        elif direction == "left":
            self.axis = self.AXIS_ROLL
            self.direction = -1   # negative roll = left
        elif direction == "right":
            self.axis = self.AXIS_ROLL
            self.direction = 1    # positive roll = right
        else:
            # Default to front flip
            self.axis = self.AXIS_PITCH
            self.direction = -1

        self.last_flip_time = current_time
        state.is_flipping = True

    def step(self, state: DroneState, dt: float):
        if not self.active:
            return

        self.elapsed += dt
        duration = config.FLIP_DURATION

        if self.elapsed >= duration:
            # Flip complete — restore exact pre-flip state
            state.roll = self.pre_flip_roll
            state.pitch = self.pre_flip_pitch
            state.y = self.pre_flip_altitude
            state.is_flipping = False
            self.active = False
            return

        # Normalized progress [0, 1]
        t = self.elapsed / duration

        # Rotation: sine-eased 360° — (1 - cos(t * pi)) / 2 * 360
        rotation = (1.0 - math.cos(t * math.pi)) / 2.0 * 360.0 * self.direction

        if self.axis == self.AXIS_ROLL:
            state.roll = self.pre_flip_roll + rotation
            state.pitch = self.pre_flip_pitch
        else:
            state.pitch = self.pre_flip_pitch + rotation
            state.roll = self.pre_flip_roll

        # Altitude dip: parabolic 4t(1-t) * dip_amount, deepest at midpoint
        dip = 4.0 * t * (1.0 - t) * config.FLIP_ALTITUDE_DIP
        state.y = self.pre_flip_altitude - dip

        # Damp horizontal velocity during flip
        state.vx *= (1.0 - 5.0 * dt)
        state.vz *= (1.0 - 5.0 * dt)


class DronePhysics:
    def __init__(self):
        self.state = DroneState()
        self.obstacles = []
        self.flip = FlipController()
        self._time = 0.0

    def step(self, command: DroneCommand, dt: float, flip_direction: str = ""):
        """Apply roll and pitch rates, and yaw angle directly."""
        self._time += dt
        s = self.state

        # --- Flip handling ---
        if flip_direction and self.flip.can_flip(s, self._time):
            self.flip.start(flip_direction, s, self._time)

        if self.flip.active:
            self.flip.step(s, dt)
            return

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

        # Yaw (rate-based, accumulates over time)
        s.yaw += command.yaw_rate * dt

        # --- Positional movement from tilt ---
        # Body-frame speed: linear mapping from tilt angle to speed
        body_forward = s.pitch / 45.0 * config.MOVE_MAX_SPEED
        body_right = -s.roll / 45.0 * config.MOVE_MAX_SPEED

        # Rotate body-frame to world-frame using yaw
        yaw_rad = math.radians(s.yaw)
        target_vx = body_forward * math.sin(yaw_rad) + body_right * math.cos(yaw_rad)
        target_vz = body_forward * math.cos(yaw_rad) - body_right * math.sin(yaw_rad)

        # Smooth velocity with drag (exponential approach)
        blend = min(config.MOVE_DRAG * dt, 1.0)
        s.vx += (target_vx - s.vx) * blend
        s.vz += (target_vz - s.vz) * blend

        # --- Altitude from throttle ---
        # throttle 0.5 = hover, >0.5 = climb, <0.5 = descend
        target_vy = (command.throttle - 0.5) * 2.0 * config.THROTTLE_MAX_SPEED
        s.vy += (target_vy - s.vy) * blend
        s.y += s.vy * dt
        s.y = max(s.y, config.THROTTLE_MIN_HEIGHT)

        # Integrate position
        s.x += s.vx * dt
        s.z += s.vz * dt

        # Collision detection
        if self.obstacles:
            from obstacles import check_all_collisions
            result = check_all_collisions(s.x, s.y, s.z,
                                          config.OBSTACLE_DRONE_RADIUS, self.obstacles)
            if result.collided:
                s.x, s.y, s.z = result.new_x, result.new_y, result.new_z
                v_dot_n = (s.vx * result.normal_x +
                           s.vy * result.normal_y +
                           s.vz * result.normal_z)
                if v_dot_n < 0:
                    bounce = config.OBSTACLE_BOUNCE_FACTOR
                    s.vx -= (1 + bounce) * v_dot_n * result.normal_x
                    s.vy -= (1 + bounce) * v_dot_n * result.normal_y
                    s.vz -= (1 + bounce) * v_dot_n * result.normal_z
                s.y = max(s.y, config.THROTTLE_MIN_HEIGHT)

    def reset(self):
        self.state = DroneState()
        self.flip = FlipController()
        self._time = 0.0


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
