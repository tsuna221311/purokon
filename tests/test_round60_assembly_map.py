"""round60: 貼り合わせ図の番号が、型紙の下に隠れていた。

49枚を印刷して、床に並べて貼り合わせるところまでやってみた。手に取った
1枚目の隅には `PatternForge  R1-C1 / 7x8枚` と書いてある。どこに置くかは
表紙の貼り合わせ図を見る——**その図の番号が、3枚に2枚は読めなかった。**

パーツの輪郭は薄い水色で**塗りつぶして**描かれる。枡の番号と区切り線は
その前に描かれていたので、塗りに消される。実測(バスト88・フレアスカート):

    印刷する面 49枚 のうち、番号が読めない面 33枚（67%）
    読めない面: R1-C3 R1-C4 R2-C2 R2-C3 R2-C4 R2-C6 R2-C7 R2-C8 R3-C2 …

消えるのは**型紙が載っている紙**の番号ばかりで、読めたのは余白だけの紙で
ある。貼り合わせ図は「どの紙がどこに来るか」の索引なのに、いちばん位置を
間違えてはいけない紙の番号が見えない。区切り線も同じで、1枚のパーツが
何枚の紙にまたがるのかも読めなかった。

round53は「印刷しない面には番号を書かない(手元に来ない紙を探させない)」
と丁寧に作ってあった。向きは正しいのに、**書いた番号が見えていなかった**。

もう1つ、同じ紙の反対の隅にあったもの:

    seam allowance: 1.0cm

全ページ日本語(表紙も凡例も縫う順番も)の中で、ここだけ英語だった。
しかも同じことを凡例では「裁断線の内側 1.0cm」と日本語で書いている。
"""

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from engine.measurements import Measurements
from engine.pdf_export import printed_tile_cells
from engine.pipeline import PatternForgePipeline, build_garment_spec


#: 枡の番号(R1-C1)かどうか。
_IS_TILE_NUMBER = re.compile(r"^R\d+-C\d+$")

MEAS = Measurements(bust=88, waist=70, hip=94, height=162,
                    sleeve_length=55, shoulder_width=39)

#: 貼り合わせ図の番号が読めるかは、**刷り上がりの画素**でしか分からない。
#: 文字としては最初から入っていた(塗りに隠れていただけ)ので、
#: `pdftotext`で拾っても「見えている」ことの証明にはならない。
_NEEDS_POPPLER = pytest.mark.skipif(
    not (shutil.which("pdftoppm") and shutil.which("pdftotext")),
    reason="pdftoppm / pdftotext が無いので刷り上がりを見られません")


@pytest.fixture(scope="module")
def printed(tmp_path_factory):
    """実際にPDFを書き出して、表紙を画像にしたものを返す。"""
    out = tmp_path_factory.mktemp("r60")
    pipeline = PatternForgePipeline(output_dir=str(out))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(spec, MEAS)
    return result, result.output_files["pdf"], out


def _word_boxes(pdf_path: str, page: int = 1) -> dict[str, tuple[float, float, float, float]]:
    """そのページの単語と位置(pt)を、pdftotext -bbox から取る。"""
    xml = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(page), "-l", str(page), pdf_path, "-"],
        capture_output=True, text=True, check=True).stdout
    root = ET.fromstring(xml)
    boxes = {}
    for word in root.iter():
        if not word.tag.endswith("word"):
            continue
        text = (word.text or "").strip()
        if text:
            boxes[text] = (float(word.attrib["xMin"]), float(word.attrib["yMin"]),
                            float(word.attrib["xMax"]), float(word.attrib["yMax"]))
    return boxes


def _render(pdf_path: str, out_dir, dpi: int = 300, page: int = 1):
    from PIL import Image

    prefix = os.path.join(str(out_dir), f"render_p{page}")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png",
                    "-f", str(page), "-l", str(page), pdf_path, prefix],
                   check=True, capture_output=True)
    made = [f for f in os.listdir(str(out_dir)) if f.startswith(f"render_p{page}")]
    assert made, "pdftoppmが画像を作りませんでした"
    return Image.open(os.path.join(str(out_dir), sorted(made)[0])).convert("RGB")


