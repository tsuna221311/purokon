"""round44: 画面を実際に測って直したUI/UX(タップ目標・読み上げ・入力の検証)。

round43まで、この製品はコントラスト(round37)だけをWCAGの基準で見張っていた。
round44でブラウザを回して測り直したところ、**押せる範囲の大きさ**と
**状態の読み上げ**が抜けていた。

【実測した状態】Playwrightで7ページ×2幅を回り、クリックできる要素の
外接矩形を全部測った結果:

  * **222件**が 24×24px 未満(WCAG 2.2 SC 2.5.8 Target Size (Minimum))
    チェックボックス・ラジオが 13×13px、<select>が19〜23px、
    ヘッダーのナビが18px、フッターのリンクが14px。
    **指ではまず当たらない大きさで、この製品の主な操作(ネックラインを
    選ぶ・ゆとりを選ぶ)がそこにあった。**
  * `aria-live` を持つ要素が **1つも無い**。この画面は押したあとに
    起きることが全部JSで差し込まれるので、スクリーンリーダーでは
    「生成する」を押しても始まったことも終わったことも読み上げられず、
    無言のまま数十秒が過ぎていた(WCAG 2.1 SC 4.1.3 Status Messages)。
  * 採寸欄に `min`/`max` が無い。単位・桁の間違い(身長1600cm)は
    サーバーへ往復してから初めてエラーになっていた。
  * ラベルの無いフォーム部品が6つ(ファイル入力2・バリエーションの
    セレクト4)。round37で3つ直したが、これらは残っていた。
  * 本文へのスキップリンクが無い。

このテストは、直した状態が**元に戻らないこと**を見張る。ブラウザを
起動せずに回せるよう、CSS/HTML/JSの中身を読んで確かめる形にしてある
(実際に測り直す台本は`scripts/audit_target_size.py`)。
"""

import pathlib
import re

import pytest

import app as app_module

STATIC = pathlib.Path(app_module.BASE_DIR) / "web" / "static"
TEMPLATES = pathlib.Path(app_module.BASE_DIR) / "web" / "templates"
STYLE_CSS = (STATIC / "style.css").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")

#: WCAG 2.2 SC 2.5.8 Target Size (Minimum) — Level AA。
MIN_TARGET_PX = 24


# --- タップ目標の大きさ ------------------------------------------------------

def test_the_clickable_controls_reserve_at_least_the_minimum_target():
    """押すためにある部品に、24px以上の当たり判定が確保されていること。

    実測ではチェックボックス・ラジオが13×13pxだった。見た目を大きくすると
    画面の密度が変わるので、絵は18pxのまま**囲い(label)**を24pxにしてある。
    """
    assert re.search(r'input\[type="checkbox"\],\s*\n\s*input\[type="radio"\]\s*\{[^}]*'
                     r'width:\s*18px', STYLE_CSS), \
        "チェックボックス・ラジオの大きさの指定が消えています"
    for selector in (".mode-row label", ".checkbox-row label", ".grid-parts label"):
        assert _rule_blocks_for(selector), f"{selector} の規則が見当たりません"
        assert _declares(selector, f"min-height: {MIN_TARGET_PX}px"), \
            f"{selector} に min-height: {MIN_TARGET_PX}px がありません"


def test_the_navigation_and_footer_links_are_tall_enough():
    """ヘッダーのナビとフッターのリンクが24px以上あること。

    どちらも「並んだ導線」であって文章の中のリンクではないので、
    SC 2.5.8のInline例外には当たらない。実測は18px・14pxだった。
    """
    for selector in (".header-nav a", ".app-footer-links a"):
        assert _declares(selector, f"min-height: {MIN_TARGET_PX}px"), \
            f"{selector} の高さの手当てが消えています"


