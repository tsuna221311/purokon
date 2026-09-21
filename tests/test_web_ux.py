"""round32: 実際にブラウザで操作して見つけた不具合と、その再発防止。

このラウンドは「バグがないか実際に動かして、使いやすくしてくれ」という
依頼で、開発サーバーを起動しヘッドレスChromeで画面を操作しながら調べた。
見つかったのは次のとおりで、どれもテストが1つも通っている状態で存在して
いた——**画面を触らないと分からない種類の不具合**である。

1. サイズ展開モードが事実上まったく使えなかった。
2. 生成ボタンを押しても画面上は何も変わらなかった。
3. スマホ幅でページ全体が横にはみ出していた。
4. 初期選択が内部識別子のアルファベット順で決まっていた。
5. 何も問題の無い生成でも赤い警告が出ていた。
"""

import pathlib
import re

import pytest

#: テストファイルの位置から辿るので、pytestをどこから起動しても壊れない。
WEB_DIR = pathlib.Path(__file__).resolve().parent.parent / "web"


def _valid_form(**overrides):
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
    }
    form.update(overrides)
    return form


# --- 1) サイズ展開モードが使えなかった -------------------------------------

def test_multi_size_works_with_the_default_custom_panel_field(client):
    """カスタムパーツを1つも作っていないサイズ展開が、普通に通ること。

    【実際に起きていたこと】`custom_panels_json`の**既定値は空文字ではなく
    文字列 "[]"** で、web/static/app.jsは手動モード以外でも明示的に "[]" を
    書き戻す。ところがサーバ側の判定が文字列の真偽値だったため、
    サイズ展開モードを選んで生成するだけで

        「カスタムパーツ(自由形状)は現在、サイズ展開モードでは併用できません。」

    という、まったく身に覚えのないエラーが出ていた。つまりサイズ展開機能は
    ブラウザからは一度も使えていなかった(テストは`custom_panels_json`を
    送っていなかったので気づけなかった)。
    """
    form = _valid_form(mode="multi_size", sizes=["S", "M"],
                       custom_panels_json="[]")
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    data = response.get_json()
    assert data["ok"] is True, data
    assert data["mode"] == "multi_size"
    assert sorted(data["sizes"]) == ["M", "S"]


def test_multi_size_still_refuses_a_real_custom_panel(client):
    """本物のカスタムパーツが入っていれば、従来どおり明確に断ること。

    (上の修正で「空でも通す」ようにしたので、**本当に併用したとき**に
     黙って無視されないことを対で確かめる。)
    """
    panel = ('[{"label":"マント","points":[[0,0],[10,0],[10,10]],'
             '"ref_point_a":[0,0],"ref_point_b":[10,0],"reference_cm":40}]')
    form = _valid_form(mode="multi_size", sizes=["M"], custom_panels_json=panel)
    data = client.post("/api/generate", data=form).get_json()
    assert data["ok"] is False
    assert "サイズ展開モード" in data["error"]


def test_a_broken_custom_panels_json_still_reports_its_own_error(client):
    """壊れたJSONは、黙って無視せず中身のエラーを返すこと。"""
    form = _valid_form(custom_panels_json="{ not json")
    data = client.post("/api/generate", data=form).get_json()
    assert data["ok"] is False
    assert "custom_panels_json" in data["error"]


# --- 2) 押しても何も起きないように見えた -------------------------------------

