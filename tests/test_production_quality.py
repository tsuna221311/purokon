from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import (fitting_checklist, pattern_geometry_warnings,
                                       production_quality_report)


MEASUREMENTS = Measurements(84, 68, 92, 160, 54, 37)


def _result(tmp_path, *, sleeve="straight", skirt="flare"):
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(sleeve_style=sleeve, skirt_style=skirt), MEASUREMENTS)


def test_quality_report_separates_digital_pass_from_physical_signoff(tmp_path):
    report = production_quality_report(_result(tmp_path))
    assert report["digital_ready"] is True
    assert report["status"] == "physical_verification_required"
    assert report["physical_signoff_required"] is True
    assert any(item["code"] == "final_toile"
               for item in report["fitting_checklist"])


def test_fitting_checklist_only_includes_parts_that_exist(tmp_path):
    result = _result(tmp_path, sleeve=None, skirt=None)
    codes = {item.code for item in fitting_checklist(result)}
    assert "shoulder_position" in codes
    assert "arm_motion" not in codes
    assert "hip_ease" not in codes


def test_unconfirmed_field_blocks_digital_release(tmp_path):
    spec = build_garment_spec(sleeve_style=None, skirt_style=None)
    spec.construction["unconfirmed_fields"] = ["背面構造を確認してください"]
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEASUREMENTS)
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert "背面構造を確認してください" in report["blockers"]


def test_summary_exposes_machine_readable_quality_report(tmp_path):
    summary = _result(tmp_path).summary()
    assert summary["production_quality"]["physical_signoff_required"] is True
    assert summary["production_quality"]["fitting_checklist"]


def test_self_intersecting_cut_line_blocks_digital_readiness(tmp_path):
    result = _result(tmp_path)
    result.finalized_parts[0].cut_line = [
        (0.0, 0.0), (5.0, 5.0), (0.0, 5.0),
        (5.0, 0.0), (0.0, 0.0)]
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("自己交差" in item for item in report["blockers"])


def test_cut_line_inside_stitch_line_blocks_digital_readiness(tmp_path):
    from shapely.geometry import Polygon

    result = _result(tmp_path)
    part = result.finalized_parts[0]
    smaller = Polygon(part.stitch_line).buffer(-1.0)
    assert not smaller.is_empty
    part.cut_line = list(smaller.exterior.coords)
    assert any("縫い線の内側" in item
               for item in pattern_geometry_warnings(result.finalized_parts))
    assert production_quality_report(result)["digital_ready"] is False


def test_non_finite_cut_coordinate_is_reported_instead_of_crashing(tmp_path):
    result = _result(tmp_path)
    result.finalized_parts[0].cut_line[0] = (float("nan"), 0.0)
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("座標が不正" in item for item in report["blockers"])


def test_grainline_outside_finished_piece_blocks_digital_readiness(tmp_path):
    result = _result(tmp_path)
    result.finalized_parts[0].grainline = {
        "line": ((10000.0, 0.0), (10000.0, 10.0)), "arrows": []}
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("布目線" in item for item in report["blockers"])


def test_notch_that_does_not_reach_cut_edge_blocks_digital_readiness(tmp_path):
    result = _result(tmp_path)
    part = next(p for p in result.finalized_parts if p.notches)
    origin, end = part.notches[0]
    part.notches[0] = (origin, ((origin[0] + end[0]) / 2,
                                (origin[1] + end[1]) / 2))
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("裁断線に届いていません" in item for item in report["blockers"])


def test_inward_notch_blocks_digital_readiness(tmp_path):
    from shapely.geometry import Polygon

    result = _result(tmp_path)
    part = next(p for p in result.finalized_parts if p.notches)
    origin, _ = part.notches[0]
    center = Polygon(part.stitch_line).representative_point()
    part.notches[0] = (origin, (center.x, center.y))
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("型紙本体を横切っています" in item for item in report["blockers"])
