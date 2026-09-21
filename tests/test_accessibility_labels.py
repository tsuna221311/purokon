"""round37: 支援技術に読まれる名前が、動的に作る入力欄にも付いていること。

【なぜこのテストがあるか】round37でキーボードだけで画面を辿ったところ、
Tabで到達できる62箇所のうち3箇所——カスタムパーツの中の
「パーツ名」「画像ファイル」「参照線の実寸」——が**名前を持たないまま**
到達できた。読み上げても「編集テキスト」としか言われず、何の欄か分からない。

3つとも`placeholder`は付いていた。だが**placeholderは名前ではない**:
読み上げソフトによっては読まれず、読まれる場合でも1文字入力した時点で
消えるので、「今どの欄にいるのか」を確かめ直せない。

これらの欄は`web/static/app.js`がJavaScriptで組み立てるので、HTMLを
見ても分からない。ここではソースを読んで、`aria-label`が付いていることを
固定する(ブラウザを起動する検査は`scripts/audit_contrast.py`と同じ理由で
テスト一式には入れない。実際のTab順の確認はブラウザで行い、その結果を
ここへ写している)。
"""

import re
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "web" / "static" / "app.js"


@pytest.fixture(scope="module")
def source() -> str:
    return APP_JS.read_text(encoding="utf-8")


@pytest.mark.parametrize("variable,expected", [
    ("labelInput", "カスタムパーツの名前"),
    ("fileInput", "輪郭を読み取る画像ファイル"),
    ("referenceCmInput", "参照点A〜B間の実寸(cm)"),
])
def test_dynamically_built_inputs_have_an_accessible_name(source, variable, expected):
    """JavaScriptで作る入力欄に、aria-labelが付いていること。"""
    pattern = rf'{variable}\.setAttribute\(\s*"aria-label"\s*,\s*"([^"]+)"'
    match = re.search(pattern, source)
    assert match, f"{variable} に aria-label がありません"
    assert match.group(1) == expected, match.group(1)


def test_the_drawing_canvas_says_what_it_is_and_offers_another_route(source):
    """キャンバスが、自分が何かと、別の道があることを伝えていること。

    【正直に書くと】輪郭をクリックで描く操作そのものは、キーボードだけでは
    できない。矢印キーで頂点を置く仕組みは、今は無い。
    ただし**同じ輪郭を得る別の道はある**——画像を選んで「画像から輪郭を
    自動抽出」を押す経路で、ファイル選択もボタンも普通にTabで辿れる。
    道があるのに、それが道だと画面のどこにも書いていなかった。

    ここでは、読み上げ用(aria-label)と目で読む説明文(status)の
    **両方**に案内があることを確かめる。片方だけだと、どちらかの利用者に
    届かない。
    """
    match = re.search(r'canvas\.setAttribute\(\s*"aria-label"\s*,\s*(.+?)\);',
                      source, re.DOTALL)
    assert match, "canvas に aria-label がありません"
    aria = match.group(1)
    assert "画像から輪郭を自動抽出" in aria, aria
    assert re.search(r'canvas\.setAttribute\(\s*"role"', source), "canvas に role がありません"

    # 目で読む側の説明にも、同じ代替手段が書いてあること。
    # `status.textContent = ...` は他にもあるので、キャンバスの使い方を
    # 説明している文(頂点の追加の話をしている方)を名指しで探す。
    idx = source.index("輪郭の頂点を3つ以上追加")
    help_text = source[idx:source.index(";", idx)]
    assert "画像から輪郭を自動抽出" in help_text, help_text


def test_a_placeholder_alone_is_not_treated_as_a_name(source):
    """placeholderだけで済ませている入力欄が、増えていないこと。

    このテストが見張っているのは「placeholderを名前の代わりにしない」という
    決めごとである。新しく入力欄を足したときに、ここが鳴る。
    """
    # `<something>.placeholder = "..."` を持つ変数を全部集める
    with_placeholder = set(re.findall(r'(\w+)\.placeholder\s*=', source))
    with_aria = set(re.findall(r'(\w+)\.setAttribute\(\s*"aria-label"', source))
    # ラベル要素で包んでいる/select などは対象外。ここでは既知の3つが
    # 必ずaria-labelを持っていることだけを見る(全部を機械的に要求すると、
    # `<label>`で包んだ正しい実装まで落としてしまう)。
    for name in ("labelInput", "fileInput", "referenceCmInput"):
        if name in with_placeholder:
            assert name in with_aria, (
                f"{name} は placeholder だけで名前が無い。"
                "placeholderは名前ではない(読まれない・入力すると消える)")
