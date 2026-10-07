"""Labels for construction-specific notch marks across output formats."""

from __future__ import annotations

import math


def shoulder_notch_label_point(part_type: str, notch_count: int, index: int,
                               notch: tuple[tuple[float, float],
                                            tuple[float, float]],
                               inset_cm: float = 0.45
                               ) -> tuple[float, float] | None:
    """The fourth sleeve notch is the shoulder station, not the cap apex."""
    if part_type != "sleeve" or notch_count != 4 or index != 3:
        return None
    stitch, cut = notch
    length = math.dist(stitch, cut)
    if length <= 1e-6:
        return None
    return (stitch[0] + (stitch[0] - cut[0]) * inset_cm / length,
            stitch[1] + (stitch[1] - cut[1]) * inset_cm / length)
