// Bounding cube + grid + wall flash planes.

import * as THREE from "/static/lib/three.module.min.js";
import { ARENA } from "/static/js/physics.js";

export function buildArena() {
  const group = new THREE.Group();

  // Floor grid: 1-m lines
  const grid = new THREE.GridHelper(ARENA.x * 2, ARENA.x * 2, 0x4a6a86, 0x29384a);
  grid.material.opacity = 0.95;
  grid.material.transparent = true;
  group.add(grid);

  // Accent grid every 5 m
  const accent = new THREE.GridHelper(ARENA.x * 2, (ARENA.x * 2) / 5, 0x7fb3d5, 0x7fb3d5);
  accent.material.opacity = 0.85;
  accent.material.transparent = true;
  accent.position.y = 0.002;
  group.add(accent);

  // Dim ceiling grid mirrors the floor so altitude changes register
  const ceil = new THREE.GridHelper(ARENA.x * 2, ARENA.x * 2, 0x2f4458, 0x1c2837);
  ceil.material.opacity = 0.45;
  ceil.material.transparent = true;
  ceil.position.y = ARENA.yMax;
  group.add(ceil);

  // Bounding cube — wireframe edges only (brighter + glow pass)
  const boxGeo = new THREE.BoxGeometry(ARENA.x * 2, ARENA.yMax, ARENA.z * 2);
  const edges = new THREE.EdgesGeometry(boxGeo);
  const cube = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({
      color: 0x00c2ff,
      transparent: true,
      opacity: 0.6,
    })
  );
  cube.position.y = ARENA.yMax / 2;
  group.add(cube);

  const cubeGlow = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({
      color: 0x6fe4ff,
      transparent: true,
      opacity: 0.18,
    })
  );
  cubeGlow.position.y = ARENA.yMax / 2;
  cubeGlow.scale.setScalar(1.005);
  group.add(cubeGlow);

  // Corner pylons — vertical lines at each floor corner from y=0 to yMax
  const pylonMat = new THREE.LineBasicMaterial({
    color: 0x00c2ff,
    transparent: true,
    opacity: 0.55,
  });
  const pylonGeo = new THREE.BufferGeometry();
  const pylonVerts = [];
  for (const sx of [-ARENA.x, ARENA.x]) {
    for (const sz of [-ARENA.z, ARENA.z]) {
      pylonVerts.push(sx, 0.001, sz, sx, ARENA.yMax, sz);
    }
  }
  pylonGeo.setAttribute("position", new THREE.Float32BufferAttribute(pylonVerts, 3));
  group.add(new THREE.LineSegments(pylonGeo, pylonMat));

  // Floor axis cross at origin — bright cyan stripes on x=0 and z=0
  const axisMat = new THREE.LineBasicMaterial({
    color: 0x6fe4ff,
    transparent: true,
    opacity: 0.7,
  });
  const axisGeo = new THREE.BufferGeometry();
  axisGeo.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(
      [
        -ARENA.x, 0.003, 0, ARENA.x, 0.003, 0,
        0, 0.003, -ARENA.z, 0, 0.003, ARENA.z,
      ],
      3
    )
  );
  group.add(new THREE.LineSegments(axisGeo, axisMat));

  // Subtle axis ticks: short outward marks at the floor every 5m for spatial sense
  const tickMat = new THREE.LineBasicMaterial({ color: 0x7fb3d5, transparent: true, opacity: 0.85 });
  const tickGeo = new THREE.BufferGeometry();
  const tickVerts = [];
  for (let x = -ARENA.x; x <= ARENA.x; x += 5) {
    tickVerts.push(x, 0.001, -ARENA.z, x, 0.5, -ARENA.z);
    tickVerts.push(x, 0.001, ARENA.z, x, 0.5, ARENA.z);
  }
  for (let z = -ARENA.z; z <= ARENA.z; z += 5) {
    tickVerts.push(-ARENA.x, 0.001, z, -ARENA.x, 0.5, z);
    tickVerts.push(ARENA.x, 0.001, z, ARENA.x, 0.5, z);
  }
  tickGeo.setAttribute("position", new THREE.Float32BufferAttribute(tickVerts, 3));
  group.add(new THREE.LineSegments(tickGeo, tickMat));

  // Wall flash planes — order matches DroneState.wallFlash: +x, -x, +z, -z, +y, -y
  const flashMat = () =>
    new THREE.MeshBasicMaterial({
      color: 0xff3b30,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
  const planeXZ = new THREE.PlaneGeometry(ARENA.x * 2, ARENA.yMax);
  const planeXY = new THREE.PlaneGeometry(ARENA.x * 2, ARENA.z * 2);

  const faces = [];
  const yCenter = ARENA.yMax / 2;

  const fPosX = new THREE.Mesh(planeXZ, flashMat());
  fPosX.rotation.y = -Math.PI / 2;
  fPosX.position.set(ARENA.x, yCenter, 0);
  faces.push(fPosX);

  const fNegX = new THREE.Mesh(planeXZ, flashMat());
  fNegX.rotation.y = Math.PI / 2;
  fNegX.position.set(-ARENA.x, yCenter, 0);
  faces.push(fNegX);

  const fPosZ = new THREE.Mesh(planeXZ, flashMat());
  fPosZ.position.set(0, yCenter, ARENA.z);
  faces.push(fPosZ);

  const fNegZ = new THREE.Mesh(planeXZ, flashMat());
  fNegZ.rotation.y = Math.PI;
  fNegZ.position.set(0, yCenter, -ARENA.z);
  faces.push(fNegZ);

  const fPosY = new THREE.Mesh(planeXY, flashMat());
  fPosY.rotation.x = Math.PI / 2;
  fPosY.position.set(0, ARENA.yMax, 0);
  faces.push(fPosY);

  const fNegY = new THREE.Mesh(planeXY, flashMat());
  fNegY.rotation.x = -Math.PI / 2;
  fNegY.position.set(0, 0.005, 0);
  faces.push(fNegY);

  for (const f of faces) group.add(f);

  function updateFlash(opacities) {
    for (let i = 0; i < faces.length; i++) {
      faces[i].material.opacity = opacities[i] * 0.25;
      faces[i].visible = opacities[i] > 0;
    }
  }

  return { group, updateFlash };
}
