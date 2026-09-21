"""round57: Claude APIを呼ぶ経路を、実際にHTTPで1往復させる。

round50から6ラウンド、「正直な限界」にこう書き続けてきた:

    **実際のClaude APIは呼んでいない。** `ai_engine()` が `"claude"` を返す
    経路は、作った判定記録での単体テストで確かめただけで、本物の鍵で
    通してはいない。

本物の鍵は用意できない。だが未検証で残っていたのは**鍵の先**ではなく、
その手前の**自分のコード**である:

    リクエストを組み立てる(画像をbase64にして、systemとmessagesを作る)
      → HTTPで送る
      → 応答の`content`ブロックからテキストを集める
      → その中からJSONを取り出す(`_extract_json`)
      → `ClassificationResult`に直す(`_to_result`)

ここはAPIと同じ形で答える受け口を立てれば、そのまま通せる。
このファイルは`http.server`で**Messages APIと同じ形のJSON**を返す
受け口を立て、`anthropic`のクライアントを`base_url`でそこへ向けて、
実際に1往復させる。

**確かめていないもの(正直に)**: Anthropicのサーバーそのものの挙動と、
モデルの判定の出来。ここで確かめているのは、自分が書いた
「組み立てる・送る・解釈する」だけである。
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from engine.part_classifier import ClaudePartClassifier


def _messages_response(text: str) -> dict:
    """Messages APIの応答と同じ形のJSON。"""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


class _FakeAnthropic(HTTPServer):
    """Messages APIと同じ形で答える受け口。受け取った本文も覚えておく。"""

    reply_text = json.dumps({"part_type": "front_bodice", "variation": "v_neck",
                             "confidence": 0.82})
    status = 200
    received: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandlerの規約
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.received.append({
            "path": self.path,
            "headers": dict(self.headers),
            "json": json.loads(body) if body else None,
        })
        payload = json.dumps(_messages_response(self.server.reply_text)).encode()
        self.send_response(self.server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):   # テスト出力を汚さない
        return


@pytest.fixture()
def fake_api():
    server = _FakeAnthropic(("127.0.0.1", 0), _Handler)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _classifier(server, **kwargs):
    host, port = server.server_address[:2]
    return ClaudePartClassifier(api_key="test-key-not-real",
                                 base_url=f"http://{host}:{port}",
                                 max_retries=0, **kwargs)


def _image():
    return Image.new("RGB", (64, 96), (90, 110, 160))


# --- 1. 実際に1往復すること --------------------------------------------------

def test_the_classifier_really_sends_a_request_and_reads_the_answer(fake_api):
    """組み立て → 送信 → 解釈 が、HTTPを1往復して通ること。"""
    result = _classifier(fake_api).classify(_image(), region_label="上半身")

    assert len(fake_api.received) == 1, "リクエストが送られていません"
    assert result.part_type == "front_bodice"
    assert result.variation == "v_neck"
    assert 0.0 <= result.confidence <= 1.0


def test_the_request_carries_the_image_and_the_hint(fake_api):
    """送っている中身が、こちらの意図どおりであること。"""
    _classifier(fake_api).classify(_image(), region_label="スカート")
    sent = fake_api.received[0]["json"]

    assert sent["model"] == "claude-sonnet-4-5"
    assert sent["system"], "systemプロンプトが入っていません"
    content = sent["messages"][0]["content"]
    kinds = [block["type"] for block in content]
    assert "image" in kinds, kinds
    image_block = next(b for b in content if b["type"] == "image")
    assert image_block["source"]["media_type"] == "image/png"
    assert image_block["source"]["data"], "画像が空です"
    text_block = next(b for b in content if b["type"] == "text")
    assert "スカート" in text_block["text"], text_block["text"]


def test_the_api_key_is_sent_as_a_header(fake_api):
    """鍵がヘッダで渡っていること(本物の鍵でも同じ経路を通る)。"""
    _classifier(fake_api).classify(_image())
    # ヘッダ名の大文字小文字は問わない(SDKは `X-Api-Key` で送る)。
    headers = {k.lower(): v for k, v in fake_api.received[0]["headers"].items()}
    assert headers.get("x-api-key") == "test-key-not-real"


# --- 2. 応答の解釈 -----------------------------------------------------------

def test_json_wrapped_in_prose_is_still_read(fake_api):
    """前後に文章が付いた応答からも、JSONを取り出せること。"""
    fake_api.reply_text = (
        "画像を確認しました。以下が判定結果です。\n"
        '{"part_type": "sleeve", "variation": "puff", "confidence": 0.6}\n'
        "ご不明な点があればお知らせください。")
    result = _classifier(fake_api).classify(_image())
    assert result.part_type == "sleeve"
    assert result.variation == "puff"


def test_an_answer_without_json_fails_without_leaking_the_text(fake_api):
    """JSONが無い応答は、**生のテキストを漏らさずに**失敗すること。

    以前ここの例外メッセージにClaudeの生の応答をそのまま入れていて、
    それがHTTP 400の本文として利用者に返っていた(修正済み)。
    その再発防止を、実際にHTTPを通した状態で確かめる。
    """
    fake_api.reply_text = "これはワンピースの前身頃だと思います。秘密の文字列XYZZY。"
    with pytest.raises(ValueError) as excinfo:
        _classifier(fake_api).classify(_image())
    assert "XYZZY" not in str(excinfo.value), str(excinfo.value)


def test_a_server_error_is_raised_not_swallowed(fake_api):
    """APIが5xxを返したら、黙って既定値にせず例外にすること。"""
    fake_api.status = 500
    with pytest.raises(Exception):
        _classifier(fake_api).classify(_image())


# --- 3. 画面に出る「どちらで判定したか」 ------------------------------------

def test_the_pipeline_reports_claude_when_the_real_classifier_is_used(fake_api, tmp_path):
    """本物の分類器を通した生成が、`ai_engine`で"claude"と名乗ること。

    round50でバッジを足したときは、作った判定記録での単体テストだけで
    確かめていた。ここでは**実際にHTTPを1往復した**分類器で通す。
    """
    from PIL import ImageDraw

    from engine.pipeline import PatternForgePipeline
    from engine.measurements import Measurements

    fake_api.reply_text = json.dumps(
        {"part_type": "front_bodice", "variation": "round_neck", "confidence": 0.9})

    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (460, 560), (240, 560)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))

    # 分類器は `get_default_classifier()` 経由で作られるので、そこを
    # 本物のクライアント(受け口へ向けたもの)に差し替える。
    import engine.pipeline as pipeline_module

    monkey = _classifier(fake_api)
    original = pipeline_module.get_default_classifier
    pipeline_module.get_default_classifier = lambda *a, **k: monkey
    try:
        pipeline = PatternForgePipeline(output_dir=str(tmp_path))
        result = pipeline.generate_from_illustration(
            image, Measurements(bust=84, waist=68, hip=92, height=160,
                                 sleeve_length=54, shoulder_width=37))
    finally:
        pipeline_module.get_default_classifier = original
    assert fake_api.received, "分類器が呼ばれていません"
    assert result.summary()["ai_engine"] == "claude"
