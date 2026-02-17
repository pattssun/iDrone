"""Phone gyroscope server: receives orientation data from phone via WebSocket."""

import asyncio
import json
import os
import socket
import ssl
import struct
import subprocess
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

import numpy as np
import websockets

import config
from tracker import TrackingResult

_CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".certs")
_CERT_FILE = os.path.join(_CERT_DIR, "cert.pem")
_KEY_FILE = os.path.join(_CERT_DIR, "key.pem")
_PHONE_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone.html")


class PhoneState:
    """Thread-safe container for latest phone orientation."""

    def __init__(self):
        self._lock = threading.Lock()
        self.connected = False
        self.last_update = 0.0
        self.phone_timestamp = 0.0  # client-side performance.now() for diagnostics
        self.roll = 0.0   # gamma after calibration
        self.pitch = 0.0  # beta after calibration
        self.yaw = 0.0    # alpha after calibration (compass heading offset)
        self._cal_beta = 0.0
        self._cal_gamma = 0.0
        self._cal_alpha = 0.0

    def calibrate(self, beta: float, gamma: float, alpha: float = 0.0):
        with self._lock:
            self._cal_beta = beta
            self._cal_gamma = gamma
            self._cal_alpha = alpha

    def update(self, beta: float, gamma: float, alpha: float = 0.0, phone_timestamp: float = 0.0):
        with self._lock:
            self.roll = float(np.clip(gamma - self._cal_gamma, -45.0, 45.0))
            self.pitch = float(np.clip(-(beta - self._cal_beta), -45.0, 45.0))
            # Yaw from compass heading with wraparound handling
            delta = (alpha - self._cal_alpha + 180) % 360 - 180
            self.yaw = float(np.clip(delta, -config.CONTROL_MAX_YAW_ANGLE, config.CONTROL_MAX_YAW_ANGLE))
            self.last_update = time.time()
            self.phone_timestamp = phone_timestamp
            self.connected = True

    def get(self) -> tuple:
        """Returns (roll, pitch, yaw, connected)."""
        with self._lock:
            connected = self.connected and (time.time() - self.last_update < config.PHONE_TIMEOUT_SECONDS)
            if not connected:
                self.connected = False
            return self.roll, self.pitch, self.yaw, connected


class PhoneServer:
    """Serves phone.html over HTTPS and receives orientation via WSS."""

    def __init__(self, ws_port: int = None, http_port: int = None):
        self.ws_port = ws_port or config.PHONE_WS_PORT
        self.http_port = http_port or config.PHONE_HTTP_PORT
        self.state = PhoneState()
        self.local_ip = self._detect_local_ip()
        self._http_server = None
        self._http_thread = None
        self._ws_thread = None
        self._ws_loop = None
        self._ws_server = None

    @property
    def is_connected(self) -> bool:
        _, _, _, connected = self.state.get()
        return connected

    @property
    def url(self) -> str:
        return f"https://{self.local_ip}:{self.http_port}/"

    def get_tracking_result(self) -> TrackingResult:
        roll, pitch, yaw, connected = self.state.get()
        return TrackingResult(
            gesture_active=connected,
            roll_angle=roll,
            pitch_angle=pitch,
            yaw_angle=yaw,
            confidence=1.0 if connected else 0.0,
        )

    def start(self):
        """Generate cert if needed, start HTTP and WebSocket servers."""
        self._ensure_cert()
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(_CERT_FILE, _KEY_FILE)

        # --- HTTPS server ---
        self._start_http(ssl_ctx)

        # --- WebSocket server ---
        self._start_ws(ssl_ctx)

        print(f"Phone gyro server ready:")
        print(f"  Open on phone: {self.url}")
        print(f"  (Accept the certificate warning in your browser)")

    def stop(self):
        if self._http_server:
            self._http_server.shutdown()
        if self._ws_loop and self._ws_server:
            self._ws_loop.call_soon_threadsafe(self._ws_server.close)
        if self._ws_thread:
            self._ws_thread.join(timeout=1)

    # --- HTTP ---

    def _start_http(self, ssl_ctx: ssl.SSLContext):
        phone_html_path = _PHONE_HTML

        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                with open(phone_html_path, "rb") as f:
                    self.wfile.write(f.read())

            def log_message(self, format, *args):
                pass  # suppress request logs

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        self._http_server = ReusableHTTPServer(("0.0.0.0", self.http_port), Handler)
        self._http_server.socket = ssl_ctx.wrap_socket(
            self._http_server.socket, server_side=True
        )
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever, daemon=True
        )
        self._http_thread.start()

    # --- WebSocket ---

    def _start_ws(self, ssl_ctx: ssl.SSLContext):
        self._ws_loop = asyncio.new_event_loop()

        async def _run():
            self._ws_server = await websockets.serve(
                self._ws_handler, "0.0.0.0", self.ws_port, ssl=ssl_ctx
            )
            await self._ws_server.wait_closed()

        def _thread_target():
            asyncio.set_event_loop(self._ws_loop)
            self._ws_loop.run_until_complete(_run())

        self._ws_thread = threading.Thread(target=_thread_target, daemon=True)
        self._ws_thread.start()

    async def _ws_handler(self, websocket):
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    # Binary: 4 floats [beta, gamma, alpha, timestamp]
                    if len(message) == 16:
                        beta, gamma, alpha, timestamp = struct.unpack('<4f', message)
                        self.state.update(beta, gamma, alpha, phone_timestamp=timestamp)
                elif isinstance(message, str):
                    # JSON: calibrate messages
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "calibrate":
                        beta = float(data.get("beta", 0))
                        gamma = float(data.get("gamma", 0))
                        alpha = float(data.get("alpha", 0))
                        self.state.calibrate(beta, gamma, alpha)
        except websockets.ConnectionClosed:
            pass

    # --- SSL cert ---

    def _ensure_cert(self):
        if os.path.exists(_CERT_FILE) and os.path.exists(_KEY_FILE):
            return

        os.makedirs(_CERT_DIR, exist_ok=True)
        print(f"Generating self-signed certificate for {self.local_ip}...")

        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", _KEY_FILE, "-out", _CERT_FILE,
                "-days", "365", "-nodes",
                "-subj", f"/CN={self.local_ip}",
                "-addext", f"subjectAltName=IP:{self.local_ip}",
            ],
            check=True,
            capture_output=True,
        )
        print("Certificate generated.")

    # --- Utilities ---

    @staticmethod
    def _detect_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


if __name__ == "__main__":
    server = PhoneServer()
    server.start()
    print("\nStandalone test — printing connection status. Ctrl+C to quit.\n")
    try:
        while True:
            result = server.get_tracking_result()
            connected = server.is_connected
            status = "CONNECTED" if connected else "waiting..."
            print(
                f"\r  [{status}]  roll={result.roll_angle:+6.1f}  "
                f"pitch={result.pitch_angle:+6.1f}  "
                f"yaw={result.yaw_angle:+6.1f}  "
                f"active={result.gesture_active}    ",
                end="", flush=True,
            )
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        server.stop()
