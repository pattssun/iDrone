// Quadcopter model built from three.js primitives.

import * as THREE from "/static/lib/three.module.min.js";

export function buildDrone() {
  const root = new THREE.Group();

  // Body — slightly elongated nose-forward (+z is forward in body frame)
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.22, 0.06, 0.32),
    new THREE.MeshStandardMaterial({ color: 0x3a3d44, roughness: 0.65, metalness: 0.2 })
  );
  body.position.y = 0;
  root.add(body);

  // Top accent strip
  const accent = new THREE.Mesh(
    new THREE.BoxGeometry(0.06, 0.008, 0.20),
    new THREE.MeshStandardMaterial({ color: 0x00c2ff, emissive: 0x002a3a, roughness: 0.4 })
  );
  accent.position.y = 0.034;
  root.add(accent);

  // X-config arms with prop hubs + spinning discs at the four tips
  const armMat = new THREE.MeshStandardMaterial({ color: 0x2a2d33, roughness: 0.7 });
  const hubMat = new THREE.MeshStandardMaterial({ color: 0x111418, roughness: 0.5 });
  const propMat = new THREE.MeshBasicMaterial({
    color: 0x00c2ff,
    transparent: true,
    opacity: 0.18,
    side: THREE.DoubleSide,
    depthWrite: false,
  });

  const propMeshes = [];
  const armLength = 0.34;
  const armOffsets = [
    [armLength, armLength],
    [armLength, -armLength],
    [-armLength, armLength],
    [-armLength, -armLength],
  ];
  for (const [dx, dz] of armOffsets) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.015, 0.025), armMat);
    arm.position.set(dx / 2, 0, dz / 2);
    arm.rotation.y = Math.atan2(dz, dx);
    root.add(arm);

    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.024, 16), hubMat);
    hub.position.set(dx, 0.015, dz);
    root.add(hub);

    const prop = new THREE.Mesh(new THREE.CircleGeometry(0.11, 32), propMat);
    prop.rotation.x = -Math.PI / 2;
    prop.position.set(dx, 0.03, dz);
    root.add(prop);
    propMeshes.push(prop);
  }

  // LEDs — white front, red rear
  const ledFront = new THREE.Mesh(
    new THREE.SphereGeometry(0.018, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  );
  ledFront.position.set(0, 0, 0.17);
  root.add(ledFront);
  const ledRear = new THREE.Mesh(
    new THREE.SphereGeometry(0.018, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0xff3b30 })
  );
  ledRear.position.set(0, 0, -0.17);
  root.add(ledRear);

  // Soft elliptical shadow (radial-gradient canvas texture)
  const shadowTex = makeShadowTexture();
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(1.4, 1.4),
    new THREE.MeshBasicMaterial({
      map: shadowTex,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
    })
  );
  shadow.rotation.x = -Math.PI / 2;
  // shadow lives on the scene root (not parented to drone) so altitude scales it.

  function updatePropSpin(dt) {
    for (const p of propMeshes) p.rotation.z += 60 * dt; // 60 rad/s
  }

  function updateShadow(state) {
    shadow.position.set(state.x, 0.012, state.z);
    const k = Math.max(0.2, 1 - state.y / 14);
    shadow.scale.setScalar(k);
    shadow.material.opacity = 0.35 * k;
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
