# iDrone — Claude Code Context

## Hand Tracking Throttle Roadmap

**Current status: Phase 3 complete** (as of 2026-04-16)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Done | Standalone prototype — webcam + MediaPipe hand tracking, visual throttle output only |
| Phase 2 | Done | Pico serial integration, `--no-serial` fallback, killswitch, simulator integration (`python main.py --hand` with webcam PiP + OpenGL calibration overlay, keyboard pitch/roll/yaw) |
| Phase 3 | **Done** | Hybrid input — hand throttle + physical USB joystick for yaw/pitch/roll. Joystick axes via pygame with deadzone, `--no-joystick` fallback. All 4 channels sent to Pico. |
| Phase 4 | **Next** | Tuning & UX polish — adjustable throttle cap (currently hardcoded 3000), throttle curve (linear/exponential), configurable EMA_ALPHA, deadzone, on-screen settings |

## Key Files

- `hand_throttle.py` — Hand tracking + joystick + serial sender. `HandTracker` class can run standalone or threaded from `main.py`
- `main.py --hand` — Simulator with hand throttle. Joystick for pitch/roll/yaw (keyboard fallback if no joystick)
- `pico/pico_dac_controller.py` — Pico firmware (DO NOT MODIFY). Protocol: `throttle,yaw,pitch,roll\n`
- `pico/mac_dac_sender.py` — Keyboard debug tool for DAC (standalone, not part of hand tracking)
- `models/hand_landmarker.task` — MediaPipe model (7.5MB, already in repo)

## Constants

- NEUTRAL = 2048 (DAC midpoint for yaw/pitch/roll)
- DAC_MAX = 4095 (12-bit DAC ceiling)
- THROTTLE_CAP = 3000 (max DAC value for hand throttle)
- EMA_ALPHA = 0.3 (smoothing factor)
- JOYSTICK_DEADZONE = 0.08 (axis deadzone)
- JOY_AXIS_ROLL/PITCH/YAW = 0/1/3 (default gamepad axis mapping)
- Pico serial: 115200 baud, auto-detect "usbmodem" port, 500ms safety timeout
