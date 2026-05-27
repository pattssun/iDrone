// Phone controller — orientation + throttle slider, relayed to the sim.

import { connect } from "/static/js/ws.js?v=5";

// --- DOM ---
const app = document.getElementById("app");
const startBtn = document.getElementById("start-btn");
const permHint = document.getElementById("perm-hint");
const calibCount = document.getElementById("calib-count");
const calibHorizon = document.getElementById("calib-horizon");
const calibrateBtn = document.getElementById("calibrate-btn");
const resetBtn = document.getElementById("reset-btn");
const connDot = document.getElementById("conn-dot");
const statConnDot = document.getElementById("stat-conn-dot");
const modeBadge = document.getElementById("mode-badge");

// CSS "1in" is always 96px regardless of device; on phones that's well under
// a physical inch. Estimate true physical-inch-in-CSS-px from device pixel
// ratio (iPhones: 460 device PPI at DPR 3, 326 at DPR 2) and expose as a
// CSS variable so the landing pad can size to a real-world 2"x2".
(function calibratePhysicalInch() {
  const dpr = window.devicePixelRatio || 1;
  const ua = navigator.userAgent;
  const isiOS = /iPhone|iPad|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);
  let pxPerInch = 96;
  if (isiOS) pxPerInch = dpr >= 3 ? 153 : 163;
  else if (isAndroid) pxPerInch = dpr >= 3 ? 150 : dpr >= 2 ? 160 : 96;
  document.documentElement.style.setProperty("--phys-in", `${pxPerInch}px`);
})();
const connLabel = document.getElementById("conn-label");
const rateEl = document.getElementById("send-rate");
const rPitch = document.getElementById("r-pitch");
const rRoll = document.getElementById("r-roll");
const rYaw = document.getElementById("r-yaw");
const horizonBody = document.getElementById("horizon-body");
const horizonRollPointer = document.getElementById("horizon-roll-pointer");
const throttleTrack = document.querySelector(".thr-track");
const thrFill = document.getElementById("thr-fill");
const thrKnob = document.getElementById("thr-knob");
const thrPct = document.getElementById("thr-pct");
const pulse = document.getElementById("pulse");

// --- Tunables ---
const SEND_HZ = 20;
const SEND_INTERVAL_MS = 1000 / SEND_HZ;
const KEEPALIVE_MS = 200;
const EPS_BG = 0.05;
const EPS_A = 0.1;

// --- State ---
let state = "awaiting";
let baseline = null;
let calibSamples = [];
let lastOrient = { beta: 0, gamma: 0, alpha: 0 };
let lastSent = { b: 0, g: 0, a: 0 };
let throttle = 0.5;
let throttleDirty = false;
let lastSendAt = 0;
let sendIntervals = [];
let pulseLastAt = 0;

// --- Helpers ---
function setStateClass(s) {
  state = s;
  app.classList.remove("state-awaiting", "state-calibrating", "state-live");
  app.classList.add(`state-${s}`);
}
function setConn(s) {
  for (const d of [connDot, statConnDot]) {
    if (!d) continue;
    d.classList.remove("linking", "live");
    if (s === "live") d.classList.add("live");
    else if (s === "linking") d.classList.add("linking");
  }
  if (s === "live") connLabel.textContent = "Live";
  else if (s === "linking") connLabel.textContent = "Linking";
  else connLabel.textContent = "Dropped";
}
function wrapDelta(d) {
  return ((d + 540) % 360) - 180;
}
function vibrate(pattern) {
  try { if (navigator.vibrate) navigator.vibrate(pattern); } catch {}
}
function flashPulse() {
  const now = performance.now();
  if (now - pulseLastAt < 80) return;
  pulseLastAt = now;
  pulse.classList.remove("on");
  // Force reflow so animation restarts.
  void pulse.offsetWidth;
  pulse.classList.add("on");
}

// --- WebSocket link ---
let simMode = "free"; // mirrors the sim's current display mode
function applyMode(next) {
  console.log("[phone] applyMode", next, "(was", simMode + ")");
  if (next !== "free" && next !== "stationary") return;
  if (simMode === next) return;
  simMode = next;
  app.classList.toggle("mode-stationary", simMode === "stationary");
  if (modeBadge) modeBadge.textContent = simMode.toUpperCase();
  console.log("[phone] body classList:", app.className);
  if (simMode === "stationary") {
    // Throttle is irrelevant — show it locked, force value to neutral.
    throttle = 0.5;
    throttleDirty = true;
    drawThrottle();
    vibrate(12);
  } else {
    vibrate(6);
  }
}

