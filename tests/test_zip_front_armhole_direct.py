"""The sewn zip-front contour, not an unsplit proxy, sizes the sleeve cap."""

from pathlib import Path
from math import dist
from copy import deepcopy

import pytest

from engine.compatibility import (armhole_length, sleeve_cap_ease_cm,
                                  sleeve_cap_length, underarm_y_of)
from engine.measurements import Measurements
from engine.endministrator_armhole import (endministrator_notch_pairing_warnings,
                                           endministrator_side_seam_warnings)
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import production_quality_report
from engine.notches import (ARMHOLE_NOTCH_RATIO, BACK_DOUBLE_NOTCH_GAP_CM,
                            armhole_notch_distance_cm)
from engine.zip_front_geometry import (front_zip_armhole_length_cm,
                                       front_zip_armhole_path)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("neckline", ["round_neck", "square_neck",
                                        "sweetheart", "v_neck", "boat_neck"])
@pytest.mark.parametrize("body", [
    Measurements(83, 60, 90, 158, 52, 37),
    Measurements(88, 68, 95, 163, 58, 39),
    Measurements(104, 92, 112, 170, 58, 42),
])
def test_zip_front_sleeve_uses_final_stitch_contour(neckline, body):
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        build_garment_spec(front_zip=True, neckline=neckline,
                           skirt_style="flare"), body, skip_export=True)
    fronts = [part for part in result.finalized_parts
              if part.part_type == "front_bodice_zip_panel"]
    backs = [part for part in result.finalized_parts
             if part.part_type == "back_bodice"]
    sleeves = [part for part in result.finalized_parts
               if part.part_type == "sleeve"]
    assert (len(fronts), len(backs), len(sleeves)) == (2, 1, 2)
    for part in fronts:
        direct = front_zip_armhole_length_cm(
            part.stitch_line, underarm_y_of(part))
        assert armhole_length(part) == pytest.approx(direct, abs=.01)
    armhole = sum(armhole_length(part) for part in fronts + backs) / 2
    expected = sleeve_cap_ease_cm(armhole)
    for sleeve in sleeves:
        assert sleeve_cap_length(sleeve) - armhole == pytest.approx(
            expected, abs=.1)
    assert not any(w.kind == "armhole_sleeve_cap"
                   for w in result.compatibility_warnings())


def _arc_position(path, point):
    """Project a notch onto its sewn edge and return (miss, distance)."""
    travelled = 0.0
    best = (float("inf"), 0.0)
    for a, b in zip(path, path[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = dist(a, b)
        if length <= 0:
            continue
        t = max(0.0, min(1.0, ((point[0] - a[0]) * dx
                                + (point[1] - a[1]) * dy) / length**2))
        projected = (a[0] + t * dx, a[1] + t * dy)
        candidate = (dist(point, projected), travelled + t * length)
        if candidate[0] < best[0]:
            best = candidate
        travelled += length
    return best


def _sleeve_cap_path(stitch_line):
    y0 = stitch_line[0][1]
    cap = [stitch_line[0]]
    for point in stitch_line[1:]:
        cap.append(point)
        if abs(point[1] - y0) < .01:
            break
    return cap


@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "boat_neck"])
@pytest.mark.parametrize("body", [
    Measurements(76, 60, 86, 152, 49, 35),
    Measurements(83, 66, 91, 158, 52, 37),
    Measurements(104, 92, 112, 170, 58, 42),
])
def test_zip_front_notches_pair_on_real_armhole_and_sleeve(neckline, body):
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        build_garment_spec(front_zip=True, neckline=neckline,
                           skirt_style="flare"), body, skip_export=True)
    fronts = [p for p in result.finalized_parts
              if p.part_type == "front_bodice_zip_panel"]
    back = next(p for p in result.finalized_parts
                if p.part_type == "back_bodice")
    sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert len(fronts) == len(sleeves) == 2
    for front in fronts:
        assert len(front.notches) == 2  # real side seam + real armhole; no zipper notch
        path = front_zip_armhole_path(front.stitch_line, underarm_y_of(front))
        front_distance = front_zip_armhole_length_cm(
            front.stitch_line, underarm_y_of(front)) * ARMHOLE_NOTCH_RATIO
        projected_marks = [_arc_position(path, point)
                           for point, _ in front.notches]
        armhole_marks = [(miss, along) for miss, along in projected_marks
                         if miss < .1]
        assert len(armhole_marks) == 1
        assert armhole_marks[0][1] == pytest.approx(front_distance, abs=.15)
        side_marks = [point for (point, _), (miss, _along) in
                      zip(front.notches, projected_marks) if miss >= .1]
        middle_x = (min(p[0] for p in front.stitch_line)
                    + max(p[0] for p in front.stitch_line)) / 2
        assert len(side_marks) == 1 and side_marks[0][0] > middle_x

    back_distance = armhole_notch_distance_cm(
        back.stitch_line, underarm_y=underarm_y_of(back))
    assert len(back.notches) == 6  # two side marks + front/back double armhole marks
    for sleeve in sleeves:
        cap = _sleeve_cap_path(sleeve.stitch_line)
        total = sum(dist(a, b) for a, b in zip(cap, cap[1:]))
        cap_marks = []
        for point, _ in sleeve.notches:
            miss, along = _arc_position(cap, point)
            assert miss < .1, "A sleeve notch must not fall on the cuff"
            cap_marks.append(along)
        assert len(cap_marks) == 3
        assert cap_marks[0] == pytest.approx(front_distance, abs=.15)
        assert total - cap_marks[1] == pytest.approx(back_distance, abs=.15)
        assert total - cap_marks[2] == pytest.approx(
            back_distance + BACK_DOUBLE_NOTCH_GAP_CM, abs=.15)


