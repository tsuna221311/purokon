"""round50: イラストモードを実際に動かして見つけたもの。

round45〜49で「イラストモードはAPIキーの要る環境が無いので通していない」と
**5回**書いた。しかし `get_default_classifier()` は鍵が無ければ
`MockPartClassifier` に落ちるので、**鍵無しで動かせる**。
確かめずに書いた思い込みを、5ラウンド「正直な限界」として並べていた。

実際に画像を上げて通したところ、2つ見つかった:

  1. **画面からのイラストモードは、1度も成功できない状態だった。**
     `custom_panels_json` の既定値は空文字ではなく**文字列 "[]"** なのに、
     イラストモード側の併用チェックが**文字列の真偽値**で判定していた。
     カスタムパーツを1つも足していなくても常に真になる。実測:

         画面そのまま(custom_panels_json="[]") → 400
           「カスタムパーツ(自由形状)は現在、イラストモードでは併用できません。」
         その欄だけ取り除いて送る              → 200・パーツ6枚

     エンジンは正常で、この1行だけがモード全体を塞いでいた。
     しかも同じ間違いは**round32にmanual側で見つかって直されており**、
     そのとき書かれた `_has_custom_panels()` の説明文には
     「文字列としての真偽値で判定してはいけない」とまで書いてある。
     直したのは見つけた場所だけだった。
  2. **AIを一度も呼んでいないのに「AI使用」と出していた。**
     バッジは `classification_log.length > 0` だけを見ていたので、
     鍵の無い環境——案内文が「未設定の場合は簡易判定（モック）で動作します」
     と書いている、まさにその状態——でも緑の「AI使用」が出ていた。
     engine側の `ai_contribution_note()` は「簡易判定(モック)」と正しく
     書き分けていたので、**目立つバッジだけが実態と食い違っていた**。
"""

import io
import json
import pathlib
import re

import pytest
from PIL import Image, ImageDraw

import app as app_module

APP_JS = (pathlib.Path(app_module.BASE_DIR) / "web" / "static" / "app.js").read_text(encoding="utf-8")


def _dress_png() -> bytes:
    """服だけが写った絵(白背景・単色のシルエット)。"""
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (470, 250), (520, 270), (500, 330),
                  (455, 315), (460, 560), (240, 560), (245, 315), (200, 330),
                  (180, 270), (230, 250)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))
    draw.ellipse([(310, 168), (390, 200)], fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _form(**extra):
    data = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "illustration",
    }
    data.update(extra)
    return data


# --- 1. 既定の "[]" がモードを塞がないこと ---------------------------------

def test_the_illustration_mode_works_with_the_default_empty_panel_field(client):
    """画面がいつも送る `custom_panels_json="[]"` で、生成できること。

    ここが塞がっていた間、画面からのイラストモードは**一度も成功しなかった**。
    """
    data = _form(custom_panels_json="[]")
    data["illustration"] = (io.BytesIO(_dress_png()), "dress.png")
    response = client.post("/api/generate", data=data,
                           content_type="multipart/form-data")
    body = response.get_json()
    assert response.status_code == 200, body.get("error")
    assert body["ok"] is True
    assert body["part_count"] > 0


