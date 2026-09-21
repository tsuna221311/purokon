"""round37: 画面の文字が実際に読める濃さかどうかを、数字で固定する。

【なぜこのテストがあるか】round34で配色を作り直したとき、READMEに
「色の見え方は検証していない。コントラスト比の実測や、色覚特性を持つ人での
確認はしていない」と限界として書いた。round36までそのまま残っていた。

round37で、実際にレンダリングした画面から`getComputedStyle`で実効色
(親から継承した背景・半透明の重なりも込み)を取り出して測ったところ、
5つの画面状態・163組のうち3組がWCAG 2.1 AAに足りていなかった。
どれも「**白の上では足りているが、この製品が実際に使っている色付きの
背景の上では足りていない**」という同じ形をしていた——白で確かめて決めた色を、
色の付いた箱の中でも使っていたのが原因である。

【このテストと、ブラウザでの実測の関係】
ブラウザを起動する検査は遅く、環境にも左右されるので、テスト一式には
入れない。ここでは
  * 色の値は`web/static/style.css`から**実際に読む**(値を変えれば再計算される)
  * 「どの文字色がどの背景の上に載るか」の組は、
    `scripts/audit_contrast.py`を実際に動かして観測した結果を写す
という形にしている。組の一覧は手で写しているので、**新しい配色の組み合わせを
足したときは、あのスクリプトを動かし直してここへ反映する必要がある**
(それが正直な限界。READMEにも書いてある)。
"""

import re
from pathlib import Path

import pytest

from engine.contrast import (LARGE_TEXT_PX, MIN_RATIO_LARGE_TEXT,
                             MIN_RATIO_NON_TEXT, MIN_RATIO_TEXT,
                             contrast_ratio, parse_hex, relative_luminance,
                             required_ratio)

STYLE_CSS = Path(__file__).resolve().parent.parent / "web" / "static" / "style.css"


def _css_variable(name: str) -> str:
    """style.cssの`:root`から、その変数の値をそのまま読む。"""
    text = STYLE_CSS.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{3,6}})\s*;",
                      text, re.MULTILINE)
    assert match, f"style.css に {name} が見つかりません"
    return match.group(1)


def _dark_variable(name: str) -> str:
    """暗い画面(`prefers-color-scheme: dark`)の側の値を読む。

    round70で追加。`_css_variable`は最初に見つかった`:root`——つまり
    明るい画面の値——を返すので、暗い側は別に取る必要がある。
    **明るい側だけ固定していると、暗い側は誰も見ていないのと同じ**である。
    """
    text = STYLE_CSS.read_text(encoding="utf-8")
    i = text.index("@media (prefers-color-scheme: dark)")
    block = text[i:text.index("\n}\n", i)]
    match = re.search(rf"^\s*{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{3,6}})\s*;",
                      block, re.MULTILINE)
    assert match, f"暗い画面の側に {name} が見つかりません"
    return match.group(1)


def _rule_color(selector_fragment: str) -> str:
    """あるセレクタのブロックに書かれた`color:`をそのまま読む。

    同じセレクタが複数のブロックに現れる(例: `.style-none-mark`は大きさを
    決めるブロックと色を決めるブロックに分かれている)ので、`color:`を
    実際に持っているブロックを探す。最初の1つを決め打ちにすると、
    CSSを並べ替えただけでテストが壊れる。
    """
    text = STYLE_CSS.read_text(encoding="utf-8")
    found = []
    start = 0
    while True:
        idx = text.find(selector_fragment, start)
        if idx < 0:
            break
        start = idx + 1
        block = text[idx:text.index("}", idx)]
        match = re.search(r"color:\s*(#[0-9a-fA-F]{3,6})", block)
        if match:
            found.append(match.group(1))
    assert found, f"{selector_fragment} に color を持つブロックがありません"
    assert len(set(found)) == 1, f"{selector_fragment} の color が食い違っています: {found}"
    return found[0]


# --- 計算そのものの検算 -------------------------------------------------------

