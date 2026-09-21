"""round19: ラフイラスト(線画)を入力として成立させる。

round18まで、イラストモードは「塗りつぶされたシルエット」でしか動かなかった。
前景マスクは「背景色から離れた画素」なので、線画では線そのものしか拾えず、
実測では前景が画像の約1%にしかならず分割器が領域を1件も返さなかった。
「舞台衣装のラフイラスト」という、このアプリが想定する入力そのものが
通っていなかったことになる。
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from engine.illustration_fit import measure_neckline, measure_proportions
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline
from engine.segmentation import SimpleSilhouetteSegmenter

SEG = SimpleSilhouetteSegmenter()
MEASUREMENTS = Measurements(83, 66, 91, 158, 52, 37)

#: くびれと丸い襟ぐりを持つワンピースの輪郭。
OUTLINE = [(140, 90), (170, 120), (230, 120), (260, 90),
           (268, 190), (300, 430), (100, 430), (132, 190)]


def _filled() -> Image.Image:
    image = Image.new("RGB", (400, 700), "white")
    ImageDraw.Draw(image).polygon(OUTLINE, fill="black")
    return image


def _sketch(gap_px: int = 0, background="white", ink="black", width: int = 3) -> Image.Image:
    """線画のラフ。gap_pxを与えると各辺の中央に途切れを作る。"""
    image = Image.new("RGB", (400, 700), background)
    draw = ImageDraw.Draw(image)
    points = OUTLINE + [OUTLINE[0]]
    for a, b in zip(points, points[1:]):
        if not gap_px:
            draw.line([a, b], fill=ink, width=width)
            continue
        length = max(1.0, ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        draw.line([a, (mx - ux * gap_px / 2, my - uy * gap_px / 2)], fill=ink, width=width)
        draw.line([(mx + ux * gap_px / 2, my + uy * gap_px / 2), b], fill=ink, width=width)
    return image


def _mask_area(image) -> int:
    mask = SEG.silhouette_mask(image)
    return 0 if mask is None else int(mask.sum())


def test_plain_line_art_used_to_produce_no_mask_at_all():
    """線だけを拾った状態では、シルエットとして成立しないこと(前提の確認)。

    塗りつぶす前の生の前景マスクは、線画では画像の1%程度しかない。
    """
    raw = SEG._foreground_mask(_sketch())
    assert raw is not None
    density = float(raw.sum()) / raw.size
    assert density < SEG.MIN_FOREGROUND_RATIO, density


@pytest.mark.parametrize("label,image_factory", [
    ("線が繋がったラフ", lambda: _sketch()),
    ("途切れ4px", lambda: _sketch(gap_px=4)),
    ("途切れ12px", lambda: _sketch(gap_px=12)),
    ("クリーム色の紙に茶の線", lambda: _sketch(background=(245, 238, 220), ink=(60, 50, 40))),
    ("薄いグレーの線", lambda: _sketch(ink=(150, 150, 150))),
])
def test_line_art_measures_like_the_filled_silhouette(label, image_factory):
    """線画でも、塗りつぶしたシルエットとほぼ同じ寸法として読めること。"""
    filled_area = _mask_area(_filled())
    sketch_area = _mask_area(image_factory())
    assert sketch_area > 0, label
    assert abs(sketch_area - filled_area) / filled_area < 0.05, (label, sketch_area, filled_area)

    reference = measure_proportions(SEG.silhouette_mask(_filled()))
    got = measure_proportions(SEG.silhouette_mask(image_factory()))
    assert got.hem_flare == pytest.approx(reference.hem_flare, rel=0.05), label
    assert measure_neckline(SEG.silhouette_mask(image_factory())) == \
        measure_neckline(SEG.silhouette_mask(_filled())), label


@pytest.mark.parametrize("gap", [0, 4, 12])
def test_pipeline_generates_a_pattern_from_a_rough_sketch(tmp_path, gap):
    """ラフイラストから実際に型紙が生成されること。

    round18までは、どの線画でも
    「イラストからパーツ種を判定できませんでした」で止まっていた。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(_sketch(gap_px=gap), MEASUREMENTS)
    assert result.scaled_parts
    assert {"front_bodice", "back_bodice"} <= {p.part_type for p in result.scaled_parts}


def test_already_filled_images_are_untouched():
    """元から塗りつぶされた画像では、マスクが変化しないこと。

    線画対応のために「内部を塗る」処理を挟んだので、既存の入力
    (平置き写真・塗りつぶしイラスト)の挙動が変わっていないことを確認する。
    腕と胴の隙間のような小さな穴が勝手に埋まると輪郭が変わってしまう。
    """
    image = _filled()
    raw = SEG._foreground_mask(image)
    solid = SEG._solid_foreground_mask(image)
    assert np.array_equal(raw, solid)


def test_a_photo_like_mask_with_a_small_hole_is_not_filled():
    """小さな穴(腕と胴の隙間など)は埋めないこと。

    塗りつぶしを採用するのは面積が1.5倍以上になる場合だけなので、
    数%の隙間では発動しない。
    """
    image = Image.new("RGB", (400, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon(OUTLINE, fill="black")
    draw.ellipse([180, 250, 220, 300], fill="white")   # 面積比 数% の穴
    raw = SEG._foreground_mask(image)
    solid = SEG._solid_foreground_mask(image)
    assert np.array_equal(raw, solid)


def test_a_broken_outline_that_cannot_be_closed_fails_loudly(tmp_path):
    """途切れが大きすぎて閉じられない絵では、黙って変な型紙を出さないこと。

    塗りつぶしが画像全体へ漏れた場合は採用せず、結果としてパーツを検出
    できず明確なエラーになる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="判定できませんでした"):
        pipeline.generate_from_illustration(_sketch(gap_px=90), MEASUREMENTS)
