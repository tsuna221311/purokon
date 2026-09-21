#!/usr/bin/env python3
"""出力が変わっていないことを確かめるための、ハッシュの控え(round63で追加)。

【何のためにあるか】コードの整理は「読みやすくするだけで、動きは変えない」
のが約束である。約束を守れたかどうかは、**出したものを突き合わせる**しか
確かめようがない。整理する前にこれを走らせて控えを取り、整理したあとに
もう一度走らせて、同じ値になるかを見る。

PDFはそのままだと中に生成日時とジョブIDが入るので、バイト列では比べられ
ない。**全ページを画像にして**その画素を突き合わせる(見た目が同じなら
同じ、という比べ方)。SVGはジョブIDだけ伏せて文字で、DXFは図形(線の位置)だけを比べる。

使い方:

    python3 scripts/snapshot_outputs.py > /tmp/before.txt   # 整理する前
    ...コードを整理する...
    python3 scripts/snapshot_outputs.py > /tmp/after.txt    # 整理したあと
    diff /tmp/before.txt /tmp/after.txt && echo "出力は変わっていません"
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec

#: 比べる型紙の組み合わせ。よく使う形と、機能を入れた形を混ぜてある。
STANDARD = Measurements(bust=88, waist=70, hip=94, height=162,
                         sleeve_length=55, shoulder_width=39)
LARGE = Measurements(bust=104, waist=92, hip=112, height=176,
                      sleeve_length=60, shoulder_width=43)


def _dress():
    return build_garment_spec(neckline="round_neck", sleeve_style="straight",
                               skirt_style="flare")


CASES = [
    ("既定のワンピース", _dress, STANDARD, {}),
    ("大きいサイズ", _dress, LARGE, {}),
    ("裏地あり", _dress, STANDARD, {"lining": True}),
    ("生地2種", _dress, STANDARD, {"fabric_group_assignments": {"skirt": "紺サテン"}}),
    ("A3", _dress, STANDARD, {"paper": "a3"}),
    ("丈の指定", _dress, STANDARD, {"design_length_overrides": {"skirt": 45.0}}),
    ("補正あり", _dress, STANDARD, {"alterations": {"bust_width": 4.0}}),
    ("プリンセスライン",
     lambda: build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                 skirt_style="flare", princess_line=True),
     STANDARD, {}),
    ("身頃だけ",
     lambda: build_garment_spec(neckline="round_neck", sleeve_style=None,
                                 skirt_style=None),
     STANDARD, {}),
    # round67で追加。**前開きファスナーの型紙が1つも無かった**ので、
    # 前開きのパネルだけ形が変わっても、この道具は「変わっていない」と
    # 言い続ける。実際round67でパネルにウエストダーツを足したとき、
    # 9通りすべてが1ビットも変わらなかった——正しいが、見張れてもいない。
    ("前開きファスナー",
     lambda: build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                 skirt_style="flare", front_zip=True),
     STANDARD, {}),
]

#: 生成のたびに変わる値。比べる前に伏せ字にする。
#:
#: DXFはezdxfが書き出すときに**毎回ちがうGUIDと書き出し時刻**を入れる。
#: 実際に2回続けて生成して差分を取ると、7,900行のうち違うのはこの8行だけ
#: だった。型紙の中身とは関係がないので伏せる(伏せないと、何も直して
#: いないのに毎回「変わった」と出る)。
_VOLATILE = [
    (re.compile(r"\b[0-9a-f]{12}\b"), "<ジョブID>"),
    (re.compile(r"\b20\d\d-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:\.\d+)?"
                r"(?:\+\d\d:\d\d)?"), "<日時>"),
    (re.compile(r"\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-"
                r"[0-9A-F]{4}-[0-9A-F]{12}\}"), "<GUID>"),
    # round68: SVGには埋め込みフォントがbase64で入っている。
    # **漢字を1文字足してフォントを作り直すだけで、10通り全部の
    # SVGのハッシュが変わる。** 実際round68でそうなり、図は1つも
    # 変わっていないのに全件「変わった」と出た(伏せ字にして
    # 突き合わせ、違うのはフォントの部分だけだと確かめてある)。
    # 毎回変わる値ではないが、**1か所の変更が全件に散る**のは
    # 同じ害なので、ここで伏せて下の「埋め込みフォント」の行に
    # 1回だけ出す。
    (re.compile(r"base64,[A-Za-z0-9+/=]+"), "base64,<埋め込みフォント>"),
]


def _mask(text: str) -> str:
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    return text


def _pdf_pixels_digest(pdf_path: str, work_dir: str, dpi: int = 60) -> str:
    """PDFの全ページを画像にして、その中身をまとめたハッシュを返す。

    PDFのバイト列には生成日時とジョブIDが入るので、そのままでは毎回
    変わってしまう。画像にすれば「刷り上がりが同じか」だけを見られる。
    """
    prefix = os.path.join(work_dir, "page")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", pdf_path, prefix],
                   check=True, capture_output=True)
    made = sorted(f for f in os.listdir(work_dir) if f.startswith("page"))
    digest = hashlib.sha256()
    for name in made:
        path = os.path.join(work_dir, name)
        with open(path, "rb") as handle:
            digest.update(handle.read())
        os.remove(path)
    return f"{len(made)}ページ {digest.hexdigest()[:16]}"


def _text_digest(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        masked = _mask(handle.read())
    return hashlib.sha256(masked.encode("utf-8")).hexdigest()[:16]


def _dxf_geometry_digest(path: str) -> str:
    """DXFは**線の位置**だけを突き合わせる。

    【なぜ文字として比べないか】DXFのファイルには、型紙とは関係のない
    ものが毎回ちがう形で入る。実際に2回生成して差分を取ると:

        GUID 2か所 / 書き出し時刻 2か所 / ユリウス日 2か所
        辞書の中の並び順 (LAYOUT と ACDBPLACEHOLDER が入れ替わる)

    並び順は伏せ字にできない。DXFを使う人が見るのは線の位置なので、
    図形だけを取り出して比べる。
    """
    import ezdxf

    doc = ezdxf.readfile(path)
    rows: list[str] = []
    for entity in doc.modelspace():
        kind = entity.dxftype()
        layer = entity.dxf.layer
        if kind == "LWPOLYLINE":
            points = [(round(x, 4), round(y, 4)) for x, y, *_ in entity.get_points()]
        elif kind == "LINE":
            points = [(round(entity.dxf.start.x, 4), round(entity.dxf.start.y, 4)),
                      (round(entity.dxf.end.x, 4), round(entity.dxf.end.y, 4))]
        elif kind == "TEXT":
            points = [(round(entity.dxf.insert.x, 4), round(entity.dxf.insert.y, 4)),
                      entity.dxf.text]
        else:
            points = [repr(sorted(entity.dxfattribs().items(), key=str))]
        rows.append(f"{kind}|{layer}|{points}")
    rows.sort()
    digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    return f"{len(rows)}本 {digest[:16]}"


def main() -> int:
    if subprocess.run(["which", "pdftoppm"], capture_output=True).returncode != 0:
        print("pdftoppm が無いので比べられません。")
        return 1

    # round68: 埋め込みフォントは1回だけ出す。各SVGの中では伏せてあるので、
    # フォントを作り直したときに変わるのはこの1行だけになる
    # (以前は10通り全部のSVGのハッシュが一斉に変わった)。
    font_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "assets",
        "pattern_label_ja_subset.ttf")
    with open(font_path, "rb") as handle:
        font_digest = hashlib.sha256(handle.read()).hexdigest()[:16]
    print(f"埋め込みフォント: {font_digest}\n")

    with tempfile.TemporaryDirectory() as work:
        out_dir = os.path.join(work, "out")
        pipeline = PatternForgePipeline(output_dir=out_dir)
        for label, make_spec, measurements, kwargs in CASES:
            result = pipeline.generate_from_selection(
                make_spec(), measurements, **kwargs)
            print(f"[{label}]")
            # 数えられるものは数字でも出す。ハッシュが違ったとき、
            # どこが動いたのかの手がかりになる。
            summary = result.summary()
            print(f"  パーツ数 {summary['part_count']}"
                  f" / 生地幅 {summary['fabric_width_cm']}cm"
                  f" / 使用長 {summary['used_length_cm']}cm"
                  f" / 印刷 {result.pdf_sheet_count()}枚")
            for fmt in sorted(result.output_files):
                path = result.output_files[fmt]
                if path.endswith(".pdf"):
                    print(f"  {fmt}: {_pdf_pixels_digest(path, work)}")
                elif path.endswith(".dxf"):
                    print(f"  {fmt}: {_dxf_geometry_digest(path)}")
                else:
                    print(f"  {fmt}: {_text_digest(path)}")
            steps = " / ".join(s.title for s in result.assembly_steps())
            print(f"  縫う順番: {steps}")
            notes = " ".join(result.design_notes) + " ".join(
                result.shopping_list.notes)
            print(f"  文章: {hashlib.sha256(_mask(notes).encode()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
