"""Simplified 6DOF drone physics simulation with altitude hold PID."""

import math
from dataclasses import dataclass, field

import numpy as np

import config
from controls import DroneCommand


@dataclass
class DroneState:
    # Position (meters)
    x: float = 0.0
    y: float = 0.0  # altitude (up)
    z: float = 0.0

    # Velocity (m/s)
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    # Orientation (degrees)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    # Motor state
    thrust: float = 0.0  # normalized 0..1

    # Mode
    is_airborne: bool = False
    is_landing: bool = False


class AltitudePID:
    def __init__(self):
        self.kp = config.ALTITUDE_PID_KP
        self.ki = config.ALTITUDE_PID_KI
        self.kd = config.ALTITUDE_PID_KD
        self.integral = 0.0
        self.prev_error = 0.0
        self.target = config.ALTITUDE_HOLD_TARGET

    def update(self, current_alt: float, dt: float) -> float:
        error = self.target - current_alt
        self.integral += error * dt
        self.integral = np.clip(self.integral, -config.ALTITUDE_PID_MAX_INTEGRAL,
                                config.ALTITUDE_PID_MAX_INTEGRAL)
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        self.prev_error = error
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        return float(output)

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.target = config.ALTITUDE_HOLD_TARGET


class DronePhysics:
    def __init__(self):
        self.state = DroneState()
        self.alt_pid = AltitudePID()
        self._accumulator = 0.0

    def step(self, command: DroneCommand, dt: float):
        """Advance physics by dt seconds using fixed timestep internally."""
        self._accumulator += dt
        fixed_dt = config.PHYSICS_TIMESTEP

        while self._accumulator >= fixed_dt:
            self._fixed_step(command, fixed_dt)
            self._accumulator -= fixed_dt

    def _fixed_step(self, command: DroneCommand, dt: float):
        s = self.state

        # --- Mode transitions ---
        if command.throttle_mode == "hold":
            if not s.is_airborne:
                s.is_airborne = True
                s.is_landing = False
                self.alt_pid.reset()
                self.alt_pid.target = config.ALTITUDE_HOLD_TARGET
            else:
                s.is_landing = False
        elif command.throttle_mode == "land":
            s.is_landing = True
        elif command.throttle_mode == "off":
            if s.y <= config.LANDING_GROUND_THRESHOLD:
                s.is_airborne = False
                s.is_landing = False

        # --- Orientation ---
        if s.is_airborne:
            # Apply roll/pitch/yaw rates
            s.roll += command.roll_rate * dt
            s.pitch += command.pitch_rate * dt
            s.yaw += command.yaw_rate * dt

            # Clamp roll and pitch
            s.roll = float(np.clip(s.roll, -config.MAX_TILT_ANGLE, config.MAX_TILT_ANGLE))
            s.pitch = float(np.clip(s.pitch, -config.MAX_TILT_ANGLE, config.MAX_TILT_ANGLE))

            # Normalize yaw
            s.yaw = s.yaw % 360.0

            # Self-leveling: roll and pitch decay toward 0 when no input
            if abs(command.roll_rate) < 0.1:
                s.roll *= (1.0 - 3.0 * dt)  # decay factor
            if abs(command.pitch_rate) < 0.1:
                s.pitch *= (1.0 - 3.0 * dt)

        # --- Thrust computation ---
        if s.is_airborne:
            if s.is_landing:
                # Reduce target altitude
                self.alt_pid.target -= config.LANDING_DESCENT_RATE * dt
                if self.alt_pid.target < 0:
                    self.alt_pid.target = 0.0

            # PID altitude hold
            thrust_command = config.GRAVITY + self.alt_pid.update(s.y, dt)
            thrust_command = max(0.0, thrust_command)

            # Motor response lag (first-order)
            tau = config.MOTOR_RESPONSE_TIME
            alpha = dt / (tau + dt)
            s.thrust = s.thrust + alpha * (thrust_command - s.thrust)
        else:
            s.thrust = 0.0

        # --- Forces ---
        roll_rad = math.radians(s.roll)
        pitch_rad = math.radians(s.pitch)
        yaw_rad = math.radians(s.yaw)

        # Thrust vector (body frame → world frame, simplified)
        # In body frame, thrust points up (0, thrust, 0)
        # Rotate by roll (around z-axis) and pitch (around x-axis) then yaw (around y-axis)
        thrust_x = s.thrust * (math.sin(yaw_rad) * math.sin(roll_rad) +
                                math.cos(yaw_rad) * math.sin(pitch_rad) * math.cos(roll_rad))
        thrust_y = s.thrust * math.cos(pitch_rad) * math.cos(roll_rad)
        thrust_z = s.thrust * (math.cos(yaw_rad) * math.sin(roll_rad) -
                                math.sin(yaw_rad) * math.sin(pitch_rad) * math.cos(roll_rad))

        # Gravity
        gravity_y = -config.GRAVITY

        # Drag
        drag_x = -config.DRAG_COEFFICIENT * s.vx
        drag_y = -config.DRAG_COEFFICIENT * s.vy
        drag_z = -config.DRAG_COEFFICIENT * s.vz

        # Net acceleration
        ax = (thrust_x + drag_x)
        ay = (thrust_y + gravity_y + drag_y)
        az = (thrust_z + drag_z)

        # --- Integration (semi-implicit Euler) ---
        s.vx += ax * dt
        s.vy += ay * dt
        s.vz += az * dt

        s.x += s.vx * dt
        s.y += s.vy * dt
        s.z += s.vz * dt

        # --- Ground collision ---
        if s.y <= 0.0:
            s.y = 0.0
            s.vy = 0.0
            s.vx *= 0.5  # ground friction
            s.vz *= 0.5
            if s.is_landing:
                s.is_airborne = False
                s.is_landing = False
                s.roll = 0.0
                s.pitch = 0.0
                s.thrust = 0.0

    def reset(self):
        self.state = DroneState()
        self.alt_pid.reset()
        self._accumulator = 0.0

    def get_interpolation_alpha(self) -> float:
        """Return interpolation factor for rendering between physics steps."""
        return self._accumulator / config.PHYSICS_TIMESTEP