def test_the_page_scrolls_to_the_result_and_locks_the_button(client):
    """生成中に結果へスクロールし、ボタンを二度押しできなくすること。

    【実際に起きていたこと】「型紙を生成する」ボタンはフォームのいちばん下
    (実測でページ先頭から約2300px)にあり、結果パネルは画面のいちばん上に
    出る。押しても画面上は何も変わらないので、壊れたと思ってもう一度押すと
    1日3回の無料枠を2回使ってしまう。
    """
    js = (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "scrollIntoView" in js
    assert "beginGenerating" in js and "endGenerating" in js
    assert "submitButton.disabled = true" in js

    html = client.get("/").get_data(as_text=True)
    assert 'id="result-panel"' in html, "スクロール先のIDが無い"


# --- 3) スマホ幅の横あふれ ---------------------------------------------------

def test_the_stylesheet_lets_narrow_screens_shrink(client):
    """狭い画面で横スクロールが出ないための指定があること。

    【実際に起きていたこと】390px幅でdocument.scrollWidthが490pxになり、
    ページ全体が横に100pxはみ出していた。真犯人は`<select id="fit">`で、
    いちばん長い選択肢「ゆったり(重ね着・動きの大きい衣装)（身頃
    バスト+14.0cm）」が入る幅(451px)より狭くならなかった
    (`.field`の中に無いので既存の width:100% が当たっていなかった)。
    """
    css = (WEB_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"^select \{[^}]*width: 100%", css, re.M), \
        "selectが画面幅より広くなるのを防ぐ指定が無い"
    assert re.search(r"^select \{[^}]*min-width: 0", css, re.M)
    # 3列固定だった採寸欄・数値タイルが、狭い画面で2列になること。
    assert ".grid-measurements .field," in css and "min-width: 0" in css
    assert css.count("@media (min-width: 560px)") >= 2


# --- 4) 初期選択が内部識別子のアルファベット順で決まっていた -------------------

def test_the_form_starts_on_the_basic_pattern(client):
    """初期表示が基本形(ラウンドネック/ストレート/フレア)であること。

    【実際に起きていたこと】選択肢は`sorted(NECKLINES)`のように**内部識別子
    のアルファベット順**で並べ、`selected`をどれにも付けていなかったので、
    初めて開いた人が何も触らずに生成すると「ボートネック + ベル袖 +
    サーキュラースカート」というかなり凝った型紙が出ていた。
    """
    html = client.get("/").get_data(as_text=True)
    # round34: 形の選択は<select>からサムネイルのラジオになった。
    # 「初期選択がちょうど1つで、それが基本形であること」という
    # 確かめたい中身は同じ。
    for name, expected in (("neckline", "round_neck"),
                            ("sleeve_style", "straight"),
                            ("skirt_style", "flare")):
        checked = re.findall(
            r'<input type="radio" name="%s" value="([^"]*)"\s*\n?\s*checked' % name,
            html)
        assert checked == [expected], (name, checked)


# --- 5) 問題の無い生成でも赤い警告が出ていた ---------------------------------

def test_a_plain_generation_produces_no_warning_at_all(client):
    """標準の採寸・標準のゆとりでは、警告も注記も出ないこと。"""
    data = client.post("/api/generate", data=_valid_form()).get_json()
    assert data["ok"] is True
    assert data["measurement_warnings"] == [], data["measurement_warnings"]
    assert data["design_notes"] == [], data["design_notes"]


def test_choosing_an_ease_is_a_note_not_a_warning(client):
    """ゆとりを選び直しただけなら、警告ではなく「作り方」に出ること。

    【実際に起きていたこと】「ゆとり『…』で作成しました」という単なる説明が
    `measurement_warnings`に入っていたため、画面では
    「⚠ 入力した採寸値の一部が、テンプレートを正確に変形できる範囲を
    超えています」という赤い見出しの下に並んでいた。何も問題が無い生成でも
    赤が出るので、本当に読むべき警告が埋もれる。
    """
    data = client.post("/api/generate", data=_valid_form(fit="relaxed")).get_json()
    assert data["ok"] is True
    assert any("ゆとり" in n for n in data["design_notes"]), data
    assert data["measurement_warnings"] == [], data["measurement_warnings"]


def test_a_real_problem_still_warns(client):
    """本物の問題は、引き続き警告として出ること。

    (注記と分けた結果「警告が何も出なくなった」のでは意味が無いので、
     対で確かめる。)
    """
    form = _valid_form(bust="130", waist="110", hip="135", shoulder_width="37")
    data = client.post("/api/generate", data=form).get_json()
    assert data["ok"] is True
    assert data["measurement_warnings"], data
    assert any("肩幅" in w for w in data["measurement_warnings"]), data


# --- 型紙に書かれる名前 -------------------------------------------------------

def test_the_parts_list_shows_japanese_names_and_cutting_notes(client):
    """結果のパーツ一覧が日本語名と裁ち方の指示を持つこと。"""
    data = client.post("/api/generate", data=_valid_form()).get_json()
    assert data["ok"] is True
    for part in data["parts"]:
        assert "_" not in part["display_name"], part
        assert part["cutting_note"]
        assert part["part_type"] and part["identifier"]
    names = [p["display_name"] for p in data["parts"]]
    assert any(n.startswith("前身頃") for n in names), names
    assert any(n.startswith("袖") for n in names), names
