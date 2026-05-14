# Legacy simulator

Before I went with the hardware hack, I tried to build this as a 3D drone simulator: an OpenGL window with `main.py`, `physics.py`, and `renderer.py` simulating a drone you could fly through obstacles. There was also a phone-gyroscope control path that streamed tilt over WebSocket from a browser running on your phone; those files (`phone_server.py`, `phone.html`) have been removed because the server bound to `0.0.0.0` with no authentication. The rest of the simulator is kept around for anyone curious about the pivot.

Run at your own risk; paths and deps assume you `cd` into this folder. You'll need to wire up a different input source if you want it to fly anything.

```bash
cd legacy/simulator
pip install -r requirements.txt
python main.py
```
