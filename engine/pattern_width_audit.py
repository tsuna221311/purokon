"""Measure horizontal material spans of open-coat bodice stitch outlines.

These are 2D paper widths, not finished garment circumferences or fit ease.
In particular, front-opening overlap/gap and sewn darts are not resolved here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from shapely.geometry import LineString, Polygon


def horizontal_material_width_cm(stitch_outline_cm: Sequence[Sequence[float]],
                                 y_cm: float) -> float:
    polygon = Polygon(stitch_outline_cm)
    if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
        raise ValueError("A bodice stitch outline must be a valid filled polygon")
    min_x, min_y, max_x, max_y = polygon.bounds
    if not min_y < y_cm < max_y:
        raise ValueError("Cross-section must lie strictly inside the bodice height")
    section = polygon.intersection(LineString(
        [(min_x - 1.0, y_cm), (max_x + 1.0, y_cm)]))
    width = section.length
    if not math.isfinite(width) or width <= 0:
        raise ValueError("Cross-section has no measurable material width")
    return width


def audit_open_bodice_widths(hosts: Sequence[Mapping], body_cm: Mapping,
                             *, hem_scene_z_m: float = -0.43,
                             scene_m_per_cm: float = 0.02) -> dict:
    """Compare paper strip spans at the three torso proxy height stations.

    Each host's own hem y coordinate maps to the same scene hem z. This is a
    diagnostic for the paper-developed *preview placement*, not anatomy.
    """
    if scene_m_per_cm <= 0:
        raise ValueError("Scene scale must be positive")
    if [host["code"] for host in hosts] != ["A", "B", "C"]:
        raise ValueError("Expected front A/B and back C bodice hosts")
    stations = (
        ("bust_proxy", 0.43, float(body_cm["bust"])),
        ("waist_proxy", 0.05, float(body_cm["waist"])),
        ("high_hip_proxy", -0.20,
         (float(body_cm["waist"]) + float(body_cm["hip"])) / 2),
    )
    rows = []
    for label, z_m, body_reference_cm in stations:
        by_host = {}
        for host in hosts:
            y_cm = host["hem_stitch_y_cm"] - (
                z_m - hem_scene_z_m) / scene_m_per_cm
            by_host[host["code"]] = {
                "paper_y_cm": round(y_cm, 3),
                "material_width_cm": round(horizontal_material_width_cm(
                    host["stitch_outline_cm"], y_cm), 3),
            }
        total = sum(item["material_width_cm"] for item in by_host.values())
        rows.append({
            "station": label, "scene_z_m": z_m,
            "paper_widths": by_host,
            "open_paper_material_sum_cm": round(total, 3),
            "body_proxy_reference_cm": round(body_reference_cm, 3),
            "paper_sum_minus_body_reference_cm": round(total - body_reference_cm, 3),
        })
    return {
        "sections": rows,
        "hem_scene_z_m": hem_scene_z_m,
        "scene_m_per_cm": scene_m_per_cm,
        "open_coat_width_is_not_finished_circumference": True,
        "darts_overlap_fasteners_and_seam_turns_not_applied": True,
        "not_wearer_fit_validation": True,
    }
