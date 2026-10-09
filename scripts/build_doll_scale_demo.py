"""Make honest 1:3 A4 paper-mockup PDFs from verified projector PDFs.

The original projector PDF uses one PDF point for one physical point.  Every
source page is vector-scaled by exactly 1/3; tiling never re-fits it to A4.
This is a paper fitting aid, not a guarantee that an unmeasured doll will fit.
"""

from __future__ import annotations

import argparse
import io
import json
from math import ceil
from pathlib import Path
import xml.etree.ElementTree as ET

import cairosvg
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


SCALE = 1 / 3
LEFT = 1.0 * cm
BOTTOM = 1.0 * cm
TILE_W = 19.0 * cm
TILE_H = 25.5 * cm
FONT_PATH = Path("C:/Windows/Fonts/NotoSansJP-VF.ttf")
TITLES = {
    "endministrator": "エンドフィールド 管理人（女性）",
    "miku": "初音ミク（定番衣装）",
    "blue_dress": "オリジナル青いドレス",
}


def _register_font() -> None:
    if "DollDemoJP" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DollDemoJP", str(FONT_PATH)))


def _draw_cover(case: dict, measurements: dict) -> bytes:
    _register_font()
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=A4)
    page.setTitle(f"PatternForge 1/3 紙模型 - {case['title']}")
    page.setFillColor(colors.HexColor("#17233d"))
    page.rect(0, A4[1] - 6.0 * cm, A4[0], 6.0 * cm, fill=1, stroke=0)
    page.setFillColor(colors.white)
    page.setFont("DollDemoJP", 17)
    page.drawString(1.4 * cm, A4[1] - 2.4 * cm, "PatternForge | 1/3 紙模型")
    page.setFont("DollDemoJP", 12)
    page.drawString(1.4 * cm, A4[1] - 3.5 * cm, case["title"])
    page.setFont("DollDemoJP", 9)
    page.drawString(1.4 * cm, A4[1] - 4.6 * cm, "型紙の初稿を紙で組み、形と着脱を確認する発表用資料")

    y = A4[1] - 7.4 * cm
    page.setFillColor(colors.HexColor("#17233d"))
    page.setFont("DollDemoJP", 11)
    page.drawString(1.4 * cm, y, "印刷と組み立て")
    page.setFont("DollDemoJP", 9.4)
    instructions = [
        "1. A4・実際のサイズ（100%）で印刷。『用紙に合わせる』はオフ。",
        "2. 下の校正線が33.3mmか定規で確認（元の10cmを1/3に縮小）。",
        "3. 青い枠を切り、行・列番号順に辺を合わせる（欠番は空白面）。",
        "4. 実線＝裁断線、破線＝縫い線。紙では縫い線をテープで仮止め。",
        "5. 人形の寸法を測り、余り・不足と動かしにくさを記録する。",
    ]
    for line in instructions:
        y -= 0.60 * cm
        page.drawString(1.4 * cm, y, line)

    y -= 1.0 * cm
    page.setFont("DollDemoJP", 11)
    page.drawString(1.4 * cm, y, "想定寸法（人体の固定採寸 ÷ 3）")
    fields = [
        ("身長", "height"), ("バスト", "bust"), ("ウエスト", "waist"),
        ("ヒップ", "hip"), ("肩幅", "shoulder_width"),
        ("袖丈", "sleeve_length"),
    ]
    page.setFont("DollDemoJP", 9.2)
    for i, (name, key) in enumerate(fields):
        row_y = y - (0.58 + i * 0.48) * cm
        page.drawString(1.55 * cm, row_y, name)
        page.drawRightString(9.4 * cm, row_y, f"{measurements[key]:.1f} cm")
        page.drawRightString(14.8 * cm, row_y, f"{measurements[key] / 3:.2f} cm")
    page.setFillColor(colors.HexColor("#3e58a6"))
    page.drawString(9.4 * cm, y + 0.13 * cm, "元の採寸")
    page.drawString(13.2 * cm, y + 0.13 * cm, "紙模型")

    y -= 4.3 * cm
    page.setFillColor(colors.HexColor("#17233d"))
    page.setFont("DollDemoJP", 10)
    page.drawString(1.4 * cm, y, "印刷倍率の校正線")
    page.setStrokeColor(colors.HexColor("#374b9a"))
    page.setLineWidth(1.1)
    page.line(1.5 * cm, y - 0.75 * cm, (1.5 + 10 / 3) * cm, y - 0.75 * cm)
    for x in (1.5 * cm, (1.5 + 10 / 3) * cm):
        page.line(x, y - 0.95 * cm, x, y - 0.55 * cm)
    page.setFont("DollDemoJP", 8)
    page.drawString(1.5 * cm, y - 1.2 * cm, "この線を測る：33.3mm（元寸10cm）")

    y -= 2.0 * cm
    page.setFillColor(colors.HexColor("#772b35"))
    page.setFont("DollDemoJP", 8.4)
    page.drawString(1.4 * cm, y, "注意：実物人形の採寸は未取得。1/3人形でも体型が違えば合いません。")
    page.drawString(1.4 * cm, y - 0.55 * cm, "デジタル縫い線検査の通過は、着脱・強度・着心地の保証ではありません。")
    if case["id"] == "blue_dress":
        page.drawString(1.4 * cm, y - 1.10 * cm, "青いドレスの後ろ開きは未製図。紙模型でも着脱の確認が必要です。")

    page.setStrokeColor(colors.HexColor("#d0d8e6"))
    page.line(1.4 * cm, 3.1 * cm, A4[0] - 1.4 * cm, 3.1 * cm)
    page.setFillColor(colors.HexColor("#17233d"))
    feedback_top = 10.0 * cm
    feedback_bottom = 3.4 * cm
    page.setFillColor(colors.HexColor("#edf4fb"))
    page.roundRect(1.35 * cm, feedback_bottom,
                   A4[0] - 2.7 * cm, feedback_top - feedback_bottom,
                   0.22 * cm, fill=1, stroke=0)
    page.setFillColor(colors.HexColor("#17233d"))
    page.setFont("DollDemoJP", 11)
    page.drawString(1.7 * cm, feedback_top - 0.75 * cm,
                    "来客と確認したことを初稿へ戻す")
    page.setFont("DollDemoJP", 9)
    page.drawString(1.7 * cm, feedback_top - 1.50 * cm,
                    "人形の実測：身長 ____ / B ____ / W ____ / H ____ / 肩幅 ____ cm")
    prompts = ["正面・側面・背面で違う場所", "肩・袖・腰の余り／不足（mm）",
               "着脱・開き位置・動き", "次の型紙で直すこと"]
    for index, prompt in enumerate(prompts):
        row_y = feedback_top - (2.25 + index * 1.05) * cm
        page.drawString(1.7 * cm, row_y, prompt)
        page.setStrokeColor(colors.HexColor("#aabbd0"))
        page.setLineWidth(0.5)
        page.line(1.7 * cm, row_y - 0.49 * cm,
                  A4[0] - 1.7 * cm, row_y - 0.49 * cm)
    page.save()
    return stream.getvalue()


