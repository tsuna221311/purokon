"""part_classifier.py — 切り出したパーツ画像の種類判定（STEP③「パーツ判定」相当）。

SAMで生成したパーツ画像をClaude APIに渡して種類をJSON形式で判定し、採寸
データで比例変形する、というパイプラインの中核部分。ANTHROPIC_API_KEY が
設定されていれば実際にClaude API(vision対応モデル)を呼び出し、無ければ
segmentation側のラベルから決定的にpart_typeを割り当てる MockPartClassifier に
フォールバックする。
"""

from __future__ import annotations
import base64
import colorsys
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


#: 1回のAPI呼び出しに待つ秒数の上限 (round45で追加)。
#:
#: 【round44まで何が起きていたか】`anthropic.Anthropic()` を引数なしで
#: 作っていたため、待ち時間はSDKの既定(10分)に任されていた。さらに
#: SDKは既定で自動リトライするので、1回の判定が最悪で数十分ブラウザを
#: 待たせうる状態だった。呼び出しは「イラスト1枚ごと × 切り出した領域ごと」
#: に走るので、これが積み上がる。ブラウザ側にも上限が無かった(round45で
#: 2分の上限を置いた)ため、利用者は「生成中です…」のまま復帰できなかった。
#:
#: 【この秒数の根拠】ここは**計測値ではなく方針**である。この呼び出しは
#: max_tokens=200 の小さな判定1件であって、長文生成ではない。SDKの既定
#: (10分)はそのような用途向けの値で、ここには大きすぎる。ブラウザ側の
#: 上限(2分)の内側に収まるよう、1件30秒・リトライ1回までとした。
#: 実際のAPI応答時間は、鍵の要る環境が無いため計測していない。
_API_TIMEOUT_SECONDS = 30.0
_API_MAX_RETRIES = 1

#: 1リクエストで判定にかける領域の数の上限 (round45で追加)。
#:
#: 領域はイラストから切り出したものなので、枚数(app.pyで6枚まで)は
#: 制限されていても、**1枚あたりの領域数は上限が無かった**。既定の
#: SimpleSilhouetteSegmenter は4領域ほどしか返さないので通常は問題に
#: ならないが、SAM(SAM_CHECKPOINT_PATHを設定したとき)は1枚で数十〜数百の
#: マスクを返しうる。その全部にAPIを1回ずつ投げていた。
#: 24 = 6枚 × 4領域(簡易実装の最大)で、既定の構成では届かない値。
MAX_CLASSIFICATIONS_PER_REQUEST = 24


class ClaudePartClassifier(PartClassifier):
    """Claude API(vision)を使った本番実装。ANTHROPIC_API_KEY が必要。"""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6",
                 timeout: float = _API_TIMEOUT_SECONDS,
                 max_retries: int = _API_MAX_RETRIES,
                 base_url: str | None = None):
        import anthropic  # 遅延importでキー無し環境でも他モジュールは読み込める

        # round57: `base_url`を受け取れるようにした。
        #
        # round50から7ラウンド「実際のClaude APIは呼んでいない」と書き続けて
        # きた。本物の鍵は用意できないが、**呼び出しから応答の解釈までの
        # コード**は、APIと同じ形で答える受け口を立てれば通せる。
        # そこだけが未検証で残っていたので、`base_url`を開けて
        # `tests/test_round57_api_path.py`が実際にHTTPを1往復させている
        # (モデルの出来そのものは、相変わらず確かめていない)。
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            timeout=timeout,
            max_retries=max_retries,
            **({"base_url": base_url} if base_url else {}),
        )
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
        if region_label == "lower_body":
            part_type, variation, confidence = _classify_lower_body_locally(image)
            return ClassificationResult(
                part_type=part_type, variation=variation, confidence=confidence,
                raw={"mode": "mock", "region_label": region_label,
                     "local_silhouette": True},
            )
        part_type = _LABEL_TO_PART_TYPE.get(region_label, "front_bodice")
        variation = _DEFAULT_VARIATION.get(part_type, "")
        return ClassificationResult(
            part_type=part_type, variation=variation, confidence=0.3,
            raw={"mode": "mock", "region_label": region_label},
        )


def _classify_lower_body_locally(image: Image.Image) -> tuple[str, str, float]:
    """APIなしでも、支配色の裾幅からパンツとスカートを区別する。

    人物入りの衣装画では背景や横に描かれた小物が輪郭へ混ざるため、画像全体の
    白黒シルエットではなく、彩度のある画素を色相30度ごとに集計する。最大の
    色群を衣装とみなし、その連結範囲の上部と裾の幅を比べる。裾が明確に広がる
    場合だけスカートとし、同幅または細くなる長い筒形はワイドパンツにする。
    判断材料が少ない線画は従来どおりフレアスカートへ安全にフォールバックする。
    """
    sample = image.convert("RGB")
    sample.thumbnail((128, 160))
    width, height = sample.size
    if width < 8 or height < 8:
        return "skirt", "flare", 0.3

    pixels = sample.load()
    bins: list[list[tuple[int, int, float]]] = [[] for _ in range(12)]
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if saturation < 0.24 or value < 0.10 or value > 0.96:
                continue
            # 肌色は衣装の色群から除く。
            degrees = hue * 360
            if 10 <= degrees <= 48 and saturation < 0.58 and value > 0.38:
                continue
            bins[min(11, int(hue * 12))].append((x, y, saturation))
    dominant = max(bins, key=lambda group: sum(item[2] for item in group))
    if len(dominant) < max(18, width * height * 0.006):
        return "skirt", "flare", 0.3

    xs = [item[0] for item in dominant]
    ys = [item[1] for item in dominant]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    garment_height = y1 - y0 + 1
    if garment_height < height * 0.22:
        return "skirt", "flare", 0.3

    def span_between(start: float, end: float) -> float | None:
        rows: list[float] = []
        low = y0 + garment_height * start
        high = y0 + garment_height * end
        for y in range(max(0, int(low)), min(height, int(high) + 1)):
            row = [x for x, py, _s in dominant if py == y]
            if len(row) >= 3:
                rows.append(max(row) - min(row) + 1)
        if not rows:
            return None
        rows.sort()
        return rows[len(rows) // 2]

    upper = span_between(.12, .35)
    hem = span_between(.72, .94)
    if not upper or not hem:
        return "skirt", "flare", 0.3
    flare_ratio = hem / upper
    if flare_ratio >= 1.22:
        variation = "flare" if flare_ratio < 1.75 else "circle"
        return "skirt", variation, 0.46
    # 裾が上部と同幅の長い下衣は、舞台衣装で頻出するワイドパンツとして扱う。
    variation = "wide" if flare_ratio >= .35 else "tapered"
    return "front_pants", variation, 0.44


def get_default_classifier() -> PartClassifier:
    """ANTHROPIC_API_KEY があればClaude、無ければMockを返す。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return ClaudePartClassifier(api_key=api_key)
        except Exception:
            pass
    return MockPartClassifier()
