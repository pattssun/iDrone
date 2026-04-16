# iDrone — Claude Code Context

## Hand Tracking Throttle Roadmap

**Current status: Ready for Phase 3** (as of 2026-04-15)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Done | Standalone prototype — webcam + MediaPipe hand tracking, visual throttle output only |
| Phase 2 | Done | Pico serial integration, `--no-serial` fallback, killswitch, simulator integration (`python main.py --hand` with webcam PiP + OpenGL calibration overlay, keyboard pitch/roll/yaw) |
| Phase 3 | **Next** | Hybrid input — hand throttle + physical USB joystick for yaw/pitch/roll. Replace keyboard arrow keys with real joystick axes via pygame. Send all 4 channels to Pico. |
| Phase 4 | Planned | Tuning & UX polish — adjustable throttle cap (currently hardcoded 3000), throttle curve (linear/exponential), configurable EMA_ALPHA, deadzone, on-screen settings |

## Key Files

- `hand_throttle.py` — Hand tracking + serial sender. `HandTracker` class can run standalone or threaded from `main.py`
- `main.py --hand` — Simulator with hand throttle. Keyboard arrows for pitch/roll, A/D for yaw
- `pico/pico_dac_controller.py` — Pico firmware (DO NOT MODIFY). Protocol: `throttle,yaw,pitch,roll\n`
- `pico/mac_dac_sender.py` — Keyboard debug tool for DAC (standalone, not part of hand tracking)
- `models/hand_landmarker.task` — MediaPipe model (7.5MB, already in repo)

## Constants

- NEUTRAL = 2048 (DAC midpoint for yaw/pitch/roll)
- THROTTLE_CAP = 3000 (max DAC value for hand throttle)
- EMA_ALPHA = 0.3 (smoothing factor)
- Pico serial: 115200 baud, auto-detect "usbmodem" port, 500ms safety timeout