def _draw_tile_frame(case: dict, row: int, col: int,
                     rows: int, cols: int) -> bytes:
    _register_font()
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=A4)
    page.setStrokeColor(colors.HexColor("#5e81ba"))
    page.setLineWidth(0.55)
    page.rect(LEFT, BOTTOM, TILE_W, TILE_H, fill=0, stroke=1)
    page.setFillColor(colors.HexColor("#17233d"))
    page.setFont("DollDemoJP", 7.4)
    page.drawString(LEFT, A4[1] - 0.63 * cm,
                    f"{case['title']} | 1/3 | 行 {row + 1}/{rows}・列 {col + 1}/{cols}")
    page.drawRightString(A4[0] - LEFT, A4[1] - 0.63 * cm,
                         "100%で印刷 / 枠の辺を突き合わせ")
    for x in (LEFT, LEFT + TILE_W):
        for y in (BOTTOM, BOTTOM + TILE_H):
            page.line(x - 0.22 * cm, y, x + 0.22 * cm, y)
            page.line(x, y - 0.22 * cm, x, y + 0.22 * cm)
    page.setFont("DollDemoJP", 6.4)
    page.drawString(LEFT, BOTTOM - 0.53 * cm,
                    f"{row + 1}-{col + 1}  上下左右の青い枠を合わせる")
    page.save()
    return stream.getvalue()


def _pattern_pdf_from_svg(source_path: Path) -> PdfReader:
    """Render SVG geometry and overlay its Japanese labels as real PDF text.

    CairoSVG does not honor the SVG's embedded subset font on Windows, which
    otherwise creates tofu squares on every part label.  The same SVG text
    coordinates are redrawn using the installed Japanese TrueType font.
    """
    _register_font()
    root = ET.fromstring(source_path.read_bytes())
    vx, vy, vw, vh = (float(value) for value in root.attrib["viewBox"].split())
    if vx != 0 or vy != 0:
        raise ValueError("Expected a zero-origin layout SVG")
    labels = []
    for parent in root.iter():
        for child in list(parent):
            if child.tag.endswith("}text"):
                labels.append((child.attrib, "".join(child.itertext())))
                parent.remove(child)
    pdf_bytes = cairosvg.svg2pdf(bytestring=ET.tostring(root, encoding="utf-8"))
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page = reader.pages[0]
    factor_x = float(page.mediabox.width) / vw
    factor_y = float(page.mediabox.height) / vh
    if abs(factor_x - factor_y) > 0.02:
        raise ValueError("Non-uniform SVG physical scaling")
    overlay = io.BytesIO()
    pen = canvas.Canvas(overlay, pagesize=(float(page.mediabox.width),
                                          float(page.mediabox.height)))
    for attributes, label in labels:
        if not label.strip():
            continue
        x = float(attributes["x"]) * factor_x
        y = float(page.mediabox.height) - float(attributes["y"]) * factor_y
        size_value = str(attributes.get("font-size", "0.9"))
        if size_value.endswith("cm"):
            size_value = size_value[:-2]
        size = float(size_value) * factor_y
        pen.setFont("DollDemoJP", size)
        pen.setFillColor(colors.HexColor(attributes.get("fill", "#333333")))
        anchor = attributes.get("text-anchor", "start")
        if anchor == "middle":
            pen.drawCentredString(x, y, label)
        elif anchor == "end":
            pen.drawRightString(x, y, label)
        else:
            pen.drawString(x, y, label)
    pen.showPage()
    pen.save()
    page.merge_page(PdfReader(io.BytesIO(overlay.getvalue())).pages[0])
    return reader