def test_unsplit_front_keeps_the_back_double_notch_in_the_same_direction():
    """The shared sleeve helper must also match an ordinary back bodice."""
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        build_garment_spec(front_zip=False, neckline="round_neck",
                           sleeve_style="straight"),
        Measurements(83, 66, 91, 158, 52, 37), skip_export=True)
    front = next(p for p in result.finalized_parts if p.part_type == "front_bodice")
    sleeve = next(p for p in result.finalized_parts if p.part_type == "sleeve")
    front_distance = armhole_notch_distance_cm(
        front.stitch_line, underarm_y=underarm_y_of(front))
    cap = _sleeve_cap_path(sleeve.stitch_line)
    total = sum(dist(a, b) for a, b in zip(cap, cap[1:]))
    marks = [_arc_position(cap, point)[1] for point, _ in sleeve.notches]
    assert len(marks) == 3
    assert marks[0] == pytest.approx(front_distance, abs=.15)
    assert total - marks[1] == pytest.approx(front_distance, abs=.15)
    assert total - marks[2] == pytest.approx(
        front_distance + BACK_DOUBLE_NOTCH_GAP_CM, abs=.15)


@pytest.mark.parametrize("body", [
    Measurements(76, 60, 86, 152, 49, 35),
    Measurements(83, 66, 91, 158, 52, 37),
    Measurements(104, 92, 112, 170, 58, 42),
])
def test_production_gate_catches_a_shifted_sleeve_notch(body):
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        build_garment_spec(front_zip=True, neckline="round_neck",
                           sleeve_style="straight"), body,
        shoulder_drop_cm=5.0, skip_export=True)
    assert endministrator_notch_pairing_warnings(result.finalized_parts) == []
    assert "sleeve_cap_toile" in {
        item["code"] for item in production_quality_report(result)["fitting_checklist"]
    }
    bad_parts = deepcopy(result.finalized_parts)
    sleeve = next(part for part in bad_parts if part.part_type == "sleeve")
    origin, end = sleeve.notches[0]
    sleeve.notches[0] = ((origin[0] + 1.0, origin[1]), end)
    assert endministrator_notch_pairing_warnings(bad_parts)
    result.finalized_parts = bad_parts
    result.garment_spec.construction["costume_project_brief"] = {
        "key": "endministrator_female",
    }
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("袖付け合印:" in item for item in report["blockers"])


def test_large_coat_side_seam_mismatch_is_a_production_blocker():
    body = Measurements(116, 100, 128, 180, 64, 45)
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        build_garment_spec(front_zip=True, neckline="round_neck",
                           sleeve_style="straight"), body,
        worn_over_bust_cm=body.bust + 10, shoulder_drop_cm=5.0,
        skip_export=True)
    warnings = endministrator_side_seam_warnings(result.finalized_parts)
    assert len(warnings) == 2
    assert all("0.95cm" in warning for warning in warnings)
    assert all("長い" in warning and "縫い線を再製図" in warning
               for warning in warnings)
    result.garment_spec.construction["costume_project_brief"] = {
        "key": "endministrator_female",
    }
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("脇縫い線:" in item for item in report["blockers"])