def test_a_link_alone_in_a_paragraph_counts_as_a_target():
    """段落に1つだけ置かれたリンクは、文章の中のリンクとして扱わないこと。

    ログイン画面の「パスワードをお忘れですか？」がこれ(実測19px)。
    一方「アカウントをお持ちでない方は〈無料登録〉」は文中なので
    `:only-child`にならず、この規則には当たらない——行間を広げると
    本文が読みにくくなるため、**わざと**触らない。
    """
    assert _rule_blocks_for("p > a:only-child"), \
        "段落に1つだけのリンクへの手当てが消えています"
    assert _declares("p > a:only-child", f"min-height: {MIN_TARGET_PX}px")


def test_the_form_controls_are_tall_enough():
    """数値入力とセレクトが32px以上あること(実測は19〜23px)。

    24pxちょうどではなく32pxにしてあるのは、採寸欄が9つ縦に並ぶ画面で
    指で押し分けられる間隔が要るため。
    """
    for selector in ('input[type="number"]', "select"):
        assert _declares(selector, "min-height: 32px"), \
            f"{selector} の高さ指定が消えています"


def test_the_pricing_call_to_action_is_a_target_not_a_sentence():
    """料金ページのCTAは押す帯なので、24px以上あること(実測21px)。"""
    assert _declares(".plan-cta", "min-height"), \
        "料金ページのCTAの高さの手当てが消えています"


def _rule_blocks_for(selector: str) -> list[str]:
    """CSSから、そのセレクタを含む規則の中身({...})を**すべて**取り出す。

    同じセレクタは複数の規則に現れる(例: `.header-nav a`は色の指定と
    round44の大きさの指定の両方にある)。最初の1つだけを見ると、
    直したことが見えないまま落ちる。
    """
    blocks = []
    idx = STYLE_CSS.find(selector)
    while idx != -1:
        brace = STYLE_CSS.find("{", idx)
        close = STYLE_CSS.find("}", brace)
        if brace != -1 and close != -1 and "}" not in STYLE_CSS[idx:brace]:
            blocks.append(STYLE_CSS[brace:close])
        idx = STYLE_CSS.find(selector, idx + 1)
    return blocks


def _declares(selector: str, declaration: str) -> bool:
    """そのセレクタに当たる規則のどれかが、その指定を持っているか。"""
    return any(declaration in block for block in _rule_blocks_for(selector))


# --- 状態の読み上げ ----------------------------------------------------------

def test_the_page_has_a_live_region_for_the_generation_status(client):
    """生成の進み具合を読み上げる領域があること(WCAG 2.1 SC 4.1.3)。

    round43までは`aria-live`が画面に1つも無く、スクリーンリーダーでは
    「型紙を生成する」を押しても**何も起きていないように聞こえた**。
    """
    body = client.get("/").get_data(as_text=True)
    assert 'id="result-status"' in body
    assert 'aria-live="polite"' in body
    assert 'role="status"' in body
    # 画面には出さない(見える表示はローディングと結果そのもの)。
    assert re.search(r'id="result-status"[^>]*class="visually-hidden"', body)


def test_the_error_message_announces_itself(client):
    """エラーは即時に読み上げられること。

    エラーはJSで後から書き込むので、role="alert"が無いと
    スクリーンリーダーには何も起きていないように聞こえる。
    """
    body = client.get("/").get_data(as_text=True)
    assert re.search(r'id="form-error"[^>]*role="alert"', body)


def test_the_script_announces_start_and_finish_and_failure():
    """開始・完了が読み上げられること。同じ文字列の連続も読み上げられること。"""
    assert "function announce(" in APP_JS
    assert "生成しています" in APP_JS
    assert "型紙ができました" in APP_JS
    # 同じ文字列を続けて入れると読み上げないブラウザがあるので、一度空にする。
    block = APP_JS.split("function announce(")[1].split("\n}")[0]
    assert 'region.textContent = ""' in block, \
        "同じ内容を続けて知らせたときに読み上げられない書き方に戻っています"


