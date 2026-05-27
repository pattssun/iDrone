// Position trail — ring buffer rendered as a Line with per-vertex alpha fade.

import * as THREE from "/static/lib/three.module.min.js";

const MAX = 60; // ~2 s at the 30 Hz push rate in sim.js

export function buildTrail() {
  const positions = new Float32Array(MAX * 3);
  const colors = new Float32Array(MAX * 3); // r,g,b in 0..1 (alpha via opacity per vertex isn't a thing → fade via color toward bg)
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.setDrawRange(0, 0);

  const mat = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.45,
  });
  const line = new THREE.Line(geo, mat);
  line.frustumCulled = false;

  let head = 0; // next write index
  let count = 0;

  function push(x, y, z) {
    const i = head * 3;
    positions[i] = x;
    positions[i + 1] = y;
    positions[i + 2] = z;
    head = (head + 1) % MAX;
    if (count < MAX) count++;
    rebuild();
  }

  function clear() {
    head = 0;
    count = 0;
    geo.setDrawRange(0, 0);
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
  }

  // The Line draws consecutive vertices in buffer order; the ring buffer is
  // unrolled into a contiguous oldest→newest sequence each push so the line
  // doesn't snap across the wrap point.
  const ordered = new Float32Array(MAX * 3);
  const orderedColor = new Float32Array(MAX * 3);

  function rebuild() {
    const start = (head - count + MAX) % MAX;
    for (let k = 0; k < count; k++) {
      const src = ((start + k) % MAX) * 3;
      const dst = k * 3;
      ordered[dst] = positions[src];
      ordered[dst + 1] = positions[src + 1];
      ordered[dst + 2] = positions[src + 2];
      // Older = darker (fade toward background); newer = accent.
      const f = k / Math.max(1, count - 1); // 0 = oldest, 1 = newest
      orderedColor[dst] = 0.0;
      orderedColor[dst + 1] = 0.02 * (1 - f) + 0.42 * f;
      orderedColor[dst + 2] = 0.04 * (1 - f) + 0.55 * f;
    }
    geo.attributes.position.array.set(ordered);
    geo.attributes.color.array.set(orderedColor);
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
    geo.setDrawRange(0, count);
  }

  return { line, push, clear };
}
