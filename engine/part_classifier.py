"""part_classifier.py — 切り出したパーツ画像の種類判定（STEP③「パーツ判定」相当）。

SAMで生成したパーツ画像をClaude APIに渡して種類をJSON形式で判定し、採寸
データで比例変形する、というパイプラインの中核部分。ANTHROPIC_API_KEY が
設定されていれば実際にClaude API(vision対応モデル)を呼び出し、無ければ
segmentation側のラベルから決定的にpart_typeを割り当てる MockPartClassifier に
フォールバックする。
"""

from __future__ import annotations
import base64
import io
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

from .templates_db import REQUIRED_PARTS

logger = logging.getLogger(__name__)

#: `_extract_json`/`_to_result`がClaudeの応答を解釈できなかった場合に、
#: 利用者に返す共通の案内文。
_AI_CLASSIFICATION_FAILED_MESSAGE = (
    "AIによるパーツ判定に失敗しました。手動選択モードをお試しください。"
)

ALLOWED_PART_TYPES: list[str] = sorted({part for part, _variation in REQUIRED_PARTS})

ALLOWED_VARIATIONS_BY_PART: dict[str, set[str]] = {}
for _part, _variation in REQUIRED_PARTS:
    ALLOWED_VARIATIONS_BY_PART.setdefault(_part, set()).add(_variation)


@dataclass
class ClassificationResult:
    part_type: str
    variation: str
    confidence: float
    raw: dict | None = None


class PartClassifier(ABC):
    @abstractmethod
    def classify(self, image: Image.Image, region_label: str = "") -> ClassificationResult:
        """パーツ画像から (part_type, variation) を判定する。"""


_SYSTEM_PROMPT = (
    "あなたは洋裁パタンナーの補助AIです。与えられた衣装パーツの画像が、"
    "型紙テンプレートDBのどの種類に対応するかを判定してください。\n"
    f"part_type は次のいずれか: {', '.join(ALLOWED_PART_TYPES)}。\n"
    "variation はそのpart_typeに実在するものだけを選び、存在しない場合は"
    "空文字にしてください。\n"
    "回答は次のJSON形式のみ、説明文なしで返してください:\n"
    '{"part_type": "front_bodice", "variation": "round_neck", "confidence": 0.8}'
)


class ClaudePartClassifier(PartClassifier):
    """Claude API(vision)を使った本番実装。ANTHROPIC_API_KEY が必要。"""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-5"):
        import anthropic  # 遅延importでキー無し環境でも他モジュールは読み込める

        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model

    def classify(self, image: Image.Image, region_label: str = "") -> ClassificationResult:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        message = self._client.messages.create(
            model=self._model,
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": f"領域ラベルの手掛かり: {region_label or '不明'}。JSONのみで回答してください。"},
                ],
            }],
        )
        text = "".join(getattr(block, "text", "") for block in message.content)
        data = _extract_json(text)
        return _to_result(data)


def _extract_json(text: str) -> dict:
    """Claude応答テキストの中からJSONオブジェクトを取り出す。

    実際に見つかった不具合(修正済み): 以前はここで発生する`ValueError`の
    メッセージに、Claudeの生の応答テキスト(`text!r`)をそのまま埋め込んで
    いた。この`ValueError`は`app.py`の`/api/generate`では「単純な入力
    ミス」用の`except ValueError`（`str(exc)`をそのままクライアントに
    返す設計。採寸値エラー等の、こちらが文言を完全に制御する安全な
    メッセージを想定している）で処理される。実際に、本物の
    `_extract_json`を通す偽の分類器を使って「JSON形式で回答してください」
    という指示に従わずに説明文だけを返すClaude応答を再現し、実際に
    Flaskのテストクライアントで`/api/generate`（イラストモード）へ
    送ったところ、そのAI応答の生テキストがそのままHTTP 400レスポンスの
    `error`フィールドに漏れて返ってくることを確認した。想定外の例外は
    エラーIDだけを返すよう既に「正常化」されている(README「エラー
    メッセージの正常化」参照)のに、この経路だけ素通りしていた。
    サーバー側ログに生テキストを残しつつ、クライアントには定型の安全な
    案内文だけを返すように修正した。
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        logger.warning("Claude応答からJSONを取り出せませんでした。raw response: %r", text)
        raise ValueError(_AI_CLASSIFICATION_FAILED_MESSAGE)
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        logger.warning("Claude応答をJSONとして解釈できませんでした。raw response: %r", text)
        raise ValueError(_AI_CLASSIFICATION_FAILED_MESSAGE) from None


def _to_result(data: dict) -> ClassificationResult:
    part_type = data.get("part_type", "")
    variation = data.get("variation") or ""
    if part_type not in ALLOWED_PART_TYPES:
        # 同上の理由で、Claudeが返した生のpart_type文字列をそのまま
        # クライアント向けメッセージに埋め込まないようにする。
        logger.warning("Claude応答に未知のpart_typeが含まれていました: %r", part_type)
        raise ValueError(_AI_CLASSIFICATION_FAILED_MESSAGE)
    allowed = ALLOWED_VARIATIONS_BY_PART.get(part_type, {""})
    if variation not in allowed:
        variation = next(iter(sorted(allowed)), "")
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return ClassificationResult(part_type=part_type, variation=variation,
                                confidence=confidence, raw=data)


_LABEL_TO_PART_TYPE = {
    "torso": "front_bodice",
    "left_sleeve": "sleeve",
    "right_sleeve": "sleeve",
    "lower_body": "skirt",
}

_DEFAULT_VARIATION = {
    "front_bodice": "round_neck",
    "back_bodice": "round_neck",
    "sleeve": "straight",
    "skirt": "flare",
}


class MockPartClassifier(PartClassifier):
    """APIキーが無い環境向けの決定的フォールバック。

    segmentation側が付けた領域ラベル(region_label)をそのままpart_typeに
    変換し、variationは標準的な既定値を返す。ネットワーク接続やAPIキーなしに
    パイプライン全体を最後まで動かして確認できるようにするためのもの。
    実運用ではANTHROPIC_API_KEYを設定してClaudePartClassifierに任せる。
    """

    def classify(self, image: Image.Image, region_label: str = "") -> ClassificationResult:
        part_type = _LABEL_TO_PART_TYPE.get(region_label, "front_bodice")
        variation = _DEFAULT_VARIATION.get(part_type, "")
        return ClassificationResult(
            part_type=part_type, variation=variation, confidence=0.3,
            raw={"mode": "mock", "region_label": region_label},
        )


def get_default_classifier() -> PartClassifier:
    """ANTHROPIC_API_KEY があればClaude、無ければMockを返す。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return ClaudePartClassifier(api_key=api_key)
        except Exception:
            pass
    return MockPartClassifier()
