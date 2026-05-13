"""Obstacle definitions, world layout, and collision detection."""

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Tuple

import config


class ObstacleType(Enum):
    BOX = auto()
    CYLINDER = auto()
    TREE = auto()
    HOOP = auto()


@dataclass
class Obstacle:
    type: ObstacleType
    x: float
    z: float
    # BOX: width (x-axis), height (y-axis), depth (z-axis)
    width: float = 1.0
    height: float = 2.0
    depth: float = 1.0
    # CYLINDER / TREE: radius, height (reuses height above)
    radius: float = 0.5
    # TREE: canopy radius (canopy sphere sits on top of trunk)
    canopy_radius: float = 0.0
    # HOOP: ring thickness
    ring_thickness: float = 0.15


@dataclass
class CollisionResult:
    collided: bool = False
    new_x: float = 0.0
    new_y: float = 0.0
    new_z: float = 0.0
    normal_x: float = 0.0
    normal_y: float = 0.0
    normal_z: float = 0.0


# ---- Collision detection ----

def _collide_sphere_box(sx, sy, sz, sr, bx, bz, bw, bh, bd):
    """Sphere at (sx,sy,sz) radius sr vs axis-aligned box on ground.
    Box center at (bx, bh/2, bz), dimensions (bw, bh, bd).
    """
    half_w, half_d = bw / 2, bd / 2

    # Closest point on box to sphere center
    closest_x = max(bx - half_w, min(sx, bx + half_w))
    closest_y = max(0.0, min(sy, bh))
    closest_z = max(bz - half_d, min(sz, bz + half_d))

    dx = sx - closest_x
    dy = sy - closest_y
    dz = sz - closest_z
    dist_sq = dx * dx + dy * dy + dz * dz

    if dist_sq >= sr * sr:
        return CollisionResult()

    dist = math.sqrt(dist_sq) if dist_sq > 0.0001 else 0.001
    nx, ny, nz = dx / dist, dy / dist, dz / dist
    penetration = sr - dist + config.OBSTACLE_PUSH_EPSILON

    return CollisionResult(
        collided=True,
        new_x=sx + nx * penetration,
        new_y=sy + ny * penetration,
        new_z=sz + nz * penetration,
        normal_x=nx, normal_y=ny, normal_z=nz,
    )


def _collide_sphere_cylinder(sx, sy, sz, sr, cx, cz, cr, ch):
    """Sphere vs vertical cylinder at (cx, 0..ch, cz) with radius cr."""
    # Y range check
    if sy + sr < 0.0 or sy - sr > ch:
        return CollisionResult()

    dx = sx - cx
    dz = sz - cz
    horiz_dist = math.sqrt(dx * dx + dz * dz)

    if horiz_dist >= cr + sr:
        return CollisionResult()

    # Above top cap
    if sy > ch:
        dy = sy - ch
        dist_3d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist_3d >= sr:
            return CollisionResult()
        penetration = sr - dist_3d + config.OBSTACLE_PUSH_EPSILON
        return CollisionResult(
            collided=True,
            new_x=sx, new_y=ch + sr + config.OBSTACLE_PUSH_EPSILON, new_z=sz,
            normal_x=0.0, normal_y=1.0, normal_z=0.0,
        )

    # Side collision
    if horiz_dist < 0.001:
        dx, dz = 1.0, 0.0
        horiz_dist = 0.001

    nx = dx / horiz_dist
    nz = dz / horiz_dist
    penetration = (cr + sr) - horiz_dist + config.OBSTACLE_PUSH_EPSILON

    return CollisionResult(
        collided=True,
        new_x=sx + nx * penetration,
        new_y=sy,
        new_z=sz + nz * penetration,
        normal_x=nx, normal_y=0.0, normal_z=nz,
    )


def _collide_sphere_tree(sx, sy, sz, sr, obs):
    """Tree = trunk cylinder + canopy sphere on top."""
    # Trunk
    trunk_result = _collide_sphere_cylinder(sx, sy, sz, sr,
                                            obs.x, obs.z, obs.radius, obs.height)
    if trunk_result.collided:
        return trunk_result

    # Canopy sphere
    if obs.canopy_radius <= 0:
        return CollisionResult()

    canopy_cy = obs.height + obs.canopy_radius * 0.7
    dx = sx - obs.x
    dy = sy - canopy_cy
    dz = sz - obs.z
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    combined = sr + obs.canopy_radius

    if dist >= combined:
        return CollisionResult()

    if dist < 0.001:
        dx, dy, dz = 0.0, 1.0, 0.0
        dist = 0.001

    nx, ny, nz = dx / dist, dy / dist, dz / dist
    penetration = combined - dist + config.OBSTACLE_PUSH_EPSILON

    return CollisionResult(
        collided=True,
        new_x=sx + nx * penetration,
        new_y=sy + ny * penetration,
        new_z=sz + nz * penetration,
        normal_x=nx, normal_y=ny, normal_z=nz,
    )


