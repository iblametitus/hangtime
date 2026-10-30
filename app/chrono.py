"""The hero image: a vertical jump as a chronophotograph, drawn as SVG.

Five exposures of one jump, left to right: standing, loading, take-off, rising, peak. Earlier
exposures are faint and smeared along the direction of travel, only the peak (the hang) is sharp.
The figure is built from joint angles, so the poses stay anatomically plausible.

Angles are in degrees, 0 = straight up, 90 = forward (to the right), 180 = straight down.
"""

from dataclasses import dataclass
from functools import cache
from math import cos, radians, sin

W, H = 900, 640
GROUND = 604

# Segment lengths in px
TRUNK, NECK, HEAD_R = 120, 12, 21
UPPER_ARM, FOREARM = 66, 60
THIGH, SHANK, FOOT = 98, 94, 34
ANKLE_H = 12  # ankle height above the floor when standing flat

INK, FAR, SHOE = "#161A2E", "#565A6B", "#1E3BD1"


@dataclass(frozen=True)
class Pose:
    x: float                 # ankle x on the floor, or hip x when airborne
    trunk: float
    arm: tuple[float, float]       # near upper arm, forearm
    far_arm: tuple[float, float]
    leg: tuple[float, float, float]  # near thigh, shank, foot
    far_leg: tuple[float, float, float]
    hip_y: float | None = None     # set when airborne
    on_toes: bool = False


POSES = [
    Pose(120, 4, (178, 166), (188, 176), (182, 178, 92), (178, 182, 92)),
    Pose(240, 46, (232, 240), (224, 232), (116, 206, 92), (124, 200, 92)),
    Pose(360, 16, (16, 6), (28, 14), (192, 200, 150), (184, 196, 154), on_toes=True),
    Pose(498, 6, (2, 356), (14, 4), (176, 190, 156), (186, 196, 160), hip_y=352),
    Pose(640, 4, (352, 346), (62, 92), (130, 196, 150), (192, 214, 162), hip_y=318),
]

# Faint to sharp: opacity and horizontal smear per exposure
GHOST = [(0.12, 9), (0.18, 8), (0.26, 6), (0.40, 4), (1.0, 0)]


def _d(a: float, length: float) -> tuple[float, float]:
    return length * sin(radians(a)), -length * cos(radians(a))


def _add(p, v, s=1):
    return p[0] + s * v[0], p[1] + s * v[1]


def joints(p: Pose) -> dict[str, tuple[float, float]]:
    thigh, shank, foot = p.leg
    if p.hip_y is not None:
        hip = (p.x, p.hip_y)
    else:
        toe_or_ankle = (p.x, GROUND)
        ankle = _add(toe_or_ankle, _d(foot, FOOT), -1) if p.on_toes else (p.x, GROUND - ANKLE_H)
        knee = _add(ankle, _d(shank, SHANK), -1)
        hip = _add(knee, _d(thigh, THIGH), -1)
    shoulder = _add(hip, _d(p.trunk, TRUNK))
    j = {"hip": hip, "shoulder": shoulder, "head": _add(shoulder, _d(p.trunk, NECK + HEAD_R))}
    for side, (t, s, f), (u, fa) in [("n", p.leg, p.arm), ("f", p.far_leg, p.far_arm)]:
        j[f"{side}knee"] = _add(hip, _d(t, THIGH))
        j[f"{side}ankle"] = _add(j[f"{side}knee"], _d(s, SHANK))
        j[f"{side}toe"] = _add(j[f"{side}ankle"], _d(f, FOOT))
        j[f"{side}elbow"] = _add(shoulder, _d(u, UPPER_ARM))
        j[f"{side}hand"] = _add(j[f"{side}elbow"], _d(fa, FOREARM))
    return j


def _line(a, b, color, width) -> str:
    return (f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>')


def figure(j: dict) -> str:
    """Far limbs first, then trunk, then near limbs. Shoes carry the only colour."""
    parts = []
    for side, color in [("f", FAR), ("n", INK)]:
        limbs = [
            _line(j["hip"], j[f"{side}knee"], color, 32),
            _line(j[f"{side}knee"], j[f"{side}ankle"], color, 25),
            _line(j[f"{side}ankle"], j[f"{side}toe"], SHOE, 17),
            _line(j["shoulder"], j[f"{side}elbow"], color, 21),
            _line(j[f"{side}elbow"], j[f"{side}hand"], color, 17),
        ]
        parts += limbs
        if side == "f":
            parts.append(_line(j["hip"], j["shoulder"], INK, 46))
            hx, hy = j["head"]
            parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{HEAD_R}" fill="{INK}"/>')
    return "".join(parts)


def _ribbon(points: list[tuple[float, float]]) -> str:
    """Smooth path through points (Catmull-Rom as cubic Béziers)."""
    p = [points[0], *points, points[-1]]
    d = f"M{p[1][0]:.1f} {p[1][1]:.1f}"
    for i in range(1, len(p) - 2):
        c1 = (p[i][0] + (p[i + 1][0] - p[i - 1][0]) / 6, p[i][1] + (p[i + 1][1] - p[i - 1][1]) / 6)
        c2 = (p[i + 1][0] - (p[i + 2][0] - p[i][0]) / 6, p[i + 1][1] - (p[i + 2][1] - p[i][1]) / 6)
        d += f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p[i + 1][0]:.1f} {p[i + 1][1]:.1f}"
    return d


@cache
def svg() -> str:
    js = [joints(p) for p in POSES]
    out = [
        f'<svg class="chrono" viewBox="0 0 {W} {H}" role="img" '
        'aria-label="A vertical jump in five overlapping exposures, from standing to the peak of the jump">',
        "<defs>",
        *(f'<filter id="smear{i}" x="-20%" y="-5%" width="140%" height="110%">'
          f'<feGaussianBlur stdDeviation="{s} 1"/></filter>' for i, (_, s) in enumerate(GHOST) if s),
        '<filter id="soft"><feGaussianBlur stdDeviation="6 2"/></filter>',
        '<filter id="trail" x="-10%" y="-20%" width="120%" height="140%"><feGaussianBlur stdDeviation="10 4"/></filter>',
        "</defs>",
    ]
    # Floor shadows: dark under the feet on the floor, lighter the higher the body
    for p, j, (op, _) in zip(POSES, js, GHOST):
        lift = GROUND - max(j["nankle"][1], j["fankle"][1])
        rx = max(34, 70 - lift * 0.25)
        out.append(f'<ellipse class="shadow" cx="{j["hip"][0] + 8:.1f}" cy="{GROUND + 4}" rx="{rx:.1f}" ry="8" filter="url(#soft)" '
                   f'fill="{INK}" opacity="{max(0.04, min(0.16, op) - lift * 0.0006):.3f}"/>')
    # Motion trails of the reaching hand and the head
    for key, width in [("nhand", 18), ("head", 26)]:
        out.append(f'<path class="trail" d="{_ribbon([j[key] for j in js])}" fill="none" stroke="{INK}" '
                   f'stroke-opacity=".07" stroke-width="{width}" stroke-linecap="round" filter="url(#trail)"/>')
    for i, (j, (op, s)) in enumerate(zip(js, GHOST)):
        attrs = f' filter="url(#smear{i})"' if s else ""
        out.append(f'<g class="phase" style="--i:{i}" opacity="{op}"{attrs}>{figure(j)}</g>')
    out.append("</svg>")
    return "".join(out)
