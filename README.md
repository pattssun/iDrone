# iDrone

A 3D drone flight simulator controlled by your phone's gyroscope over Wi-Fi. Tilt your phone to fly through a world of buildings, trees, poles, and hoops.

## How It Works

### System Overview

```
Phone (Gyroscope + Slider)
    │
    │  WebSocket (WSS, binary frames @ ~60 Hz)
    ▼
PhoneServer (phone_server.py)
    │  calibration offset, clipping to ±45°
    ▼
TrackingResult { roll, pitch, yaw, throttle }
    │
    ▼
ControlMapper (controls.py)
    │  deadzone → EMA smoothing → sensitivity → rate clipping → rate limiting
    ▼
DroneCommand { roll_rate, pitch_rate, yaw_rate, throttle }
    │
    ▼
DronePhysics (physics.py)
    │  orientation integration → tilt-to-velocity → position integration → collision
    ▼
DroneState { x, y, z, roll, pitch, yaw, vx, vy, vz }
    │
    ├──► Renderer (OpenGL 3D scene)
    ├──► Dashboard (OpenGL 2D HUD overlay)
    └──► PhoneServer (telemetry back to phone @ 5 Hz)
```

### Stage 1: Phone Input

The phone runs a single-page web app (`phone.html`) served over HTTPS. The browser's `DeviceOrientationEvent` provides Euler angles at native sensor rate (~60 Hz on most devices):

| Browser Event | Axis | Maps To |
|---------------|------|---------|
| `gamma` | Left/right tilt | Roll |
| `beta` | Forward/back tilt | Pitch |
| `alpha` | Compass heading | Yaw |

A vertical slider on the phone UI controls throttle (0.0 to 1.0, center = hover).

**Calibration**: When the user taps "Calibrate", the current orientation is stored as zero-offset. All subsequent readings are relative to that position. This lets the user hold the phone at any comfortable angle.

**Transport**: Orientation data is packed as 4 little-endian floats (16 bytes per frame) and sent over WSS for minimal latency. Throttle and calibration are sent as JSON.

### Stage 2: Server-Side Normalization (PhoneState)

`phone_server.py` receives the raw sensor data and applies:

1. **Calibration subtraction**: `gamma - cal_gamma`, `-(beta - cal_beta)`, `(alpha - cal_alpha)`
2. **Clipping**: Roll and pitch clamped to ±45°
3. **Yaw wraparound**: Handles 0°/360° boundary via `(delta + 180) % 360 - 180`
4. **Timeout detection**: If no data received for 2 seconds, marks as disconnected

Output: `TrackingResult` — a normalized snapshot of phone orientation.

### Stage 3: Control Mapping (ControlMapper)

`controls.py` transforms raw angles into rate commands through a 4-stage pipeline. Each axis (roll, pitch, yaw) passes through the same chain:

```
Raw angle (degrees)
    │
    ▼
[1] Deadzone (±3°)
    Angles within ±3° snap to 0. Eliminates hand tremor noise.
    Subtracts threshold from absolute value to avoid a jump at the boundary.
    │
    ▼
[2] EMA Smoothing (alpha = 0.85)
    smoothed = 0.85 * input + 0.15 * previous
    Higher alpha = snappier response, lower = smoother but more lag.
    │
    ▼
[3] Sensitivity & Rate Clipping
    rate = smoothed_angle * 2.0 (sensitivity multiplier)
    Clipped to ±45°/s for roll/pitch, ±90°/s for yaw.
    │
    ▼
[4] Rate Limiting (500°/s²)
    Caps frame-to-frame rate change to prevent jerky commands.
    delta = clamp(new_rate - prev_rate, ±max_change * dt)
```

**Throttle** passes through directly (no smoothing — immediate altitude response feels better).

**Disconnection**: When the phone disconnects, all smoothed values decay by 0.9x per frame, bringing the drone to a gentle stop rather than an abrupt halt.

Output: `DroneCommand { roll_rate, pitch_rate, yaw_rate, throttle }` in degrees/second.

### Stage 4: Physics Simulation (DronePhysics)

`physics.py` steps the drone state forward each frame. The physics model is simplified for a responsive arcade feel rather than full aerodynamic simulation.

#### Orientation Update

```
state.roll  += roll_rate * dt       (clamped to ±45°)
state.pitch += pitch_rate * dt      (clamped to ±45°)
state.yaw   += yaw_rate * dt        (accumulates freely)
```

When rate input drops below 0.1°/s, roll and pitch auto-decay: `angle *= (1 - 3 * dt)`. This self-levels the drone when the phone is held flat.

#### Tilt-to-Velocity (Body Frame to World Frame)

The drone flies in the direction it's tilted, like a real quadcopter:

```
body_forward = (pitch / 45°) * 8.0 m/s     at max tilt
body_right   = (-roll / 45°) * 8.0 m/s     negative because right tilt = move right

world_vx = body_forward * sin(yaw) + body_right * cos(yaw)
world_vz = body_forward * cos(yaw) - body_right * sin(yaw)
```