def check_collision(drone_x, drone_y, drone_z, drone_radius, obs):
    """Check drone sphere against a single obstacle."""
    if obs.type == ObstacleType.BOX:
        return _collide_sphere_box(drone_x, drone_y, drone_z, drone_radius,
                                   obs.x, obs.z, obs.width, obs.height, obs.depth)
    elif obs.type == ObstacleType.CYLINDER:
        return _collide_sphere_cylinder(drone_x, drone_y, drone_z, drone_radius,
                                        obs.x, obs.z, obs.radius, obs.height)
    elif obs.type == ObstacleType.TREE:
        return _collide_sphere_tree(drone_x, drone_y, drone_z, drone_radius, obs)
    # HOOP: no collision (fly through)
    return CollisionResult()


def check_all_collisions(drone_x, drone_y, drone_z, drone_radius, obstacles):
    """Check drone against all obstacles. Returns first collision."""
    for obs in obstacles:
        # Broad-phase skip
        dx = drone_x - obs.x
        dz = drone_z - obs.z
        max_extent = max(obs.width, obs.depth, obs.radius * 2, obs.canopy_radius * 2, 2.0) + drone_radius
        if dx * dx + dz * dz > max_extent * max_extent:
            continue

        result = check_collision(drone_x, drone_y, drone_z, drone_radius, obs)
        if result.collided:
            return result

    return CollisionResult()


# ---- World layout ----

def create_world():
    """Create the obstacle layout around the origin."""
    obstacles = []

    # === BUILDINGS ===
    # Cluster to the right
    obstacles.append(Obstacle(type=ObstacleType.BOX, x=8.0, z=5.0,
                              width=3.0, height=6.0, depth=3.0))
    obstacles.append(Obstacle(type=ObstacleType.BOX, x=12.0, z=4.0,
                              width=2.0, height=10.0, depth=2.5))
    obstacles.append(Obstacle(type=ObstacleType.BOX, x=10.0, z=8.0,
                              width=4.0, height=4.0, depth=3.0))
    # Behind start
    obstacles.append(Obstacle(type=ObstacleType.BOX, x=-2.0, z=-8.0,
                              width=5.0, height=8.0, depth=3.0))
    # Low warehouse left
    obstacles.append(Obstacle(type=ObstacleType.BOX, x=-10.0, z=6.0,
                              width=6.0, height=3.0, depth=4.0))
    # Tall skinny tower
    obstacles.append(Obstacle(type=ObstacleType.BOX, x=5.0, z=-6.0,
                              width=1.5, height=15.0, depth=1.5))

    # === TREES ===
    # Line of trees
    for i in range(5):
        obstacles.append(Obstacle(type=ObstacleType.TREE, x=-5.0, z=2.0 + i * 3.0,
                                  radius=0.15, height=2.5, canopy_radius=1.2))
    # Scattered
    obstacles.append(Obstacle(type=ObstacleType.TREE, x=3.0, z=12.0,
                              radius=0.2, height=3.0, canopy_radius=1.5))
    obstacles.append(Obstacle(type=ObstacleType.TREE, x=-8.0, z=-4.0,
                              radius=0.15, height=2.0, canopy_radius=1.0))
    obstacles.append(Obstacle(type=ObstacleType.TREE, x=15.0, z=-3.0,
                              radius=0.2, height=3.5, canopy_radius=1.8))

    # === POLES ===
    obstacles.append(Obstacle(type=ObstacleType.CYLINDER, x=4.0, z=0.0,
                              radius=0.08, height=5.0))
    obstacles.append(Obstacle(type=ObstacleType.CYLINDER, x=-4.0, z=0.0,
                              radius=0.08, height=5.0))
    obstacles.append(Obstacle(type=ObstacleType.CYLINDER, x=0.0, z=10.0,
                              radius=0.08, height=5.0))
    # Thick antenna tower
    obstacles.append(Obstacle(type=ObstacleType.CYLINDER, x=-12.0, z=-8.0,
                              radius=0.2, height=12.0))

    # === HOOPS (fly-through) ===
    obstacles.append(Obstacle(type=ObstacleType.HOOP, x=0.0, z=6.0,
                              radius=1.5, height=3.0, ring_thickness=0.12))
    obstacles.append(Obstacle(type=ObstacleType.HOOP, x=6.0, z=12.0,
                              radius=1.8, height=5.0, ring_thickness=0.12))
    obstacles.append(Obstacle(type=ObstacleType.HOOP, x=-6.0, z=15.0,
                              radius=1.2, height=2.0, ring_thickness=0.12))

    return obstacles
