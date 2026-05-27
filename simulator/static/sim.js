// iDrone simulator front-end: three.js scene + 60 Hz physics + HUD wiring.

import * as THREE from "/static/lib/three.module.min.js";
import { connect } from "/static/js/ws.js";
import { ControlPipeline, DroneState, ARENA } from "/static/js/physics.js";
import { buildArena } from "/static/js/arena.js";
import { buildDrone } from "/static/js/drone.js";
import { buildTrail } from "/static/js/trail.js";
import {
  updateAttitude,
  updateCompass,
  updateTelemetry,
  setLinkStatus,
} from "/static/js/hud.js";

const canvas = document.getElementById("canvas");
const hintEl = document.getElementById("hud-hint");

// ---------- scene ----------
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0d12);
scene.fog = new THREE.Fog(0x0a0d12, 30, 80);

const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 200);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);

scene.add(new THREE.HemisphereLight(0xc8e0ff, 0x222024, 0.7));
const sun = new THREE.DirectionalLight(0xffffff, 0.7);
sun.position.set(10, 20, 8);
scene.add(sun);

const arena = buildArena();
scene.add(arena.group);

const drone = buildDrone();
scene.add(drone.root);
scene.add(drone.shadow);

const trail = buildTrail();
scene.add(trail.line);

// ---------- state ----------
const state = new DroneState();
const ctrl = new ControlPipeline();

let latestInput = { b: 0, g: 0, a: 0, t: 0 }; // calibrated phone angles
let throttle = 0.5;
let lastInputT = 0;
let inputRateEMA = 0;
let lastRTT = null;
let peerState = "disconnected"; // peer == phone

let trailAccumulator = 0;
const TRAIL_PUSH_INTERVAL = 1 / 30; // 30 samples/sec is plenty for a 5s line

window.addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// ---------- WebSocket ----------
const link = connect({
  role: "sim",
  onState: (s) => {
    if (s === "live") {
      // peer state arrives via 'peer' messages — keep "WAITING" until phone joins.
      if (peerState !== "connected") setLinkStatus({ peer: "waiting" });
    } else if (s === "linking") {
      setLinkStatus({ peer: "linking" });
    } else {
      setLinkStatus({ peer: "disconnected" });
    }
  },
  onMessage: (msg) => handlePhoneMessage(msg),
});

function handlePhoneMessage(msg) {
  if (!msg || !msg.type) return;
  switch (msg.type) {
    case "peer":
      peerState = msg.state;
      if (peerState === "connected") {
        hintEl.classList.add("hidden");
        setLinkStatus({ peer: "connected" });
      } else {
        hintEl.classList.remove("hidden");
        setLinkStatus({ peer: "waiting" });
      }
      break;
    case "orient": {
      const now = performance.now();
      if (lastInputT > 0) {
        const dt = now - lastInputT;
        if (dt > 0) {
          const hz = 1000 / dt;
          inputRateEMA = inputRateEMA === 0 ? hz : 0.85 * inputRateEMA + 0.15 * hz;
        }
      }
      lastInputT = now;
      latestInput = { b: msg.b, g: msg.g, a: msg.a, t: msg.t };
      break;
    }
    case "throttle":
      throttle = Math.max(0, Math.min(1, msg.v));
      break;
    case "calibrate":
      // Reset only the yaw baseline tracking; alpha drift is unavoidable so
      // we treat each calibration as a fresh zero for yaw input.
      ctrl.reset();
      break;
    case "reset":
      state.reset();
      ctrl.reset();
      trail.clear();
      throttle = 0.5;
      break;
    case "pong":
      if (typeof msg.t === "number") lastRTT = performance.now() - msg.t;
      break;
  }
}

// Ping the phone once per second for RTT
setInterval(() => {
  if (peerState === "connected") {
    link.send({ type: "ping", t: Math.round(performance.now()) });
  }
}, 1000);

// ---------- loop ----------
const PHYS_DT = 1 / 60;
let physAcc = 0;
let lastFrame = performance.now();
const tmpCam = new THREE.Vector3();
const camTarget = new THREE.Vector3(0, 4, -8);

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;

  physAcc += dt;
  while (physAcc >= PHYS_DT) {
    stepPhysics(PHYS_DT);
    physAcc -= PHYS_DT;
  }

  // Drone visual
  drone.root.position.set(state.x, state.y, state.z);
  // Apply orientation: yaw around Y, then pitch around X, then roll around Z.
  drone.root.rotation.set(
    state.pitch * (Math.PI / 180),
    state.yaw * (Math.PI / 180),
    state.roll * (Math.PI / 180),
    "YXZ"
  );
  drone.updatePropSpin(dt);
  drone.updateShadow(state);

  // Trail (decoupled from physics tick so it's frame-rate independent)
  trailAccumulator += dt;
  if (trailAccumulator >= TRAIL_PUSH_INTERVAL) {
    trail.push(state.x, state.y, state.z);
    trailAccumulator = 0;
  }

  arena.updateFlash(state.wallFlash);

  // Chase camera
  const yawRad = state.yaw * (Math.PI / 180);
  tmpCam.set(
    state.x - Math.sin(yawRad) * 5.5,
    state.y + 2.5,
    state.z - Math.cos(yawRad) * 5.5
  );
  camTarget.lerp(tmpCam, 0.07);
  camera.position.copy(camTarget);
  camera.lookAt(state.x, state.y + 0.3, state.z);

  // HUD
  updateAttitude(state.roll, state.pitch);
  updateCompass(state.yaw);
  updateTelemetry(state, throttle, now);
  if (peerState === "connected") {
    setLinkStatus({
      peer: "connected",
      latencyMs: lastRTT,
      rateHz: inputRateEMA,
    });
  }

  renderer.render(scene, camera);
}

function stepPhysics(dt) {
  // No fresh input for >0.4s → fall toward hover (controls drift toward zero).
  const stale = performance.now() - lastInputT > 400;
  const rollIn = stale ? 0 : latestInput.g;
  const pitchIn = stale ? 0 : -latestInput.b;
  const yawIn = stale ? 0 : latestInput.a;
  const rates = ctrl.step(rollIn, pitchIn, yawIn, dt);
  state.step(rates, throttle, dt);
}

requestAnimationFrame(frame);