const link = connect({
  role: "phone",
  onState: setConn,
  onMessage: (msg) => {
    if (msg.type === "ping" && typeof msg.t === "number") {
      link.send({ type: "pong", t: msg.t });
    } else if (msg.type === "mode" && typeof msg.value === "string") {
      applyMode(msg.value);
    }
  },
});

// --- Orientation handling ---
function onOrientation(e) {
  if (e.beta === null) return;
  lastOrient = { beta: e.beta || 0, gamma: e.gamma || 0, alpha: e.alpha || 0 };
  if (state === "calibrating") {
    calibSamples.push({ ...lastOrient });
    // Live mirror during calibration too so the user sees it react.
    drawHorizon(e.beta, e.gamma);
  } else if (state === "live" && baseline) {
    const b = e.beta - baseline.b;
    const g = e.gamma - baseline.g;
    drawHorizon(b, g);
  }
}

function drawHorizon(pitchDeg, rollDeg) {
  // 2 px per degree of pitch, matches sim attitude indicator scale.
  horizonBody.style.transform = `rotate(${-rollDeg}deg) translateY(${pitchDeg * 2}px)`;
  if (horizonRollPointer) {
    horizonRollPointer.style.transform = `translateX(-50%) rotate(${rollDeg}deg)`;
    horizonRollPointer.style.transformOrigin = `50% calc(50% + 6px)`;
  }
}

// Lightweight horizon for the calibration bubble (rotates only).
function drawCalibHorizon(pitchDeg, rollDeg) {
  calibHorizon.style.transform = `rotate(${-rollDeg}deg) translateY(${pitchDeg * 1.4}px)`;
}

// --- Calibration ---
function startCalibration(onDone) {
  setStateClass("calibrating");
  calibSamples = [];
  let count = 3;
  calibCount.textContent = String(count);
  const tick = setInterval(() => {
    count--;
    if (count > 0) {
      calibCount.textContent = String(count);
    } else {
      clearInterval(tick);
      const tail = calibSamples.slice(-30);
      const sum = tail.reduce(
        (acc, s) => ({ b: acc.b + s.beta, g: acc.g + s.gamma, a: acc.a + s.alpha }),
        { b: 0, g: 0, a: 0 }
      );
      const n = Math.max(1, tail.length);
      baseline = { b: sum.b / n, g: sum.g / n, a: sum.a / n };
      vibrate(20);
      setStateClass("live");
      if (onDone) onDone();
    }
  }, 1000);
}

// Mirror live orientation into the calibration bubble too.
const calibPoll = setInterval(() => {
  if (state === "calibrating") drawCalibHorizon(lastOrient.beta, lastOrient.gamma);
}, 80);

// --- Permission flow ---
async function requestPermission() {
  if (
    typeof DeviceOrientationEvent !== "undefined" &&
    typeof DeviceOrientationEvent.requestPermission === "function"
  ) {
    try {
      const res = await DeviceOrientationEvent.requestPermission();
      if (res !== "granted") {
        permHint.textContent =
          "Motion permission denied. Enable in Settings → Safari → Motion & Orientation Access, then reload.";
        return false;
      }
    } catch (err) {
      permHint.textContent = "Couldn't request motion permission: " + err.message;
      return false;
    }
  }
  return true;
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  const ok = await requestPermission();
  if (!ok) {
    startBtn.disabled = false;
    return;
  }
  window.addEventListener("deviceorientation", onOrientation);
  vibrate(8);
  startCalibration();
});

calibrateBtn.addEventListener("click", () => {
  link.send({ type: "calibrate" });
  vibrate(8);
  startCalibration();
});

resetBtn.addEventListener("click", () => {
  link.send({ type: "reset" });
  throttle = 0.5;
  throttleDirty = true;
  drawThrottle();
  vibrate([8, 30, 8]);
});

// --- Throttle slider ---
function setThrottleFromY(clientY) {
  const rect = throttleTrack.getBoundingClientRect();
  const y = clientY - rect.top;
  const f = 1 - y / rect.height;
  throttle = Math.max(0, Math.min(1, f));
  throttleDirty = true;
  drawThrottle();
}

