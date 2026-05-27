// Stylized Holystone-style mini whoop quadcopter — ducted prop guards in
// light gray with subtle teal accent rings (read against the dark arena),
// white pod body with bold green nose-to-tail stripe and side accents,
// green 2-blade front props, black 3-blade rear props, soft under-glow.

import * as THREE from "/static/lib/three.module.min.js";

const SCALE = 2.2;

export function buildDrone() {
  const root = new THREE.Group();

  // ---------- materials ----------
  // Prop guards: medium-light gray so they pop against the dark arena.
  const guard = new THREE.MeshStandardMaterial({
    color: 0xb2b9c2,
    roughness: 0.55,
    metalness: 0.25,
  });
  const guardDark = new THREE.MeshStandardMaterial({
    color: 0x4a5057,
    roughness: 0.6,
    metalness: 0.25,
  });
  const shellWhite = new THREE.MeshStandardMaterial({
    color: 0xf6f7f9,
    roughness: 0.4,
    metalness: 0.12,
  });
  const stripeGreen = new THREE.MeshStandardMaterial({
    color: 0x2ee07a,
    emissive: 0x1a8f4a,
    emissiveIntensity: 0.65,
    roughness: 0.4,
    metalness: 0.15,
  });
  const accentTeal = new THREE.MeshStandardMaterial({
    color: 0x00c2ff,
    emissive: 0x00aee8,
    emissiveIntensity: 1.0,
    roughness: 0.35,
    metalness: 0.4,
  });
  const propGreen = new THREE.MeshStandardMaterial({
    color: 0x2ee07a,
    emissive: 0x0e6634,
    emissiveIntensity: 0.55,
    roughness: 0.45,
    metalness: 0.1,
    side: THREE.DoubleSide,
  });
  const propDark = new THREE.MeshStandardMaterial({
    color: 0x2a2d32,
    roughness: 0.55,
    metalness: 0.2,
    side: THREE.DoubleSide,
  });
  const motorCap = new THREE.MeshStandardMaterial({
    color: 0x3a3e44,
    roughness: 0.35,
    metalness: 0.75,
  });
  const battery = new THREE.MeshStandardMaterial({
    color: 0x22262c,
    roughness: 0.5,
    metalness: 0.3,
  });

  // ---------- ducted prop guards (the defining feature) ----------
  const ductRadius = 0.34;
  const ductTube = 0.04;
  const ductHalfHeight = 0.07;
  const ductOffset = 0.42;

  const propMeshes = [];
  const corners = [
    { sx: +1, sz: +1, front: true },
    { sx: -1, sz: +1, front: true },
    { sx: +1, sz: -1, front: false },
    { sx: -1, sz: -1, front: false },
  ];

  for (const { sx, sz, front } of corners) {
    const cx = sx * ductOffset;
    const cz = sz * ductOffset;

    // Outer wall of the duct.
    const wall = new THREE.Mesh(
      new THREE.CylinderGeometry(ductRadius, ductRadius, ductHalfHeight * 2, 36, 1, true),
      guard
    );
    wall.position.set(cx, 0.0, cz);
    root.add(wall);

    // Top + bottom torus rims.
    for (const ry of [ductHalfHeight, -ductHalfHeight]) {
      const rim = new THREE.Mesh(
        new THREE.TorusGeometry(ductRadius, ductTube * 0.6, 12, 32),
        guardDark
      );
      rim.rotation.x = Math.PI / 2;
      rim.position.set(cx, ry, cz);
      root.add(rim);
    }

    // Inner teal accent ring at the top — subtle tech glow.
    const accent = new THREE.Mesh(
      new THREE.TorusGeometry(ductRadius * 0.92, 0.006, 8, 32),
      accentTeal
    );
    accent.rotation.x = Math.PI / 2;
    accent.position.set(cx, ductHalfHeight + 0.002, cz);
    root.add(accent);

    // Motor stack centered inside the duct.
    const motorBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.045, 0.05, 0.07, 14),
      guardDark
    );
    motorBody.position.set(cx, -0.005, cz);
    root.add(motorBody);

    const motorTop = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.02, 14),
      motorCap
    );
    motorTop.position.set(cx, 0.04, cz);
    root.add(motorTop);

    // Propellers: green 2-blade for front, dark 3-blade for rear.
    const propGroup = new THREE.Group();
    propGroup.position.set(cx, 0.06, cz);
    root.add(propGroup);

    const bladeMat = front ? propGreen : propDark;
    const bladeCount = front ? 2 : 3;
    const bladeLength = ductRadius * 1.7;
    const bladeWidth = 0.06;
    for (let i = 0; i < bladeCount; i++) {
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(bladeLength, 0.008, bladeWidth),
        bladeMat
      );
      blade.rotation.y = (i / bladeCount) * Math.PI * 2;
      blade.rotation.x = 0.18;
      propGroup.add(blade);
    }

    const hub = new THREE.Mesh(
      new THREE.CylinderGeometry(0.028, 0.028, 0.018, 12),
      front ? propGreen : motorCap
    );
    hub.position.y = 0.006;
    propGroup.add(hub);

    const sweep = new THREE.Mesh(
      new THREE.CircleGeometry(ductRadius * 0.92, 32),
      new THREE.MeshBasicMaterial({
        color: front ? 0x7af0a8 : 0xc8d0db,
        transparent: true,
        opacity: 0.07,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    sweep.rotation.x = -Math.PI / 2;
    sweep.position.y = 0.005;
    propGroup.add(sweep);

    propMeshes.push(propGroup);
  }

  // ---------- center pod body ----------
  const podGroup = new THREE.Group();
  root.add(podGroup);

  // Main pod (capsule along Z).
  const pod = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.13, 0.42, 8, 18),
    shellWhite
  );
  pod.rotation.x = Math.PI / 2;
  pod.position.y = 0.02;
  podGroup.add(pod);

  // Underside battery housing.
  const batt = new THREE.Mesh(
    new THREE.BoxGeometry(0.17, 0.06, 0.38),
    battery
  );
  batt.position.set(0, -0.06, 0);
  podGroup.add(batt);

  // Bold green stripe along the top spine.
  const stripeTop = new THREE.Mesh(
    new THREE.BoxGeometry(0.08, 0.014, 0.66),
    stripeGreen
  );
  stripeTop.position.set(0, 0.14, 0);
  podGroup.add(stripeTop);

  // Two flanking green stripes that taper toward the nose and tail.
  for (const sx of [-1, 1]) {
    const flank = new THREE.Mesh(
      new THREE.BoxGeometry(0.022, 0.012, 0.58),
      stripeGreen
    );
    flank.position.set(sx * 0.08, 0.105, 0);
    flank.rotation.z = sx * 0.12;
    podGroup.add(flank);
  }

  // Green nose chevron — pointed accent at the very front, makes forward
  // direction unmistakable even at a glance.
  const noseChev = new THREE.Mesh(
    new THREE.ConeGeometry(0.07, 0.12, 4),
    stripeGreen
  );
  noseChev.rotation.x = Math.PI / 2;
  noseChev.rotation.y = Math.PI / 4;
  noseChev.position.set(0, 0.06, 0.3);
  podGroup.add(noseChev);

  // Nose canopy bump.
  const nose = new THREE.Mesh(
    new THREE.SphereGeometry(0.1, 18, 12, 0, Math.PI * 2, 0, Math.PI / 2),
    shellWhite
  );
  nose.scale.set(1.0, 0.5, 1.1);
  nose.position.set(0, 0.04, 0.18);
  podGroup.add(nose);

  // Cyan canopy detail line across the top of the nose.
  const noseLine = new THREE.Mesh(
    new THREE.BoxGeometry(0.16, 0.006, 0.018),
    accentTeal
  );
  noseLine.position.set(0, 0.085, 0.21);
  podGroup.add(noseLine);

  // ---------- arm connectors (thin struts from pod to each duct) ----------
  for (const { sx, sz } of corners) {
    const strut = new THREE.Mesh(
      new THREE.BoxGeometry(0.46, 0.024, 0.055),
      guard
    );
    strut.position.set((sx * ductOffset) / 2, 0.0, (sz * ductOffset) / 2);
    strut.rotation.y = -Math.atan2(sz * ductOffset, sx * ductOffset);
    root.add(strut);

    // Small green accent block where the strut meets the duct.
    const tip = new THREE.Mesh(
      new THREE.BoxGeometry(0.05, 0.018, 0.05),
      stripeGreen
    );
    tip.position.set(sx * (ductOffset * 0.78), 0.01, sz * (ductOffset * 0.78));
    root.add(tip);
  }

  // ---------- nav LEDs ----------
  const ledMat = (hex, em) =>
    new THREE.MeshStandardMaterial({
      color: hex,
      emissive: hex,
      emissiveIntensity: em,
      roughness: 0.4,
    });
  const led = (hex, x, y, z, em = 1.2, r = 0.022) => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 10), ledMat(hex, em));
    m.position.set(x, y, z);
    return m;
  };
  root.add(led(0xffffff, 0.0, 0.08, 0.36, 1.6));
  root.add(led(0xff3b30, 0.0, 0.08, -0.36, 1.4));

  // ---------- under-glow (subtle teal disc on the belly) ----------
  const underGlow = new THREE.Mesh(
    new THREE.CircleGeometry(0.32, 36),
    new THREE.MeshBasicMaterial({
      color: 0x00c2ff,
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  underGlow.rotation.x = Math.PI / 2;
  underGlow.position.y = -0.105;
  root.add(underGlow);

  // ---------- landing feet ----------
  for (const { sx, sz } of corners) {
    const foot = new THREE.Mesh(
      new THREE.CylinderGeometry(0.018, 0.022, 0.05, 8),
      guardDark
    );
    foot.position.set(sx * ductOffset, -ductHalfHeight - 0.025, sz * ductOffset);
    root.add(foot);
  }

  // ---------- scale ----------
  root.scale.setScalar(SCALE);

  // ---------- shadow ----------
  const shadowTex = makeShadowTexture();
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(2.4 * SCALE, 2.4 * SCALE),
    new THREE.MeshBasicMaterial({
      map: shadowTex,
      transparent: true,
      opacity: 0.4,
      depthWrite: false,
    })
  );
  shadow.rotation.x = -Math.PI / 2;

  function updatePropSpin(dt) {
    for (const p of propMeshes) p.rotation.y += 60 * dt;
  }

  function updateShadow(state) {
    shadow.position.set(state.x, 0.012, state.z);
    const k = Math.max(0.25, 1 - state.y / 16);
    shadow.scale.setScalar(k);
    shadow.material.opacity = 0.4 * k;
  }

  return { root, shadow, updatePropSpin, updateShadow };
}

function makeShadowTexture() {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(0,0,0,0.55)");
  g.addColorStop(0.5, "rgba(0,0,0,0.18)");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}