def test_the_maths_matches_the_wcag_worked_examples():
    """WCAGの定義どおりに計算できていること。

    実装を疑えるように、答えが分かっている値で検算する。
    黒と白は21:1、同じ色どうしは1:1というのが定義上の両端。
    """
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.001)
    assert contrast_ratio("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    # 順序を入れ替えても同じ
    assert contrast_ratio("#123456", "#fedcba") == pytest.approx(
        contrast_ratio("#fedcba", "#123456"))
    # 相対輝度の両端
    assert relative_luminance((0, 0, 0)) == pytest.approx(0.0)
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    # 短縮表記
    assert parse_hex("#fff") == (255, 255, 255)


def test_large_text_has_a_lower_bar():
    """大きい文字は3:1でよい、という基準を取り違えていないこと。"""
    assert required_ratio(12) == MIN_RATIO_TEXT
    assert required_ratio(LARGE_TEXT_PX) == MIN_RATIO_LARGE_TEXT
    assert required_ratio(20, font_weight=700) == MIN_RATIO_LARGE_TEXT
    assert required_ratio(20, font_weight=400) == MIN_RATIO_TEXT   # 太字でなければ通常扱い


# --- 実際の配色 ---------------------------------------------------------------

#: 文字が実際に載る背景。`scripts/audit_contrast.py`で観測したもの。
#: (ヘッダーの濃色 #1f2430 と アクセント #3b4a8f は白文字用なので別に見る。)
LIGHT_BACKGROUNDS = {
    "パネル(白)": "#ffffff",
    "ページ地": "#f5f2ec",
    "淡いパネル": "#faf8f4",
    "アクセント淡": "#eef0fb",
    "琥珀(注意)": "#fffbeb",
    "赤淡(警告)": "#fef2f2",
    "石板淡": "#f1f5f9",
}

DARK_BACKGROUNDS = {
    "ヘッダー": "#1f2430",
    "主ボタン(アクセント)": "#3b4a8f",
}


@pytest.mark.parametrize("bg_name", sorted(LIGHT_BACKGROUNDS))
def test_the_muted_text_is_readable_on_every_background_it_lands_on(bg_name):
    """控えめな字(--muted)が、載りうる背景すべてで4.5:1以上あること。

    【実際に起きていたこと】#78716c は白の上では4.80:1で足りていたが、
    ページ地4.29:1・アクセント淡4.22:1・赤淡4.39:1で足りていなかった。
    この色は`.hint`・`.part-chip-size`・`.fabric-need-sub`・
    フッターなど15か所以上で使われており、そのうち色の付いた箱の中に
    入るものが読みにくくなっていた。
    """
    muted = _css_variable("--muted")
    ratio = contrast_ratio(muted, LIGHT_BACKGROUNDS[bg_name])
    assert ratio >= MIN_RATIO_TEXT, (
        f"--muted {muted} は {bg_name} の上で {ratio:.2f}:1 しかない "
        f"(必要 {MIN_RATIO_TEXT}:1)")


@pytest.mark.parametrize("bg_name", sorted(LIGHT_BACKGROUNDS))
def test_the_body_text_is_readable_on_every_background(bg_name):
    """本文(--ink)も同じく確かめる(こちらは元から余裕がある)。"""
    ink = _css_variable("--ink")
    ratio = contrast_ratio(ink, LIGHT_BACKGROUNDS[bg_name])
    assert ratio >= MIN_RATIO_TEXT, f"--ink は {bg_name} で {ratio:.2f}:1"


@pytest.mark.parametrize("bg_name", sorted(DARK_BACKGROUNDS))
def test_white_text_on_the_dark_areas_is_readable(bg_name):
    """ヘッダーと主ボタンの白文字が読めること。"""
    ratio = contrast_ratio("#ffffff", DARK_BACKGROUNDS[bg_name])
    assert ratio >= MIN_RATIO_TEXT, f"白文字は {bg_name} で {ratio:.2f}:1"


def test_the_none_thumbnail_mark_is_visible():
    """「なし」のサムネイルに描く横棒が、見える濃さであること。

    【実際に起きていたこと】#c4bcab は白の上で1.89:1しかなく、
    ほとんど見えていなかった。これは文字ではなく**選択肢を表す図**なので、
    必要なのは4.5:1ではなく3:1(WCAG 2.1 SC 1.4.11 非テキストのコントラスト)。

    4.5:1まで濃くすると、他のサムネイルの線画より目立って「なし」だけが
    強調されて見えるので、3:1で止めている——**基準を満たす中でいちばん
    控えめな値**を選んだ、という判断の記録でもある。

    round70で、この横棒の色とその背景を**どちらも名前(トークン)から読む**
    ようにした。round70の作業中、`--accent-soft`を#eef0fb→#eaedfaへ
    少しだけ動かしたところ、この横棒は選択中の地で**2.95:1**になっていた
    ——3:1をわずかに割っていたのに、このテストは背景を`#eef0fb`と
    直書きしていたので**何も言わなかった**。値を写して固定すると、
    写した側が動いたときに黙る。
    """
    for label, mark, surface, selected in (
        ("明るい画面", _css_variable("--thumb-mark"),
         _css_variable("--surface"), _css_variable("--accent-soft")),
        ("暗い画面", _dark_variable("--thumb-mark"),
         _dark_variable("--surface"), _dark_variable("--accent-soft")),
    ):
        for bg_name, bg in (("通常時", surface), ("選択時", selected)):
            ratio = contrast_ratio(mark, bg)
            assert ratio >= MIN_RATIO_NON_TEXT, (
                f"{label}: 「なし」の横棒 {mark} は {bg_name}({bg}) の上で "
                f"{ratio:.2f}:1 (必要 {MIN_RATIO_NON_TEXT}:1)")


def test_the_warning_colours_stay_readable_on_their_own_boxes():
    """警告・注記の文字色が、その箱の背景の上で読めること。

    赤い警告(#991b1b on #fef2f2)・橙の注意(#92400e on #fffbeb)・
    青い説明(#1d4ed8 on #eef0fb)は、色そのものが意味を持つ表示なので、
    薄くすると意味も弱くなる。実測値を固定しておく。
    """
    pairs = [
        ("赤い警告", "#991b1b", LIGHT_BACKGROUNDS["赤淡(警告)"]),
        ("橙の注意", "#92400e", LIGHT_BACKGROUNDS["琥珀(注意)"]),
        ("青い説明", "#1d4ed8", LIGHT_BACKGROUNDS["アクセント淡"]),
        ("青い説明(白地)", "#1d4ed8", LIGHT_BACKGROUNDS["パネル(白)"]),
    ]
    for name, fg, bg in pairs:
        ratio = contrast_ratio(fg, bg)
        assert ratio >= MIN_RATIO_TEXT, f"{name} は {ratio:.2f}:1"


def test_a_deliberately_bad_pair_is_caught():
    """このテストが本当に落ちることを、わざと薄い色で確かめる。

    「全部通っている」ことに意味があるのは、落ちるべきものが落ちるときだけ。
    """
    assert contrast_ratio("#cccccc", "#ffffff") < MIN_RATIO_TEXT
    assert contrast_ratio("#78716c", "#eef0fb") < MIN_RATIO_TEXT   # 修正前の値


# --- レイアウトがはみ出さないための決めごと(round38) --------------------------

def test_grid_columns_can_shrink_below_their_content():
    """`.layout`の列に`min-width: 0`が付いていること。

    【なぜ要るか】CSSグリッドの列は、既定では「中身が縮められる最小幅
    (min-content)」より細くならない。中に**折り返せない要素**が1つでもあると、
    その幅まで列が広がり、ページ全体が横スクロールする。

    round38で買い物メモの表を足した直後、320pxで生成するとページが394px幅に
    なった。はみ出していたのは表ではなく`.panel`そのもので、表のmin-contentが
    列を押し広げていた——表に`overflow-x:auto`を付けても、列の最小幅の計算は
    それより先に効くので直らなかった。

    round32で`<select>`が同じ形で画面をはみ出させたのと同じ原因である。
    2度あったので、決めごととして固定する。
    """
    text = STYLE_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.layout\s*>\s*\.panel\s*\{[^}]*min-width:\s*0", text), \
        ".layout > .panel に min-width: 0 がありません"
    # round32の手当ても残っていること
    assert re.search(r"select\s*\{[^}]*min-width:\s*0", text), \
        "select の min-width: 0 が消えています(round32の修正)"


def test_long_urls_in_notes_can_wrap():
    """注記の中のURLがどこでも折り返せること(round41)。

    【なぜ要るか】`min-width: 0`は**列が縮むこと**を許すだけで、
    **中身が縮む**わけではない。URLは空白を含まない1語なので折り返せず、
    そのURLの長さがそのまま列の最小幅になり、結局ページがはみ出す。

    round41で裏地の注記に出典URL
    (https://yousai.net/how_to/bubunnui/migoro/urajituke)を入れた直後、
    実測で320px幅のページが504px(184pxはみ出し)、390px幅で114pxはみ出した。
    裏地を付けない生成では0だったので、原因は新しい注記のURLである。

    このエンジンは**出典の無い数字を出さない**方針なので、注記にURLが入る
    経路は今後も増える。URLを短くする・消すのではなく、折り返せるようにする。
    """
    text = STYLE_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.hint[^{]*\{[^}]*overflow-wrap:\s*anywhere", text), \
        "注記(.hint)に overflow-wrap: anywhere がありません"
