"""Experimental paper side-seam truing for the Endministrator zip coat.

This adjusts only the length *below* a sewn bust dart.  It does not assert
physical fit: the front/back relationship still needs a fabric toile.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from .compatibility import _closed_points, _is_dart_notch_at, side_seam_length
from .darts import _shift_below
from .svgpath import bounding_box, segments_to_polyline


def _dart_lower_mouth_y(segments) -> float | None:
    points = [(float(nums[0]), float(nums[1])) for command, nums in segments
              if command in ("M", "L") and len(nums) >= 2]
    if len(points) < 5:
        return None
    closed = _closed_points(points)
    mouths = [max(closed[index][1], closed[index + 2][1])
              for index in range(len(points) - 2)
              if _is_dart_notch_at(closed, index, .5)]
    return max(mouths) if mouths else None


def _front_side_length(part, segments) -> float | None:
    return side_seam_length(SimpleNamespace(
        part_type=part.part_type,
        stitch_line=segments_to_polyline(segments),
        underarm_y_cm=part.underarm_y_cm,
        reference_lines=(), compatibility_measurements={}))


def true_front_side_seam(part, back_half_cm: float, *,
                         tolerance_cm: float = .05,
                         max_move_cm: float = 1.5):
    """Return (replacement, diagnostic) or the original with a rejection reason.

    A length change at the hem is a *hypothesis*, not the only valid fitting
    correction.  Reject if the desired seam length cannot be reached by a
    small, monotone movement below the last bust-dart mouth.
    """
    original = _front_side_length(part, part.segments)
    if part.part_type != "front_bodice_zip_panel" or original is None:
        return part, {"status": "not_applicable"}
    delta = original - back_half_cm
    if abs(delta) <= tolerance_cm:
        return part, {"status": "already_matched", "difference_cm": delta}
    threshold = _dart_lower_mouth_y(part.segments)
    if threshold is None or abs(delta) > max_move_cm:
        return part, {"status": "manual_re_draft_required",
                      "difference_cm": delta,
                      "reason": "missing bust dart or correction exceeds limit"}

    def candidate(dy):
        segments = _shift_below(part.segments, threshold + 1e-5, dy)
        return segments, _front_side_length(part, segments)

    low, high = (-max_move_cm, 0.0) if delta > 0 else (0.0, max_move_cm)
    _low_segments, low_length = candidate(low)
    _high_segments, high_length = candidate(high)
    if (low_length is None or high_length is None or
            not min(low_length, high_length) <= back_half_cm <=
            max(low_length, high_length)):
        return part, {"status": "manual_re_draft_required",
                      "difference_cm": delta,
                      "reason": "paper seam length is not bracketed"}
    for _ in range(24):
        mid = (low + high) / 2
        _segments, length = candidate(mid)
        if length < back_half_cm:
            low = mid
        else:
            high = mid
    dy = (low + high) / 2
    segments, length = candidate(dy)
    if length is None or abs(length - back_half_cm) > tolerance_cm:
        return part, {"status": "manual_re_draft_required",
                      "difference_cm": delta,
                      "reason": "numerical truing did not converge"}
    _min_x, min_y, _max_x, max_y = bounding_box(segments)
    waist = part.waist_y_cm
    adjusted = replace(
        part, segments=segments, height_cm=max_y - min_y,
        bust_dart_shift_cm=max(0.0, part.bust_dart_shift_cm + dy),
        waist_y_cm=waist + dy if waist is not None and waist > threshold else waist,
        fit_anchors_y_scaled=tuple((role, y + dy if y > threshold else y)
                                   for role, y in part.fit_anchors_y_scaled))
    return adjusted, {"status": "paper_trial", "original_front_cm": original,
                      "back_half_cm": back_half_cm, "adjusted_front_cm": length,
                      "lower_panel_shift_cm": dy,
                      "bust_dart_mouth_y_cm": threshold,
                      "physical_fit_verified": False}