if __name__ == "__main__":
    """Standalone physics test: scripted commands, verify altitude hold and landing."""
    import time

    physics = DronePhysics()
    dt = 1.0 / 60.0

    print("=== Phase 1: Takeoff + altitude hold (3s) ===")
    hold_cmd = DroneCommand(throttle_mode="hold")
    for i in range(180):  # 3 seconds at 60fps
        physics.step(hold_cmd, dt)
        if i % 30 == 0:
            s = physics.state
            print(f"  t={i*dt:.1f}s  alt={s.y:.2f}m  vy={s.vy:.2f}  thrust={s.thrust:.2f}")

    print("\n=== Phase 2: Roll right for 2s ===")
    roll_cmd = DroneCommand(roll_rate=20.0, throttle_mode="hold")
    for i in range(120):
        physics.step(roll_cmd, dt)
        if i % 30 == 0:
            s = physics.state
            print(f"  t={(180+i)*dt:.1f}s  pos=({s.x:.2f}, {s.y:.2f}, {s.z:.2f})  roll={s.roll:.1f}")

    print("\n=== Phase 3: Landing (5s) ===")
    land_cmd = DroneCommand(throttle_mode="land")
    for i in range(300):
        physics.step(land_cmd, dt)
        if i % 60 == 0:
            s = physics.state
            print(f"  t={(300+i)*dt:.1f}s  alt={s.y:.2f}m  airborne={s.is_airborne}  landing={s.is_landing}")

    print(f"\nFinal state: airborne={physics.state.is_airborne}, alt={physics.state.y:.3f}m")
