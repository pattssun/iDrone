// iDrone simulator front-end: three.js scene + 60 Hz physics + HUD wiring.

import * as THREE from "/static/lib/three.module.min.js";
import { connect } from "/static/js/ws.js?v=5";
import { ControlPipeline, DroneState, ARENA } from "/static/js/physics.js?v=5";
import { buildArena } from "/static/js/arena.js?v=5";
import { buildDrone } from "/static/js/drone.js?v=5";
import { buildTrail } from "/static/js/trail.js?v=5";
import {
  buildPedestal,
  buildOrbitCamera,
  STATIONARY_POS,
} from "/static/js/stationary.js?v=5";
import {
  updateAttitude,
  updateCompass,
  updateTelemetry,
  setLinkStatus,
} from "/static/js/hud.js?v=5";

const canvas = document.getElementById("canvas");
const hintEl = document.getElementById("hud-hint");
const modeToggle = document.getElementById("mode-toggle");

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

// Stationary-mode visuals
const pedestal = buildPedestal();
scene.add(pedestal.group);

const orbitCam = buildOrbitCamera(canvas, camera, STATIONARY_POS.clone());

// ---------- state ----------
const state = new DroneState();
const ctrl = new ControlPipeline();

let latestInput = { b: 0, g: 0, a: 0, t: 0 };
let throttle = 0.5;
let lastInputT = 0;
let inputRateEMA = 0;
let lastRTT = null;
let peerState = "disconnected";

// Smoothed orientation used in stationary mode (1:1 phone mirror).
const statOri = { roll: 0, pitch: 0, yaw: 0 };

// Starts as null so the initial setMode("free") runs through the body and
// sizes the segmented-thumb (its CSS vars default to 0 width).
let mode = null; // null | 'free' | 'stationary'

let trailAccumulator = 0;
const TRAIL_PUSH_INTERVAL = 1 / 30;

window.addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  syncModeThumb();
});

