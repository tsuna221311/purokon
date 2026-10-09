"""Presentation examples are disclosed fixed inputs, not image-AI claims."""

import pytest

import app as app_module
from engine.costume_projects import get_costume_project
from engine.demo_cases import DEMO_CASES, DEMO_MEASUREMENTS
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.production_quality import production_quality_report


@pytest.mark.parametrize("case", DEMO_CASES, ids=lambda case: case["id"])
def test_fixed_demo_pattern_passes_digital_seam_gate(tmp_path, case):
    body = Measurements(**DEMO_MEASUREMENTS)
    project = get_costume_project(case["project_key"], body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    extras = [request for panel in project.custom_panel_specs
              for request in build_custom_panel_requests(
                  panel.label, panel.points_cm, quantity=panel.quantity,
                  mirror=panel.mirror, allow_split=panel.allow_split)]
    if extras:
        spec.parts = merge_custom_panel_requests(
            spec.parts, extras, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    report = production_quality_report(result)
    assert result.finalized_parts
    assert report["digital_ready"] is True, report["blockers"]
    assert result.compatibility_warnings() == []
    assert all(part.stitch_line and part.cut_line for part in result.finalized_parts)


@pytest.mark.parametrize("case", DEMO_CASES, ids=lambda case: case["id"])
def test_fixed_demo_uses_manual_generator_and_downloads(client, monkeypatch, case):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    form = {key: str(value) for key, value in DEMO_MEASUREMENTS.items()}
    form.update({"mode": "manual", "fit": "standard",
                 "costume_project": case["project_key"],
                 "project_name": "発表用・" + case["title"]})
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    payload = response.get_json()
    assert payload["costume_project"]["key"] == case["project_key"]
    assert payload["parts"]
    for fmt in ("pdf", "svg"):
        download = client.get(payload["download"][fmt])
        assert download.status_code == 200
        assert download.data


def test_demo_page_discloses_fixed_inputs_and_original_sketch(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    page = client.get("/").get_data(as_text=True)
    assert "画像を自動解析した結果ではありません" in page
    for case in DEMO_CASES:
        assert f'data-demo-case="{case["id"]}"' in page
    sketch = client.get("/static/demo/blue_dress_three_views.svg")
    assert sketch.status_code == 200
    assert b"<svg" in sketch.data
