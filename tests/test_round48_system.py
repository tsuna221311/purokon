"""round48: システムの表面を実際に叩いて見つけたものと、結果パネルの見え方。

round47まではUIばかり見ていた。round48は**システムとして**の振る舞い——
ヘッダー・キャッシュ・エラー応答・同時実行——を、実際にHTTPで叩いて測った。

見つかったもの:

  1. **静的ファイルを毎回サーバへ確認しに行っていた。** 寿命を指定して
     いなかったのでFlask既定の `Cache-Control: no-cache` が付き、実測で

         1回目: /static/ へ 20リクエスト
         2回目: /static/ へ 20リクエスト(**全部304**)

     中身は配信し直すまで1バイトも変わらないのに、開くたびに20往復していた。
  2. **`PATTERNFORGE_FORCE_HTTPS=1` でもHSTSを送っていなかった。**
     その切り替えでCookieのSecureは付けていたのに、
     `Strict-Transport-Security` は一度も出ていなかった。
  3. **405だけ手当てが無く、Flask既定の英語ページが出ていた**
     (`<title>405 Method Not Allowed</title>`)。404・413・500には
     日本語の手当てがあった。
  4. **今どきの防御ヘッダーが3つ無かった**(Permissions-Policy /
     Cross-Origin-Opener-Policy / Cross-Origin-Resource-Policy)。
  5. **結果の半分が画面の外にあるのに、その合図が無かった。**
     1440×950で実測すると 見えている918px / 中身1836px で、
     隠れている側に縫う順番・パーツ一覧・買い物メモが全部入っていた。
"""

import os
import pathlib
import re
import subprocess
import sys

import pytest

import app as app_module

STATIC = pathlib.Path(app_module.BASE_DIR) / "web" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
STYLE_CSS = (STATIC / "style.css").read_text(encoding="utf-8")


# --- 1. 静的ファイルのキャッシュ -------------------------------------------

def test_static_urls_carry_a_version_derived_from_the_file(client):
    """静的ファイルのURLに、中身から決まる版が付くこと。"""
    body = client.get("/").get_data(as_text=True)
    urls = re.findall(r'/static/([^"\'?\s]+)\?v=([0-9a-f]+)', body)
    assert urls, "静的ファイルのURLに版が付いていません"
    # ページの中の静的ファイルは全部版つきであること(付け忘れを許さない)。
    bare = re.findall(r'/static/([^"\'?\s]+)(?=["\'])', body)
    assert bare == [], f"版の付いていない静的URLが残っています: {bare[:5]}"


def test_the_version_changes_when_the_file_changes(tmp_path):
    """中身が変われば版が変わり、変わらなければ同じであること。"""
    target = STATIC / "style.css"
    before = app_module._static_asset_version("style.css")
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n/* round48 */\n")
        app_module._static_asset_version.cache_clear()
        after = app_module._static_asset_version("style.css")
        assert after != before, "中身を変えても版が変わりません"
    finally:
        target.write_bytes(original)
        app_module._static_asset_version.cache_clear()
    # 同じ中身なら、呼び直しても同じ版。
    assert app_module._static_asset_version("style.css") == \
        app_module._static_asset_version("style.css")


def test_a_missing_static_file_gets_no_version():
    """無いファイルには版を付けないこと(404はそのまま404にする)。"""
    assert app_module._static_asset_version("no-such-file.css") == ""
    with app_module.app.test_request_context():
        from flask import url_for
        assert "?v=" not in url_for("static", filename="no-such-file.css")


def test_static_files_are_cacheable_for_a_long_time(client):
    """版つきURLは長くキャッシュしてよいこと。

    版が変われば別のURLになるので、古いものが残り続けることはない。
    """
    assert app_module.app.config["SEND_FILE_MAX_AGE_DEFAULT"] >= 30 * 24 * 3600
    response = client.get("/static/style.css")
    cache = response.headers.get("Cache-Control", "")
    assert "max-age=" in cache and "no-cache" not in cache, cache


# --- 2. HSTS ---------------------------------------------------------------

def test_hsts_is_sent_only_when_https_is_declared():
    """HTTPSで運用すると宣言したときだけHSTSを送ること。

    平文で送っても意味が無く、ローカル開発をHTTPSに縛ってしまう。
    """
    script = (
        "import os, sys; sys.path.insert(0, %r); os.environ['SECRET_KEY']='test';\n"
        "os.environ['PATTERNFORGE_FORCE_HTTPS']=%r;\n"
        "import app as A;\n"
        "c = A.app.test_client();\n"
        "print(c.get('/').headers.get('Strict-Transport-Security', ''))\n"
    )
    for flag, expect in (("0", False), ("1", True)):
        out = subprocess.run(
            [sys.executable, "-c", script % (app_module.BASE_DIR, flag)],
            capture_output=True, text=True).stdout.strip()
        if expect:
            assert "max-age=" in out and "includeSubDomains" in out, out
            # 取り消しにくい preload は、運用する人が選ぶもの。勝手に付けない。
            assert "preload" not in out
        else:
            assert out == "", f"平文なのにHSTSを送っています: {out}"


