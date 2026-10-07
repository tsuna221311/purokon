"""A digitally blocked pattern PDF must remain visibly non-cuttable."""

from pypdf import PdfReader

from engine.pdf_draft import _warning_overlay
from engine.pdf_export import unprintable_characters
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import production_quality_report


def test_warning_overlay_has_printable_japanese_and_english():
    assert unprintable_characters("検査不合格・裁断禁止") == []
    text = PdfReader(_warning_overlay(595, 842)).pages[0].extract_text()
    assert "検査不合格・裁断禁止" in text
    assert "DRAFT - NOT FOR CUTTING" in text


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
    assert not list(tmp_path.glob("*.quality.tmp"))


def test_ready_export_does_not_receive_draft_watermark(tmp_path):
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        build_garment_spec(), Measurements(84, 68, 92, 160, 54, 37))
    assert production_quality_report(result)["digital_ready"] is True
    text = "\n".join(page.extract_text() or ""
                     for page in PdfReader(result.output_files["pdf"]).pages)
    assert "DRAFT - NOT FOR CUTTING" not in text
