#!/usr/bin/env python3
"""round62: 投影用の紙の「どこを映しても格子の大きさが読めるか」を測る。

【なぜこの検査を足したか】投影用PDFは実寸1枚もので、ワンピース1着でも
145 × 187cm になる。プロジェクターは布の一部(60〜90cm四方)を映して
ずらしながら使うので、格子の大きさを紙の隅に1度書いただけでは、
**そこを映さなかった人には届かない**。紙の大きさはパーツ構成で変わる
ので、1つの組み合わせを見ても足りない。

pytest(tests/test_round62_projector_scale.py)は1つの組み合わせだけを
見る。ここではパーツ構成・採寸・生地の分け方を変えて、紙の大きさが
変わっても成り立つかをまとめて測る。

使い方:

    python3 scripts/audit_projector_scale.py

読めない窓があれば終了コード1で、その位置を並べる。
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.measurements import Measurements
from engine.pdf_export import PROJECTOR_GRID_CM
from engine.pipeline import PatternForgePipeline, build_garment_spec

CM_PER_PT = 1 / 28.3465

#: 投影範囲。出典(Craftstorming)の想定は60〜90cm四方なので、狭い方で測る。
WINDOW_CM = 60.0
#: 窓をずらす刻み。細かくするほど厳しくなる。
STEP_CM = 10.0


def _words(pdf_path: str):
    xml = subprocess.run(["pdftotext", "-bbox", pdf_path, "-"],
                          capture_output=True, text=True, check=True).stdout
    for word in ET.fromstring(xml).iter():
        if not word.tag.endswith("word"):
            continue
        text = (word.text or "").strip()
        if not text:
            continue
        a = word.attrib
        yield (text,
               float(a["xMin"]) * CM_PER_PT, float(a["yMin"]) * CM_PER_PT,
               float(a["xMax"]) * CM_PER_PT, float(a["yMax"]) * CM_PER_PT)


def _page_size_cm(pdf_path: str) -> tuple[float, float]:
    info = subprocess.run(["pdfinfo", pdf_path], capture_output=True,
                          text=True, check=True).stdout
    match = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
    return float(match.group(1)) * CM_PER_PT, float(match.group(2)) * CM_PER_PT


def _check(label: str, pdf_path: str) -> list[str]:
    wanted = f"1マス{PROJECTOR_GRID_CM:.0f}cm"
    words = list(_words(pdf_path))
    marks = [w for w in words if w[0] == wanted]
    others = [w for w in words if w[0] != wanted]
    page_w, page_h = _page_size_cm(pdf_path)

    empty = []
    y = 0.0
    while y + WINDOW_CM <= page_h + 1e-6:
        x = 0.0
        while x + WINDOW_CM <= page_w + 1e-6:
            if not any(x <= m[1] and m[3] <= x + WINDOW_CM
                        and y <= m[2] and m[4] <= y + WINDOW_CM for m in marks):
                empty.append((round(x), round(y)))
            x += STEP_CM
        y += STEP_CM

    clashes = [f"{m[0]}×{o[0]}" for m in marks for o in others
               if o[1] < m[3] and m[1] < o[3] and o[2] < m[4] and m[2] < o[4]]

    print(f"{label}: 紙 {page_w:.0f}×{page_h:.0f}cm"
          f" / 目盛り {len(marks)}個"
          f" / 読めない窓 {len(empty)}か所"
          f" / 文字の重なり {len(clashes)}件")
    problems = []
    if not marks:
        problems.append(f"{label}: 目盛りが1つもありません")
        print("    目盛りが1つもありません")
    if empty:
        problems.append(f"{label}: 読めない窓 {empty[:6]}")
        print(f"    読めない窓の左上: {empty[:6]}")
    if clashes:
        problems.append(f"{label}: 重なり {clashes[:5]}")
        print(f"    重なり: {clashes[:5]}")
    return problems


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if subprocess.run(["which", "pdftotext"], capture_output=True).returncode != 0:
        print("pdftotext が無いので測れません。")
        return 0

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as work:
        pipeline = PatternForgePipeline(output_dir=os.path.join(work, "out"))
        standard = Measurements(bust=88, waist=70, hip=94, height=162,
                                 sleeve_length=55, shoulder_width=39)
        small = Measurements(bust=76, waist=60, hip=84, height=150,
                              sleeve_length=50, shoulder_width=35)
        large = Measurements(bust=104, waist=92, hip=112, height=176,
                              sleeve_length=60, shoulder_width=43)

        cases = [
            ("ワンピース", build_garment_spec(neckline="round_neck",
                                              sleeve_style="straight",
                                              skirt_style="flare"), standard, {}),
            ("身頃だけ", build_garment_spec(neckline="round_neck",
                                            sleeve_style=None,
                                            skirt_style=None), standard, {}),
            ("小さいサイズ", build_garment_spec(neckline="round_neck",
                                                sleeve_style="straight",
                                                skirt_style="flare"), small, {}),
            ("大きいサイズ", build_garment_spec(neckline="round_neck",
                                                sleeve_style="straight",
                                                skirt_style="flare"), large, {}),
            ("パンツつき", build_garment_spec(neckline="round_neck",
                                              sleeve_style="straight",
                                              include_pants=True,
                                              pants_style="tapered"), standard, {}),
        ]
        for label, spec, meas, kwargs in cases:
            result = pipeline.generate_from_selection(spec, meas, **kwargs)
            problems.extend(_check(label, result.output_files["projector"], ))

        # 生地を分けたときは、生地ごとに投影用の紙が出る。
        result = pipeline.generate_from_selection(
            build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                skirt_style="flare"),
            standard, fabric_group_assignments={"skirt": "紺サテン"})
        problems.extend(_check("生地2種・表地", result.output_files["projector"]))
        problems.extend(_check("生地2種・紺サテン",
                                result.output_files["fabric2_projector"]))

    if problems:
        print(f"\n格子の大きさが読めない箇所: {len(problems)}件")
        return 1
    print("\nどの紙でも、60cm四方をどこに置いても格子の大きさが読めます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
