"""round47: キーボードだけで通し、触っていなかった機能を実際に使って見つけたもの。

round46は「マウスで、目で見て」通した。round47は**マウスを一度も使わず**
Tab / 矢印 / Space / Enter だけで型紙を作り、そのあと、これまで一度も
触っていなかった機能(カスタムパーツ・手持ちの生地・生地の配置設定)を
実際に操作した。

見つかったもの:

  1. **「型紙を生成する」をEnterで押すと、フォーカスが消える。**
     実測: 押す前 BUTTON → 150ms後 **BODY** → 完了後も BODY。
     `beginGenerating()` がボタンを disabled にするので、フォーカスを
     持った要素が無効になり、ブラウザがフォーカスを文書へ落とす。
     キーボードだけで使うと現在地が失われ、スクリーンリーダーでは
     読み上げの起点が文書の先頭に戻る。
  2. **保存したプロフィールを読み込むと、採寸値の指摘が一度も走らない。**
     実測: ウエスト95・ヒップ70 を手で打つと
     「ヒップがウエストより細くなっています…履く動作が成り立ちません」
     が出るのに、**同じ値をプロフィールから読み込むと何も出ない**。
     `input.value = ...` の代入では change が飛ばないため。
  3. **その指摘の箱に読み上げの指定が無い。** round44で生成の進み具合は
     読み上げるようにしたのに、round33自身が「このサービスの最大の
     失敗要因」と書いている採寸ミスの指摘は、スクリーンリーダーでは
     一言も出ないままだった(WCAG 2.1 SC 4.1.3)。
  4. **カスタムパーツの採寸値セレクトに、読み上げ用の名前が無い。**
     名前の無い `<select>` は、ブラウザが選択肢を全部つなげたものを
     名前として読む——実測で「バストウエストヒップ身長袖丈肩幅
     コンボボックス」と読み上げられていた。round44で静的な画面の同種
     6件は直したが、この欄は押して初めて作られるので調査に入っていなかった。
"""

import pathlib
import re

import app as app_module

STATIC = pathlib.Path(app_module.BASE_DIR) / "web" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


# --- 1. 押したあと、フォーカスが迷子にならない -----------------------------

def test_focus_leaves_the_button_before_it_is_disabled():
    """ボタンを無効にする**前**に、フォーカスを逃がしていること。

    順番が逆だと、無効にした瞬間にブラウザがフォーカスを <body> へ落とす。
    後から拾い直しても、その間の一瞬は現在地が無い。
    """
    block = APP_JS.split("function beginGenerating(")[1].split("\n}\n")[0]
    move_at = block.find("moveFocusTo(")
    disable_at = block.find("submitButton.disabled = true")
    assert move_at != -1, "フォーカスを移す処理がありません"
    assert disable_at != -1
    assert move_at < disable_at, \
        "無効にしてからフォーカスを移しています(その瞬間に <body> へ落ちます)"


def test_the_focus_target_is_the_result_heading(client):
    """行き先は結果の見出しで、Tab順には入らないこと。

    `tabindex="-1"` にするのは、JSから当てられるが Tab では素通りさせる
    ため。見出しがTab順に入ると、押していない人にとって余計な停留点になる。
    """
    body = client.get("/").get_data(as_text=True)
    assert re.search(r'<h2 id="result-heading" tabindex="-1">', body)
    block = APP_JS.split("function beginGenerating(")[1].split("\n}\n")[0]
    assert '"result-heading"' in block


def test_the_focus_is_only_moved_when_it_was_on_the_button():
    """フォーカスがボタンに無いときは、奪わないこと。

    採寸欄を打っている途中に(別経路で)生成が走っても、
    打っている場所からフォーカスを取り上げない。
    """
    block = APP_JS.split("function beginGenerating(")[1].split("\n}\n")[0]
    assert "document.activeElement === submitButton" in block


def test_a_programmatic_focus_does_not_scroll_on_its_own():
    """フォーカスを当てるときに、ブラウザに勝手に寄せさせないこと。

    直後に `scrollResultIntoView()` が位置を決めるので、二重に動くと
    round46で直した着地位置が崩れる。
    """
    block = APP_JS.split("function moveFocusTo(")[1].split("\n}\n")[0]
    assert "preventScroll: true" in block
    # 古いブラウザ向けの退避があること(preventScrollを解さない実装がある)。
    assert "catch" in block


