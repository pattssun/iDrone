# Legacy simulator

Before I went with the hardware hack, I tried to build this as a phone-gyroscope-controlled 3D drone simulator: a phone served by `phone_server.py` streamed tilt data over WebSocket into an OpenGL window driven by `main.py`, `physics.py`, and `renderer.py`. It worked, but it wasn't the thing — flying a real drone with my hand was. This folder is kept around for anyone curious about the pivot.

Run at your own risk; paths and deps assume you `cd` into this folder.

```bash
cd legacy/simulator
pip install -r requirements.txt
python main.py
```
