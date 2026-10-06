from pathlib import Path

from pypdf import PdfReader

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.specification import export_specification_pdf, production_readiness


MEASUREMENTS = Measurements(84, 68, 92, 160, 54, 37)


def _text(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def test_pipeline_exports_manufacturing_specification(tmp_path):
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(sleeve_style="straight", skirt_style="flare"),
        MEASUREMENTS,
    )

    path = Path(result.output_files["spec_pdf"])
    assert path.exists()
    text = _text(path)
    assert "製作仕様書" in text
    assert "採寸" in text
    assert "型紙パーツ一覧" in text
    assert "縫製順" in text


def test_unconfirmed_image_fields_make_specification_not_ready(tmp_path):
    spec = build_garment_spec(sleeve_style="straight", skirt_style="flare")
    spec.construction["unconfirmed_fields"] = [
        "後ろの襟ぐりを確認してください", "開閉方法を確認してください"]
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEASUREMENTS)

    ready, pending = production_readiness(result)
    assert ready is False
    assert "開閉方法を確認してください" in pending
    export_specification_pdf(result, result.output_files["spec_pdf"])
    text = _text(result.output_files["spec_pdf"])
    assert "要確認" in text
    assert "確認完了まで裁断しない" in text


def test_specification_does_not_approve_a_broken_cut_outline(tmp_path):
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(skirt_style=None), MEASUREMENTS, skip_export=True)
    result.finalized_parts[0].cut_line = []
    ready, pending = production_readiness(result)
    assert ready is False
    assert any("型紙形状" in message for message in pending)


def test_specification_spells_out_confirmed_construction_values(tmp_path):
    spec = build_garment_spec(sleeve_style="straight", skirt_style="flare")
    spec.construction.update({
        "closure": "side_zip", "closure_length_cm": 30,
        "symmetry": "symmetric", "layer_count": 2,
        "layer_lengths_cm": [70, 50], "movement": "dance",
        "gather_ratio": 1.8, "internal_support": "boning",
        "construction_note": "左肩の装飾を手縫いで固定",
    })
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEASUREMENTS)
    text = _text(result.output_files["spec_pdf"])
    for phrase in ("脇ファスナー", "30", "左右対称", "第1層 70cm",
                   "第2層 50cm", "ダンス", "1.8倍", "ボーン",
                   "左肩の装飾を手縫いで固定"):
        assert phrase in text