def test_a_failure_returns_the_focus_to_the_button():
    """失敗したときは、もう一度押せる場所へフォーカスを返すこと。"""
    tail = APP_JS.split("型紙を作れませんでした")[1][:600]
    assert "moveFocusTo(submitButton)" in tail, \
        "失敗するとフォーカスが <body> に落ちたままになります"


# --- 2. プロフィールを読み込んだときも、採寸値を見直すこと -------------------

def test_loading_a_profile_notifies_the_fields_it_changed():
    """プロフィール読込が、値を入れた欄に change を投げること。

    `value` の代入だけではブラウザは change を投げないので、
    採寸値の指摘(round33)がこの経路でだけ一度も走らなかった。
    個別に関数を呼ぶのではなくイベントを投げるのは、この欄を見ている
    処理が増えても勝手に動くようにするため。
    """
    handler = APP_JS.split("profileSelect.addEventListener(\"change\"")[1].split("\n});")[0]
    assert "input.value = option.dataset[field]" in handler
    assert 'new Event("change"' in handler, \
        "値を入れるだけで、採寸値の見直しが走らない書き方に戻っています"
    assert "bubbles: true" in handler


def test_the_measurement_check_listens_for_change():
    """採寸値の指摘が change を聞いていること(投げる側と受ける側の対)。"""
    assert 'input.addEventListener("change", refreshMeasurementHints)' in APP_JS


# --- 3. 採寸値の指摘が読み上げられること -----------------------------------

def test_the_measurement_hint_box_is_a_live_region(client):
    """採寸値の指摘に、読み上げの指定があること。

    この指摘は「欄から離れた瞬間に画面へ現れる」ので、目で見ていなければ
    気づけない。round33自身が、採寸ミスはこのサービスの最大の失敗要因だと
    書いている(WCAG 2.1 SC 4.1.3 Status Messages)。
    """
    body = client.get("/").get_data(as_text=True)
    tag = re.search(r'<div id="measurement-hints"[^>]*>', body)
    assert tag, "採寸値の指摘の箱が見当たりません"
    assert 'role="status"' in tag.group(0)
    assert 'aria-live="polite"' in tag.group(0)


def test_the_hints_are_filled_in_before_the_box_is_revealed():
    """中身を入れてから見せること。

    先に空の箱を見せてから足すと、読み上げを取りこぼすことがある。
    """
    block = APP_JS.split("async function refreshMeasurementHints(")[1].split("\n}\n")[0]
    fill = block.find("measurementHintList.appendChild")
    reveal = block.find('measurementHintBox.classList.toggle("hidden"')
    assert fill != -1 and reveal != -1
    assert fill < reveal, "空の箱を見せてから中身を入れる順に戻っています"


# --- 4. 押して初めて作られる欄にも、名前があること -------------------------

def test_every_dynamically_built_control_has_a_name():
    """カスタムパーツの中の部品に、読み上げ用の名前があること。

    この欄は「＋カスタムパーツを追加」を押して初めて作られるので、
    round44の静的な調査には入っていなかった。名前の無い `<select>` は、
    ブラウザが選択肢を全部つなげたものを名前として読む。
    """
    block = APP_JS.split("const measurementFieldBox = document.createElement")[1][:700]
    assert 'measurementSelect.setAttribute("aria-label"' in block, \
        "流用する採寸値のセレクトに、読み上げ用の名前がありません"
    # 近くの数値欄にも名前があること(こちらは元からある)。
    assert 'referenceCmInput.setAttribute("aria-label"' in APP_JS


def test_no_control_in_the_custom_panel_is_named_only_by_its_placeholder():
    """placeholder だけを頼りにした部品が無いこと。

    placeholder は打ち始めると消えるし、読み上げも実装によって違う。
    このパネルの部品は、aria-label か画面上のラベルを持つこと。
    """
    section = APP_JS.split("function createCustomPanelCard")[1] if \
        "function createCustomPanelCard" in APP_JS else APP_JS
    # placeholder を付けている入力は、同じ変数に aria-label も付けていること。
    for match in re.finditer(r"(\w+)\.placeholder = ", section):
        name = match.group(1)
        assert f'{name}.setAttribute("aria-label"' in section, \
            f"{name} が placeholder だけで名乗っています"