// ---------- WebSocket ----------
const link = connect({
  role: "sim",
  onState: (s) => {
    if (s === "live") {
      if (peerState !== "connected") setLinkStatus({ peer: "waiting" });
    } else if (s === "linking") {
      setLinkStatus({ peer: "linking" });
    } else {
      setLinkStatus({ peer: "disconnected" });
    }
  },
  onOpen: () => {
    // Tell the (already-connected) phone what mode the sim is in.
    sendModeToPhone();
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
        sendModeToPhone();
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
      ctrl.reset();
      statOri.roll = statOri.pitch = statOri.yaw = 0;
      break;
    case "reset":
      state.reset();
      ctrl.reset();
      trail.clear();
      throttle = 0.5;
      statOri.roll = statOri.pitch = statOri.yaw = 0;
      break;
    case "pong":
      if (typeof msg.t === "number") lastRTT = performance.now() - msg.t;
      break;
  }
}

setInterval(() => {
  if (peerState === "connected") {
    link.send({ type: "ping", t: Math.round(performance.now()) });
  }
}, 1000);

// ---------- mode toggle ----------
function setMode(next, opts = {}) {
  if (next !== "free" && next !== "stationary") return;
  if (mode === next) return;
  mode = next;
  modeToggle.dataset.mode = mode;
  for (const btn of modeToggle.querySelectorAll(".mode-opt")) {
    const on = btn.dataset.mode === mode;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  }
  syncModeThumb();
  document.body.classList.toggle("mode-stationary", mode === "stationary");
  pedestal.setActive(mode === "stationary");
  orbitCam.setActive(mode === "stationary");
  trail.line.visible = mode === "free";
  if (mode === "stationary") {
    // Park the kinematic state at the pedestal so the free→stationary entry
    // is glitch-free (positions/velocities all settled).
    state.x = STATIONARY_POS.x;
    state.y = STATIONARY_POS.y;
    state.z = STATIONARY_POS.z;
    state.vx = state.vy = state.vz = 0;
    statOri.roll = state.roll;
    statOri.pitch = state.pitch;
    statOri.yaw = state.yaw;
    trail.clear();
  } else {
    // Re-zero attitude when returning to flight so the drone is hover-stable.
    state.roll = state.pitch = 0;
    state.vx = state.vy = state.vz = 0;
    ctrl.reset();
  }
  if (!opts.silent) sendModeToPhone();
}

function sendModeToPhone() {
  link.send({ type: "mode", value: mode });
}

function syncModeThumb() {
  const active = modeToggle.querySelector(".mode-opt.active");
  const thumb = modeToggle.querySelector(".mode-thumb");
  if (active && thumb) {
    thumb.style.setProperty("--thumb-w", `${active.offsetWidth}px`);
    thumb.style.setProperty("--thumb-x", `${active.offsetLeft}px`);
  }
}

for (const btn of modeToggle.querySelectorAll(".mode-opt")) {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
}

// Initial thumb position once layout has settled.
requestAnimationFrame(() => setMode("free", { silent: true }));

// ---------- loop ----------
const PHYS_DT = 1 / 60;
let physAcc = 0;
let lastFrame = performance.now();
const tmpCam = new THREE.Vector3();
const camTarget = new THREE.Vector3(0, 4, -8);
const STAT_EMA = 0.18; // smoothing for stationary orientation (~150 ms)

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;

  physAcc += dt;
  while (physAcc >= PHYS_DT) {
    stepPhysics(PHYS_DT);
    physAcc -= PHYS_DT;
  }

  // Mode-specific drone visual.
  if (mode === "stationary") {
    drone.root.position.copy(STATIONARY_POS);
    drone.root.rotation.set(
      statOri.pitch * (Math.PI / 180),
      statOri.yaw * (Math.PI / 180),
      statOri.roll * (Math.PI / 180),
      "YXZ"
    );
  } else {
    drone.root.position.set(state.x, state.y, state.z);
    drone.root.rotation.set(
      state.pitch * (Math.PI / 180),
      state.yaw * (Math.PI / 180),
      state.roll * (Math.PI / 180),
      "YXZ"
    );
  }
  drone.updatePropSpin(dt);
  drone.updateShadow(mode === "stationary"
    ? { x: STATIONARY_POS.x, y: STATIONARY_POS.y, z: STATIONARY_POS.z }
    : state);

  pedestal.update(dt);

  // Trail only in flight mode.
  if (mode === "free") {
    trailAccumulator += dt;
    if (trailAccumulator >= TRAIL_PUSH_INTERVAL) {
      trail.push(state.x, state.y, state.z);
      trailAccumulator = 0;
    }
  }

  arena.updateFlash(state.wallFlash);

  // Camera
  if (mode === "stationary") {
    orbitCam.apply();
  } else {
    const yawRad = state.yaw * (Math.PI / 180);
    tmpCam.set(
      state.x - Math.sin(yawRad) * 5.5,
      state.y + 2.5,
      state.z - Math.cos(yawRad) * 5.5
    );
    camTarget.lerp(tmpCam, 0.07);
    camera.position.copy(camTarget);
    camera.lookAt(state.x, state.y + 0.3, state.z);
  }

  // HUD
  if (mode === "stationary") {
    updateAttitude(statOri.roll, statOri.pitch);
    updateCompass(statOri.yaw);
    updateTelemetry(
      { x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, roll: statOri.roll, pitch: statOri.pitch, yaw: statOri.yaw },
      0.5,
      now
    );
  } else {
    updateAttitude(state.roll, state.pitch);
    updateCompass(state.yaw);
    updateTelemetry(state, throttle, now);
  }
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
  const stale = performance.now() - lastInputT > 400;
  const rollIn = stale ? 0 : latestInput.g;
  const pitchIn = stale ? 0 : -latestInput.b;
  const yawIn = stale ? 0 : latestInput.a;

  if (mode === "stationary") {
    // Direct 1:1 mapping with EMA smoothing. No throttle, no kinematics.
    const targetRoll = rollIn;
    const targetPitch = pitchIn;
    const targetYaw = yawIn;
    statOri.roll += (targetRoll - statOri.roll) * STAT_EMA;
    statOri.pitch += (targetPitch - statOri.pitch) * STAT_EMA;
    statOri.yaw += (targetYaw - statOri.yaw) * STAT_EMA;
    return;
  }

  const rates = ctrl.step(rollIn, pitchIn, yawIn, dt);
  state.step(rates, throttle, dt);
}

requestAnimationFrame(frame);
