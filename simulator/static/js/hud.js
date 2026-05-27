// HUD: attitude indicator, compass tape, telemetry cards, top status bar.

const $ = (id) => document.getElementById(id);

const attBody = $("att-body");
const attReticle = $("att-reticle");
const compassStrip = $("compass-strip");
const fpsEl = $("hud-fps");
const latEl = $("hud-lat");
const rateEl = $("hud-rate");
const stateLabel = $("hud-state");
const stateDot = $("hud-state-dot");

const vAlt = $("v-alt");
const vVsp = $("v-vsp");
const vHsp = $("v-hsp");
const vThr = $("v-thr");
const vX = $("v-x");
const vY = $("v-y");
const vZ = $("v-z");

// Build compass tick marks once: every 5°, labels at 30°.
(function buildCompass() {
  const dirLabels = { 0: "N", 90: "E", 180: "S", 270: "W" };
  // Show a window of -90..+90 around current yaw; the strip itself is 1080px
  // wide (3° per pixel) and we translate the parent.
  let html = "";
  for (let deg = -180; deg <= 540; deg += 5) {
    const norm = ((deg % 360) + 360) % 360;
    const cls =
      norm % 90 === 0 ? "tick major" : norm % 30 === 0 ? "tick mid" : "tick";
    let lbl = "";
    if (norm % 30 === 0) {
      lbl = dirLabels[norm] || String(norm);
    }
    const x = (deg + 180) * 4; // 4 px per degree → 720px wide strip
    html += `<div class="${cls}" style="left:${x}px"><span>${lbl}</span></div>`;
  }
  compassStrip.innerHTML = html;
})();

export function updateAttitude(rollDeg, pitchDeg) {
  // Sky/ground halves: rotate by -roll, then translate vertical by pitch*2 px/°.
  attBody.style.transform = `rotate(${-rollDeg}deg) translateY(${pitchDeg * 2}px)`;
}

export function updateCompass(yawDeg) {
  // yaw 0 = N → strip translated so the "0" tick sits under the centre reticle.
  // Strip width per degree = 4 px. Centre offset baked in via the CSS layout.
  compassStrip.style.transform = `translateX(${-yawDeg * 4}px)`;
}

let lastT = performance.now();
let fpsEMA = 60;
let lastFpsUpdate = 0;

export function updateTelemetry(state, throttle, now) {
  const dt = (now - lastT) / 1000;
  lastT = now;
  if (dt > 0) fpsEMA = 0.92 * fpsEMA + 0.08 * (1 / dt);
  if (now - lastFpsUpdate > 250) {
    fpsEl.textContent = fpsEMA.toFixed(0);
    lastFpsUpdate = now;
  }

  vAlt.textContent = state.y.toFixed(1) + " m";
  vVsp.textContent = (state.vy >= 0 ? "+" : "") + state.vy.toFixed(1);
  const hsp = Math.hypot(state.vx, state.vz);
  vHsp.textContent = hsp.toFixed(1);
  vThr.textContent = Math.round(throttle * 100) + "%";
  vX.textContent = (state.x >= 0 ? "+" : "") + state.x.toFixed(1);
  vY.textContent = (state.y >= 0 ? "+" : "") + state.y.toFixed(1);
  vZ.textContent = (state.z >= 0 ? "+" : "") + state.z.toFixed(1);
}

export function setLinkStatus({ peer, latencyMs, rateHz }) {
  if (peer === "connected") {
    stateLabel.textContent = "LIVE";
    stateDot.className = "dot live";
  } else if (peer === "linking") {
    stateLabel.textContent = "LINKING";
    stateDot.className = "dot linking";
  } else {
    stateLabel.textContent = "WAITING";
    stateDot.className = "dot";
  }
  if (latencyMs != null) latEl.textContent = Math.round(latencyMs);
  if (rateHz != null) rateEl.textContent = Math.round(rateHz);
}