def _cut_boxes(source_path: Path, page_width: float,
               page_height: float) -> list[tuple[float, float, float, float]]:
    """PDF-space bounding boxes for actual black cut polygons, not fabric fill."""
    root = ET.fromstring(source_path.read_bytes())
    _vx, _vy, vw, vh = (float(value) for value in root.attrib["viewBox"].split())
    sx, sy = page_width / vw, page_height / vh
    boxes = []
    for polygon in root.iter():
        if not polygon.tag.endswith("}polygon") or polygon.get("stroke") != "black":
            continue
        points = [tuple(map(float, pair.split(",")))
                  for pair in polygon.attrib["points"].split()]
        if points:
            xs, ys = zip(*points)
            boxes.append((min(xs) * sx, (vh - max(ys)) * sy,
                          max(xs) * sx, (vh - min(ys)) * sy))
    if not boxes:
        raise ValueError("No black cutting polygons found in pattern SVG")
    return boxes


def build_case(source_path: Path, case: dict, measurements: dict,
               output_path: Path) -> dict:
    # The projector PDF has labels that say "1 square = 10 cm" at full size.
    # Reusing it at 1:3 would make those embedded labels misleading.  The
    # source SVG has the same physical cut/sew paths without that grid.
    source = _pattern_pdf_from_svg(source_path)
    if len(source.pages) != 1:
        raise ValueError("Expected a single-page full-size projector PDF")
    source_page = source.pages[0]
    source_w = float(source_page.mediabox.width)
    source_h = float(source_page.mediabox.height)
    cut_boxes = _cut_boxes(source_path, source_w, source_h)
    scaled_w = source_w * SCALE
    scaled_h = source_h * SCALE
    cols = ceil(scaled_w / TILE_W)
    rows = ceil(scaled_h / TILE_H)
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(_draw_cover(case, measurements))).pages[0])
    omitted = []
    for row in range(rows):
        source_y0 = max(0.0, source_h - (row + 1) * TILE_H / SCALE)
        source_y1 = source_h - row * TILE_H / SCALE
        for col in range(cols):
            source_x0 = col * TILE_W / SCALE
            source_x1 = min(source_w, (col + 1) * TILE_W / SCALE)
            if not any(max(x0, source_x0) < min(x1, source_x1) - 0.5
                       and max(y0, source_y0) < min(y1, source_y1) - 0.5
                       for x0, y0, x1, y1 in cut_boxes):
                omitted.append(f"{row + 1}-{col + 1}")
                continue
            # pypdf clips merged content to the source cropbox before applying
            # the vector transform. This prevents the next tile bleeding into
            # the non-printable margin of the current A4 sheet.
            source_page.cropbox = RectangleObject(
                (source_x0, source_y0, source_x1, source_y1))
            tile = writer.add_blank_page(width=A4[0], height=A4[1])
            tile.merge_transformed_page(source_page, Transformation()
                                        .scale(SCALE)
                                        .translate(LEFT - source_x0 * SCALE,
                                                   BOTTOM - source_y0 * SCALE))
            tile.merge_page(PdfReader(io.BytesIO(
                _draw_tile_frame(case, row, col, rows, cols))).pages[0])
    writer.add_metadata({
        "/Title": f"PatternForge {case['title']} 1/3 A4 paper mockup",
        "/Subject": "Exactly 1:3 vector-scaled presentation pattern, not doll-fit verified",
    })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)
    return {"pages": len(writer.pages), "tile_rows": rows, "tile_cols": cols,
            "omitted_blank_cells": omitted,
            "scale": SCALE, "source_width_pt": source_w,
            "source_height_pt": source_h}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True,
                        help="The verified presentation_demo_..._ready directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.source / "manifest.json").read_text(encoding="utf-8"))
    summary = {"model_scale": "1:3", "doll_fit_verified": False,
               "cases": []}
    for case in manifest["cases"]:
        source_rel = case["files"]["svg"]
        source = args.source / source_rel
        output = args.out / f"{case['id']}_one_third_A4.pdf"
        info = build_case(source, case, manifest["measurements_cm"], output)
        summary["cases"].append({"id": case["id"], "path": str(output), **info})
    (args.out / "pdf_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
