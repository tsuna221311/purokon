"""round62: 投影用の紙は、格子が何cmかを左上隅でしか言っていなかった。

プロジェクターで布に直接投影して裁つ人になって、投影用PDFを開いた。
やることは決まっている——像を布に映し、定規を当てて、**格子が10cmに
なるまで**ズームを合わせ、それから裁つ。

その「格子が10cm」と書いてあるのは、紙の中で1か所だけだった。実測:

    ページの大きさ        145.0 × 186.6 cm （ワンピース1着・実寸）
    較正の指示の位置      左上隅 (2.7, 1.2) cm
    その文字の高さ        4.6 mm
    紙の中で他に、格子の大きさを書いてある場所   0か所

プロジェクターは布の一部(記事の想定で60〜90cm四方)を映して、少しずつ
ずらしながら使う。**左上から始めなかった人は、その一文を一度も見ない。**
格子が何cmか分からなければ較正できないし、よくある5cm方眼だと思い込めば
**倍の大きさで裁つ**ことになる。

格子と一緒に「1マス10cm」の目盛りを40cmおきに置いた。間隔40cmの格子点は
幅40cm以上のどの区間にも1つ以上あるので、記事の想定する投影範囲なら
どこを映しても必ず目に入る。
"""

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from engine.measurements import Measurements
from engine.pdf_export import (PROJECTOR_GRID_CM, PROJECTOR_PADDING_CM,
                                PROJECTOR_SCALE_LABEL_EVERY_CM,
                                PROJECTOR_SCALE_LABEL_RGB)
from engine.pipeline import PatternForgePipeline, build_garment_spec


CM_PER_PT = 1 / 28.3465

MEAS = Measurements(bust=88, waist=70, hip=94, height=162,
                    sleeve_length=55, shoulder_width=39)

#: 出典(Craftstorming)が想定する投影範囲の下限。これより狭い窓は想定しない。
PROJECTION_WINDOW_CM = 60.0

_NEEDS_POPPLER = pytest.mark.skipif(
    not (shutil.which("pdftoppm") and shutil.which("pdftotext")),
    reason="pdftotext / pdftoppm が無いので刷り上がりを見られません")


@pytest.fixture(scope="module")
def projected(tmp_path_factory):
    out = tmp_path_factory.mktemp("r62")
    pipeline = PatternForgePipeline(output_dir=str(out))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(spec, MEAS)
    return result, result.output_files["projector"], out


def _words(pdf_path: str):
    """(文字列, x0, y0, x1, y1) をcmで返す。左上が原点。"""
    xml = subprocess.run(["pdftotext", "-bbox", pdf_path, "-"],
                          capture_output=True, text=True, check=True).stdout
    root = ET.fromstring(xml)
    out = []
    for word in root.iter():
        if not word.tag.endswith("word"):
            continue
        text = (word.text or "").strip()
        if not text:
            continue
        a = word.attrib
        out.append((text,
                    float(a["xMin"]) * CM_PER_PT, float(a["yMin"]) * CM_PER_PT,
                    float(a["xMax"]) * CM_PER_PT, float(a["yMax"]) * CM_PER_PT))
    return out


def _page_size_cm(pdf_path: str) -> tuple[float, float]:
    info = subprocess.run(["pdfinfo", pdf_path], capture_output=True,
                          text=True, check=True).stdout
    match = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
    return float(match.group(1)) * CM_PER_PT, float(match.group(2)) * CM_PER_PT


def _scale_labels(pdf_path: str):
    wanted = f"1マス{PROJECTOR_GRID_CM:.0f}cm"
    return [w for w in _words(pdf_path) if w[0] == wanted]


# ---------------------------------------------------------------------------
# 1. どこを映しても、格子の大きさが読めること
# ---------------------------------------------------------------------------

@_NEEDS_POPPLER
def test_every_projection_window_contains_the_scale(projected):
    """紙のどこに60cm四方の窓を置いても、目盛りが1つ以上入ること。

    round61まで、較正の指示は左上隅に1つあるだけだった。この検査を
    そのときの紙に当てると、**ほとんどの窓で0件**になる。
    """
    _result, pdf_path, _out = projected
    page_w, page_h = _page_size_cm(pdf_path)
    labels = _scale_labels(pdf_path)
    assert labels, "「1マス○cm」が1つも見つかりません"

    empty = []
    step = 10.0     # 10cmずつ窓をずらして、全面を舐める
    y = 0.0
    while y + PROJECTION_WINDOW_CM <= page_h + 1e-6:
        x = 0.0
        while x + PROJECTION_WINDOW_CM <= page_w + 1e-6:
            inside = [l for l in labels
                      if x <= l[1] and l[3] <= x + PROJECTION_WINDOW_CM
                      and y <= l[2] and l[4] <= y + PROJECTION_WINDOW_CM]
            if not inside:
                empty.append((round(x), round(y)))
            x += step
        y += step
    assert not empty, (
        f"格子の大きさが読めない窓が{len(empty)}か所あります"
        f"（左上の座標の例: {empty[:5]}）")


@_NEEDS_POPPLER
def test_the_spacing_is_smaller_than_a_projection_window(projected):
    """目盛りの間隔が、想定する投影範囲より狭いこと。

    間隔Sの格子点は、幅S以上のどの区間にも必ず1つ入る。ここが逆転すると、
    上の検査は「たまたま入っている」だけになる。
    """
    assert PROJECTOR_SCALE_LABEL_EVERY_CM <= PROJECTION_WINDOW_CM, (
        f"目盛りの間隔{PROJECTOR_SCALE_LABEL_EVERY_CM}cmが、"
        f"投影範囲{PROJECTION_WINDOW_CM}cmより広くなっています")