def test_the_finished_announcement_says_what_to_buy():
    """完了の読み上げが「何を買えばいいか」を先に言うこと。

    画面のいちばん上に置いてある情報(round34で決めた並び)と揃える。
    """
    # 「サイズ分の型紙ができました」(複数サイズ)ではなく、単サイズの方を見る。
    tail = APP_JS.split("`型紙ができました。")[1][:400]
    assert "part_count" in tail and "fabric_width_cm" in tail and "used_length_cm" in tail


# --- 入力の検証 --------------------------------------------------------------

def test_the_measurement_inputs_carry_the_engine_range(client):
    """採寸欄の min/max が、エンジンの有効範囲そのものであること。

    round43までは`required`だけで、単位・桁の間違い(身長1600cm)は
    サーバーへ往復してから初めてエラーになっていた。
    数値を画面に書き写すと範囲を動かしたときに食い違うので、
    `_VALID_RANGES`をそのまま渡している。
    """
    from engine.measurements import _VALID_RANGES

    body = client.get("/").get_data(as_text=True)
    for field in ("bust", "waist", "hip", "height", "sleeve_length",
                   "shoulder_width", "upper_arm", "bust_point_spacing",
                   "bust_point_drop"):
        lo, hi = _VALID_RANGES[field]
        pattern = (rf'id="field-{field}"[^>]*min="{lo}"[^>]*max="{hi}"'
                   rf'|id="field-{field}"[^>]*\n\s*min="{lo}" max="{hi}"')
        assert re.search(pattern, body), f"{field} の min/max が範囲と合っていません"


def test_every_form_control_on_the_main_page_has_a_name(client):
    """フォーム部品に、読み上げられる名前(label/aria-label)が付いていること。

    round37で3つ直したが、ファイル入力2つとバリエーションのセレクト4つが
    残っていた(round44の実測)。
    """
    body = client.get("/").get_data(as_text=True)
    for control_id in ("field-illustration", "field-illustration-back",
                        "field-include-body-garment"):
        # `data-for=` などに引っかからないよう、属性の切れ目まで見る。
        assert re.search(rf'<label[^>]*(?<![-\w]){re.escape("for")}="{control_id}"', body), \
            f"{control_id} を指すlabelが無い"
        assert re.search(rf'<(input|select|textarea)[^>]*id="{control_id}"', body), \
            f"{control_id} という部品が実在しない(labelの指し先が空)"
    for select_id in ("field-pants-style", "field-collar-style",
                       "field-cuffs-style", "field-waistband-style"):
        tag = re.search(rf'<select[^>]*id="{select_id}"[^>]*>', body)
        assert tag, f"{select_id} が見当たりません"
        assert re.search(r'(?<![-\w])aria-label="[^"]+"', tag.group(0)), \
            f"{select_id} に読み上げ用の名前が無い"


# --- キーボード --------------------------------------------------------------

def test_every_page_offers_a_skip_link_to_the_main_content():
    """どの画面にも、本文へ飛ぶリンクと飛び先があること。

    ヘッダーのナビを毎回たどらずに本題へ行けるようにする。
    ふだんは画面の外にあり、Tabでフォーカスが当たったときだけ現れる。
    """
    nav = (TEMPLATES / "_nav.html").read_text(encoding="utf-8")
    assert 'class="skip-link" href="#main-content"' in nav
    assert _declares(".skip-link:focus", "top: 0"), "フォーカスしても現れない書き方です"

    missing = []
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        if "<main" in text and 'id="main-content"' not in text:
            missing.append(path.name)
    assert missing == [], f"飛び先(id=main-content)が無い画面: {missing}"


def test_no_vague_link_text_is_left(client):
    """「こちら」だけのリンクを残さないこと。

    リンクの文言だけを拾って読む使い方(スクリーンリーダーのリンク一覧)では、
    「こちら」がいくつ並んでもどこへ行くか分からない。
    """
    for path in ("/", "/guide", "/pricing", "/login", "/signup"):
        body = client.get(path).get_data(as_text=True)
        assert not re.search(r">\s*(こちら|ここ|click here)\s*</a>", body), path
