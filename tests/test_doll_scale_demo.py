"""One-third paper PDFs retain exact vector scaling and print calibration."""

from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4

from scripts.build_doll_scale_demo import SCALE, build_case


def test_one_third_pdf_tiling_and_calibration(tmp_path: Path):
    source = tmp_path / "tiny.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="90cm" '
        'height="60cm" viewBox="0 0 90 60">'
        '<polygon points="0,0 90,0 90,60 0,60" stroke="black" fill="white" />'
        '<text x="45" y="30" font-size="0.9" text-anchor="middle">試験</text>'
        '</svg>', encoding="utf-8")
    destination = tmp_path / "doll.pdf"
    case = {"id": "blue_dress", "title": "紙模型の試験"}
    measurements = {"bust": 83, "waist": 66, "hip": 91,
                    "height": 158, "shoulder_width": 37,
                    "sleeve_length": 52}
    info = build_case(source, case, measurements, destination)
    reader = PdfReader(str(destination))
    assert info["scale"] == SCALE == 1 / 3
    assert info["tile_cols"] == 2
    assert info["tile_rows"] == 1
    assert len(reader.pages) == info["pages"] == 3
    assert "33.3mm" in reader.pages[0].extract_text()
    for page in reader.pages:
        assert round(float(page.mediabox.width), 2) == round(A4[0], 2)
        assert round(float(page.mediabox.height), 2) == round(A4[1], 2)
    assert "試験" in reader.pages[1].extract_text()
    content = reader.pages[1].get_contents().get_data()
    assert b"0.333333" in content


def test_blank_cells_are_omitted_without_changing_tile_coordinates(tmp_path: Path):
    source = tmp_path / "partial.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="90cm" '
        'height="60cm" viewBox="0 0 90 60">'
        '<polygon points="1,1 20,1 20,59 1,59" stroke="black" fill="white" />'
        '</svg>', encoding="utf-8")
    output = tmp_path / "partial.pdf"
    info = build_case(source, {"id": "miku", "title": "省略テスト"},
                      {"bust": 83, "waist": 66, "hip": 91,
                       "height": 158, "shoulder_width": 37,
                       "sleeve_length": 52}, output)
    assert info["tile_cols"] == 2
    assert info["omitted_blank_cells"] == ["1-2"]
    assert info["pages"] == len(PdfReader(str(output)).pages) == 2
