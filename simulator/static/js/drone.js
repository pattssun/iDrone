// Stylized quadcopter, three.js primitives. Mavic-inspired silhouette.

import * as THREE from "/static/lib/three.module.min.js";

const SCALE = 2.2; // overall multiplier — bake the new size into the model

export function buildDrone() {
  const root = new THREE.Group();

  // ---------- materials ----------
  // Pearl-white shell. Reads bright against the #0a0d12 sim background and
  // catches the directional light dramatically.
  const shell = new THREE.MeshStandardMaterial({
    color: 0xe9ecf2,
    roughness: 0.38,
    metalness: 0.15,
  });
  const shellAccent = new THREE.MeshStandardMaterial({
    color: 0xb8c0cc,
    roughness: 0.45,
    metalness: 0.2,
  });
  const glossBlack = new THREE.MeshStandardMaterial({
    color: 0x0a0c10,
    roughness: 0.08,
    metalness: 0.2,
  });
  const accentTeal = new THREE.MeshStandardMaterial({
    color: 0x00c2ff,
    emissive: 0x00aee8,
    emissiveIntensity: 1.0,
    roughness: 0.35,
    metalness: 0.4,
  });
  const metalRing = new THREE.MeshStandardMaterial({
    color: 0x6a6e76,
    roughness: 0.32,
    metalness: 0.85,
  });
  const motorTop = new THREE.MeshStandardMaterial({
    color: 0xff4b3a,
    emissive: 0x7a1a0c,
    emissiveIntensity: 0.55,
    roughness: 0.4,
    metalness: 0.5,
  });
  const propMat = new THREE.MeshStandardMaterial({
    color: 0xd4dae3,
    roughness: 0.5,
    metalness: 0.1,
    side: THREE.DoubleSide,
  });
  // Front props are green so the forward direction is unmistakable.
  const propMatFront = new THREE.MeshStandardMaterial({
    color: 0x2ee07a,
    emissive: 0x0e6634,
    emissiveIntensity: 0.45,
    roughness: 0.45,
    metalness: 0.1,
    side: THREE.DoubleSide,
  });

  // ---------- core body (sleek lozenge) ----------
  const bodyGroup = new THREE.Group();
  root.add(bodyGroup);

  // Bottom shell — capsule scaled into a flat oval.
  const bellyGeo = new THREE.CapsuleGeometry(0.18, 0.34, 6, 18);
  const belly = new THREE.Mesh(bellyGeo, shell);
  belly.rotation.z = Math.PI / 2;
  belly.scale.set(0.65, 1.0, 1.0); // squish vertically into a flat oval
  belly.position.y = -0.02;
  bodyGroup.add(belly);

  // Top dome (sensor pod).
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(0.16, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2),
    glossBlack
  );
  dome.scale.set(1.0, 0.55, 1.6);
  dome.position.set(0, 0.03, -0.02);
  bodyGroup.add(dome);

  // Cyan accent strip running along the top of the dome.
  const strip = new THREE.Mesh(
    new THREE.BoxGeometry(0.04, 0.005, 0.42),
    accentTeal
  );
  strip.position.set(0, 0.116, -0.02);
  bodyGroup.add(strip);

  // Subtle ridge running across the nose for texture.
  const ridge = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.012, 0.05), shellAccent);
  ridge.position.set(0, 0.04, 0.21);
  bodyGroup.add(ridge);

  // ---------- camera gimbal under the nose ----------
  const gimbalArm = new THREE.Mesh(
    new THREE.CylinderGeometry(0.022, 0.022, 0.09, 12),
    glossBlack
  );
  gimbalArm.position.set(0, -0.04, 0.22);
  gimbalArm.rotation.x = Math.PI / 12;
  bodyGroup.add(gimbalArm);

  const gimbalHousing = new THREE.Mesh(
    new THREE.BoxGeometry(0.1, 0.08, 0.1),
    glossBlack
  );
  gimbalHousing.position.set(0, -0.1, 0.27);
  bodyGroup.add(gimbalHousing);

  const lens = new THREE.Mesh(
    new THREE.SphereGeometry(0.034, 18, 14),
    new THREE.MeshStandardMaterial({
      color: 0x0a0c10,
      roughness: 0.05,
      metalness: 0.1,
      emissive: 0x003040,
      emissiveIntensity: 0.5,
    })
  );
  lens.position.set(0, -0.1, 0.33);
  bodyGroup.add(lens);

  const lensRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.04, 0.006, 10, 22),
    metalRing
  );
  lensRing.position.copy(lens.position);
  lensRing.rotation.y = Math.PI / 2;
  lensRing.rotation.x = Math.PI / 2;
  bodyGroup.add(lensRing);

  // ---------- antenna ----------
  const antenna = new THREE.Mesh(
    new THREE.CylinderGeometry(0.008, 0.008, 0.16, 8),
    glossBlack
  );
  antenna.position.set(0, 0.15, -0.18);
  bodyGroup.add(antenna);
  const antennaTip = new THREE.Mesh(
    new THREE.SphereGeometry(0.018, 10, 8),
    accentTeal
  );
  antennaTip.position.set(0, 0.24, -0.18);
  bodyGroup.add(antennaTip);

  // ---------- arms + motors + props ----------
  const armOffsets = [
    [+1, +1, "front-right"],
    [+1, -1, "back-right"],
    [-1, +1, "front-left"],
    [-1, -1, "back-left"],
  ];
  const armReach = 0.55;
  const armThickness = 0.045;

  const propMeshes = [];

  for (const [sx, sz] of armOffsets) {
    // Arm — tapered using two boxes (root + tip) to fake taper without lathe.
    const armRoot = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, armThickness, armThickness * 1.6),
      shell
    );
    armRoot.position.set((sx * armReach) / 2, -0.02, (sz * armReach) / 2);
    armRoot.rotation.y = -Math.atan2(sz, sx);
    bodyGroup.add(armRoot);

    const armX = sx * armReach;
    const armZ = sz * armReach;

    // Motor stack — base cylinder + heat-sink ring + top cap (red/blue per side)
    const motorBase = new THREE.Mesh(
      new THREE.CylinderGeometry(0.062, 0.07, 0.05, 18),
      glossBlack
    );
    motorBase.position.set(armX, 0.0, armZ);
    bodyGroup.add(motorBase);

    const motorCore = new THREE.Mesh(
      new THREE.CylinderGeometry(0.055, 0.055, 0.06, 18),
      metalRing
    );
    motorCore.position.set(armX, 0.045, armZ);
    bodyGroup.add(motorCore);

    const motorCap = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.052, 0.018, 18),
      motorTop
    );
    motorCap.position.set(armX, 0.085, armZ);
    bodyGroup.add(motorCap);

    // Propeller — two long blades crossed, plus a translucent disc to fake
    // motion-blurred sweep when spinning. Blades are big enough to read at a
    // glance and bright enough to pop against the dark background.
    const propGroup = new THREE.Group();
    propGroup.position.set(armX, 0.108, armZ);
    bodyGroup.add(propGroup);

    const isFront = sz > 0;
    const bladeMat = isFront ? propMatFront : propMat;
    const blade1 = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.008, 0.028), bladeMat);
    const blade2 = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.008, 0.028), bladeMat);
    blade2.rotation.y = Math.PI / 2;
    propGroup.add(blade1, blade2);

    // A faint hub cap to seat the props.
    const hubCap = new THREE.Mesh(
      new THREE.CylinderGeometry(0.024, 0.024, 0.012, 14),
      shellAccent
    );
    hubCap.position.y = 0.008;
    propGroup.add(hubCap);

    const sweep = new THREE.Mesh(
      new THREE.CircleGeometry(0.22, 32),
      new THREE.MeshBasicMaterial({
        color: isFront ? 0x7af0a8 : 0xb0d6ff,
        transparent: true,
        opacity: 0.09,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    sweep.rotation.x = -Math.PI / 2;
    sweep.position.y = 0.002;
    propGroup.add(sweep);
    propMeshes.push(propGroup);
  }

  // ---------- nav LEDs (proper aviation: red right, green left, white front, red rear) ----------
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
  bodyGroup.add(led(0xffffff, 0.0, 0.0, 0.32, 1.4)); // front white
  bodyGroup.add(led(0xff3b30, 0.0, 0.0, -0.32, 1.4)); // rear red
  bodyGroup.add(led(0xff3b30, 0.28, -0.02, 0.02, 1.0, 0.018)); // starboard red
  bodyGroup.add(led(0x33d17a, -0.28, -0.02, 0.02, 1.0, 0.018)); // port green

  // ---------- landing skids ----------
  const skidMat = glossBlack;
  for (const sx of [-1, 1]) {
    const skid = new THREE.Mesh(
      new THREE.CylinderGeometry(0.012, 0.012, 0.5, 10),
      skidMat
    );
    skid.rotation.x = Math.PI / 2;
    skid.position.set(sx * 0.18, -0.16, 0);
    bodyGroup.add(skid);

    for (const sz of [-0.18, 0.18]) {
      const strut = new THREE.Mesh(
        new THREE.CylinderGeometry(0.01, 0.01, 0.16, 8),
        skidMat
      );
      strut.position.set(sx * 0.18, -0.08, sz);
      bodyGroup.add(strut);
    }
  }

  // ---------- scale ----------
  bodyGroup.scale.setScalar(SCALE);

  // ---------- shadow (lives on scene root, not parented to drone) ----------
  const shadowTex = makeShadowTexture();
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(2.2 * SCALE, 2.2 * SCALE),
    new THREE.MeshBasicMaterial({
      map: shadowTex,
      transparent: true,
      opacity: 0.4,
      depthWrite: false,
    })
  );
  shadow.rotation.x = -Math.PI / 2;

  function updatePropSpin(dt) {
    for (const p of propMeshes) p.rotation.y += 60 * dt; // 60 rad/s
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
