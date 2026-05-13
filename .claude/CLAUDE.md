# iDrone — Claude Code Context

## Hand Tracking Throttle Roadmap

**Current status: Finger Direction Control complete** (as of 2026-04-21)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Done | Standalone prototype — webcam + MediaPipe hand tracking, visual throttle output only |
| Phase 2 | Done | Pico serial integration, `--no-serial` fallback, killswitch, simulator integration |
| Phase 3 | Done | Hybrid input — joystick for yaw/pitch/roll, `--no-joystick` fallback, all 4 channels to Pico |
| Zone Control | Done | Zone-based hand throttle (replaced by Finger Direction) |
| Finger Direction | **Done** | Finger direction throttle — all 5 fingers pointing up=climb, down=descend, fist=hover. Binary: unanimous finger direction determines throttle. Neon ray beams shoot from fingertips with pulsing glow. EMA smoothing (~300ms). Right-hand-only tracking. |

## Key Files

- `hand_throttle.py` — Hand tracking + keyboard/joystick + serial sender. `HandTracker` class can run standalone or threaded. Keyboard fallback: A/D=yaw, arrows=pitch/roll (tap-and-decay)
- `pico/pico_dac_controller.py` — Pico firmware (DO NOT MODIFY). Protocol: `throttle,yaw,pitch,roll\n`
- `pico/mac_dac_sender.py` — Keyboard debug tool for DAC (standalone, not part of hand tracking)
- `models/hand_landmarker.task` — MediaPipe model (7.5MB, already in repo)
- `legacy/simulator/` — abandoned phone-gyro simulator (former `main.py --hand` path). Archived; not part of the current build.

## Constants

- NEUTRAL = 2048 (DAC midpoint = hover for HS210)
- DAC_MAX = 4095 (12-bit DAC ceiling)
- FIST_THRESHOLD = 1.3 (raw openness below this = fist = hover)
- FINGER_ANGLE_THRESHOLD = 45 (degrees from vertical for up/down detection)
- EMA_ALPHA = 0.3 (smoothing factor for DAC value)
- JOYSTICK_DEADZONE = 0.08 (axis deadzone)
- JOY_AXIS_ROLL/PITCH/YAW = 0/1/3 (default gamepad axis mapping)
- RAY_PULSE_HZ = 2.0 (glow oscillation frequency)
- Pico serial: 115200 baud, auto-detect "usbmodem" port, 500ms safety timeout

## Finger Direction Pipeline

- Right hand only (wrist x >= 0.5 in mirrored frame, left hand ignored)
- Fist anywhere → hover (NEUTRAL). No hand → hover (NEUTRAL)
- For each of 4 fingers (index, middle, ring, pinky): vector from MCP to fingertip
- "Pointing up" = angle from vertical < 45°. "Pointing down" = angle from downward vertical < 45°
- All 4 pointing up → climb (DAC_MAX). All 4 pointing down → descend (DAC=0)
- Any disagreement → hover (NEUTRAL)
- EMA smoothing on DAC value softens the binary input into a ~300ms ramp
- Neon ray beams from each fingertip in pointing direction (green=climb, red=descend, gray=hover)
- No calibration needed — start flying immediately

## Demo Animations

- **Fingertip particle trails**: sparks shed from each fingertip, drift in ray direction, fade over ~0.5s
- **Palm energy orb**: glowing sphere at palm center, radius scales with throttle deviation, pulsing
- **Skeleton color wave**: gradient ripple washes wrist→fingertips over 0.4s on zone change
- **Zone transition flash**: brief white bloom at palm on zone change (0.15s)
- **Wrist throttle ring**: spinning arc around wrist, fill proportional to throttle deviation
- **Finger angle graph**: top-left, 4-line real-time plot of finger angles, 5s rolling window
