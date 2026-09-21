"""round45: 失敗したときに何が起きるか——画面を実際に止めて測った。

round44までこの製品は「うまくいったとき」ばかり見ていた。round45は
**わざと失敗させて**、そのとき利用者に何が見えるかを測った。

【実測した状態】Playwrightで通信を切る・壊れた応答を返す・応答を返さない、
をそれぞれ再現して、画面に出た文字をそのまま読んだ:

  通信が切れた   → 「Failed to fetch」
  502(HTMLが返る) → 「Unexpected token '<', "<html><bod"... is not valid JSON」
  応答が来ない    → **60秒待ってもボタンは「生成中です…」のまま disabled**

家庭で服を縫う人に向けた日本語の製品で、失敗したときにだけ英語の
パーサのメッセージが出ていた。原因は3か所とも同じ書き方にある:

    const data = await response.json();          // ← ifより先に走る
    if (!response.ok) throw new Error(data.error || "…日本語…");

`response.json()` が先なので、JSONでない応答が来た時点で例外になり、
**用意してあった日本語の文言に到達する経路が無かった**。

さらに、round44で置いた読み上げ領域が**失敗のときだけ何も言わず**、
「型紙を生成しています。しばらくお待ちください。」が残り続けていた。
スクリーンリーダーでは、失敗したことすら分からない。

このテストはブラウザを起動せずに回せるよう、JSの中身を読んで確かめる
(実際に止めて測る台本は `scripts/audit_failure_paths.py`)。
"""

import pathlib
import re

import app as app_module

STATIC = pathlib.Path(app_module.BASE_DIR) / "web" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
STYLE_CSS = (STATIC / "style.css").read_text(encoding="utf-8")


# --- 失敗の文言 --------------------------------------------------------------

def test_no_fetch_call_parses_the_body_before_checking_the_status():
    """`response.json()` を直に await して、その後で状態を見る書き方が無いこと。

    この書き方が1か所でも残っていると、JSONでない応答(502のHTML、空の本文、
    プロキシのエラーページ)でその場で例外になり、日本語の文言へ行き着かない。
    """
    code = _without_comments(APP_JS)
    offenders = []
    for match in re.finditer(r"await\s+response\.json\(\)", code):
        head = code[:match.start()]
        # readJsonOrThrow の中の1件は、直後に状態を見るので正当。
        opened = head.rfind("async function readJsonOrThrow")
        if opened != -1 and head.find("\n}", opened) == -1:
            continue
        # それ以外は、同じtryの中で本文を解く前に状態を見ていること。
        try_start = head.rfind("try {")
        window = head[try_start:] if try_start != -1 else head[-400:]
        if "response.ok" not in window and "response.status" not in window:
            offenders.append(code[:match.start()].count("\n") + 1)
    assert offenders == [], \
        f"状態を見る前に本文を解いている箇所が残っています(行 {offenders})"


