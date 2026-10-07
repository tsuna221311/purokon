"""Sewing instructions must report the sewn pattern, not a design target."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.pipeline import _sleeve_cap_ease_for


def _parts():
    return [SimpleNamespace(part_type=kind) for kind in (
        "front_bodice_zip_panel", "front_bodice_zip_panel",
        "back_bodice", "sleeve", "sleeve",
    )]


def test_uses_actual_cap_after_drop_shoulder_adjustment():
    parts = _parts()
    armholes = {id(part): value for part, value in zip(parts[:3],
                (20.46, 20.46, 45.50))}
    caps = {id(part): 44.715 for part in parts[3:]}
    with patch("engine.pipeline.armhole_length",
               side_effect=lambda part: armholes[id(part)]), patch(
                   "engine.pipeline.sleeve_cap_length",
                   side_effect=lambda part: caps[id(part)]):
        assert _sleeve_cap_ease_for(parts) == pytest.approx(1.51, abs=0.01)


def test_does_not_print_measured_ease_without_sleeves():
    assert _sleeve_cap_ease_for(_parts()[:3]) is None


def test_does_not_print_negative_or_unmeasurable_ease():
    parts = _parts()
    with patch("engine.pipeline.armhole_length", return_value=20.0), patch(
            "engine.pipeline.sleeve_cap_length", return_value=15.0):
        assert _sleeve_cap_ease_for(parts) is None
    with patch("engine.pipeline.armhole_length", return_value=20.0), patch(
            "engine.pipeline.sleeve_cap_length", return_value=None):
        assert _sleeve_cap_ease_for(parts) is None


@pytest.mark.parametrize("ease", [None, -1.0, 0.0, float("nan"), float("inf")])
def test_sewing_step_does_not_order_unmeasured_easing(ease):
    from engine.assembly import assembly_steps

    parts = [SimpleNamespace(part_type=kind, display_name=kind,
                             label_suffix="", dart_count=0, notches=[])
             for kind in ("front_bodice", "back_bodice", "sleeve")]
    step = next(s for s in assembly_steps(parts, sleeve_cap_ease_cm=ease)
                if s.title == "袖を身頃に付ける")
    assert "縮め量は指定しません" in step.detail
    assert "少し縮めます" not in step.detail


def test_endministrator_real_pattern_and_sewing_step_agree():
    from engine.costume_projects import get_costume_project
    from engine.measurements import Measurements
    from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                                 build_garment_spec, merge_custom_panel_requests)

    body = Measurements(87, 75, 98, 155, 49, 41)
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    extras = [request for panel in project.custom_panel_specs
              for request in build_custom_panel_requests(
                  panel.label, panel.points_cm, quantity=panel.quantity,
                  mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, extras, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)

    measured_ease = _sleeve_cap_ease_for(result.finalized_parts)
    assert measured_ease == pytest.approx(1.5, abs=0.1)
    sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert len(sleeves) == 2
    assert all(len(sleeve.notches) == 4 for sleeve in sleeves)
    step = next(s for s in result.assembly_steps() if s.title == "袖を身頃に付ける")
    assert f"約{measured_ease:.1f}cm" in step.detail
    assert "4本目" in step.detail