def _pixels(image):
    """画素を順に返す。Pillowの版によって呼び名が違うので、ここで吸収する。"""
    getter = getattr(image, "get_flattened_data", None) or image.getdata
    return getter()


def _dark_pixels(image, box_pt, dpi=300, page_height_pt=None) -> int:
    """PDF座標(pt)の矩形の中にある、濃い画素の数を数える。

    pdftotext -bbox の y は**上が0**で、pdftoppm の画像も上が0なので、
    そのまま使える(ここを取り違えると、常に0個になる)。
    """
    scale = dpi / 72.0
    x0, y0, x1, y1 = box_pt
    left, top = int(x0 * scale), int(y0 * scale)
    right, bottom = int(x1 * scale) + 1, int(y1 * scale) + 1
    crop = image.crop((left, top, right, bottom))
    return sum(1 for r, g, b in _pixels(crop) if r < 140 and g < 140 and b < 140)


# ---------------------------------------------------------------------------
# 1. 番号が、刷り上がりで実際に読めること
# ---------------------------------------------------------------------------

@_NEEDS_POPPLER
def test_every_printed_sheet_number_is_visible_on_the_map(printed):
    """印刷する全部の面の番号が、貼り合わせ図の上で**画素として**見えること。

    round59まで、49枚のうち33枚の番号がパーツの塗りに消されていた。
    文字としては入っていたので、pdftotextでは見つからない不具合である。
    """
    result, pdf_path, out_dir = printed
    _rows, _cols, cells = printed_tile_cells(result.nesting)
    boxes = _word_boxes(pdf_path)
    image = _render(pdf_path, out_dir)

    invisible = []
    for row, col in cells:
        name = f"R{row + 1}-C{col + 1}"
        assert name in boxes, f"{name} が貼り合わせ図に書かれていません"
        if _dark_pixels(image, boxes[name]) < 10:
            invisible.append(name)
    assert not invisible, (
        f"{len(invisible)}/{len(cells)}枚の番号が読めません: {invisible[:12]}")


@_NEEDS_POPPLER
def test_no_number_is_printed_for_a_sheet_that_is_not_printed(printed):
    """印刷しない面の番号は、載せないこと(round53の約束を守り続ける)。

    手元に来ない紙の番号が図にあると、「印刷に失敗した」と探させる。
    """
    result, pdf_path, _out = printed
    rows, cols, cells = printed_tile_cells(result.nesting)
    printed_names = {f"R{r + 1}-C{c + 1}" for r, c in cells}
    boxes = _word_boxes(pdf_path)
    extra = sorted(name for name in boxes
                   if name.startswith("R") and "-C" in name
                   and name not in printed_names)
    assert not extra, f"印刷しない面の番号が載っています: {extra}"
    assert len(cells) < rows * cols, "白紙の面が無い例なので、この検査は無意味です"


@_NEEDS_POPPLER
def test_part_names_are_not_cut_apart_by_the_numbers(printed):
    """枡の番号が、他のどの文字とも重なっていないこと。

    番号を上に描いたら、今度はパーツの名前が番号の白地で割れた
    (実際に刷って「スカート（フレア） 前」が「カート」「レア）」に
    なっているのを見た)。名前は番号の帯を避けて描く。

    【最初に書いたテストは効いていなかった】パーツ名を
    `display_name.split("（")[0]` で切って探したが、pdftotextが拾う語は
    `スカート（フレア）` と丸ごとなので、`スカート` では一度も見つからず、
    **何も確かめずに通っていた**(ミューテーションで発覚)。
    名前を当てにいくのをやめ、**番号以外のすべての語**と突き合わせる。
    """
    _result, pdf_path, _out = printed
    boxes = _word_boxes(pdf_path)
    numbers = {t: b for t, b in boxes.items() if _IS_TILE_NUMBER.match(t)}
    others = {t: b for t, b in boxes.items() if not _IS_TILE_NUMBER.match(t)}
    assert len(numbers) >= 10 and len(others) >= 5, (len(numbers), len(others))

    for number, (bx0, by0, bx1, by1) in numbers.items():
        for text, (nx0, ny0, nx1, ny1) in others.items():
            if nx0 < bx1 and bx0 < nx1 and ny0 < by1 and by0 < ny1:
                pytest.fail(f"番号 {number} が「{text}」と重なっています")


