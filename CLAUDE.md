# iDrone — Claude Code Context

## Hand Tracking Throttle Roadmap

**Current status: Zone Control complete** (as of 2026-04-20)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Done | Standalone prototype — webcam + MediaPipe hand tracking, visual throttle output only |
| Phase 2 | Done | Pico serial integration, `--no-serial` fallback, killswitch, simulator integration |
| Phase 3 | Done | Hybrid input — joystick for yaw/pitch/roll, `--no-joystick` fallback, all 4 channels to Pico |
| Zone Control | **Done** | Zone-based hand throttle — fist=hover, open hand top half=full climb, bottom half=full descend. Binary: zone membership alone determines throttle (no gradient). EMA smoothing (~300ms) softens motor command. No calibration needed. Rich HUD with zone tints, drifting particles, direction arrow. Right-hand-only tracking. |

## Key Files

- `hand_throttle.py` — Hand tracking + joystick + serial sender. `HandTracker` class can run standalone or threaded from `main.py`
- `main.py --hand` — Simulator with hand throttle. Joystick for pitch/roll/yaw (keyboard fallback if no joystick)
- `pico/pico_dac_controller.py` — Pico firmware (DO NOT MODIFY). Protocol: `throttle,yaw,pitch,roll\n`
- `pico/mac_dac_sender.py` — Keyboard debug tool for DAC (standalone, not part of hand tracking)
- `models/hand_landmarker.task` — MediaPipe model (7.5MB, already in repo)

## Constants

- NEUTRAL = 2048 (DAC midpoint = hover for HS210)
- DAC_MAX = 4095 (12-bit DAC ceiling)
- FIST_THRESHOLD = 1.3 (raw openness below this = fist = hover)
- DEADZONE_HALF = 0.08 (±8% of frame height around midline = hover strip)
- EMA_ALPHA = 0.3 (smoothing factor for DAC value)
- JOYSTICK_DEADZONE = 0.08 (axis deadzone)
- JOY_AXIS_ROLL/PITCH/YAW = 0/1/3 (default gamepad axis mapping)
- Pico serial: 115200 baud, auto-detect "usbmodem" port, 500ms safety timeout

## Zone Control Pipeline

- Palm centroid (mean of 21 landmarks) determines position
- Right hand only (wrist x >= 0.5 in mirrored frame, left hand ignored)
- Fist anywhere → hover (NEUTRAL). No hand → hover (NEUTRAL)
- Open hand top half → full climb (DAC_MAX)
- Open hand bottom half → full descend (DAC=0)
- Deadzone ±8% around midline → hover
- EMA smoothing on DAC value softens the binary input into a ~300ms ramp
- No calibration needed — start flying immediately