def _without_comments(src: str) -> str:
    """JSのコメントを取り除く。

    この検査は「書き方」を見るものなので、**説明として引用した悪い例**まで
    拾ってしまわないようにする(このテストを書いたとき、実際に自分の
    コメントに書いた悪い例を製品の不具合として報告してしまった)。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_the_failure_messages_are_japanese():
    """通信の失敗に、日本語の文言が用意されていること。

    文字列を探すのではなく、**その関数を実際に走らせて**返り値を見る。
    最初はソースに "TypeError" と書いてあるかを見ていたが、条件を
    `if (false)` に書き換えても通ってしまい、回帰を捕まえられなかった。
    """
    out = _run_js("""
      const fetchFailure = new TypeError("Failed to fetch");
      console.log(JSON.stringify({
        network: describeFetchFailure(fetchFailure, "予備の文言"),
        aborted: describeFetchFailure(
          Object.assign(new Error("時間切れです"), {name: "AbortError"}), "予備の文言"),
        other:   describeFetchFailure(new Error("サーバーからの文言"), "予備の文言"),
      }));
    """)
    # fetch が通信障害で投げるのは TypeError("Failed to fetch")。
    assert out["network"] == ("サーバーに接続できませんでした。"
                             "通信の状態を確かめて、もう一度お試しください。"), \
        f"通信断のときに英語のままです: {out['network']}"
    assert "Failed to fetch" not in out["network"]
    # 中断(上限)のときは、こちらで用意した日本語をそのまま使う。
    assert out["aborted"] == "時間切れです"
    # サーバーが日本語の文言を返したときは、それを尊重する。
    assert out["other"] == "サーバーからの文言"


def test_a_broken_response_becomes_a_japanese_sentence():
    """JSONでない応答が、日本語の文になること。実際に走らせて確かめる。

    実測で画面に出ていたのは
    「Unexpected token '<', "<html><bod"... is not valid JSON」だった。
    """
    out = _run_js("""
      const bad = {status: 502, ok: false, json: async () => { JSON.parse("<html>"); }};
      const empty = {status: 504, ok: false, json: async () => { JSON.parse(""); }};
      const over = {status: 413, ok: false, json: async () => { JSON.parse("<"); }};
      (async () => {
        const grab = async r => {
          try { await readJsonOrThrow(r, "型紙の生成に失敗しました。"); return "(例外なし)"; }
          catch (e) { return e.message; }
        };
        console.log(JSON.stringify({
          bad: await grab(bad), empty: await grab(empty), over: await grab(over),
        }));
      })();
    """)
    for key, text in out.items():
        assert "Unexpected token" not in text and "not valid JSON" not in text, \
            f"{key}: パーサの英語がそのまま出ています: {text}"
        assert "型紙" in text or "大きすぎます" in text, f"{key}: 日本語になっていません: {text}"
    assert "502" in out["bad"], "どのHTTP状態だったかが分からない文になっています"
    assert "大きすぎます" in out["over"], "413(大きすぎる)の案内が消えています"


def _run_js(snippet: str) -> dict:
    """app.js の純粋な関数だけを取り出してNodeで走らせ、JSONを読む。

    app.js は全体としてDOMを触るので丸ごとは読めない。ここで見たいのは
    「通信の失敗を文言に変える」部分だけなので、その関数だけを切り出す。
    """
    import json
    import shutil
    import subprocess
    import textwrap

    node = shutil.which("node")
    if node is None:                                  # pragma: no cover
        import pytest
        pytest.skip("nodeが無い環境では、この振る舞いの確認はできない")

    start = APP_JS.find("[失敗の文言:ここから]")
    end = APP_JS.find("[失敗の文言:ここまで]")
    assert start != -1 and end > start, \
        "app.js の「失敗の文言」の印が消えています(テストが切り出せません)"
    # 印はどちらもコメントの中にあるので、開きコメントの `*/` の後ろから、
    # 閉じ印のコメントが始まる `/*` の手前までを取る。
    block = APP_JS[APP_JS.index("*/", start) + 2:end].rsplit("/*", 1)[0]
    program = block + "\n" + textwrap.dedent(snippet)
    proc = subprocess.run([node, "-e", program], capture_output=True, text=True)
    assert proc.returncode == 0, f"Nodeでの実行に失敗:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_every_fetch_site_uses_the_shared_reader():
    """3か所のfetchが、すべて共通の読み取りを通ること。

    round44までは3か所が同じ誤った書き方を各自に持っていた。1か所直して
    他が残る事故を防ぐため、まとめてある。
    """
    for endpoint in ("/api/generate", "/api/custom-panel/trace", "/api/profiles"):
        idx = APP_JS.find(f'fetch("{endpoint}"')
        assert idx != -1, f"{endpoint} を呼ぶ箇所が見当たりません"
        following = APP_JS[idx:idx + 400]
        assert "readJsonOrThrow" in following, \
            f"{endpoint} が共通の読み取りを通っていません"


def test_the_raw_response_body_is_not_shown_to_the_user():
    """壊れた応答の中身を、そのまま画面に出さないこと。

    サーバーやプロキシの内部事情(スタックトレース、内部URL)が
    漏れるのを防ぐ。状態コードだけを使って文を作る。
    """
    block = APP_JS.split("async function readJsonOrThrow(")[1].split("\n}")[0]
    assert "parseError" in block
    assert "parseError.message" not in block, \
        "パーサの英語メッセージを画面に出す書き方に戻っています"


# --- 失敗の読み上げ ----------------------------------------------------------

def test_a_failure_is_announced_too():
    """失敗も読み上げること(round44は開始と完了しか言わなかった)。

    round44のテストは名前が `..._start_and_finish_and_failure` だったのに、
    **失敗を確かめていなかった**。名前が約束していたことを、ここで見る。
    """
    catch_block = APP_JS.split('showError(message, err.upgradeUrl)')[1][:400]
    assert "announce(" in catch_block, \
        "生成に失敗したとき、読み上げ領域が「生成中」のまま残ります"
    assert "型紙を作れませんでした" in APP_JS


# --- 応答が返ってこないとき --------------------------------------------------

def test_the_request_gives_up_and_returns_control():
    """応答が返らないとき、操作を取り戻せること。

    実測では60秒待ってもボタンは disabled のままで、再読み込みしか
    手が無かった——そして再読み込みすると採寸値が全部消える。
    """
    assert "GENERATE_TIMEOUT_MS" in APP_JS
    assert "AbortController" in APP_JS
    block = APP_JS.split("function startGenerateTimeout(")[1].split("\n}\n")[0]
    assert "controller.abort(" in block
    # 中断の理由が日本語であること(既定のDOMExceptionは英語)。
    assert "GENERATE_TIMEOUT_MESSAGE" in block
    # 送信側が signal を渡していること。
    gen = APP_JS.split('fetch("/api/generate"')[1][:200]
    assert "signal" in gen, "上限を作っても、fetchに渡していません"
    # 成功しても失敗しても後片付けすること。
    assert "timer.clear()" in APP_JS


def test_the_timeout_message_says_the_input_is_kept():
    """上限に達したとき、「入力は残っている」と伝えること。

    ここで利用者がいちばん恐れるのは、9つ測って入れた値が消えることである。
    """
    assert "入力した値はそのままです" in APP_JS


# --- 外部APIの上限 -----------------------------------------------------------

def test_the_vision_api_call_has_its_own_limit():
    """Claude APIの呼び出しに、待ち時間と回数の上限があること。

    round44までは `anthropic.Anthropic()` を引数なしで作っていたので、
    待ち時間はSDKの既定(10分)、しかも自動リトライ付きだった。
    イラスト1枚ごと×領域ごとに呼ぶので、これが積み上がる。
    """
    from engine import part_classifier

    assert part_classifier._API_TIMEOUT_SECONDS <= 60
    assert part_classifier._API_MAX_RETRIES <= 2
    src = pathlib.Path(part_classifier.__file__).read_text(encoding="utf-8")
    block = src.split("class ClaudePartClassifier")[1].split("def classify")[0]
    assert "timeout=timeout" in block and "max_retries=max_retries" in block, \
        "APIクライアントに上限を渡していません"


def test_the_number_of_classifications_is_capped():
    """1リクエストで投げる判定の回数に、上限があること。

    領域の数には上限が無く、SAMを使う構成では1枚で数十〜数百の領域が
    返りうる。その全部に外部APIを1回ずつ投げていた。
    """
    from engine.part_classifier import MAX_CLASSIFICATIONS_PER_REQUEST
    from engine import pipeline

    assert 0 < MAX_CLASSIFICATIONS_PER_REQUEST <= 100
    src = pathlib.Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "MAX_CLASSIFICATIONS_PER_REQUEST" in src
    # 判定を呼ぶ手前で止めていること(呼んだ後に数えても遅い)。
    loop = src.split("for region in regions:")[1].split("classifications.append")[0]
    assert loop.index("MAX_CLASSIFICATIONS_PER_REQUEST") < loop.index("classifier.classify("), \
        "上限の判定が、API呼び出しより後に来ています"


# --- 選択肢の群に名前があること ----------------------------------------------

def test_the_choice_groups_carry_a_name(client):
    """まとまった選択肢に、読み上げられる群の名前があること。

    アクセシビリティツリーを実際に読んだところ、ネックライン・袖・スカートの
    3つには群の名前があったが(既存)、**入力モードの3つとサイズの5つには
    無かった**。サイズは「XS チェックボックス」「S チェックボックス」と
    しか聞こえず、何のサイズなのか分からない。
    """
    body = client.get("/").get_data(as_text=True)
    assert re.search(r'<h2 id="mode-group-label"', body)
    assert re.search(r'class="mode-row"[^>]*role="radiogroup"[^>]*'
                     r'aria-labelledby="mode-group-label"', body)
    assert 'id="sizes-group-label"' in body
    assert re.search(r'role="group"[^>]*aria-labelledby="sizes-group-label"', body)


# --- 動きを減らす設定 --------------------------------------------------------

def test_the_reduced_motion_preference_is_honoured():
    """動きを減らす設定のとき、回り続けるものを止めること。

    実測では `prefers-reduced-motion: reduce` にしても何も変わらず、
    スピナーは `animation: pf-spin 0.8s linear infinite` で回り続けていた。
    """
    assert "@media (prefers-reduced-motion: reduce)" in STYLE_CSS
    block = STYLE_CSS.split("@media (prefers-reduced-motion: reduce)")[1]
    assert "pf-fade" in block, "回転を止める手当てが消えています"
    assert "animation-duration: 0.01ms !important" in block
    # ただしスピナーは消さない——止めると「固まったのか」が分からなくなる。
    assert "animation-iteration-count: infinite !important" in block, \
        "スピナーまで止めてしまうと、動いているのか固まったのか分かりません"
