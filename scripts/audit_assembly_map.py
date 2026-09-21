#!/usr/bin/env python3
"""round60: 貼り合わせ図の番号が、**刷り上がりで読めるか**を測る。

【なぜこの検査を足したか】番号と区切り線はパーツより先に描かれていたので、
薄い水色の塗りに消されていた。文字としてはPDFに入っているため、
`pdftotext`でも、枚数を数えるテストでも見つからない。実際に画像にして、
その位置に濃い画素があるかを見るしかない。

実測(round59まで): バスト88のワンピース、印刷する49枚のうち**33枚**の
番号が読めなかった。しかも読めないのは型紙が載っている紙ばかりだった。

pytest(tests/test_round60_assembly_map.py)は1つの組み合わせしか見ない。
ここでは用紙・白紙の扱い・生地の分け方・パーツ構成を変えて、まとめて測る。

使い方:

    python3 scripts/audit_assembly_map.py

不足があれば終了コード1で、どの面の番号が読めないかを並べる。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# 直接実行できるように、リポジトリの根をimport対象に足す
# (他の監査スクリプトと同じやり方)。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.measurements import Measurements
from engine.pdf_export import A3_PAPER, printed_tile_cells
from engine.pipeline import PatternForgePipeline, build_garment_spec


_IS_TILE_NUMBER = re.compile(r"^R\d+-C\d+$")
_DPI = 300

MEAS = Measurements(bust=88, waist=70, hip=94, height=162,
                    sleeve_length=55, shoulder_width=39)


def _word_boxes(pdf_path: str) -> dict[str, tuple[float, float, float, float]]:
    xml = subprocess.run(["pdftotext", "-bbox", "-f", "1", "-l", "1", pdf_path, "-"],
                          capture_output=True, text=True, check=True).stdout
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for word in ET.fromstring(xml).iter():
        if not word.tag.endswith("word"):
            continue
        text = (word.text or "").strip()
        if text:
            boxes[text] = (float(word.attrib["xMin"]), float(word.attrib["yMin"]),
                            float(word.attrib["xMax"]), float(word.attrib["yMax"]))
    return boxes


def _pixels(image):
    getter = getattr(image, "get_flattened_data", None) or image.getdata
    return getter()


def _cover_image(pdf_path: str, work_dir: str):
    from PIL import Image

    prefix = os.path.join(work_dir, "cover")
    subprocess.run(["pdftoppm", "-r", str(_DPI), "-png", "-f", "1", "-l", "1",
                    pdf_path, prefix], check=True, capture_output=True)
    made = sorted(f for f in os.listdir(work_dir) if f.startswith("cover"))
    return Image.open(os.path.join(work_dir, made[0])).convert("RGB")


def _check(label: str, pdf_path: str, cells, work_dir: str) -> list[str]:
    problems: list[str] = []
    boxes = _word_boxes(pdf_path)
    image = _cover_image(pdf_path, work_dir)
    scale = _DPI / 72.0

    unreadable, unbacked = [], []
    for row, col in cells:
        name = f"R{row + 1}-C{col + 1}"
        if name not in boxes:
            unreadable.append(name + "(書かれていない)")
            continue
        x0, y0, x1, y1 = boxes[name]
        crop = image.crop((int(x0 * scale), int(y0 * scale),
                            int(x1 * scale) + 1, int(y1 * scale) + 1))
        data = list(_pixels(crop))
        dark = sum(1 for r, g, b in data if r < 140 and g < 140 and b < 140)
        white = sum(1 for r, g, b in data if r > 245 and g > 245 and b > 245)
        if dark < 10:
            unreadable.append(name)
        elif white < 20:
            unbacked.append(name)

    numbers = {t: b for t, b in boxes.items() if _IS_TILE_NUMBER.match(t)}
    others = {t: b for t, b in boxes.items() if not _IS_TILE_NUMBER.match(t)}
    clashes = [f"{n}×{t}"
               for n, (a0, c0, a1, c1) in numbers.items()
               for t, (d0, e0, d1, e1) in others.items()
               if d0 < a1 and a0 < d1 and e0 < c1 and c0 < e1]
    extra = sorted(n for n in numbers
                   if (int(n[1:n.index("-")]) - 1,
                       int(n[n.index("C") + 1:]) - 1) not in set(cells))

    print(f"{label}: 印刷する面 {len(cells)}枚"
          f" / 読めない {len(unreadable)}件"
          f" / 白地なし {len(unbacked)}件"
          f" / 文字の重なり {len(clashes)}件"
          f" / 余計な番号 {len(extra)}件")
    for kind, items in (("読めない", unreadable), ("白地なし", unbacked),
                        ("重なり", clashes), ("余計な番号", extra)):
        if items:
            problems.append(f"{label}: {kind} {items[:10]}")
            print(f"    {kind}: {items[:10]}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if not (subprocess.run(["which", "pdftoppm"], capture_output=True).returncode == 0):
        print("pdftoppm が無いので刷り上がりを見られません。")
        return 0

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as work_dir:
        out_dir = os.path.join(work_dir, "out")
        pipeline = PatternForgePipeline(output_dir=out_dir)
        dress = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                    skirt_style="flare")
        bodice_only = build_garment_spec(neckline="round_neck", sleeve_style=None,
                                          skirt_style=None)

        cases = []
        result = pipeline.generate_from_selection(dress, MEAS)
        cases.append(("A4・既定", result.output_files["pdf"],
                      printed_tile_cells(result.nesting)[2]))

        result = pipeline.generate_from_selection(dress, MEAS, paper="a3")
        cases.append(("A3", result.output_files["pdf"],
                      printed_tile_cells(result.nesting, paper=A3_PAPER)[2]))

        result = pipeline.generate_from_selection(dress, MEAS, include_empty_tiles=True)
        cases.append(("白紙の面も印刷", result.output_files["pdf"],
                      printed_tile_cells(result.nesting, include_empty_tiles=True)[2]))

        result = pipeline.generate_from_selection(
            dress, MEAS, fabric_group_assignments={"skirt": "紺サテン"})
        cases.append(("生地2種・表地", result.output_files["pdf"],
                      printed_tile_cells(result.fabric_groups[0].nesting)[2]))
        cases.append(("生地2種・紺サテン", result.output_files["fabric2_pdf"],
                      printed_tile_cells(result.fabric_groups[1].nesting)[2]))

        result = pipeline.generate_from_selection(bodice_only, MEAS)
        cases.append(("身頃だけ", result.output_files["pdf"],
                      printed_tile_cells(result.nesting)[2]))

        for label, pdf_path, cells in cases:
            problems.extend(_check(label, pdf_path, cells, work_dir))

    if problems:
        print(f"\n読めない・重なっている箇所: {len(problems)}件")
        return 1
    print("\nどの組み合わせでも、貼り合わせ図の番号は全部読めます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
