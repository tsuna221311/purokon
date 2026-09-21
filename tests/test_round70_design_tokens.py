"""round70: 押すボタンが3画面下にあり、色は16進で73か所に散らばっていた。

コスプレイヤーとして使い直して、2つのことが同時に効いているのが分かった。

【実測1】いちばん押してほしいボタンが、画面3.3枚ぶん下にあった

    1440x900   「型紙を生成する」の y = 2,965px（3.3画面ぶん下）
      390x844   同                 y = 4,253px（5.0画面ぶん下）
    必須の採寸欄が終わるのは y = 923px

必須の入力（採寸6つ）を終えたあと、**任意の設定が2,042px続いてから**
ようやくボタンに届く。初めて使う人は、途中で「まだ何か入れないと
いけないのか」と思って手が止まる。ボタンを画面の下へ貼り付けた
(`.action-bar`)。

【実測2】状態の色が、HTMLとJavaScriptに16進で73か所

    web/templates/index.html   43か所（style="color:#1d4ed8" など）
    web/static/app.js          30か所（el.style.color = "#92400e" など）

直接書いてあると、(1)配色を変えるたび全部を探し直すことになり、
(2)**ダークモードが原理的に作れない**。地の色だけ暗くしても、
文字色は明るい画面向けのまま取り残される。実際、暗い画面にして
みると濃い茶色の注記が濃い地に乗って読めなかった。

名前（CSSトークン）にして1か所へ集め、状態は fg/bg/bd の3つ揃いで
持たせた。生成り＋藍という今の個性は変えていない。

このファイルが見張るのは:

  1. 状態の色を、またHTML/JSに16進で直接書く
  2. 3つ揃い（文字・地・枠）のどれかが片方のモードで欠ける
  3. 押すボタンが、貼り付けの外へ戻る
  4. 明るい画面を前提にした `white` が、面や文字に戻る
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "web" / "static" / "style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")
_APP_JS_RAW = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def _strip_js_comments(source: str) -> str:
    """// と /* */ を落とす(round65・round69の教訓)。

    コメントを残したまま文字列を探すと、**呼び出しをコメントアウト
    しただけで通ってしまう**。逆に、コメントの中に書いた16進が
    「まだ直っていない」ように見えるのも困る。
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//")[0] for line in source.splitlines())


APP_JS = _strip_js_comments(_APP_JS_RAW)

#: 状態の色。fg=文字 / bg=地 / bd=枠 の3つで1つの意味を表す。
STATUS_ROLES = ("info", "warn", "danger", "success", "plan")

#: 型紙のプレビューと、カスタムパーツを描くcanvas。どちらも
#: **白い紙の上の図**として描くと決めている(暗い画面でも紙は白い)。
#: ここだけは16進を直に書いてよい、と決めた場所である。
CANVAS_ALLOWED = ("#faf9f6", "#e7e2d9", "#1e293b", "#fff", "#16a34a",
                  "#dc2626", "#2563eb")


# --- 1. 状態の色を、HTML/JSに直接書かない -----------------------------------

def test_the_template_has_no_inline_hex_colours():
    """index.html の style="" に16進の色を書かないこと。

    round69では43か所あった。1か所でも戻ると、そこだけ暗い画面で
    取り残される。
    """
    found = re.findall(r'style="[^"]*#[0-9a-fA-F]{3,8}[^"]*"', INDEX)
    assert found == [], found


def test_the_screen_code_sets_status_colours_by_class_not_by_hex():
    """app.js が `style.color = "#..."` で状態の色を塗らないこと。

    canvas の描画(型紙の下絵)は白い紙の上の図なので別扱いにする。
    見張るのは **DOMの要素に色を塗る**書き方だけ。
    """
    offenders = []
    for m in re.finditer(r'\.style\.(?:color|backgroundColor|borderColor)\s*=\s*'
                         r'([^;\n]+)', APP_JS):
        expr = m.group(1)
        if "#" in expr:
            offenders.append(expr.strip())
    assert offenders == [], offenders


