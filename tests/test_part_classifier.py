import pytest
from PIL import Image

from engine.part_classifier import (
    ALLOWED_PART_TYPES,
    ALLOWED_VARIATIONS_BY_PART,
    MockPartClassifier,
    PartClassifier,
    ClassificationResult,
    _AI_CLASSIFICATION_FAILED_MESSAGE,
    _extract_json,
    _to_result,
)


def test_mock_classifier_maps_region_labels_to_part_types():
    classifier = MockPartClassifier()
    image = Image.new("RGB", (10, 10), "white")

    result = classifier.classify(image, region_label="torso")
    assert result.part_type == "front_bodice"
    assert result.raw["mode"] == "mock"

    result = classifier.classify(image, region_label="left_sleeve")
    assert result.part_type == "sleeve"

    result = classifier.classify(image, region_label="lower_body")
    assert result.part_type == "skirt"


def test_mock_classifier_falls_back_for_unknown_label():
    classifier = MockPartClassifier()
    image = Image.new("RGB", (10, 10), "white")
    result = classifier.classify(image, region_label="something_unrecognized")
    assert result.part_type in ALLOWED_PART_TYPES


def test_extract_json_finds_embedded_object():
    text = 'ここに理由... {"part_type": "sleeve", "variation": "curve", "confidence": 0.9} 以上です'
    data = _extract_json(text)
    assert data == {"part_type": "sleeve", "variation": "curve", "confidence": 0.9}


def test_extract_json_raises_when_no_json_present():
    with pytest.raises(ValueError):
        _extract_json("JSONではない普通の文章です")


def test_to_result_rejects_unknown_part_type():
    with pytest.raises(ValueError):
        _to_result({"part_type": "wing", "variation": "", "confidence": 0.5})


def test_to_result_falls_back_to_valid_variation_when_unknown():
    # フォールバック先の具体的な値(sorted()の先頭)はsleeveのバリエーション
    # 追加のたびに変わりうるため、ALLOWED_VARIATIONS_BY_PARTから動的に
    # 参照する（ハードコードした具体値だと、新バリエーション追加のたびに
    # このテストが無関係な理由で壊れてしまう）。
    result = _to_result({"part_type": "sleeve", "variation": "not_a_real_variation", "confidence": 0.7})
    assert result.part_type == "sleeve"
    assert result.variation in ALLOWED_VARIATIONS_BY_PART["sleeve"]


def test_to_result_defaults_confidence_when_missing_or_invalid():
    result = _to_result({"part_type": "collar", "variation": ""})
    assert result.confidence == pytest.approx(0.5)
    result = _to_result({"part_type": "collar", "variation": "", "confidence": "not-a-number"})
    assert result.confidence == pytest.approx(0.5)


def test_extract_json_error_does_not_leak_raw_claude_response_text():
    # 実際に見つかった不具合(修正済み): 以前はJSONが見つからない場合の
    # ValueErrorメッセージに、Claudeの生の応答テキストをそのまま埋め込んで
    # いた。このValueErrorはapp.pyの/api/generateでは「安全な文言だけの
    # ValueError」として、str(exc)がそのままクライアントのHTTPレスポンスに
    # 返る設計になっている(採寸値エラー等を想定した経路)。そのため、AIが
    # 「JSON形式で回答してください」という指示に従わなかった場合、その
    # 生テキストがそのままクライアントに漏れていた。生テキストがメッセージに
    # 含まれない、定型の安全な文言だけが例外メッセージになることを固定する。
    suspicious_text = "これは漏れてはいけない機密情報めいた本文です123456"
    with pytest.raises(ValueError) as excinfo:
        _extract_json(suspicious_text)
    assert str(excinfo.value) == _AI_CLASSIFICATION_FAILED_MESSAGE
    assert suspicious_text not in str(excinfo.value)


def test_extract_json_error_does_not_leak_raw_text_when_braces_present_but_invalid_json():
    # 波括弧はあるが中身が壊れているケース(json.loads自体が失敗するケース)
    # も同様に生テキストを漏らさないことを確認する。
    suspicious_text = '前置き {"part_type": "sleeve", これは壊れたJSONです} 後書き'
    with pytest.raises(ValueError) as excinfo:
        _extract_json(suspicious_text)
    assert str(excinfo.value) == _AI_CLASSIFICATION_FAILED_MESSAGE
    assert suspicious_text not in str(excinfo.value)


def test_to_result_error_does_not_leak_raw_part_type_value():
    # 同じ理由で、未知のpart_typeが返された場合もその生の値をメッセージに
    # 埋め込まないことを確認する。
    suspicious_part_type = "これは漏れてはいけない機密情報めいた値"
    with pytest.raises(ValueError) as excinfo:
        _to_result({"part_type": suspicious_part_type, "variation": "", "confidence": 0.5})
    assert str(excinfo.value) == _AI_CLASSIFICATION_FAILED_MESSAGE
    assert suspicious_part_type not in str(excinfo.value)


def test_api_generate_illustration_mode_does_not_leak_raw_ai_text_on_classification_failure(
    client, monkeypatch,
):
    # 上記の単体テストに加え、実際にFlaskのテストクライアントで
    # /api/generate(イラストモード)まで通し、本物の_extract_json()を
    # 経由した場合にHTTPレスポンスへ生テキストが漏れないことを確認する
    # 回帰テスト(実際にこの経路で漏れることを一度確認した上での修正)。
    import io
    from PIL import Image as PILImage
    import app as app_module
    import engine.pipeline as pipeline_module

    class BrokenClassifier(PartClassifier):
        def classify(self, image, region_label=""):
            fake_claude_text = (
                "申し訳ございませんが、この画像からは衣装パーツの種類を"
                "判定できませんでした。もう少し鮮明な画像をお試しください。"
            )
            data = _extract_json(fake_claude_text)  # 実際にValueErrorを起こす
            return ClassificationResult(**data)

    monkeypatch.setattr(pipeline_module, "get_default_classifier", lambda: BrokenClassifier())

    img = PILImage.new("RGB", (400, 600), (255, 255, 255))
    for y in range(100, 500):
        for x in range(100, 300):
            img.putpixel((x, y), (30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    response = client.post(
        "/api/generate",
        data={
            "mode": "illustration",
            "bust": "84", "waist": "66", "hip": "90", "height": "160",
            "sleeve_length": "55", "shoulder_width": "38",
            "illustration": (buf, "test.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == _AI_CLASSIFICATION_FAILED_MESSAGE
    assert "申し訳ございませんが" not in body["error"]
