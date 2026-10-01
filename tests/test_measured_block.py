import pytest

from engine.blocks import build_measured_block, validate_measured_block
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, _closed_points_from_segments,
                             _x_span_at_y, build_garment_spec)


VALUES = {
    "back_width_cm": 18.2,
    "chest_width_cm": 17.5,
    "neck_half_cm": 7.5,
    "armhole_depth_cm": 24.0,
    "shoulder_slope_front_deg": 15.0,
    "shoulder_slope_back_deg": 13.0,
    "standard_ease_cm": 12.0,
    "bust_dart_angle_deg": 0.0,
}


def _form():
    data = {
        "mode": "manual", "bust": "96", "waist": "82", "hip": "98",
        "height": "178", "sleeve_length": "61", "shoulder_width": "44",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "", "block": "measured",
    }
    data.update({f"block_{key}": str(value) for key, value in VALUES.items()})
    return data


def test_measured_block_uses_every_supplied_value_without_formula_guessing():
    block = build_measured_block(VALUES)
    assert block.back_width.value(96) == 18.2
    assert block.chest_width.value(96) == 17.5
    assert block.neck_half.value(96) == 7.5
    assert block.armhole_depth.value(96, 178) == 24.0
    assert block.shoulder_slope_front_deg == 15.0
    assert block.shoulder_slope_back_deg == 13.0
    assert block.ease_cm(96) == 12.0
    assert block.bust_dart_angle.value(96) == 0.0
    assert block.draws_bust_point is False


def test_measured_block_refuses_missing_values():
    incomplete = dict(VALUES)
    incomplete.pop("armhole_depth_cm")
    try:
        validate_measured_block(incomplete)
    except ValueError as exc:
        assert "全項目" in str(exc)
        assert "袖ぐり深さ" in str(exc)
    else:
        raise AssertionError("missing measured-block value was accepted")


def test_pipeline_discloses_that_a_measured_block_was_used(tmp_path):
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(sleeve_style="straight", skirt_style=None),
        Measurements(96, 82, 98, 178, 61, 44),
        block_key="measured", measured_block=VALUES, skip_export=True)
    notes = " ".join(result.design_notes)
    assert "採寸指定（専用原型）" in notes
    assert "背幅=18.2" in notes
    assert "胸幅=17.5" in notes
    assert "値の出どころ" in notes


def test_measured_block_values_land_on_the_generated_bodice(tmp_path):
    """入力欄に値があるだけでなく、輪郭の基準点がその実寸になること。"""
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(sleeve_style="straight", skirt_style=None),
        Measurements(96, 82, 98, 178, 61, 44),
        block_key="measured", measured_block=VALUES, skip_export=True)
    front = next(part for part in result.scaled_parts
                 if part.part_type == "front_bodice")
    back = next(part for part in result.scaled_parts
                if part.part_type == "back_bodice")

    assert front.chest_width_cm_actual == pytest.approx(VALUES["chest_width_cm"], abs=0.005)
    assert back.chest_width_cm_actual == pytest.approx(VALUES["back_width_cm"], abs=0.005)
    points = _closed_points_from_segments(front.segments)
    neck_y = min(point[1] for point in points)
    assert front.bust_line_y_cm - neck_y == pytest.approx(
        VALUES["armhole_depth_cm"], abs=0.005)
    span = _x_span_at_y(points, front.bust_line_y_cm)
    assert (span[1] - span[0]) / 2 == pytest.approx(
        (96 + VALUES["standard_ease_cm"]) / 4, abs=0.005)


def test_web_generation_and_regeneration_keep_measured_block(client):
    client.post("/signup", data={
        "email": "measured-block@example.com", "password": "password123",
        "password_confirm": "password123"}, follow_redirects=True)
    first = client.post("/api/generate", data=_form())
    assert first.status_code == 200, first.get_json().get("error")
    data = first.get_json()
    assert any("採寸指定（専用原型）" in note for note in data["design_notes"])
    regenerated = client.post(
        f"/account/jobs/{data['job_id']}/regenerate", follow_redirects=True)
    assert regenerated.status_code == 200
    assert "採寸指定（専用原型）" in regenerated.get_data(as_text=True)


def test_measured_block_is_graded_from_selected_size_measurements(client):
    form = _form()
    form.update({"mode": "multi_size", "sizes": ["S", "M"]})
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    results = response.get_json()["results"]
    assert set(results) == {"S", "M"}
    assert results["S"]["measurements"]["shoulder_width"] < \
        results["M"]["measurements"]["shoulder_width"]
