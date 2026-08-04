from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicsResult:
    x: float
    y: float
    vx: float
    vy: float
    grounded: bool
    hard_impact: bool


def advance_body(
    *,
    x: float,
    y: float,
    vx: float,
    vy: float,
    dt: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    gravity: float,
    bounce: float,
    wall_bounce: float,
    hurt_threshold: float,
) -> PhysicsResult:
    """Advance one bounded physics step without any platform or UI work."""
    vx *= math.exp(-0.12 * dt)
    vy += gravity * dt
    x += vx * dt
    y += vy * dt

    impact_speed = math.hypot(vx, vy)
    hard_impact = False

    if x < min_x:
        x = min_x
        hard_impact = impact_speed >= hurt_threshold
        vx = abs(vx) * wall_bounce
    elif x > max_x:
        x = max_x
        hard_impact = impact_speed >= hurt_threshold
        vx = -abs(vx) * wall_bounce

    if y < min_y:
        y = min_y
        hard_impact = hard_impact or impact_speed >= hurt_threshold
        vy = abs(vy) * bounce

    grounded = y >= max_y
    if grounded:
        y = max_y
        hard_impact = hard_impact or impact_speed >= hurt_threshold
        if vy > 0.0:
            vy = -vy * bounce
        if abs(vy) < 95.0:
            vy = 0.0
        vx *= math.exp(-7.5 * dt)
        if abs(vx) < 11.0:
            vx = 0.0

    return PhysicsResult(x, y, vx, vy, grounded, hard_impact)

