"""round64: スマホで採寸していると、測り方が1pxも見えない。

コスプレイヤーは**一人で**自分を測る。片手にメジャー、もう片手にスマホで、
バスト・ウエスト・ヒップ・身長・袖丈・肩幅を順に入れていく。
round34はそのために採寸図と「どこをどう測るか」の文を用意し、狭い画面では
図を採寸欄の下へ移すところまでやってあった。

【実測】390x844で、6つの必須採寸欄のどれにフォーカスしても——

    採寸図       見えている高さ 0px（図そのものが523px、欄の339〜473px下）
    測り方の文   見えている高さ 0px（図のさらに下）

ソフトキーボードを出した状態(390x508)では、いちばん下の肩幅でも 0px。
1440x900では図が712px見えているので、**狭い画面だけの問題**である。

肩幅の注意書き「腕の付け根から付け根まで、ではありません」は、
round33が指摘文でわざわざ否定する羽目になったほど間違えやすい所で、
round34はそれを図の横に出すために書かれた。その文が、いちばん測りにくい
状況で1pxも見えていなかった。

直し方: 採寸欄のすぐ下(`#measure-inline-guide`)にも同じ文を出す。
**文は `engine/measure_guide.py` が唯一の出どころのまま**で、画面側は
同じ辞書を別の場所にも描くだけである(文を書き足さない)。

このファイルが見張るのは、次にここを触る人が踏みやすい4つである。

  1. 採寸欄を足したのに、測り方を書き忘れる
  2. 測り方の文を画面側へ書き写す(片方だけ古くなる)
  3. 案内の段落に class="hint" を付ける
     → round32の`collapseLongHints`が<details>へ畳み、また読めなくなる
  4. 「狭い画面か」の境目をCSSとJSで別々に決める
"""

import re
from pathlib import Path

import pytest

from engine.measure_guide import MEASURE_GUIDES

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
STYLE = (ROOT / "web" / "static" / "style.css").read_text(encoding="utf-8")
FIGURE = (ROOT / "web" / "templates" / "_measure_figure.html").read_text(encoding="utf-8")

#: 採寸欄のすぐ下に案内を出す器のid(画面・CSS・JSで同じものを指す)。
GUIDE_BOX_ID = "measure-inline-guide"

#: 必須の6項目が入っている入れ物。ここに入っている欄が案内の対象になる。
GRID_CLASS = "grid-measurements"


def _grid_measurement_fields() -> list[str]:
    """`.grid-measurements` の中にある入力欄の名前を、HTMLから読み取る。

    JS側(`inlineGuideFields`)と同じ取り方をする。一覧をテストに書き写すと、
    欄を足したときに**テストだけが古くなって通り続ける**。
    """
    start = INDEX.index(GRID_CLASS)
    end = INDEX.index(GUIDE_BOX_ID, start)
    return re.findall(r"""\('(\w+)','[^']+',\s*-?\d""", INDEX[start:end])


def test_the_screen_and_the_test_agree_on_which_fields_are_in_the_grid():
    """取り方そのものが空振りしていないことを、まず確かめる。"""
    fields = _grid_measurement_fields()
    assert len(fields) == 6, fields
    assert "shoulder_width" in fields


@pytest.mark.parametrize("field", _grid_measurement_fields())
def test_every_measurement_field_has_a_way_to_measure_it(field):
    """採寸欄を足したのに測り方を書き忘れたら、ここで落ちる。"""
    assert field in MEASURE_GUIDES, (
        f"採寸欄 {field} に対応する測り方が engine/measure_guide.py にありません。"
        "画面には欄だけが出て、案内は空になります。")
    guide = MEASURE_GUIDES[field]
    assert guide.how.strip(), f"{field} の how が空です。"


def test_the_guide_box_exists_on_the_screen():
    """案内の器と、中を3つに分けた場所が画面にあること。"""
    assert f'id="{GUIDE_BOX_ID}"' in INDEX
    for part in ("title", "how", "caution"):
        assert f'id="{GUIDE_BOX_ID}-{part}"' in INDEX, part
        assert f'"{GUIDE_BOX_ID}-{part}"' in APP_JS, part


