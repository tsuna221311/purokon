"""round46: 実際に最初から最後まで操作して見つけた不具合。

round45までは「失敗させたとき」までは見たが、**うまくいったときの
使い心地**をブラウザで通しては見ていなかった。round46は利用者と同じ順で
——開く・採寸値を入れる・デザインを選ぶ・生成する・結果を読む・
ダウンロードしたPDFを開く——を実際にやり、画面と紙を目で見た。

見つかったもの:

  1. **スマホで生成すると、画面が結果から離れていく。**
     390px幅でボタン(y=3681)まで下げて押すと、1.5秒後には scrollY=117——
     **ほぼ最上部**まで戻され、出来上がった結果は4190px下で見えない。
     押したのに何も起きていないように見える、いちばん困る形だった。
  2. **複数サイズの読み上げが「右のパネル」と言う。** 1段組のスマホに
     右のパネルは無い。結果はフォームの下に出る。
  3. **裏地の注記の計算が合わない。** 「表地の1.0cmから2cm減らしています」
     ——1.0から2.0は引けない。既定の縫い代は全辺1.0cmなので、
     **何も指定しなければ必ずこの文が出ていた**。
  4. **PDFのパーツ名が裁断線を越える。** round11は「外接矩形の幅」に
     収めていたが、文字は**パーツの中央の高さ**に描かれる。袖や身頃は
     その高さの実幅が外接矩形より狭い。実測で最大2.5pt(≒0.9mm)出ていた。
"""

import pathlib
import re

import pytest

import app as app_module
from engine import pdf_export
from engine.lining import LINING_HEM_REDUCTION_CM, lining_hem_allowance_cm, lining_notes

APP_JS = (pathlib.Path(app_module.BASE_DIR) / "web" / "static" / "app.js").read_text(encoding="utf-8")


class _Part:
    def __init__(self, part_type="front_bodice"):
        self.part_type = part_type


# --- 1. 生成したあと、結果が見える位置に来ること --------------------------

def test_the_scroll_target_depends_on_whether_the_panel_is_stuck():
    """結果まで画面を動かす先が、2段組と1段組で切り替わること。

    round34は「貼り付いた(sticky)パネルには scrollIntoView が効かない」
    ため、親(.layout)を基準にした。**これは2段組のときだけ正しい**。
    1段組では .layout の先頭は結果ではなく**フォームの先頭**なので、
    押すと画面が結果から遠ざかっていた。
    """
    block = APP_JS.split("function scrollResultIntoView(")[1].split("\n}\n")[0]
    assert 'position === "sticky"' in block, \
        "貼り付いているかどうかを見ずに親へ寄せる書き方に戻っています"
    assert "parentElement" in block and "resultPanel" in block
    # 貼り付いていないときは、親ではなくパネル自身を基準にすること。
    assert re.search(r"sticky\s*&&\s*resultPanel\.parentElement\s*\)\s*\|\|\s*resultPanel", block), \
        "1段組でパネル自身へ寄せる書き方になっていません"


def test_the_view_is_re_anchored_after_the_result_is_filled_in():
    """結果を差し込んだ**後**にも、位置を取り直すこと。

    押してから返るまでの間にフォームの高さが変わる(採寸の指摘が後から
    出る等)ので、押した瞬間に測った位置はずれている。実測でも、
    結果の先頭が画面の542px下に来ていた。
    """
    # 単サイズの経路。
    tail = APP_JS.split("content.classList.remove(\"hidden\")")[1][:500]
    assert "scrollResultIntoView()" in tail, \
        "単サイズの結果を入れた後に、位置を取り直していません"
    # 複数サイズの経路。こちらも1段組では同じことが起きる。
    multi = APP_JS.split("multiSizeContent.classList.remove(\"hidden\")")[1][:500]
    assert "scrollResultIntoView()" in multi, \
        "複数サイズの結果を入れた後に、位置を取り直していません"
    # 押した瞬間だけの呼び出しに戻っていないこと(定義行を数えない)。
    call_sites = len(re.findall(r"^\s*scrollResultIntoView\(\);", APP_JS, re.M))
    assert call_sites >= 3, f"呼び出し箇所が{call_sites}か所しかありません"


def test_the_multi_size_announcement_does_not_assume_two_columns():
    """複数サイズの読み上げが、画面の作りに依らない言い方であること。"""
    idx = APP_JS.find("サイズ分の型紙ができました")
    tail = APP_JS[idx:idx + 260]
    assert "右のパネル" not in tail, \
        "1段組(スマホ)には無い「右のパネル」を案内しています"
    assert "生成結果" in tail


# --- 2. 裏地の注記が、実際にした計算と合っていること ----------------------

@pytest.mark.parametrize("outer, expected_lining", [
    (4.0, 2.0), (3.0, 1.0), (2.0, 0.0),      # 出典の実例
    (1.0, 0.0), (0.0, 0.0),                   # 引き切れない側
])
def test_the_lining_hem_note_states_the_reduction_actually_made(outer, expected_lining):
    """「何cm減らしたか」が、実際に減った量であること。

    `lining_hem_allowance_cm` は負の縫い代を作らないよう0で止める。
    表地の裾が2cm未満だと減った量は2cmではないのに、注記は「2cm減らして
    います」と決め打ちで書いていた。**既定の縫い代は1.0cmなので、
    何も指定しなければ必ずこの矛盾した文が出ていた。**
    """
    assert lining_hem_allowance_cm(outer) == pytest.approx(expected_lining)
    note = lining_notes([_Part()], outer)[0]
    removed = outer - expected_lining
    assert f"から{removed:.1f}cm減らしています" in note, note
    if removed < LINING_HEM_REDUCTION_CM:
        assert "から2.0cm減らしています" not in note


