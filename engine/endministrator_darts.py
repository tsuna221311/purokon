"""Identify the side-bust dart legs in this front-zip coat block."""

from __future__ import annotations

from math import dist

from .endministrator_armhole import mesh_indices_for_contour_path


def front_bust_dart_legs(stitch_outline_cm, pattern_mesh):
    points = list(stitch_outline_cm)
    xs = [point[0] for point in points]
    span = max(xs) - min(xs)
    darts = []
    for index in range(1, len(points) - 1):
        mouth_a, tip, mouth_b = points[index - 1:index + 2]
        if not (mouth_a[0] - tip[0] > .3 * span and
                mouth_b[0] - tip[0] > .3 * span and
                mouth_a[1] > tip[1] and mouth_b[1] > tip[1]):
            continue
        length_a, length_b = dist(mouth_a, tip), dist(tip, mouth_b)
        if abs(length_a - length_b) > .1:
            raise ValueError("Bust dart legs are not equal in stitch length")
        leg_a = [mouth_a, tip]
        leg_b = [tip, mouth_b]
        darts.append({
            "leg_a_cm": leg_a,
            "leg_b_cm": leg_b,
            "leg_a_mesh_indices": mesh_indices_for_contour_path(
                pattern_mesh, stitch_outline_cm, leg_a),
            "leg_b_mesh_indices": mesh_indices_for_contour_path(
                pattern_mesh, stitch_outline_cm, leg_b),
            "leg_length_cm": (length_a + length_b) / 2,
            "mouth_gap_cm": dist(mouth_a, mouth_b),
        })
    if not 1 <= len(darts) <= 2:
        raise ValueError(f"Expected one or two side-bust dart Vs, found {len(darts)}")
    return darts


def hem_waist_dart_legs(stitch_outline_cm, pattern_mesh, sewn_hem_runs,
                        hem_y_cm):
    """Identify verified V-shaped hem mouths, without bridging them to a panel."""
    outline = list(stitch_outline_cm)
    if outline[0] == outline[-1]:
        outline.pop()
    darts = []
    for (_left, mouth_a), (mouth_b, _right) in zip(
            sewn_hem_runs, sewn_hem_runs[1:]):
        candidates = []
        for index in range(len(outline)):
            first, tip, last = (outline[(index + offset) % len(outline)]
                                for offset in (0, 1, 2))
            if (abs(first[1] - hem_y_cm) > .03 or
                    abs(last[1] - hem_y_cm) > .03 or
                    {round(first[0], 5), round(last[0], 5)} !=
                    {round(mouth_a, 5), round(mouth_b, 5)}):
                continue
            if abs(dist(first, tip) - dist(tip, last)) > .1:
                continue
            candidates.append((first, tip, last))
        if len(candidates) != 1:
            raise ValueError("Waist dart mouth is missing or ambiguous")
        first, tip, last = candidates[0]
        legs = [mesh_indices_for_contour_path(pattern_mesh, stitch_outline_cm,
                                              [a, b])
                for a, b in ((first, tip), (tip, last))]
        darts.append({
            "leg_a_cm": [first, tip], "leg_b_cm": [tip, last],
            "leg_a_mesh_indices": legs[0], "leg_b_mesh_indices": legs[1],
            "leg_length_cm": (dist(first, tip) + dist(tip, last)) / 2,
            "mouth_gap_cm": mouth_b - mouth_a,
            "sewn_to_lower_panel": False,
            "3d_sewing_verified": False,
        })
    return darts