def test_the_guide_sits_next_to_the_fields_it_explains():
    """案内が採寸欄から離れたら落ちる。

    round34の図は採寸欄の下にあったが、あいだに何も無かったわけではなく、
    **図そのものが523pxある**ために画面の外へ出ていた。器は
    `.grid-measurements` の直後、任意項目より前に置く。
    """
    grid = INDEX.index(GRID_CLASS)
    box = INDEX.index(f'id="{GUIDE_BOX_ID}"')
    optional = INDEX.index('id="field-upper_arm"')
    figure_slot = INDEX.index('id="measure-figure-slot"')
    assert grid < box < optional < figure_slot


def test_the_measuring_text_is_not_copied_into_the_screen_files():
    """測り方の文を画面側へ書き写したら落ちる(round61と同じ理由)。

    同じ文が2か所にあると、必ずどちらかが古くなる。画面は
    `engine/measure_guide.py` の辞書を受け取って描くだけにする。
    """
    screen_files = {
        "web/templates/index.html": INDEX,
        "web/static/app.js": APP_JS,
        "web/static/style.css": STYLE,
        "web/templates/_measure_figure.html": FIGURE,
    }
    for key, guide in MEASURE_GUIDES.items():
        for kind, text in (("how", guide.how), ("caution", guide.caution)):
            if not text:
                continue
            for name, body in screen_files.items():
                assert text not in body, (
                    f"{name} に {key} の {kind} が書き写されています。"
                    "engine/measure_guide.py を直しても、こちらが古いまま残ります。")


def test_the_guide_is_not_a_hint_paragraph():
    """案内に class="hint" を付けたら落ちる。

    round32の`collapseLongHints`は、フォームの中の長い `p.hint` を
    <details>へ畳む。肩幅の案内は注意書きまで入れて160pxあるので、
    hintにすると**また読めなくなる**(直したものが元に戻る)。
    """
    start = INDEX.index(f'id="{GUIDE_BOX_ID}"')
    end = INDEX.index('id="field-upper_arm"', start)
    block = INDEX[start:end]
    assert 'class="hint"' not in block
    assert "hint " not in block.replace("measure-inline-guide", "")


def test_the_guide_is_read_as_the_description_of_the_field():
    """読み上げで、案内が「その欄の説明」として読まれること。

    aria-live にすると欄を移るたびに割り込んで読み上げる。
    欄に aria-describedby を付け、離れるときに外す。
    """
    assert f'setAttribute("aria-describedby", "{GUIDE_BOX_ID}")' in APP_JS
    assert 'removeAttribute("aria-describedby")' in APP_JS


def test_css_and_script_use_the_same_narrow_screen_boundary():
    """「狭い画面か」の境目が、CSSとJSでずれたら落ちる。

    ずれると、CSSで隠れているのにJSが aria-describedby を付ける
    (読み上げが見えない要素を指す)、あるいはその逆が起きる。
    """
    css_hits = re.findall(
        r"@media\s*\(min-width:\s*(\d+)px\)\s*\{\s*\.measure-inline-guide", STYLE)
    js_hits = re.findall(r'matchMedia\("\(min-width: (\d+)px\)"\)', APP_JS)
    assert css_hits, "CSSに .measure-inline-guide を隠す@mediaがありません。"
    assert js_hits, "app.jsに matchMedia がありません。"
    assert set(css_hits) == set(js_hits), (css_hits, js_hits)
    assert len(set(js_hits)) == 1, f"境目が複数あります: {js_hits}"


def test_the_figure_and_the_inline_guide_show_the_same_sentences():
    """図の説明と欄の下の案内が、同じ辞書から来ていること。

    どちらも `guides[field]` の label / how / caution を使う。
    片方だけ別の出どころに変えたら落ちる。
    """
    for expr in ("guide.label", "guide.how", "guide.caution"):
        assert APP_JS.count(expr) >= 2, (
            f"{expr} を使っている箇所が {APP_JS.count(expr)} か所しかありません。"
            "図と欄下の両方が同じ辞書を使っているはずです。")
