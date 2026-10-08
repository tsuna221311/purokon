"""A digitally blocked pattern PDF must remain visibly non-cuttable."""

from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from engine.pdf_draft import _blocked_svg_markup, _warning_overlay
from engine.pdf_export import unprintable_characters
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import production_quality_report


def test_warning_overlay_has_printable_japanese_and_english():
    assert unprintable_characters("検査不合格・裁断禁止") == []
    text = PdfReader(_warning_overlay(595, 842)).pages[0].extract_text()
    assert "検査不合格・裁断禁止" in text
    assert "DRAFT - NOT FOR CUTTING" in text


def test_blocked_svg_markup_is_scale_aware_and_idempotent():
    source = '<svg viewBox="0 0 110 270" xmlns="http://www.w3.org/2000/svg"></svg>'
    marked = _blocked_svg_markup(source)
    assert 'id="patternforge-draft-watermark"' in marked
    assert "検査不合格・裁断禁止" in marked
    assert "DRAFT - NOT FOR CUTTING" in marked
    assert marked.count('<path d="') >= 20  # 文字を輪郭化して豆腐を防ぐ
    assert "font-family=\"PatternForgeJP" not in marked
    assert 'x="55.0"' in marked
    assert ElementTree.fromstring(marked).tag.endswith("svg")
    assert _blocked_svg_markup(marked) == marked


def test_blocked_export_marks_every_pdf_page(tmp_path):
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(), Measurements(66, 45, 72, 148, 46, 37),
        lining=True)
    assert production_quality_report(result)["digital_ready"] is False
    pdf_paths = [path for path in result.output_files.values()
                 if path.lower().endswith(".pdf")]
    assert pdf_paths
    for path in pdf_paths:
        pages = PdfReader(path).pages
        assert pages
        assert all("DRAFT - NOT FOR CUTTING" in (page.extract_text() or "")
                   and "検査不合格・裁断禁止" in (page.extract_text() or "")
                   for page in pages), path
    svg_paths = [path for key, path in result.output_files.items()
                 if key.endswith("svg")]
    assert svg_paths
    assert all('id="patternforge-draft-watermark"' in
               Path(path).read_text(encoding="utf-8") for path in svg_paths)
    assert not any(key.endswith("dxf") for key in result.output_files)
    assert not list(tmp_path.glob("*.dxf"))
    assert not list(tmp_path.glob("*.quality.tmp"))


def test_ready_export_does_not_receive_draft_watermark(tmp_path):
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(), Measurements(84, 68, 92, 160, 54, 37))
    assert production_quality_report(result)["digital_ready"] is True
    text = "\n".join(page.extract_text() or ""
                     for page in PdfReader(result.output_files["pdf"]).pages)
    assert "DRAFT - NOT FOR CUTTING" not in text
    assert 'id="patternforge-draft-watermark"' not in Path(
        result.output_files["svg"]).read_text(encoding="utf-8")
    assert result.output_files["dxf"].endswith(".dxf")
    assert Path(result.output_files["dxf"]).exists()
