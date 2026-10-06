"""A lower coat panel joins the hem after waist darts are sewn closed."""

from types import SimpleNamespace

import pytest

from engine.costume_projects import get_costume_project
from engine.darts import retrue_bodice_waist_darts
from engine.hem_extensions import (_hem_mark_at, _sewn_bottom_edge,
                                   hem_extension_rows,
                                   hem_extension_warnings)
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.production_quality import production_quality_report


@pytest.mark.parametrize("dimensions", [
    (68, 47, 70, 148, 47, 36),
    (76, 54, 87, 160, 50, 38),
    (96, 67, 100, 160, 50, 38),
    (116, 84, 112, 165, 54, 42),
])
def test_sewn_dart_mouth_is_excluded_from_join_length_and_notches(dimensions):
    body = Measurements(*dimensions)
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    requests = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, requests, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)

    host = next(part for part in result.finalized_parts
                if part.part_type == "front_bodice_zip_panel")
    runs, y = _sewn_bottom_edge(host, allow_darts=True)
    assert len(runs) >= 2
    sewn_length = sum(right - left for left, right in runs)
    assert sewn_length < runs[-1][1] - runs[0][0] - .2
    assert all(any(abs(origin[0] - _hem_mark_at(runs, y, f)[0]) < .03
                   and abs(origin[1] - y) < .03
                   for origin, _end in host.notches)
               for f in (.25, .75))
    assert hem_extension_warnings(result.finalized_parts, project.as_dict()) == []
    rows = hem_extension_rows(result.finalized_parts, project.as_dict())
    left_length, right_length = (float(value) for value in
                                 rows[0][3].removesuffix(" cm").split(" / "))
    assert left_length == pytest.approx(sewn_length, abs=.1)
    assert left_length == right_length
    assert "digital_ready" in production_quality_report(result)


def test_waist_dart_truing_moves_only_a_nearby_tip():
    outline = [("M", [0, 0]), ("L", [0, 20]), ("L", [6, 20]),
               ("L", [8.5, 8]), ("L", [10, 20]), ("L", [14, 20]),
               ("L", [14, 0]), ("Z", [])]
    trued = retrue_bodice_waist_darts(outline)
    assert trued[3] == ("L", [8.0, 8])
    assert trued[2] == outline[2] and trued[4] == outline[4]
    far_tip = [*outline]
    far_tip[3] = ("L", [9.0, 8])
    assert retrue_bodice_waist_darts(far_tip) == far_tip


def test_unverified_gap_is_not_treated_as_a_closed_waist_dart():
    invalid = SimpleNamespace(display_name="broken hem", stitch_line=[
        (0, 0), (10, 0), (10, 10), (6, 10), (5, 8), (4, 10), (0, 10), (0, 0)])
    with pytest.raises(ValueError, match="裾辺が途切れています"):
        _sewn_bottom_edge(invalid, allow_darts=False)
    with pytest.raises(ValueError, match="閉じるダーツと確認できません"):
        _sewn_bottom_edge(invalid, allow_darts=True)
    unequal_legs = SimpleNamespace(display_name="unequal dart legs", stitch_line=[
        (0, 0), (10, 0), (10, 10), (6, 10), (4.1, 2),
        (4, 10), (0, 10), (0, 0)])
    with pytest.raises(ValueError, match="閉じるダーツと確認できません"):
        _sewn_bottom_edge(unequal_legs, allow_darts=True)
