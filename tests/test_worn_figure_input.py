"""round20: 人物が着ているイラスト(アニメ画像等)から、服の範囲だけを測る。

round19まで、シルエットに頭・髪・腕・脚が含まれるとすべての読み取りが
**静かに壊れていた**。黙って誤った寸法の型紙を出すのが最も悪い振る舞い
なので、服の範囲を切り出してから測るようにした。ここではその回帰を防ぐ。
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from engine.illustration_fit import (
    garment_span, measure_neckline, measure_proportions,
)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline
from engine.segmentation import SimpleSilhouetteSegmenter

SEG = SimpleSilhouetteSegmenter()
MEASUREMENTS = Measurements(83, 66, 91, 158, 52, 37)

#: 服が写っている範囲(この合成図の正解)。身頃の上端140、スカートの裾560。
GARMENT_TOP, GARMENT_BOTTOM = 140, 560


def _figure(worn: bool) -> Image.Image:
    """同じワンピースを、服だけ／人物が着た状態で描いた合成シルエット。"""
    image = Image.new("RGB", (400, 900), "white")
    draw = ImageDraw.Draw(image)
    if worn:
        draw.ellipse([165, 40, 235, 120], fill="black")       # 頭
        draw.rectangle([190, 115, 210, 140], fill="black")    # 首
    draw.polygon([(150, 140), (250, 140), (240, 300), (160, 300)], fill="black")
    draw.polygon([(160, 300), (240, 300), (300, 560), (100, 560)], fill="black")
    if worn:
        draw.polygon([(150, 145), (165, 145), (150, 330), (135, 330)], fill="black")
        draw.polygon([(235, 145), (250, 145), (265, 330), (250, 330)], fill="black")
        draw.rectangle([175, 560, 195, 800], fill="black")    # 脚
        draw.rectangle([205, 560, 225, 800], fill="black")
    return image


def _mask(worn: bool):
    return SEG.silhouette_mask(_figure(worn))


def test_garment_span_finds_the_same_range_with_or_without_the_person():
    """人物が写っていても、服の上端(肩)と下端(裾)を同じ位置で切り出せること。"""
    assert garment_span(_mask(False)) == (GARMENT_TOP, GARMENT_BOTTOM, False)
    assert garment_span(_mask(True)) == (GARMENT_TOP, GARMENT_BOTTOM, True)


def test_worn_figure_measurements_match_the_garment_only_reading():
    """人物込みの絵と服だけの絵が、同じ広がりとして読めること。

    実測の推移(同じワンピース):
      round19まで … 服だけ2.48 / 人物込み**1.00**(くびれを脚の間に見つけていた)
      round20     … 服だけ2.48 / 人物込み2.12(腕がウエストの幅に混ざる)
      round22     … 服だけ2.481 / 人物込み**2.481**(腕を分離して測る)

    round22で、腕が体から離れて描かれている行では前景が「腕|胴|腕」の
    3つに分かれることを使い、真ん中の塊を胴の幅として測るようにした
    (`engine/illustration_fit._torso_widths`)。
    """
    reference = measure_proportions(_mask(False))
    worn = measure_proportions(_mask(True))
    assert reference.hem_flare is not None and worn.hem_flare is not None
    assert worn.hem_flare == pytest.approx(reference.hem_flare, abs=0.05), (
        worn.hem_flare, reference.hem_flare)


def test_the_skirt_length_is_not_read_from_where_the_arms_end():
    """腕が終わる位置を「ウエスト」と取り違えて丈を出さないこと。

    round20〜21の実測では、人物込みの絵からスカート丈46.4cmという
    もっともらしい値が出ていた。しかしその根拠になったくびれの位置は
    **y=331**——この合成図で腕を描き終えている y=330 のすぐ下であり、
    腕が消えて幅が急に細くなった行を「胴がいちばんくびれた所」と
    取り違えていたにすぎない。つまり測っていたのは服ではなく**腕の長さ**
    だった。

    同じワンピースを服だけで描いた絵ではくびれが見つからない(この図の胴は
    上から下まで5%しか細くなっていない)ことが、それが実在しないくびれで
    あったことの裏付けになる。人物込みでも同じく「読めない」と答えるのが
    正しい。読めない項目を黙って埋めない、というのがこのプロジェクトの方針。
    """
    reference = measure_proportions(_mask(False))
    worn = measure_proportions(_mask(True))
    assert reference.skirt_ratio is None, "服だけの絵にくびれは無い(前提)"
    assert worn.skirt_ratio is None, (
        "腕の終わりをくびれと取り違えている: " f"{worn.skirt_ratio}")


def test_a_detached_arm_row_is_found_where_the_arms_leave_the_body():
    """腕が体から離れ始める行を、実際に見つけられること。

    上の「読まない」判断がここに依存しているので、判定器そのものが
    働いていることを別に固定する(服だけの絵では見つからないこと付き)。
    """
    from engine.illustration_fit import first_detached_arm_row

    worn_mask = _mask(True)
    top, bottom, _figure = garment_span(worn_mask)
    assert first_detached_arm_row(worn_mask, top, bottom) == 260
    assert first_detached_arm_row(_mask(False), top, bottom) is None


def test_neckline_is_not_read_from_a_worn_figure():
    """人物込みでは襟ぐりを読まずNoneを返すこと。

    着ている絵では襟ぐりは服の内側の線で、シルエットには現れない。
    修正前は頭部の輪郭を読んで sweetheart と誤判定していた。
    """
    assert measure_neckline(_mask(True)) is None
    assert measure_neckline(_mask(False)) is not None


def test_a_garment_only_image_is_not_mistaken_for_a_person():
    """服だけの絵で、襟ぐりのくぼみを「首」と誤検出しないこと。

    襟ぐりも「上が細く下が広い」形なので、頭の有無を確かめないと
    首と区別できない。導入前は自前テンプレート6種すべてで襟ぐりの
    読み取りがNoneになった。
    """
    from engine.templates_db import TemplateDB

    cairosvg = pytest.importorskip("cairosvg")
    import io as _io

    db = TemplateDB()
    assert db.get("front_bodice", "round_neck") is not None
    with open("pattern_templates/front_bodice__round_neck.svg", encoding="utf-8") as fh:
        svg = fh.read().replace('fill="none"', 'fill="black"')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=400, background_color="white")
    body = Image.open(_io.BytesIO(png)).convert("RGB")
    canvas = Image.new("RGB", (int(body.width * 1.8), int(body.height * 1.8)), "white")
    canvas.paste(body, (int(body.width * 0.4), int(body.height * 0.4)))

    mask = SEG.silhouette_mask(canvas)
    span = garment_span(mask)
    assert span is not None and span[2] is False
    assert measure_neckline(mask) == "round_neck"


def test_a_dress_waist_is_not_mistaken_for_a_neck():
    """ウエストのくびれを「首」と誤検出しないこと。

    上に身頃+袖、下にスカートがある絵では、ウエストは「上下より細い行」と
    いう首と同じ条件を満たす。頭は体より細い、という条件で区別している。
    導入前はミディ丈のワンピースで服の上端がスカートの途中(y=248)になった。
    """
    image = Image.new("RGB", (400, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(140, 90), (260, 90), (230, 200), (170, 200)], fill="black")
    draw.polygon([(118, 95), (140, 95), (140, 180), (112, 180)], fill="black")
    draw.polygon([(260, 95), (282, 95), (288, 180), (260, 180)], fill="black")
    draw.polygon([(170, 200), (230, 200), (300, 430), (100, 430)], fill="black")
    span = garment_span(SEG.silhouette_mask(image))
    assert span is not None
    assert span[2] is False, span
    assert span[0] < 100, span     # 服の上端は絵の上端付近


def test_pipeline_discloses_that_a_person_was_detected(tmp_path):
    """人物込みと判断したことを、利用者へ開示すること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(_figure(True), MEASUREMENTS)
    # round32: イラストから読み取った内容の説明は design_notes へ移した。
    text = " / ".join(result.design_notes + result.measurement_warnings)
    assert "人物が着ている" in text, text
    assert "襟ぐり" in text, text
