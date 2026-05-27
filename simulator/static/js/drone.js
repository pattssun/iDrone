// Stylized Holystone-style mini whoop quadcopter: ducted prop guards,
// white+green striped pod body, green 2-blade front props, black 3-blade rear.

import * as THREE from "/static/lib/three.module.min.js";

const SCALE = 2.2;

export function buildDrone() {
  const root = new THREE.Group();

  // ---------- materials ----------
  const frame = new THREE.MeshStandardMaterial({
    color: 0x14171c,
    roughness: 0.55,
    metalness: 0.15,
  });
  const shellWhite = new THREE.MeshStandardMaterial({
    color: 0xf2f3f5,
    roughness: 0.42,
    metalness: 0.1,
  });
  const stripeGreen = new THREE.MeshStandardMaterial({
    color: 0x2ee07a,
    emissive: 0x1a8f4a,
    emissiveIntensity: 0.5,
    roughness: 0.4,
    metalness: 0.15,
  });
  const accentTeal = new THREE.MeshStandardMaterial({
    color: 0x00c2ff,
    emissive: 0x00aee8,
    emissiveIntensity: 0.9,
    roughness: 0.35,
    metalness: 0.4,
  });
  const propGreen = new THREE.MeshStandardMaterial({
    color: 0x2ee07a,
    emissive: 0x0e6634,
    emissiveIntensity: 0.45,
    roughness: 0.45,
    metalness: 0.1,
    side: THREE.DoubleSide,
  });
  const propBlack = new THREE.MeshStandardMaterial({
    color: 0x1a1c20,
    roughness: 0.55,
    metalness: 0.15,
    side: THREE.DoubleSide,
  });
  const motorCap = new THREE.MeshStandardMaterial({
    color: 0x3a3e44,
    roughness: 0.4,
    metalness: 0.7,
  });

  // ---------- ducted prop guards (the defining feature) ----------
  const ductRadius = 0.34;          // outer radius of each duct
  const ductTube = 0.04;            // tube thickness (torus)
  const ductHalfHeight = 0.07;      // half-height of the cylindrical wall
  const ductOffset = 0.42;          // distance from drone center to duct center

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

    // Cylindrical wall of the duct.
    const wall = new THREE.Mesh(
      new THREE.CylinderGeometry(ductRadius, ductRadius, ductHalfHeight * 2, 36, 1, true),
      frame
    );
    wall.position.set(cx, 0.0, cz);
    root.add(wall);

    // Top and bottom torus rims so the duct reads as a ring from any angle.
    for (const ry of [ductHalfHeight, -ductHalfHeight]) {
      const rim = new THREE.Mesh(
        new THREE.TorusGeometry(ductRadius, ductTube * 0.55, 10, 28),
        frame
      );
      rim.rotation.x = Math.PI / 2;
      rim.position.set(cx, ry, cz);
      root.add(rim);
    }

    // Motor stack centered inside the duct.
    const motorBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.045, 0.05, 0.07, 14),
      frame
    );
    motorBody.position.set(cx, -0.005, cz);
    root.add(motorBody);

    const motorTop = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.02, 14),
      motorCap
    );
    motorTop.position.set(cx, 0.04, cz);
    root.add(motorTop);

    // Propeller: 2-blade for front (green), 3-blade for rear (black) — matches photo.
    const propGroup = new THREE.Group();
    propGroup.position.set(cx, 0.06, cz);
    root.add(propGroup);

    const bladeMat = front ? propGreen : propBlack;
    const bladeCount = front ? 2 : 3;
    const bladeLength = ductRadius * 1.7;
    const bladeWidth = 0.06;
    for (let i = 0; i < bladeCount; i++) {
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(bladeLength, 0.008, bladeWidth),
        bladeMat
      );
      blade.rotation.y = (i / bladeCount) * Math.PI * 2;
      // Slight twist (pitched leading edge) — fakes airfoil shape.
      blade.rotation.x = 0.18;
      propGroup.add(blade);
    }

    const hub = new THREE.Mesh(
      new THREE.CylinderGeometry(0.028, 0.028, 0.018, 12),
      front ? propGreen : motorCap
    );
    hub.position.y = 0.006;
    propGroup.add(hub);

    // Translucent motion-blur disc when spinning.
    const sweep = new THREE.Mesh(
      new THREE.CircleGeometry(ductRadius * 0.9, 32),
      new THREE.MeshBasicMaterial({
        color: front ? 0x7af0a8 : 0x808890,
        transparent: true,
        opacity: 0.08,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    sweep.rotation.x = -Math.PI / 2;
    sweep.position.y = 0.005;
    propGroup.add(sweep);

    propMeshes.push(propGroup);
  }

  // ---------- center pod body (white shell with bold green stripe) ----------
  const podGroup = new THREE.Group();
  root.add(podGroup);

  // Main pod — capsule along Z, narrow and sleek.
  const pod = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.13, 0.4, 8, 18),
    shellWhite
  );
  pod.rotation.x = Math.PI / 2;
  pod.position.y = 0.02;
  podGroup.add(pod);

  // Underside ridge / battery housing — flatter dark block under the pod.
  const battery = new THREE.Mesh(
    new THREE.BoxGeometry(0.16, 0.06, 0.36),
    frame
  );
  battery.position.set(0, -0.06, 0);
  podGroup.add(battery);

  // Green stripe — runs along the top of the pod from nose to tail.
  const stripe = new THREE.Mesh(
    new THREE.BoxGeometry(0.07, 0.012, 0.62),
    stripeGreen
  );
  stripe.position.set(0, 0.13, 0);
  podGroup.add(stripe);

  // Side wings of the stripe (small green tabs flaring out near the middle).
  for (const sx of [-1, 1]) {
    const tab = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.008, 0.18),
      stripeGreen
    );
    tab.position.set(sx * 0.08, 0.07, 0);
    tab.rotation.z = sx * 0.25;
    podGroup.add(tab);
  }

  // Nose bump (canopy front).
  const nose = new THREE.Mesh(
    new THREE.SphereGeometry(0.1, 18, 12, 0, Math.PI * 2, 0, Math.PI / 2),
    shellWhite
  );
  nose.scale.set(1.0, 0.5, 1.1);
  nose.position.set(0, 0.04, 0.22);
  podGroup.add(nose);

  // ---------- arm connectors (thin struts from pod to each duct) ----------
  for (const { sx, sz } of corners) {
    const strut = new THREE.Mesh(
      new THREE.BoxGeometry(0.46, 0.022, 0.05),
      frame
    );
    strut.position.set((sx * ductOffset) / 2, 0.0, (sz * ductOffset) / 2);
    strut.rotation.y = -Math.atan2(sz * ductOffset, sx * ductOffset);
    root.add(strut);
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
  root.add(led(0xffffff, 0.0, 0.06, 0.33, 1.4));   // front white
  root.add(led(0xff3b30, 0.0, 0.06, -0.33, 1.4));  // rear red

  // ---------- landing feet (tiny stubs under each duct) ----------
  for (const { sx, sz } of corners) {
    const foot = new THREE.Mesh(
      new THREE.CylinderGeometry(0.018, 0.022, 0.05, 8),
      frame
    );
    foot.position.set(sx * ductOffset, -ductHalfHeight - 0.025, sz * ductOffset);
    root.add(foot);
  }

  // ---------- scale ----------
  root.scale.setScalar(SCALE);

  // ---------- shadow (lives on scene root, not parented to drone) ----------
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