@_NEEDS_POPPLER
def test_the_labels_are_spread_over_the_whole_sheet(projected):
    """目盛りが紙の全体に散っていること(隅に固まっていないこと)。"""
    _result, pdf_path, _out = projected
    page_w, page_h = _page_size_cm(pdf_path)
    labels = _scale_labels(pdf_path)
    assert max(l[3] for l in labels) > page_w * 0.6, "右側に目盛りがありません"
    assert max(l[4] for l in labels) > page_h * 0.6, "下側に目盛りがありません"
    assert len(labels) >= 6, f"目盛りが{len(labels)}個しかありません"


@_NEEDS_POPPLER
def test_the_scale_text_says_the_same_number_as_the_grid(projected):
    """目盛りの数字が、実際に引いてある格子の間隔と同じであること。

    ここが食い違うと、**倍の大きさで裁つ**ことになる。
    """
    _result, pdf_path, _out = projected
    texts = {w[0] for w in _words(pdf_path)}
    assert f"1マス{PROJECTOR_GRID_CM:.0f}cm" in texts
    header = [t for t in texts if t.startswith("投影したら")]
    assert header, texts
    assert f"{PROJECTOR_GRID_CM:.0f}cm" in header[0], header


def test_the_numbers_are_not_hand_written():
    """目盛りの文言が、定数から組み立てられていること(round61の続き)。"""
    import ast

    with open("engine/pdf_export.py", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    joined = [node for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)]
    built = [node for node in joined
             if any(isinstance(v, ast.FormattedValue)
                    and isinstance(v.value, ast.Name)
                    and v.value.id == "PROJECTOR_GRID_CM"
                    for v in node.values)]
    assert len(built) >= 2, (
        "格子の大きさを述べる文が、定数から組み立てられていません"
        f"（見つかったのは{len(built)}か所）")


# ---------------------------------------------------------------------------
# 2. 目盛りが、裁つのを邪魔しないこと
# ---------------------------------------------------------------------------

@_NEEDS_POPPLER
def test_the_scale_labels_do_not_overlap_the_part_names(projected):
    """目盛りが、パーツの名前と重なっていないこと。"""
    _result, pdf_path, _out = projected
    wanted = f"1マス{PROJECTOR_GRID_CM:.0f}cm"
    labels = [w for w in _words(pdf_path) if w[0] == wanted]
    others = [w for w in _words(pdf_path) if w[0] != wanted]
    for _t, ax0, ay0, ax1, ay1 in labels:
        for text, bx0, by0, bx1, by1 in others:
            if bx0 < ax1 and ax0 < bx1 and by0 < ay1 and ay0 < by1:
                pytest.fail(f"目盛りが「{text}」と重なっています")


def test_the_label_colour_is_readable_but_quiet():
    """目盛りの色が、読める濃さで、かつ裁断線ほど目立たないこと。

    布の色は選べないので、白地に対して4.5:1を下回らない濃さにしておく。
    """
    def _luminance(rgb):
        def channel(v):
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = rgb
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    contrast = (_luminance((1, 1, 1)) + 0.05) / (_luminance(PROJECTOR_SCALE_LABEL_RGB) + 0.05)
    assert contrast >= 4.5, f"白地に対して{contrast:.2f}:1しかありません"
    assert contrast <= 7.0, (
        f"白地に対して{contrast:.2f}:1。濃すぎて裁断線と競ります")


# ---------------------------------------------------------------------------
# 3. A4分割PDFを、この改修で動かしていないこと
# ---------------------------------------------------------------------------

@_NEEDS_POPPLER
def test_the_a4_pdf_is_untouched(projected, tmp_path):
    """触ったのは投影用だけで、印刷用の紙は1ページも変わっていないこと。

    改修のたびに実寸の型紙が動いていないかを確かめるのは、この製品で
    いちばん大事な確認である。全ページを画像にして突き合わせる。
    """
    import hashlib

    result, _projector, _out = projected
    prefix = os.path.join(str(tmp_path), "a4")
    subprocess.run(["pdftoppm", "-r", "60", "-png",
                    result.output_files["pdf"], prefix],
                   check=True, capture_output=True)
    made = sorted(f for f in os.listdir(str(tmp_path)) if f.startswith("a4"))
    assert len(made) > 10, f"{len(made)}ページしか画像になっていません"
    digest = hashlib.sha256()
    for name in made:
        with open(os.path.join(str(tmp_path), name), "rb") as handle:
            digest.update(handle.read())
    # round62の改修前に同じ条件で測った値を、round71で更新した。
    #
    # **この値を書き換えてよいのは、型紙そのものを直したときだけである。**
    # round71は胸ぐせダーツの2本の脚を揃えた——たたんでも平らにならない
    # 型紙を直した回なので、実寸の型紙は当然変わる。round63〜70では
    # この値は1度も動いていない(画面と書類だけを触っていたため)。
    #
    #   round62〜70  91241d68a10c323cf259c0a2...
    #   round71〜    c060598abf2a153e498d6179...
    assert digest.hexdigest().startswith("c060598abf2a153e498d6179"), (
        "A4分割PDFが変わっています。型紙そのものを直したのでなければ、"
        "どこかで実寸が動いています")


@_NEEDS_POPPLER
def test_the_scale_labels_are_only_on_the_projector_sheet(projected):
    """目盛りが、印刷用の紙には出ていないこと。

    A4は1枚ずつが定規で測れる大きさなので、この目盛りは要らない
    (round33の「印刷倍率の確認」の四角がその役目をしている)。
    """
    result, _projector, _out = projected
    text = subprocess.run(["pdftotext", result.output_files["pdf"], "-"],
                          capture_output=True, text=True, check=True).stdout
    assert f"1マス{PROJECTOR_GRID_CM:.0f}cm" not in text
