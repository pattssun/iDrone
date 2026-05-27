# iDrone Phone-Gyro Simulator

Tilt your iPhone to fly a drone in a clean 3D arena rendered in the browser. The
desktop runs a tiny aiohttp server on your LAN; the phone connects over HTTPS
and streams its tilt and a throttle slider to the sim.

This replaces the deleted `legacy/simulator/` phone path. Same idea, hardened
network model: HTTPS only, single one-time token, binds to the detected LAN IP
(never `0.0.0.0`), no public exposure.

## Quickstart

```bash
cd /Users/patricksun/GitHub/iDrone
python -m venv venv && source venv/bin/activate
pip install -r simulator/requirements.txt
python -m simulator
```

You'll see something like:

```
  iDrone simulator
  ----------------
  LAN IP : 192.168.1.42
  Token  : 7a3f9c1e8b4d2a06
  Sim    : https://192.168.1.42:8443/?t=7a3f9c1e8b4d2a06
  Phone  : https://192.168.1.42:8443/phone?t=7a3f9c1e8b4d2a06

  [ASCII QR code for the phone URL]
```

1. **Open the Sim URL** on your Mac in Chrome. Click "Advanced → Proceed" past
   the self-signed cert warning. The HUD shows `WAITING`.
2. **Scan the QR with your iPhone Camera** (must be on the same Wi-Fi).
   Tap the Safari prompt. Past Safari's cert warning ("Show details → visit
   this website"), tap **Tap to start**, grant motion permission, hold the
   phone level while it calibrates.
3. Sim status flips to `LIVE`. Tilt your phone; the drone flies.

## Controls

| Phone gesture                | Drone response                                  |
| ---------------------------- | ----------------------------------------------- |
| Tilt phone forward / back    | Pitch — drone moves forward / back              |
| Tilt phone left / right      | Roll — drone slides left / right                |
| Rotate phone around vertical | Yaw — drone spins in place                      |
| Vertical slider              | Throttle — climbs / descends; spring-returns    |
| **Calibrate** button         | Zero current phone pose. Re-tap any time.       |
| **Reset** button             | Snap drone to origin, hover, clear trail        |

The arena is 20 × 20 × 20 m with soft walls — drift into a face and you'll see
a quick red flash; the drone stops at the boundary, no bounce.

## CLI flags

```
python -m simulator [--port 8443] [--ip 192.168.x.y] [--token HEX] [--regen-cert]
```

- `--ip` — override LAN-IP autodetection (useful on a VPN or unusual interface)
- `--token` — pin the token (e.g. for testing scripts); otherwise random
- `--regen-cert` — force regenerate the self-signed cert (e.g. after changing
  networks so the cert SAN includes the new LAN IP)

## Troubleshooting

**Safari refuses to connect / TCP timeout** — phone is on a different SSID,
guest network, or the router has AP isolation enabled. Confirm same Wi-Fi.

**iOS motion permission denied** — Settings → Safari → Motion & Orientation
Access → On. Reload the phone page.

**Detected IP is loopback / not private** — you're on a VPN that captures
default routing. Disable the VPN or pass `--ip <your-LAN-IP>`.

**Cert was working, now isn't** — you switched networks and the LAN IP
changed. The simulator regenerates automatically when it detects the SAN no
longer matches; if needed, delete `simulator/cert/` or run with
`--regen-cert`.

**Smoother iOS cert flow (optional)** — email `simulator/cert/cert.pem` to
yourself, open on iPhone, install the profile (Settings → General → VPN &
Device Management), then Settings → General → About → Certificate Trust
Settings → enable for `iDrone Simulator`. Subsequent visits skip the warning.

## What's intentionally not here

- No real-drone bridge — this is sim-only. The `pico/` USB-DAC path and the
  `hand_throttle.py` runtime are unchanged and untouched.
- No obstacles, flip controller, recording, multi-drone. Add later if useful.
- No public-internet path. By design.