def test_cssText_does_not_carry_status_colours():
    """`style.cssText` に紛れ込ませる抜け道も塞ぐ。"""
    offenders = [m.group(0) for m in re.finditer(r'cssText\s*=[^\n]*#[0-9a-fA-F]{3,8}',
                                                 APP_JS)]
    assert offenders == [], offenders


def test_the_canvas_hexes_are_the_only_ones_left_in_the_screen_code():
    """残っている16進が、白い紙の上の図の分だけであること。

    「全部消した」で終わらせず、**残したものを数える**。ここが
    増えていたら、誰かが別の場所に色を直書きしている。
    """
    hexes = set(re.findall(r'"(#[0-9a-fA-F]{3,8})"', APP_JS))
    assert hexes <= set(CANVAS_ALLOWED), sorted(hexes - set(CANVAS_ALLOWED))


# --- 2. 3つ揃いが、明暗どちらでも欠けない ------------------------------------

def _token_block(selector_start: str) -> str:
    i = CSS.index(selector_start)
    return CSS[i:CSS.index("}", i)]


def test_both_schemes_define_every_status_triple():
    """明るい画面と暗い画面の両方で、fg/bg/bd が3つとも定義されていること。

    1つでも欠けると、その役割だけ**もう一方のモードの値**が残る。
    文字だけ暗いまま、地だけ明るいまま、という壊れ方をする。
    """
    light = _token_block(":root {")
    i = CSS.index("@media (prefers-color-scheme: dark)")
    dark = CSS[i:CSS.index("\n}\n", i)]
    for role in STATUS_ROLES:
        for part in ("fg", "bg", "bd"):
            name = f"--{role}-{part}:"
            assert name in light, f"明るい画面に {name} が無い"
            assert name in dark, f"暗い画面に {name} が無い"


def test_dark_mode_follows_the_os_and_has_no_manual_toggle():
    """OSの設定に追従すること(手動の切り替えは置かないと決めた)。"""
    assert "@media (prefers-color-scheme: dark)" in CSS
    # 切り替えボタンを置くなら、この見張りごと書き換えること。
    assert "theme-toggle" not in INDEX
    assert "theme-toggle" not in APP_JS


def test_the_accent_has_a_matching_ink_colour():
    """操作の色の上に載せる文字の色を、モードごとに持つこと。

    暗い画面では操作の色そのものが明るくなる(#9fb0ef)。そこへ
    白い文字を載せると 2.11:1 しか無く読めない(実測)。
    """
    assert "--accent-ink:" in _token_block(":root {")
    i = CSS.index("@media (prefers-color-scheme: dark)")
    assert "--accent-ink:" in CSS[i:CSS.index("\n}\n", i)]
    assert ".btn-solid { background: var(--accent); color: var(--accent-ink);" in CSS


# --- 3. 押すボタンは、画面の下に貼り付いている -------------------------------

def test_the_submit_button_lives_in_the_sticky_action_bar():
    """「型紙を生成する」が `.action-bar` の中にあること。

    実測: round69では 1440x900 で y=2,965px（3.3画面ぶん下）にあった。
    必須の採寸欄が終わるのは y=923px なので、その間の2,042pxは
    **全部任意の設定**である。
    """
    i = INDEX.index('<div class="action-bar">')
    j = INDEX.index("</div>", INDEX.index('button', i))
    bar = INDEX[i:j]
    assert 'class="primary"' in bar or "primary" in bar
    assert "型紙を生成する" in bar


def test_the_action_bar_is_actually_sticky():
    block = _token_block(".action-bar {")
    assert "position: sticky" in block
    assert "bottom: 0" in block
    # 透ける地は、backdrop-filter が無いブラウザだと読めなくなる。
    assert "@supports not (backdrop-filter" in CSS


