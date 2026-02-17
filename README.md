# iDrone: Phone-Controlled Drone Simulator

A drone simulator controlled by phone gyroscope. Tilt your phone to fly.

## Control Scheme

| Input | Action |
|-------|--------|
| Rock sign (index + pinky extended) | Take off / altitude hold |
| Release rock sign | Gradual descent + auto-land |
| Hand roll (tilt left/right) | Drone roll |
| Hand pitch (tilt forward/back) | Drone pitch |
| Head tilt (left/right) | Drone yaw |

## Setup

```bash
# Create virtual environment (recommended)
python3 -m venv venvw
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### macOS Note

You may need to grant camera access to your terminal application in **System Settings > Privacy & Security > Camera**.

## Usage

```bash
python main.py
```

### Keyboard Controls

| Key | Action |
|-----|--------|
| `ESC` | Quit |
| `R` | Reset drone position |
| `C` | Calibrate neutral hand position |

### Tips

- Hold your hand about 30-50cm from the webcam
- Make the rock sign clearly: extend index and pinky, fold middle and ring fingers
- Press `C` with your hand in a neutral position to calibrate pitch zero-point
- The webcam thumbnail in the bottom-right corner shows tracking landmarks

## Architecture

```
Webcam → Tracker (MediaPipe) → Control Mapper → Drone Interface → Simulator (Physics)
                                                                        ↓
                                                              3D Renderer + HUD
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point, main loop |
| `config.py` | Tunable constants |
| `tracker.py` | MediaPipe hand + face tracking |
| `controls.py` | Gesture → drone command mapping |
| `physics.py` | Drone physics simulation |
| `renderer.py` | Pygame + OpenGL 3D scene |
| `dashboard.py` | HUD overlay |
| `drone_interface.py` | Abstract interface + simulator adapter |

## Standalone Tests

```bash
# Test tracker (shows webcam with landmarks)
python tracker.py

# Test physics (scripted flight sequence)
python physics.py
```
