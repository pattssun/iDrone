// Pedestal halo + downward spotlight + gimbal axes + user-orbit camera,
// used together when the sim is in stationary mode.

import * as THREE from "/static/lib/three.module.min.js";

export const STATIONARY_POS = new THREE.Vector3(0, 4, 0);

// ---------- pedestal halo + spotlight ----------
export function buildPedestal() {
  const group = new THREE.Group();
  group.visible = false;

  // Floor halo — radial-gradient cyan disc on the ground directly below.
  const haloTex = makeHaloTexture();
  const halo = new THREE.Mesh(
    new THREE.PlaneGeometry(8, 8),
    new THREE.MeshBasicMaterial({
      map: haloTex,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
  );
  halo.rotation.x = -Math.PI / 2;
  halo.position.set(STATIONARY_POS.x, 0.02, STATIONARY_POS.z);
  group.add(halo);

  // Thin bright ring on the floor at the same radius — adds a crisp edge
  // the gradient alone is too diffuse to give.
  const ringGeo = new THREE.RingGeometry(1.85, 1.95, 128);
  const ring = new THREE.Mesh(
    ringGeo,
    new THREE.MeshBasicMaterial({
      color: 0x00c2ff,
      transparent: true,
      opacity: 0.0,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(STATIONARY_POS.x, 0.03, STATIONARY_POS.z);
  group.add(ring);

  // Spotlight from above.
  const spot = new THREE.SpotLight(0x9be7ff, 0.0, 18, Math.PI / 6, 0.65, 1.6);
  spot.position.set(STATIONARY_POS.x, 14, STATIONARY_POS.z);
  spot.target.position.copy(STATIONARY_POS);
  group.add(spot);
  group.add(spot.target);

  // Animation state
  const state = { t: 0, intensity: 0, target: 0 };

  function setActive(on) {
    state.target = on ? 1 : 0;
    group.visible = true; // keep visible so the fade animates; hide when fully out
  }

  function update(dt) {
    state.t += dt;
    // Smooth intensity envelope (~250 ms)
    state.intensity += (state.target - state.intensity) * Math.min(1, dt * 6);
    if (state.intensity < 0.005 && state.target === 0) {
      group.visible = false;
      halo.material.opacity = 0;
      ring.material.opacity = 0;
      spot.intensity = 0;
      return;
    }
    // Gentle pulse so the static drone still feels "powered on"
    const pulse = 0.92 + 0.08 * Math.sin(state.t * 2.4);
    halo.material.opacity = 0.55 * state.intensity * pulse;
    ring.material.opacity = 0.85 * state.intensity * pulse;
    spot.intensity = 1.6 * state.intensity * pulse;
  }

  return { group, setActive, update };
}

function makeHaloTexture() {
  const size = 256;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(0, 194, 255, 0.85)");
  g.addColorStop(0.35, "rgba(0, 194, 255, 0.35)");
  g.addColorStop(0.75, "rgba(0, 194, 255, 0.08)");
  g.addColorStop(1, "rgba(0, 194, 255, 0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}

// ---------- user-orbit camera ----------
// Minimal orbit controller: drag to orbit, wheel/pinch to zoom. Active flag
// is checked externally so we can attach once and just gate apply().
export function buildOrbitCamera(canvas, camera, target) {
  let active = false;
  let azimuth = Math.PI; // facing -Z initially → camera is on +Z side, looking at origin
  let elevation = 0.35; // ~20°
  let distance = 5.2; // 20% closer than previous default (was 6.5) — drone reads bigger
  const minDist = 2.0;
  const maxDist = 14.0;
  const minEl = -1.2;
  const maxEl = 1.45;

  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let pointerId = null;

  function onDown(e) {
    if (!active) return;
    dragging = true;
    pointerId = e.pointerId;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(pointerId);
    canvas.style.cursor = "grabbing";
  }
  function onMove(e) {
    if (!dragging || e.pointerId !== pointerId) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    azimuth -= dx * 0.0065;
    elevation = Math.max(minEl, Math.min(maxEl, elevation + dy * 0.0055));
  }
  function onUp(e) {
    if (e.pointerId !== pointerId) return;
    dragging = false;
    pointerId = null;
    canvas.style.cursor = active ? "grab" : "";
  }
  function onWheel(e) {
    if (!active) return;
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1.08 : 1 / 1.08;
    distance = Math.max(minDist, Math.min(maxDist, distance * factor));
  }

  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("pointercancel", onUp);
  canvas.addEventListener("wheel", onWheel, { passive: false });

  function setActive(on) {
    active = on;
    canvas.style.cursor = on ? "grab" : "";
  }

  function apply() {
    const cosEl = Math.cos(elevation);
    const px = target.x + cosEl * Math.sin(azimuth) * distance;
    const py = target.y + Math.sin(elevation) * distance;
    const pz = target.z + cosEl * Math.cos(azimuth) * distance;
    camera.position.set(px, py, pz);
    camera.lookAt(target);
  }

  return { setActive, apply };
}
