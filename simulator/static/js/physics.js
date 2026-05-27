// Port of legacy/simulator/controls.py + physics.py.
// State angles are in DEGREES (matches legacy); conversion to radians happens
// only inside the body→world rotation. Position is in metres, y is up.

const DEG = Math.PI / 180;

// Control pipeline constants (legacy controls.py)
const DEADZONE_DEG = 3.0;
const EMA_ALPHA = 0.85;
const SENSITIVITY = 2.0;
const ROLL_CAP = 45.0;
const PITCH_CAP = 45.0;
const YAW_CAP = 90.0;
const MAX_RATE_CHANGE = 500.0; // deg/s per second

// Physics constants (legacy physics.py + config.py)
const ATTITUDE_CAP = 45.0; // visual roll/pitch clamp
const ATTITUDE_DECAY = 3.0; // passive return-to-level rate when no input
const MOVE_MAX_SPEED = 8.0; // m/s at 45° tilt
const MOVE_DRAG = 5.0; // velocity blend rate
const THROTTLE_MAX_SPEED = 4.0; // m/s at throttle = 1.0 (mid = 0.5 = hover)

function deadzone(x, dz) {
  return Math.abs(x) < dz ? 0 : x;
}

function clamp(x, lo, hi) {
  return x < lo ? lo : x > hi ? hi : x;
}

function rateLimit(target, prev, maxStep) {
  const d = target - prev;
  if (d > maxStep) return prev + maxStep;
  if (d < -maxStep) return prev - maxStep;
  return target;
}

export class ControlPipeline {
  constructor() {
    this.smoothed = { roll: 0, pitch: 0, yaw: 0 };
    this.lastRate = { roll: 0, pitch: 0, yaw: 0 };
  }

  // Inputs are calibrated phone angles in degrees. yawInput is the
  // accumulated yaw delta from baseline (also degrees, already wrapped).
  step(rollInput, pitchInput, yawInput, dt) {
    const dRoll = deadzone(rollInput, DEADZONE_DEG);
    const dPitch = deadzone(pitchInput, DEADZONE_DEG);
    const dYaw = deadzone(yawInput, DEADZONE_DEG);

    this.smoothed.roll = EMA_ALPHA * dRoll + (1 - EMA_ALPHA) * this.smoothed.roll;
    this.smoothed.pitch = EMA_ALPHA * dPitch + (1 - EMA_ALPHA) * this.smoothed.pitch;
    this.smoothed.yaw = EMA_ALPHA * dYaw + (1 - EMA_ALPHA) * this.smoothed.yaw;

    const maxStep = MAX_RATE_CHANGE * dt;
    const rTarget = clamp(this.smoothed.roll * SENSITIVITY, -ROLL_CAP, ROLL_CAP);
    const pTarget = clamp(this.smoothed.pitch * SENSITIVITY, -PITCH_CAP, PITCH_CAP);
    const yTarget = clamp(this.smoothed.yaw * SENSITIVITY, -YAW_CAP, YAW_CAP);

    this.lastRate.roll = rateLimit(rTarget, this.lastRate.roll, maxStep);
    this.lastRate.pitch = rateLimit(pTarget, this.lastRate.pitch, maxStep);
    this.lastRate.yaw = rateLimit(yTarget, this.lastRate.yaw, maxStep);

    return { ...this.lastRate };
  }

  reset() {
    this.smoothed = { roll: 0, pitch: 0, yaw: 0 };
    this.lastRate = { roll: 0, pitch: 0, yaw: 0 };
  }
}

export const ARENA = {
  // Half-extents in metres. Centre at origin in x/z; floor at y=0.
  x: 10,
  z: 10,
  yMax: 20,
};

export class DroneState {
  constructor() {
    this.x = 0;
    this.y = 2;
    this.z = 0;
    this.vx = 0;
    this.vy = 0;
    this.vz = 0;
    this.roll = 0;
    this.pitch = 0;
    this.yaw = 0;
    // Per-face wall flash opacities (0..1). Order: +x, -x, +z, -z, +y, -y.
    this.wallFlash = [0, 0, 0, 0, 0, 0];
  }

  reset() {
    this.x = 0;
    this.y = 2;
    this.z = 0;
    this.vx = this.vy = this.vz = 0;
    this.roll = this.pitch = this.yaw = 0;
    this.wallFlash.fill(0);
  }

  // rates: deg/s for roll, pitch, yaw. throttle in [0, 1].
  step(rates, throttle, dt) {
    // Update attitude (legacy physics.py:144-160)
    this.roll = clamp(this.roll + rates.roll * dt, -ATTITUDE_CAP, ATTITUDE_CAP);
    this.pitch = clamp(this.pitch + rates.pitch * dt, -ATTITUDE_CAP, ATTITUDE_CAP);
    this.yaw = ((this.yaw + rates.yaw * dt) % 360 + 540) % 360 - 180;

    // Passive return-to-level when no input
    if (Math.abs(rates.roll) < 0.1) this.roll *= Math.max(0, 1 - ATTITUDE_DECAY * dt);
    if (Math.abs(rates.pitch) < 0.1) this.pitch *= Math.max(0, 1 - ATTITUDE_DECAY * dt);

    // Body-frame target velocity from tilt (legacy physics.py:165-175)
    const bodyForward = (this.pitch / ATTITUDE_CAP) * MOVE_MAX_SPEED;
    const bodyRight = -(this.roll / ATTITUDE_CAP) * MOVE_MAX_SPEED;
    const yawRad = this.yaw * DEG;
    const targetVx = bodyForward * Math.sin(yawRad) + bodyRight * Math.cos(yawRad);
    const targetVz = bodyForward * Math.cos(yawRad) - bodyRight * Math.sin(yawRad);
    const targetVy = (throttle - 0.5) * 2 * THROTTLE_MAX_SPEED;

    const blend = Math.min(MOVE_DRAG * dt, 1);
    this.vx += (targetVx - this.vx) * blend;
    this.vz += (targetVz - this.vz) * blend;
    this.vy += (targetVy - this.vy) * blend;

    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.z += this.vz * dt;

    // Soft wall clamp + face flash (no bounce)
    if (this.x > ARENA.x) {
      this.x = ARENA.x; this.vx = 0; this.wallFlash[0] = 1;
    } else if (this.x < -ARENA.x) {
      this.x = -ARENA.x; this.vx = 0; this.wallFlash[1] = 1;
    }
    if (this.z > ARENA.z) {
      this.z = ARENA.z; this.vz = 0; this.wallFlash[2] = 1;
    } else if (this.z < -ARENA.z) {
      this.z = -ARENA.z; this.vz = 0; this.wallFlash[3] = 1;
    }
    if (this.y > ARENA.yMax) {
      this.y = ARENA.yMax; this.vy = 0; this.wallFlash[4] = 1;
    } else if (this.y < 0) {
      this.y = 0; this.vy = 0; this.wallFlash[5] = 1;
    }

    // Decay all face flashes
    for (let i = 0; i < this.wallFlash.length; i++) {
      this.wallFlash[i] *= Math.pow(0.92, dt * 60);
      if (this.wallFlash[i] < 0.005) this.wallFlash[i] = 0;
    }
  }
}
