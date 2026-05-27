"""iDrone phone-gyro simulator server.

aiohttp app that serves the static sim + phone pages over HTTPS, and
relays messages between exactly one sim WebSocket and one phone
WebSocket. Authentication is a single shared one-time token printed at
startup and embedded in the QR code the phone scans.

Binds to the detected LAN IP only — never 0.0.0.0.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import secrets
import ssl
import sys
from pathlib import Path

import qrcode
from aiohttp import WSMsgType, web

from simulator import net

log = logging.getLogger("simulator")

STATIC_DIR = Path(__file__).parent / "static"
CERT_DIR = Path(__file__).parent / "cert"
DEFAULT_PORT = 8443

ROLES = ("sim", "phone")


class Hub:
    """Holds one WS per role, relays messages, notifies on peer state."""

    def __init__(self) -> None:
        self.sockets: dict[str, web.WebSocketResponse] = {}

    def peer_role(self, role: str) -> str:
        return "phone" if role == "sim" else "sim"

    async def attach(self, role: str, ws: web.WebSocketResponse) -> None:
        old = self.sockets.get(role)
        self.sockets[role] = ws
        if old is not None and not old.closed:
            await old.close(code=1000, message=b"displaced")
        await self._broadcast_peer_state()

    async def detach(self, role: str, ws: web.WebSocketResponse) -> None:
        # Only clear if we still own the slot — a newer connection may have replaced us.
        if self.sockets.get(role) is ws:
            self.sockets.pop(role, None)
            await self._broadcast_peer_state()

    async def relay(self, role: str, payload: str) -> None:
        peer = self.sockets.get(self.peer_role(role))
        if peer is None or peer.closed:
            return
        try:
            await peer.send_str(payload)
        except ConnectionResetError:
            pass

    async def _broadcast_peer_state(self) -> None:
        for role in ROLES:
            ws = self.sockets.get(role)
            if ws is None or ws.closed:
                continue
            peer_present = self.sockets.get(self.peer_role(role)) is not None
            msg = json.dumps(
                {"type": "peer", "state": "connected" if peer_present else "disconnected"}
            )
            try:
                await ws.send_str(msg)
            except ConnectionResetError:
                pass


@web.middleware
async def token_middleware(request: web.Request, handler):
    """Reject pages and websockets without the right ?t=<token>.

    Static assets (/static/*) are exempt — browsers don't carry the parent
    page's query string into asset requests, and the JS itself isn't sensitive
    (anyone on the LAN can see it via the page source either way). The real
    auth gate is on the WebSockets where actual control flows.
    """
    if request.path.startswith("/static/"):
        return await handler(request)
    expected = request.app["token"]
    provided = request.query.get("t", "")
    if not hmac.compare_digest(expected, provided):
        return web.Response(status=401, text="missing or invalid token\n")
    return await handler(request)


async def index_sim(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "sim.html")


async def index_phone(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "phone.html")


async def static_handler(request: web.Request) -> web.FileResponse:
    rel = request.match_info["path"]
    target = (STATIC_DIR / rel).resolve()
    if not str(target).startswith(str(STATIC_DIR.resolve())):
        raise web.HTTPForbidden()
    if not target.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(target)


def _ws_handler_factory(role: str):
    async def handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20.0)
        await ws.prepare(request)
        hub: Hub = request.app["hub"]
        await hub.attach(role, ws)
        log.info("%s connected", role)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await hub.relay(role, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    log.warning("%s ws error: %s", role, ws.exception())
        finally:
            await hub.detach(role, ws)
            log.info("%s disconnected", role)
        return ws

    return handler


def build_app(token: str) -> web.Application:
    app = web.Application(middlewares=[token_middleware])
    app["token"] = token
    app["hub"] = Hub()
    app.router.add_get("/", index_sim)
    app.router.add_get("/phone", index_phone)
    app.router.add_get("/ws/sim", _ws_handler_factory("sim"))
    app.router.add_get("/ws/phone", _ws_handler_factory("phone"))
    app.router.add_get("/static/{path:.*}", static_handler)
    return app


def _print_banner(lan_ip: str, port: int, token: str) -> None:
    sim_url = f"https://{lan_ip}:{port}/?t={token}"
    phone_url = f"https://{lan_ip}:{port}/phone?t={token}"
    print()
    print(f"  iDrone simulator")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"  LAN IP : {lan_ip}")
    print(f"  Token  : {token}")
    print()
    print(f"  [1] Open on THIS Mac (the 3D viewport):")
    print(f"      {sim_url}")
    print()
    print(f"  [2] Open on your iPhone (the controller — scan QR):")
    print(f"      {phone_url}")
    print()
    if not net.is_private_ipv4(lan_ip):
        print(
            "  [warn] Detected IP is not in a private range — likely a VPN or unusual"
            " network. Pass --ip <addr> to override.\n"
        )
    qr = qrcode.QRCode(border=1)
    qr.add_data(phone_url)
    qr.make(fit=True)
    qr.print_ascii(tty=sys.stdout.isatty())
    print()
    print("  You need BOTH pages open at the same time:")
    print("    • The Mac shows the drone in 3D.")
    print("    • The iPhone reads tilt + throttle and streams them in.")
    print("  Accept the self-signed cert warning on both browsers.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(prog="simulator")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ip", default=None, help="Override detected LAN IP")
    parser.add_argument("--regen-cert", action="store_true")
    parser.add_argument("--token", default=None, help="Override generated token")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    lan_ip = args.ip or net.detect_lan_ip()
    token = args.token or secrets.token_hex(8)

    cert_path, key_path = net.ensure_cert(CERT_DIR, lan_ip, regenerate=args.regen_cert)
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

    app = build_app(token)
    _print_banner(lan_ip, args.port, token)

    try:
        web.run_app(
            app,
            host=lan_ip,
            port=args.port,
            ssl_context=ssl_ctx,
            print=None,
            access_log=None,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
