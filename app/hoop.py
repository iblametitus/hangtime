"""Geometry for the hero: a basketball rim seen from below, with its net, as SVG path data.

Seen from below the rim is a flat ellipse and the net hangs towards the viewer, narrowing to a
smaller ellipse. The net is a diamond lattice: every rim point connects to the two neighbouring
points one ring further down. The near half (lower arc) is drawn stronger than the far half.
"""

import math

CX = 300
RINGS = [(170, 250, 70), (300, 190, 52), (420, 128, 34)]  # (cy, rx, ry): rim, middle, bottom
POINTS = 22


def _point(ring: tuple[int, int, int], t: float) -> tuple[float, float]:
    cy, rx, ry = ring
    return CX + rx * math.cos(t), cy + ry * math.sin(t)


def net_paths() -> dict[str, str]:
    """SVG path data for the far and near halves of the net."""
    far, near = [], []
    step = 2 * math.pi / POINTS
    for upper, lower in zip(RINGS, RINGS[1:]):
        for i in range(POINTS):
            t = i * step
            x1, y1 = _point(upper, t)
            for dt in (-step / 2, step / 2):
                x2, y2 = _point(lower, t + dt)
                (near if math.sin(t + dt / 2) > 0 else far).append(f"M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}")
    return {"far": "".join(far), "near": "".join(near)}