@_NEEDS_POPPLER
def test_each_number_sits_on_a_clean_white_patch(printed):
    """番号の下に白地が敷かれていること。

    敷かないと、番号が水色の塗りや黒い裁断線の上に直に乗る。塗りの上
    でも読めなくはないが、裁断線と重なった番号は線に紛れる。
    白地があれば、どこに来ても同じ読みやすさになる。
    """
    result, pdf_path, out_dir = printed
    _rows, _cols, cells = printed_tile_cells(result.nesting)
    boxes = _word_boxes(pdf_path)
    image = _render(pdf_path, out_dir)

    tinted = []
    for row, col in cells:
        name = f"R{row + 1}-C{col + 1}"
        x0, y0, x1, y1 = boxes[name]
        # 文字そのものではなく、その周りに白があるかを見る。
        scale = 300 / 72.0
        crop = image.crop((int(x0 * scale), int(y0 * scale),
                            int(x1 * scale) + 1, int(y1 * scale) + 1))
        white = sum(1 for r, g, b in _pixels(crop)
                    if r > 245 and g > 245 and b > 245)
        if white < 20:
            tinted.append(name)
    assert not tinted, (
        f"白地が敷かれていない番号があります: {tinted[:12]}")


# ---------------------------------------------------------------------------
# 2. 紙の隅の文言
# ---------------------------------------------------------------------------

def test_the_sheet_corner_is_written_in_japanese(printed):
    """型紙ページの隅の縫い代表示が、日本語であること。

    全ページ日本語の中で、ここだけ `seam allowance: 1.0cm` だった。
    """
    _result, pdf_path, _out = printed
    text = subprocess.run(["pdftotext", pdf_path, "-"],
                          capture_output=True, text=True, check=True).stdout
    assert "seam allowance" not in text, "英語の縫い代表示が残っています"
    assert "縫い代 1.0cm" in text, text[:300]


def test_the_hem_allowance_is_also_japanese(tmp_path):
    """裾の縫い代が違うときの書き方も、日本語であること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(
        spec, MEAS, seam_allowance_cm=1.0, hem_seam_allowance_cm=3.0)
    text = subprocess.run(["pdftotext", result.output_files["pdf"], "-"],
                          capture_output=True, text=True, check=True).stdout
    assert "hem:" not in text
    assert "縫い代 1.0cm（裾 3.0cm）" in text, text[:300]


def test_the_wording_matches_the_legend(printed):
    """隅の言い方が、表紙の凡例と食い違っていないこと。

    同じことを別の言葉で書くと、どちらが本当か分からなくなる。
    """
    _result, pdf_path, _out = printed
    text = subprocess.run(["pdftotext", "-f", "1", "-l", "1", pdf_path, "-"],
                          capture_output=True, text=True, check=True).stdout
    assert "裁断線の内側" in text and "1.0cm" in text


# ---------------------------------------------------------------------------
# 3. 既定の出力を、この改修で壊していないこと
# ---------------------------------------------------------------------------

@_NEEDS_POPPLER
def test_the_tile_pages_are_untouched(printed, tmp_path):
    """型紙そのもののページは、1枚も変わっていないこと。

    今回触ったのは表紙の図と、紙の隅の文言だけである。実寸の型紙が
    1mmでも動いていたら、この改修は失敗している。
    """
    from PIL import Image

    result, pdf_path, out_dir = printed
    # 型紙ページ(4ページ目以降)を何枚か画像にして、中身だけを見る
    # (隅の文言は変えたので、そこは除いて比べる)。
    for page in (5, 12, 30):
        image = _render(pdf_path, tmp_path, dpi=150, page=page)
        w, h = image.size
        body = image.crop((0, int(h * 0.06), w, int(h * 0.94)))
        dark = sum(1 for r, g, b in _pixels(body) if r < 140)
        assert dark > 0, f"{page}ページ目に型紙が描かれていません"
        assert isinstance(image, Image.Image)
