from types import SimpleNamespace
from pathlib import Path

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import (fitting_checklist, pattern_geometry_warnings,
                                       production_quality_report)


MEASUREMENTS = Measurements(84, 68, 92, 160, 54, 37)


def test_blocked_digital_pattern_is_flagged_before_download_and_per_size():
    root = Path(__file__).resolve().parents[1]
    html = (root / "web/templates/index.html").read_text(encoding="utf-8")
    js = (root / "web/static/app.js").read_text(encoding="utf-8")
    assert html.index('id="digital-quality-alert"') < html.index('id="download-pdf"')
    assert 'renderDigitalQualityAlert(quality)' in js
    assert 'quality.digital_ready === false' in js
    assert 'sizeQuality.digital_ready === false' in js
    assert '本番生地を裁断しないでください。' in js


def test_paper_preflight_is_in_physical_checklist_without_generation():
    result = SimpleNamespace(
        finalized_parts=[],
        garment_spec=SimpleNamespace(construction={}),
    )
    checks = fitting_checklist(result)
    assert [item.code for item in checks[:2]] == ["print_scale", "tile_assembly"]
    assert "5.0cm" in checks[0].pass_condition
    assert "裁断線" in checks[1].method


def test_sleeve_fitting_check_uses_actual_pattern_notch_marks():
    result = SimpleNamespace(
        finalized_parts=[SimpleNamespace(part_type="sleeve")],
        garment_spec=SimpleNamespace(construction={}),
    )
    sleeve_check = next(item for item in fitting_checklist(result)
                        if item.code == "sleeve_cap_toile")
    assert "前後・肩の合印" in sleeve_check.method
    assert "前1本・後ろ2本" not in sleeve_check.method


def test_malformed_notch_is_a_blocker_instead_of_a_crash():
    part = SimpleNamespace(
        display_name="試験片", stitch_line=[(0, 0), (10, 0), (10, 10), (0, 10)],
        cut_line=[(-1, -1), (11, -1), (11, 11), (-1, 11)],
        grainline={"line": ((2, 2), (2, 8)), "arrows": []},
        notches=[((0, 5),), ((0, 5), ("bad", 5))],
    )
    warnings = pattern_geometry_warnings([part])
    assert "試験片: 合印1の座標が不正です" in warnings
    assert "試験片: 合印2の座標が不正です" in warnings


def test_unplaced_lining_and_second_fabric_block_digital_release():
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        build_garment_spec(), MEASUREMENTS, lining=True, skip_export=True)
    assert production_quality_report(result)["digital_ready"] is True

    result.lining_nesting.unplaced.append(result.lining_parts[0])
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("裏地で配置できていない型紙が1枚" in item
               for item in report["blockers"])

    result.lining_nesting.unplaced.clear()
    result.fabric_groups.append(SimpleNamespace(
        name="別布", index=1, nesting=SimpleNamespace(unplaced=[object()])))
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert any("生地「別布」で配置できていない型紙が1枚" in item
               for item in report["blockers"])


def test_summary_counts_and_warns_for_unplaced_lining_and_accent_fabric():
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        build_garment_spec(), MEASUREMENTS, lining=True,
        fabric_group_assignments={"skirt": "別布"}, skip_export=True)
    assert len(result.fabric_groups) == 2
    assert result.summary()["unplaced_count"] == 0

    result.lining_nesting.unplaced.append(result.lining_parts[0])
    accent = result.fabric_groups[1]
    accent.nesting.unplaced.append(accent.parts[0])
    summary = result.summary()
    assert summary["unplaced_count"] == 2
    assert summary["lining"]["unplaced_count"] == 1
    assert summary["fabric_groups"][1]["unplaced_count"] == 1
    assert any("裏地の型紙が1枚" in item for item in summary["unplaced_warnings"])
    assert any("生地「別布」の型紙が1枚" in item
               for item in summary["unplaced_warnings"])
    assert summary["production_quality"]["digital_ready"] is False

    # 1種類目の生地は result.nesting と同じ配置を参照する。二重に数えない。
    result.nesting.unplaced.append(result.fabric_groups[0].parts[0])
    summary = result.summary()
    assert summary["unplaced_count"] == 3
    assert len(summary["unplaced_warnings"]) == 3


def test_missing_lining_layout_blocks_digital_release():
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        build_garment_spec(), MEASUREMENTS, lining=True, skip_export=True)
    result.lining_nesting = None
    report = production_quality_report(result)
    assert report["digital_ready"] is False
    assert "裏地型紙の配置が未計算です" in report["blockers"]


def _result(tmp_path, *, sleeve="straight", skirt="flare"):
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(sleeve_style=sleeve, skirt_style=skirt), MEASUREMENTS)


def test_quality_report_separates_digital_pass_from_physical_signoff(tmp_path):
    report = production_quality_report(_result(tmp_path))
    assert report["digital_ready"] is True
    assert report["status"] == "physical_verification_required"
    assert report["physical_signoff_required"] is True
    assert {"print_scale", "tile_assembly"}.issubset(
        {item["code"] for item in report["fitting_checklist"]})
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