# --- 3. 405 ----------------------------------------------------------------

def test_a_wrong_method_answers_in_this_products_language(client):
    """405が、枠組み既定の英語ページにならないこと。"""
    response = client.get("/api/generate")
    assert response.status_code == 405
    body = response.get_data(as_text=True)
    assert "Method Not Allowed" not in body, "Flask既定の英語ページが出ています"
    assert response.get_json()["ok"] is False
    assert "メソッド" in response.get_json()["error"]


def test_a_wrong_method_on_a_page_returns_the_styled_page(client):
    """画面側の405も、この製品の見た目で返すこと。"""
    response = client.post("/guide", headers={"Accept": "text/html"})
    assert response.status_code in (405, 400)
    if response.status_code == 405:
        assert "Method Not Allowed" not in response.get_data(as_text=True)


# --- 4. 防御ヘッダー --------------------------------------------------------

@pytest.mark.parametrize("header, must_contain", [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin"),
    ("Content-Security-Policy", "default-src 'self'"),
    ("Permissions-Policy", "camera=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
])
def test_the_response_carries_its_defensive_headers(client, header, must_contain):
    value = client.get("/").headers.get(header, "")
    assert must_contain in value, f"{header}: {value!r}"


def test_the_download_keeps_its_stricter_headers(client):
    """個別にもっと厳しくしている応答を、共通の設定で緩めないこと。

    `setdefault` で足しているのは、/download が自分で付ける
    `Cache-Control: private, no-store` を上書きしないため。
    """
    source = pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    block = source.split("def _set_security_headers(")[1].split("\ndef ")[0]
    assert "headers[" not in block.replace("headers.setdefault(", ""), \
        "共通のヘッダー設定が、個別の指定を上書きする書き方になっています"


# --- 5. 結果パネルの「まだ下がある」合図 ------------------------------------

def test_the_panel_tells_you_when_there_is_more_below():
    """あふれていて、かつ下まで読んでいないときだけ合図を出すこと。"""
    block = APP_JS.split("function updateResultPanelOverflowHint(")[1].split("\n}\n")[0]
    assert "scrollHeight" in block and "clientHeight" in block
    assert "scrollTop" in block, "下まで読んだかを見ていません"
    assert 'classList.toggle("has-more-below"' in block
    # 小数の丸めで1〜2px余るだけの場合に出さない余裕があること。
    assert re.search(r">\s*8\b", block), "丸め誤差の余裕がありません"


def test_the_hint_is_kept_up_to_date():
    """スクロール・画面の大きさ・中身の入れ替えのすべてで見直すこと。"""
    assert 'resultPanel.addEventListener("scroll", updateResultPanelOverflowHint' in APP_JS
    assert 'window.addEventListener("resize", updateResultPanelOverflowHint)' in APP_JS
    # 「ResizeObserver という語がある」だけでは、条件を `if (false)` に
    # 書き換えても通ってしまう(実際にそれで素通りした)。見張りを**作って
    # いる**ことと、それがこのパネルを**見ている**ことの両方を確かめる。
    wiring = APP_JS.split("if (resultPanel) {")[-1]
    assert re.search(r'typeof ResizeObserver === "function"', wiring), \
        "ResizeObserverの有無を見る分岐がありません"
    assert re.search(r"new ResizeObserver\(updateResultPanelOverflowHint\)"
                     r"\.observe\(resultPanel\)", wiring), \
        "結果が差し込まれて高さが変わったときに見直していません"
    # 分岐を殺していないこと。
    assert "if (false)" not in wiring


def test_the_hint_is_drawn_over_the_content_not_behind_it():
    """合図を、中身の上に重ねて描くこと。

    最初 `background-image` で書いたが、背景は中身の**下**に描かれるので
    パーツ図や表に隠れて見えなかった(実測: 下端の明るさが247.4→246.2と
    1しか変わらなかった)。`position: sticky` の `::after` に作り直した。
    """
    block = STYLE_CSS.split(".layout > .panel.has-more-below::after")[1].split("}")[0]
    assert "position: sticky" in block
    assert "bottom: 0" in block
    assert "pointer-events: none" in block, "合図が操作の邪魔をします"
    # 自分の高さの分だけ中身が伸びないこと。
    assert re.search(r"height:\s*(\d+)px", block)
    assert re.search(r"margin-top:\s*-(\d+)px", block)
    height = int(re.search(r"height:\s*(\d+)px", block).group(1))
    pull = int(re.search(r"margin-top:\s*-(\d+)px", block).group(1))
    assert height == pull, "合図の分だけ中身が長くなります"


def test_the_hint_only_applies_where_the_panel_scrolls_itself():
    """1段組(狭い画面)には合図を出さないこと。そこでは自前でスクロールしない。"""
    idx = STYLE_CSS.index(".layout > .panel.has-more-below::after")
    before = STYLE_CSS[:idx]
    assert before.rstrip().endswith("{") or "@media (min-width: 1024px)" in before[-400:], \
        "合図の規則が、2段組の幅に限定されていません"