def test_a_real_custom_panel_is_still_refused(client):
    """本物のカスタムパーツを併用したら、今までどおり断ること。

    直したのは「空を空として読む」ところだけで、併用の制限は外していない。
    """
    panel = json.dumps([{
        "label": "マント", "points": [[0, 0], [100, 0], [100, 100], [0, 100]],
        "ref_point_a": [0, 0], "ref_point_b": [100, 0],
        "quantity": 1, "mirror": False, "reference_cm": 50,
    }])
    data = _form(custom_panels_json=panel)
    data["illustration"] = (io.BytesIO(_dress_png()), "dress.png")
    response = client.post("/api/generate", data=data,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert "イラストモードでは併用できません" in response.get_json()["error"]


def test_a_broken_panel_json_is_still_refused(client):
    """JSONとして壊れている場合も断ること(黙って無視しない)。"""
    data = _form(custom_panels_json="{これはJSONではない")
    data["illustration"] = (io.BytesIO(_dress_png()), "dress.png")
    response = client.post("/api/generate", data=data,
                           content_type="multipart/form-data")
    assert response.status_code == 400


def test_the_check_goes_through_the_shared_helper():
    """空かどうかの判定を、手書きの真偽値に戻さないこと。

    `_has_custom_panels()` は round32 でこの間違いを直したときに作られ、
    説明文に「文字列としての真偽値で判定してはいけない」と書いてある。
    それでも**もう1か所**が素の真偽値のままだった。
    """
    source = pathlib.Path(app_module.__file__).read_text(encoding="utf-8")
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())
    offenders = re.findall(
        r'if \(request\.form\.get\("custom_panels_json"\)[^\n]*\)\.strip\(\):', code)
    assert offenders == [], \
        f"文字列の真偽値で判定している箇所が残っています: {offenders}"
    # 参照するときは必ず helper を通っていること。
    assert code.count("_has_custom_panels(") >= 2


# --- 2. 何が判定したのかを、正しく名乗ること --------------------------------

def test_the_engine_reports_which_classifier_actually_ran():
    """`ai_engine` が none / mock / claude を返し分けること。"""
    from engine.pipeline import PipelineResult

    class _Entry:
        def __init__(self, mode):
            self.raw = {"mode": mode} if mode else None

    def engine_for(log):
        result = PipelineResult.__new__(PipelineResult)
        result.classification_log = log
        return PipelineResult.ai_engine(result)

    assert engine_for([]) == "none"
    assert engine_for([_Entry("mock"), _Entry("mock")]) == "mock"
    assert engine_for([_Entry("claude")]) == "claude"
    # 1件でも実APIなら「モックだけ」ではない。
    assert engine_for([_Entry("mock"), _Entry("claude")]) == "claude"
    # rawが無い古い記録は、実APIとして扱う(既存の`ai_contribution_note`と同じ)。
    assert engine_for([_Entry(None)]) == "claude"


def test_the_summary_carries_that_field(client):
    """画面が文を解釈しなくて済むよう、判定に使える値を返すこと。

    round35で「分割が起きたか」を`split_panels`として出したのと同じ方針。
    """
    data = _form(custom_panels_json="[]")
    data["illustration"] = (io.BytesIO(_dress_png()), "dress.png")
    body = client.post("/api/generate", data=data,
                       content_type="multipart/form-data").get_json()
    # 鍵の無いテスト環境なので、走ったのはモック。
    assert body["ai_engine"] == "mock"
    assert "簡易判定" in body["ai_contribution"]


def test_a_manual_job_reports_no_ai(client):
    body = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare",
    }).get_json()
    assert body["ai_engine"] == "none"
    assert "AIは使用していません" in body["ai_contribution"]


def test_the_badge_does_not_claim_ai_for_the_mock():
    """バッジが `ai_engine` を見て、モックを「AI使用」と言わないこと。"""
    block = APP_JS.split("const aiEngine = data.ai_engine")[1].split("\n\n")[0]
    assert 'aiEngine === "claude"' in block, \
        "実APIかどうかを見ずに強調する書き方に戻っています"
    assert "簡易判定" in block, "モックのときの表示がありません"
    # 強調(緑)は実APIのときだけ。
    assert 'aiBadge.classList.toggle("ai-badge-active", usedRealAi)' in APP_JS
    # 件数だけで判断する古い書き方が残っていないこと。
    assert "classification_log.length > 0\n" not in APP_JS.replace(" ", "")


def test_the_badge_text_matches_what_the_engine_says():
    """バッジの3つの言い方が、engine側の3つの値と1対1であること。"""
    block = APP_JS.split("aiBadge.textContent = {")[1].split("}")[0]
    for key in ("claude:", "mock:", "none:"):
        assert key in block, f"{key} の表示がありません"