def test_the_error_text_stays_with_the_button():
    """送信できなかった理由が、ボタンと一緒に見えること。

    貼り付けたボタンだけが見えていて、理由がページの上の方に
    出ていると、押しても何も起きないように見える。
    """
    i = INDEX.index('<div class="action-bar">')
    j = INDEX.index("</form>", i)
    assert 'id="form-error"' in INDEX[i:j]


# --- 4. 明るい画面を前提にした指定を戻さない --------------------------------

def test_no_bare_white_backgrounds_outside_the_paper():
    """`background: white` を面に使わないこと。

    暗い画面でそこだけ白い箱になる。実測で、パーツ一覧のチップ・
    形の見本・枠線ボタン・削除ボタンの4か所がそうなっていた。
    """
    offenders = re.findall(r"background:\s*(?:white|#fff|#ffffff)\s*;", CSS)
    # ヘッダーの中の白い丸ボタン(.nav-cta)だけは、暗い帯の上の白なので
    # 明暗どちらでも同じ見え方が正しい。
    assert len(offenders) == 1, offenders
    i = CSS.index(".nav-cta {")
    assert "background: #ffffff;" in CSS[i:CSS.index("}", i)]


def test_no_bare_white_text_on_the_accent():
    """操作の色の上の文字に `white` を直書きしないこと。"""
    assert not re.search(r"color:\s*white\s*;", CSS)


def test_the_status_boxes_use_the_component_classes():
    """状態の箱が、クラスで色を持っていること。

    16進を消しただけで**色が何も付かなくなる**直し方をしていない
    ことを確かめる。round69に出ていた箱がそのまま残っている。
    """
    for element_id, cls in [
        ("measurement-hints", "note-warn"),
        ("unplaced-warning", "note-danger"),
        ("measurement-clamp-warning", "note-danger"),
        ("design-note", "note-info"),
        ("dart-note", "note-info"),
        ("compatibility-warning", "note-warn"),
        ("multi-size-totals", "note-info"),
        ("grading-precision-note", "note-info"),
        ("fabric-groups-box", "note-plan"),
        ("lining-box", "note-info"),
        ("rotation-warning", "note-warn"),
        ("size-consistency-warning", "note-warn"),
        ("multi-size-note", "note-warn"),
    ]:
        m = re.search(rf'id="{element_id}"[^>]*class="([^"]*)"', INDEX)
        if m is None:
            m = re.search(rf'class="([^"]*)"[^>]*id="{element_id}"', INDEX)
        assert m, element_id
        assert cls in m.group(1), (element_id, m.group(1))


def test_the_multi_size_notes_pick_a_tone_by_name():
    """サイズ展開の警告も、色ではなく**意味**で指定していること。"""
    i = APP_JS.index("const noteGroups = [")
    block = APP_JS[i:APP_JS.index("];", i)]
    assert '"danger"' in block
    assert '"info"' in block
    assert "#" not in block


def test_setNoteTone_clears_the_previous_tone():
    """色を塗り替えるとき、前の色を消してから付けること。

    消さずに足すと、一度「足りません(橙)」を出した箱が
    「足ります(緑)」になったときに2つのクラスが重なり、
    CSSの後勝ちで**意味と色が食い違う**。
    """
    i = APP_JS.index("function setNoteTone")
    block = APP_JS[i:APP_JS.index("\nfunction ", i + 10)]
    assert "classList.remove" in block
    assert "NOTE_TONES" in block


# --- 5. 測る道具の側 ---------------------------------------------------------

def test_the_contrast_audit_can_measure_the_dark_scheme():
    """コントラストの台本が、暗い画面も測れること。

    明るい側だけ測っていると、暗い側は誰も見ていないのと同じである。
    既定で両方測る。
    """
    audit = (ROOT / "scripts" / "audit_contrast.py").read_text(encoding="utf-8")
    assert '"--scheme", default="both"' in audit
    assert 'color_scheme=scheme' in audit
    assert '"light", "dark"' in audit
