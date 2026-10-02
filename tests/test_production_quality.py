from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import fitting_checklist, production_quality_report


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
