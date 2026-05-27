// Bounding cube + grid + wall flash planes.

import * as THREE from "/static/lib/three.module.min.js";
import { ARENA } from "/static/js/physics.js";

export function buildArena() {
  const group = new THREE.Group();

  // Floor grid: 1-m lines
  const grid = new THREE.GridHelper(ARENA.x * 2, ARENA.x * 2, 0x2a3340, 0x1c2129);
  grid.material.opacity = 0.85;
  grid.material.transparent = true;
  group.add(grid);

  // Accent grid every 5 m
  const accent = new THREE.GridHelper(ARENA.x * 2, (ARENA.x * 2) / 5, 0x3c4a5a, 0x3c4a5a);
  accent.material.opacity = 0.7;
  accent.material.transparent = true;
  accent.position.y = 0.002;
  group.add(accent);

  // Bounding cube — wireframe edges only
  const boxGeo = new THREE.BoxGeometry(ARENA.x * 2, ARENA.yMax, ARENA.z * 2);
  const edges = new THREE.EdgesGeometry(boxGeo);
  const cube = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({
      color: 0x00c2ff,
      transparent: true,
      opacity: 0.32,
    })
  );
  cube.position.y = ARENA.yMax / 2;
  group.add(cube);

  // Subtle axis ticks: short outward marks at the floor every 5m for spatial sense
  const tickMat = new THREE.LineBasicMaterial({ color: 0x3c4a5a, transparent: true, opacity: 0.7 });
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