def test_the_clamped_case_says_so_plainly():
    """規則どおり引けなかったときは、そのことをはっきり書くこと。

    「0.0cm」とだけ書かれても、出来上がり線で裁つという意味だとは
    読み取れないし、2cm引けなかったことも分からない。
    """
    note_text = " ".join(lining_notes([_Part()], 1.0))
    assert "規則どおりの2cmは引けず" in note_text
    assert "出来上がり線で裁つ" in note_text
    # 直し方まで書く。
    assert "縫い代" in note_text and "3〜4cm" in note_text
    # 2cm以上あるときは、この断り書きを出さない(毎回出ると読み飛ばされる)。
    assert "規則どおりの2cmは引けず" not in " ".join(lining_notes([_Part()], 3.0))


def test_the_lining_note_does_not_hard_code_a_section_number():
    """注記が「⑧」のような見出し番号を名指ししないこと。

    round41で手順番号はDOMの順に振り直すようにした。入力モードによって
    番号が動くので、文章に焼き付けると指す先がずれる(複数サイズモードでは
    縫い代は⑦になる)。PDFに刷られる文でもあり、紙には番号が無い。
    """
    for outer in (0.5, 1.0, 2.0, 4.0):
        text = " ".join(lining_notes([_Part()], outer))
        assert not re.search(r"[①-⑳]", text), f"見出し番号が入っています: {text[:80]}"


# --- 3. PDFのパーツ名が、裁断線を越えないこと ----------------------------

def test_the_label_is_measured_at_the_height_where_it_is_drawn():
    """走査線でその高さの実幅を測る関数があり、実際に使われていること。"""
    assert hasattr(pdf_export, "_label_span_cm")
    source = pathlib.Path(pdf_export.__file__).read_text(encoding="utf-8")
    # 縮小図・実寸ページの両方で使うこと。
    assert source.count("_label_span_cm(") >= 3, \
        "貼り合わせ図と実寸ページの両方で使われていません"
    # 外接矩形をそのまま渡す書き方が残っていないこと。
    assert "_fit_label_to_width(\n                        label_text, (max_x - min_x) * CM)" not in source


def test_the_span_is_the_run_that_contains_the_centre():
    """中央xを含む区間の幅を返すこと(離れた2つの間の空白を数えない)。

    深い切り込みで輪郭が左右に分かれる高さでは、min〜maxを幅にすると
    間の何も無いところまで幅に数えてしまう。
    """
    # 高さ5で x=0..2 と x=8..10 の2本に分かれる形
    shape = [(0, 0), (10, 0), (10, 10), (8, 10), (8, 4), (2, 4), (2, 10), (0, 10)]
    assert pdf_export._label_span_cm(shape, 7.0, 1.0) == pytest.approx(2.0)
    assert pdf_export._label_span_cm(shape, 7.0, 9.0) == pytest.approx(2.0)
    # 切り込みより下では、全幅が使える。
    assert pdf_export._label_span_cm(shape, 2.0, 5.0) == pytest.approx(10.0)
    # 交点が取れない高さでは None(呼び出し側が外接矩形に従う)。
    assert pdf_export._label_span_cm(shape, 99.0, 5.0) is None
    assert pdf_export._label_span_cm([(0, 0), (1, 1)], 0.5, 0.5) is None


def test_no_part_label_crosses_its_own_cutting_line():
    """実際に型紙を引いて、どのパーツ名も裁断線の内側に収まること。

    これが round11 が立てた約束で、round46まで**縮小図では破れていた**
    (実測: 裏地付きの前身頃で2.5pt、後身頃で2.1pt)。
    """
    from reportlab.pdfbase import pdfmetrics

    from engine.measurements import Measurements
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    pipeline = PatternForgePipeline()
    measurements = Measurements(bust=88, waist=72, hip=96, height=162,
                                sleeve_length=55, shoulder_width=38)
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(
        garment_spec=spec, measurements=measurements, skip_export=True, lining=True)

    offenders = []
    for nesting in (result.nesting, result.lining_nesting):
        if nesting is None:
            continue
        # 貼り合わせ図の縮小倍率(pdf_exportと同じ考え方)。
        scale = min(18.0 / nesting.fabric_width_cm,
                    16.0 / max(nesting.used_length_cm, 0.1))
        for placed in nesting.placed:
            x0, y0, x1, y1 = placed.bbox()
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            cut = placed.placed_cut_line()
            usable = pdf_export._label_span_cm(cut, cy, cx)
            if usable is None:
                usable = x1 - x0
            for factor in (1.0, scale):      # 実寸ページと縮小図の両方
                text, size = pdf_export._fit_label_to_width(
                    placed.part.display_name, usable * factor * pdf_export.CM)
                drawn = max(4.0, min(size, 7.0)) if factor != 1.0 else size
                width_pt = pdfmetrics.stringWidth(text, pdf_export._LABEL_FONT, drawn)
                if width_pt > usable * factor * pdf_export.CM + 0.01:
                    offenders.append(
                        f"{placed.part.display_name}: 文字{width_pt:.1f}pt > "
                        f"実幅{usable * factor * pdf_export.CM:.1f}pt")
    assert offenders == [], "裁断線からはみ出すパーツ名: " + "; ".join(offenders)