function drawThrottle() {
  const pct = (1 - throttle) * 100;
  thrKnob.style.top = `${pct}%`;
  if (throttle >= 0.5) {
    thrFill.classList.remove("down");
    thrFill.style.bottom = "50%";
    thrFill.style.top = `${pct}%`;
  } else {
    thrFill.classList.add("down");
    thrFill.style.top = "50%";
    thrFill.style.bottom = `${throttle * 100}%`;
  }
  thrPct.textContent = `${Math.round(throttle * 100)}`;
}

let dragId = null;
let dragVibedOff = false;
throttleTrack.addEventListener(
  "pointerdown",
  (e) => {
    dragId = e.pointerId;
    throttleTrack.setPointerCapture(dragId);
    setThrottleFromY(e.clientY);
    vibrate(4);
    dragVibedOff = false;
  },
  { passive: true }
);
throttleTrack.addEventListener("pointermove", (e) => {
  if (e.pointerId !== dragId) return;
  const before = throttle;
  setThrottleFromY(e.clientY);
  // Tiny haptic when crossing the mid line
  if ((before < 0.5) !== (throttle < 0.5)) vibrate(4);
});
function endDrag(e) {
  if (e.pointerId !== dragId) return;
  dragId = null;
  springReturn();
}
throttleTrack.addEventListener("pointerup", endDrag);
throttleTrack.addEventListener("pointercancel", endDrag);

function springReturn() {
  const start = performance.now();
  const v0 = throttle;
  function tick(now) {
    const t = (now - start) / 280;
    if (t >= 1) {
      throttle = 0.5;
      throttleDirty = true;
      drawThrottle();
      return;
    }
    const k = 1 - Math.pow(1 - t, 3);
    throttle = v0 + (0.5 - v0) * k;
    throttleDirty = true;
    drawThrottle();
    if (dragId === null) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
drawThrottle();

// --- Send loop @ 20 Hz ---
function recordSendInterval(now) {
  if (lastSendAt > 0) {
    sendIntervals.push(now - lastSendAt);
    if (sendIntervals.length > 10) sendIntervals.shift();
    const avg = sendIntervals.reduce((a, b) => a + b, 0) / sendIntervals.length;
    rateEl.textContent = (1000 / avg).toFixed(0);
  }
  lastSendAt = now;
}

function sendLoop() {
  requestAnimationFrame(sendLoop);
  if (state !== "live" || !baseline) return;

  const now = performance.now();
  if (now - lastSendAt < SEND_INTERVAL_MS) return;

  const b = lastOrient.beta - baseline.b;
  const g = lastOrient.gamma - baseline.g;
  const a = wrapDelta(lastOrient.alpha - baseline.a);

  const bMoved = Math.abs(b - lastSent.b) > EPS_BG;
  const gMoved = Math.abs(g - lastSent.g) > EPS_BG;
  const aMoved = Math.abs(a - lastSent.a) > EPS_A;
  const thrMoved = throttleDirty;

  if (!(bMoved || gMoved || aMoved || thrMoved) && now - lastSendAt < KEEPALIVE_MS) {
    return;
  }

  // numeric readouts (always update so the user sees the gyro responding even
  // when nothing's being transmitted)
  rPitch.textContent = fmtDeg(b);
  rRoll.textContent = fmtDeg(g);
  rYaw.textContent = fmtDeg(a);

  let sentSomething = false;
  if (bMoved || gMoved || aMoved || now - lastSendAt >= KEEPALIVE_MS) {
    link.send({ type: "orient", b, g, a, t: Math.round(now) });
    lastSent.b = b;
    lastSent.g = g;
    lastSent.a = a;
    sentSomething = true;
  }
  if (thrMoved) {
    link.send({ type: "throttle", v: throttle, t: Math.round(now) });
    throttleDirty = false;
    sentSomething = true;
  }
  if (sentSomething) {
    recordSendInterval(now);
    flashPulse();
  }
}
requestAnimationFrame(sendLoop);

function fmtDeg(v) {
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${Math.abs(v).toFixed(0)}°`;
}

// --- Quiet hint for Android / desktop browsers without iOS permission API ---
if (
  typeof DeviceOrientationEvent === "undefined" ||
  typeof DeviceOrientationEvent.requestPermission !== "function"
) {
  if (permHint)
    permHint.textContent = "If sensing doesn't start after tapping, reload over HTTPS.";
}

// Prevent iOS pull-to-refresh / rubber-band from interfering with the slider
document.addEventListener(
  "touchmove",
  (e) => {
    if (e.target.closest(".thr-track")) e.preventDefault();
  },
  { passive: false }
);
