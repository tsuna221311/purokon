"""Transparent, measurement-based collision stand-in for garment trials.

It is not a scanned person.  The chosen elliptical aspect ratio and vertical
landmarks are hypotheses that must be replaced by wearer measurements.
"""

from __future__ import annotations

import math


def ellipse_circumference(major: float, minor: float) -> float:
    """Ramanujan's near-exact ellipse perimeter approximation."""
    if major <= 0 or minor <= 0:
        raise ValueError("Ellipse axes must be positive")
    return math.pi * (3 * (major + minor)
                      - math.sqrt((3 * major + minor) * (major + 3 * minor)))


def axes_for_circumference(circumference_cm: float, *,
                           depth_to_width: float = .75,
                           scene_m_per_cm: float = .02) -> tuple[float, float]:
    """Return x/y radii in scene units for a specified body circumference."""
    if circumference_cm <= 0 or not .5 <= depth_to_width <= 1.0:
        raise ValueError("Invalid body circumference or ellipse aspect ratio")
    coefficient = ellipse_circumference(1.0, depth_to_width)
    major = circumference_cm * scene_m_per_cm / coefficient
    return major, major * depth_to_width