Velocity smoothing via exponential approach (drag factor 5.0) prevents instant speed changes.

#### Altitude

```
target_vy = (throttle - 0.5) * 2.0 * 4.0 m/s
```

Throttle at 0.5 = hover (0 m/s). Full up = +4 m/s climb. Full down = -4 m/s descent. Ground clamped at 0.1m.

#### Collision Detection

After position integration, the drone (modeled as a sphere of radius 0.4m) is tested against all obstacles:

| Obstacle Type | Collision Shape | Method |
|---------------|----------------|--------|
| Building (BOX) | Axis-aligned bounding box | Closest-point-on-box to sphere center |
| Pole (CYLINDER) | Vertical cylinder | Horizontal distance + Y range check |
| Tree (TREE) | Trunk cylinder + canopy sphere | Compound: check both shapes |
| Hoop (HOOP) | None | Fly-through target, no collision |

On collision: the drone is pushed out to the nearest surface, and velocity is reflected along the collision normal with a 0.3 bounce factor. This feels like bumping into a wall — the drone stops and deflects slightly.

### Stage 5: Rendering

#### 3D Scene (Renderer)

OpenGL immediate-mode rendering at 60 FPS. Draw order:

1. Sky (3-band gradient: horizon haze → sky blue → deep blue)
2. Chase camera (5m behind, 2.5m above drone, smooth-follow with 0.05 lerp)
3. Ground (solid dark surface + 1m grid, accent lines every 5m)
4. Drone shadow (elliptical, fades with altitude)
5. Obstacles (buildings, trees, poles, hoops)
6. Drone model (4 arms in X-config, center body, front LEDs, prop discs)

#### HUD Overlay (Dashboard)

DJI Fly-style 2D overlay drawn in orthographic projection on top of the 3D scene:

- **Compass bar** (top center): Heading with tick marks and cardinal labels
- **Telemetry strip** (below compass): Alt | V.Speed | H.Speed | THR
- **Attitude indicator** (left): Sky/ground sphere responding to roll and pitch
- **Connection dot** (top-left): Green when phone connected, red when disconnected
- **FPS counter** (top-right)

#### Phone HUD

The phone displays a mirrored subset: attitude indicator, telemetry (Alt, V.Speed, H.Speed), and connection status. Telemetry data flows back from the server at 5 Hz via WebSocket.

## Setup

```bash
pip install -r requirements.txt
python main.py
```

Open the printed URL on your phone (same Wi-Fi network). Accept the self-signed certificate warning.

## Controls

| Input | Action |
|-------|--------|
| Tilt phone left/right | Roll |
| Tilt phone forward/back | Pitch |
| Rotate phone (compass) | Yaw |
| Throttle slider | Altitude (center = hover) |
| Calibrate button | Set current orientation as neutral |

| Key | Action |
|-----|--------|
| `R` | Reset drone to start |
| `P` | Print phone URL |
| `ESC` | Quit |

## Configuration

All tunable parameters live in `config.py`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `CONTROL_DEADZONE_DEG` | 3.0° | Ignore tilt below this |
| `CONTROL_EMA_ALPHA` | 0.85 | Smoothing (higher = snappier) |
| `CONTROL_ROLL_SENSITIVITY` | 2.0 | Angle-to-rate multiplier |
| `CONTROL_MAX_ROLL_RATE` | 45°/s | Max rotation speed |
| `MOVE_MAX_SPEED` | 8.0 m/s | Top horizontal speed |
| `THROTTLE_MAX_SPEED` | 4.0 m/s | Top vertical speed |
| `MOVE_DRAG` | 5.0 | Velocity smoothing |
| `OBSTACLE_BOUNCE_FACTOR` | 0.3 | Collision elasticity |

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point and main loop |
| `config.py` | All tunable constants |
| `phone.html` | Phone controller UI (served over HTTPS) |
| `phone_server.py` | HTTPS + WSS server for phone communication |
| `tracker.py` | TrackingResult data type |
| `controls.py` | Control mapping pipeline (deadzone, smoothing, rate limiting) |
| `physics.py` | Drone physics and collision detection |
| `obstacles.py` | Obstacle types, world layout, collision math |
| `renderer.py` | OpenGL 3D scene rendering |
| `dashboard.py` | OpenGL 2D HUD overlay |
| `drone_interface.py` | Abstract drone interface + simulator adapter |

## World Layout

The drone starts at origin (0, 2, 0) hovering at 2m altitude. Obstacles are placed within a ~30m radius:

- **6 buildings** — gray boxes of varying height (3m to 15m)
- **8 trees** — brown trunks with green sphere canopies
- **4 poles** — thin metal cylinders, red beacon lights on tall ones
- **3 hoops** — orange rings to fly through (no collision)
