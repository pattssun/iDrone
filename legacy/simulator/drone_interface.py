"""Abstract drone interface + simulator adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from controls import DroneCommand
from physics import DronePhysics, DroneState


@dataclass
class Telemetry:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    is_airborne: bool = False
    is_landing: bool = False
    thrust: float = 0.0


class DroneInterface(ABC):
    @abstractmethod
    def connect(self):
        """Connect to the drone."""
        pass

    @abstractmethod
    def send_command(self, command: DroneCommand):
        """Send a control command to the drone."""
        pass

    @abstractmethod
    def get_telemetry(self) -> Telemetry:
        """Get current telemetry from the drone."""
        pass

    @abstractmethod
    def get_state(self) -> DroneState:
        """Get full drone state (for rendering)."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the drone."""
        pass

    @abstractmethod
    def reset(self):
        """Reset the drone to initial state."""
        pass


class SimulatorAdapter(DroneInterface):
    """Wraps DronePhysics as a DroneInterface implementation."""

    def __init__(self):
        self._physics = DronePhysics()
        self._last_command = DroneCommand()

    def connect(self):
        self._physics.reset()

    def send_command(self, command: DroneCommand):
        self._last_command = command

    def step(self, dt: float):
        """Advance the simulation. Called from the main loop."""
        self._physics.step(self._last_command, dt, flip_direction=self._last_command.flip_direction)

    def get_telemetry(self) -> Telemetry:
        s = self._physics.state
        return Telemetry(
            x=s.x, y=s.y, z=s.z,
            vx=s.vx, vy=s.vy, vz=s.vz,
            roll=s.roll, pitch=s.pitch, yaw=s.yaw,
            is_airborne=s.is_airborne,
            is_landing=s.is_landing,
            thrust=s.thrust,
        )

    def get_state(self) -> DroneState:
        return self._physics.state

    def disconnect(self):
        pass

    def reset(self):
        self._physics.reset()
        self._last_command = DroneCommand()
