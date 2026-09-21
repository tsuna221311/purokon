"""round17: イラストの「丈」と「裾の広がり」を型紙へ反映する。

round16まで、イラストモードはイラストを (part_type, variation) の選択に
しか使っておらず、まったく違うデザインを入れても寸法が1mmも変わらなかった。
ここではその回帰を防ぐ。
"""

import pytest
from PIL import Image, ImageDraw

from engine.illustration_fit import (
    NAPE_TO_WAIST_RATIO,
    SKIRT_FLARE_BY_VARIATION,
    SKIRT_LENGTH_RANGE_CM,
    choose_skirt_variation,
    measure_proportions,
    nape_to_waist_cm,
    skirt_length_cm,
)
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import PatternForgePipeline
from engine.segmentation import SimpleSilhouetteSegmenter
from engine.svgpath import bounding_box, segments_to_polyline
from engine.templates_db import TemplateDB

SEG = SimpleSilhouetteSegmenter()


def _dress(hem, with_sleeves: bool = True) -> Image.Image:
    """くびれのあるワンピースのシルエットを描く。hem=((右下),(左下))。"""
    image = Image.new("RGB", (400, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(140, 90), (260, 90), (230, 200), (170, 200)], fill="black")
    if with_sleeves:
        draw.polygon([(118, 95), (140, 95), (140, 180), (112, 180)], fill="black")
        draw.polygon([(260, 95), (282, 95), (288, 180), (260, 180)], fill="black")
    draw.polygon([(170, 200), (230, 200), hem[0], hem[1]], fill="black")
    return image


SHORT = ((320, 340), (80, 340))    # 短くて大きく広がる
MIDI = ((300, 430), (100, 430))    # ミディ丈で広がる
LONG = ((238, 600), (162, 600))    # 長くて細い


# --- テンプレート側の指標が実測値であること -------------------------------

def test_skirt_flare_table_matches_the_actual_templates():
    """`SKIRT_FLARE_BY_VARIATION`が、生成済みテンプレートの実測と一致すること。

    この表は「イラストの広がりに最も近いスカートを選ぶ」ための基準なので、
    テンプレートを描き変えたのに表が古いままだと、静かに別のスカートが
    選ばれるようになる。当てずっぽうの数値を置かないためにも固定する。
    """
    db = TemplateDB()
    for variation, expected in SKIRT_FLARE_BY_VARIATION.items():
        segments = db.get("skirt", variation)
        assert segments is not None, variation
        points = segments_to_polyline(segments, curve_steps=300)
        min_x, min_y, max_x, _max_y = bounding_box(segments)
        top_xs = [x for x, y in points if y <= min_y + 0.5]
        waist = max(top_xs) - min(top_xs)
        measured = (max_x - min_x) / waist
        assert measured == pytest.approx(expected, abs=0.01), variation


def test_nape_to_waist_matches_the_standard_body():
    """背丈の推定が、標準Mサイズの実寸(約38cm)と整合すること。"""
    assert nape_to_waist_cm(STANDARD_M.height) == pytest.approx(38.7, abs=0.5)
    assert 0.20 < NAPE_TO_WAIST_RATIO < 0.28


# --- シルエットの測定 -------------------------------------------------------

@pytest.mark.parametrize("label,hem,expect_flare_over", [
    ("短い・大きく広がる", SHORT, 3.0),
    ("ミディ・広がる", MIDI, 2.5),
])
def test_flared_silhouettes_measure_wide(label, hem, expect_flare_over):
    design = measure_proportions(SEG.silhouette_mask(_dress(hem)))
    assert design.hem_flare is not None, label
    assert design.hem_flare > expect_flare_over, (label, design.hem_flare)


def test_slim_silhouette_measures_narrow():
    design = measure_proportions(SEG.silhouette_mask(_dress(LONG)))
    assert design.hem_flare is not None
    assert design.hem_flare < 1.5, design.hem_flare


def test_skirt_ratio_orders_the_lengths_correctly():
    """丈の比が、短い<ミディ<長い の順になること。"""
    ratios = [measure_proportions(SEG.silhouette_mask(_dress(hem))).skirt_ratio
              for hem in (SHORT, MIDI, LONG)]
    assert all(r is not None for r in ratios), ratios
    assert ratios[0] < ratios[1] < ratios[2], ratios


def test_no_waist_means_no_length_reading():
    """くびれの無いAラインでは、丈を測らずNoneを返すこと。

    「探索範囲でいちばん細い行」を無条件に採用していたときは、上から下へ
    単調に広がる絵でも探索範囲の上端が選ばれ、3種類の別々の絵がそろって
    「丈比3.0」という同じ値を返していた。当てずっぽうの値を型紙へ入れる
    くらいなら測らない、という方針の回帰テスト。
    """
    image = Image.new("RGB", (400, 700), "white")
    ImageDraw.Draw(image).polygon(
        [(160, 90), (240, 90), (340, 600), (60, 600)], fill="black")
    design = measure_proportions(SEG.silhouette_mask(image))
    assert design.skirt_ratio is None
    # 広がりの方は基準を変えて測れるので、こちらは読める。
    assert design.hem_flare is not None


def test_unreadable_image_reports_that_nothing_was_read():
    design = measure_proportions(None)
    assert design.skirt_ratio is None and design.hem_flare is None
    assert any("読み取れませんでした" in n for n in design.notes())


# --- 変換と選択 -------------------------------------------------------------

def test_skirt_length_is_clamped_and_the_clamp_is_reported():
    length, clamped = skirt_length_cm(9.0, 158.0)   # 現実にはありえない比
    assert length == SKIRT_LENGTH_RANGE_CM[1]
    assert clamped is True
    length, clamped = skirt_length_cm(1.3, 158.0)
    assert SKIRT_LENGTH_RANGE_CM[0] < length < SKIRT_LENGTH_RANGE_CM[1]
    assert clamped is False
    assert skirt_length_cm(None, 158.0) == (None, False)


def test_choose_skirt_variation_picks_the_closest_flare():
    assert choose_skirt_variation(1.4, "flare") == "tight"
    assert choose_skirt_variation(2.9, "flare") == "circle"
    assert choose_skirt_variation(None, "wrap") == "wrap"


# --- 本題: 違うイラストから違う型紙が出ること -------------------------------

def test_different_illustrations_now_produce_different_patterns(tmp_path):
    """同じ採寸でも、イラストが違えばスカートの寸法と種類が変わること。

    round16までの実測では、下の3枚すべてが flare 80.0 × 60.0 cm という
    まったく同じ型紙になっていた(1mmも違わなかった)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    measurements = Measurements(83, 66, 91, 158, 52, 37)
    seen = []
    for hem in (SHORT, MIDI, LONG):
        result = pipeline.generate_from_illustration(_dress(hem), measurements)
        skirt = [p for p in result.scaled_parts if p.part_type == "skirt"][0]
        seen.append((skirt.variation, round(skirt.width_cm, 1), round(skirt.height_cm, 1)))
    assert len(set(seen)) == 3, seen
    # 丈は 短い < ミディ < 長い の順。
    assert seen[0][2] < seen[1][2] < seen[2][2], seen
    # 広がりは 短い・ミディが広く、長いが細い。
    assert seen[2][1] < seen[0][1], seen


def test_illustration_mode_discloses_what_it_read(tmp_path):
    """読み取った内容を利用者へ開示すること(黙って寸法を変えない)。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(
        _dress(MIDI), Measurements(83, 66, 91, 158, 52, 37))
    # round32: イラストから読み取った内容の説明は design_notes へ移した。
    text = " / ".join(result.design_notes + result.measurement_warnings)
    assert "スカート丈" in text and "裾の広がり" in text


def test_manual_mode_is_unaffected(tmp_path):
    """手動選択モードは従来通り(イラストの読み取りが混入しないこと)。"""
    from engine.pipeline import build_garment_spec

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style="flare")
    result = pipeline.generate_from_selection(spec, Measurements(83, 66, 91, 158, 52, 37))
    skirt = [p for p in result.scaled_parts if p.part_type == "skirt"][0]
    assert skirt.variation == "flare"
    assert skirt.height_cm == pytest.approx(60.0, abs=0.1)
    assert not any("イラストから" in n
                   for n in result.design_notes + result.measurement_warnings)


# --- round18: 複数枚 --------------------------------------------------------

def _scaled(hem, scale=1.0, offset=0):
    """同じ衣装を、別の縮尺・位置で描いたカット。"""
    image = Image.new("RGB", (400, 700), "white")
    draw = ImageDraw.Draw(image)

    def s(pt):
        return (int(200 + (pt[0] - 200) * scale), int(90 + (pt[1] - 90) * scale) + offset)

    draw.polygon([s(p) for p in [(140, 90), (260, 90), (230, 200), (170, 200)]], fill="black")
    draw.polygon([s(p) for p in [(170, 200), (230, 200)]] + [s(hem[0]), s(hem[1])], fill="black")
    return image


def test_combine_uses_the_median_not_the_mean():
    """外れ値1枚に引きずられないこと(平均ではなく中央値)。"""
    from engine.illustration_fit import DesignProportions, combine_proportions

    combined = combine_proportions([
        DesignProportions(skirt_ratio=2.0, hem_flare=2.3),
        DesignProportions(skirt_ratio=2.1, hem_flare=2.4),
        DesignProportions(skirt_ratio=9.9, hem_flare=9.9),   # 別カット/小物のアップ等
    ])
    assert combined.skirt_ratio == 2.1          # 平均なら4.67になる
    assert combined.hem_flare == pytest.approx(2.4)
    assert combined.image_count == 3
    assert combined.skirt_ratio_samples == 3


def test_combine_counts_only_the_images_that_could_be_read():
    from engine.illustration_fit import DesignProportions, combine_proportions

    combined = combine_proportions([
        DesignProportions(skirt_ratio=2.0, hem_flare=2.3),
        DesignProportions(skirt_ratio=None, hem_flare=2.4),
    ])
    assert combined.skirt_ratio_samples == 1
    assert combined.hem_flare_samples == 2
    assert any("2枚" in n for n in combined.notes())


def test_multiple_cuts_of_the_same_costume_agree_with_a_single_cut(tmp_path):
    """同じ衣装を縮尺違いで3枚渡しても、1枚のときと同じ型紙になること。

    読み取りは比率だけを使うので、絵の大きさや位置には依存しない。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    measurements = Measurements(83, 66, 91, 158, 52, 37)

    single = pipeline.generate_from_illustration(_dress(MIDI), measurements)
    multi = pipeline.generate_from_illustration(
        [_dress(MIDI), _scaled(MIDI, scale=0.6), _scaled(MIDI, offset=40)], measurements)

    def _skirt(result):
        p = [x for x in result.scaled_parts if x.part_type == "skirt"][0]
        return (p.variation, round(p.width_cm, 1), round(p.height_cm, 1))

    assert _skirt(multi) == _skirt(single)
    assert any("3枚" in n for n in multi.design_notes + multi.measurement_warnings)


def test_an_unreadable_extra_image_does_not_change_the_result(tmp_path):
    """読み取れないカット(小物のアップ等)が混ざっても結果が変わらないこと。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    measurements = Measurements(83, 66, 91, 158, 52, 37)
    blob = Image.new("RGB", (400, 700), "white")
    ImageDraw.Draw(blob).ellipse([150, 300, 250, 400], fill="black")

    single = pipeline.generate_from_illustration(_dress(MIDI), measurements)
    multi = pipeline.generate_from_illustration(
        [_dress(MIDI), blob, _scaled(MIDI, offset=30)], measurements)

    def _height(result):
        return round([x for x in result.scaled_parts
                      if x.part_type == "skirt"][0].height_cm, 1)

    assert _height(multi) == _height(single)


def test_parts_are_the_union_across_images(tmp_path):
    """パーツ構成が全枚の和になること。

    1枚では見切れていたパーツが別のカットに写っていれば拾える、という
    複数枚対応の主目的。ここでは「スカートだけのカット」と
    「上半身だけのカット」を渡し、両方のパーツが揃うことを確認する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    measurements = Measurements(83, 66, 91, 158, 52, 37)
    result = pipeline.generate_from_illustration(
        [_dress(MIDI), _dress(SHORT)], measurements)
    kinds = {p.part_type for p in result.scaled_parts}
    assert {"front_bodice", "back_bodice", "skirt"} <= kinds


def test_empty_image_list_is_rejected(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="1枚も"):
        pipeline.generate_from_illustration([], Measurements(83, 66, 91, 158, 52, 37))


# --- round18: 襟ぐりの形の読み取り ------------------------------------------

def _template_silhouette(part: str, variation: str, pad: float = 1.8) -> Image.Image:
    """テンプレートSVGを塗りつぶしのシルエット画像として描画する。

    「服だけが写った画像」(このアプリが推奨する入力)の理想形。
    余白を付けるのは、前景が画面いっぱいになると分割器が
    「背景の推定に失敗した」と判断して何も返さないため。
    """
    cairosvg = pytest.importorskip("cairosvg")
    import io as _io

    path = f"pattern_templates/{part}__{variation}.svg"
    with open(path, encoding="utf-8") as handle:
        svg = handle.read().replace('fill="none"', 'fill="black"')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=400,
                            background_color="white")
    body = Image.open(_io.BytesIO(png)).convert("RGB")
    canvas = Image.new("RGB", (int(body.width * pad), int(body.height * pad)), "white")
    canvas.paste(body, (int(body.width * (pad - 1) / 2), int(body.height * (pad - 1) / 2)))
    return canvas


@pytest.mark.parametrize("variation", [
    "round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart", "turtle_neck",
])
def test_neckline_detector_recognises_our_own_templates(variation):
    """自前の前身頃テンプレートを描画して入力すると、その襟ぐりだと分かること。

    しきい値はこの6枚を実測して決めた値なので、テンプレートを描き変えたら
    ここで気付ける。6種すべてを見分けられることが、この判定の唯一の
    客観的な裏付けである。
    """
    import numpy as np

    from engine.illustration_fit import measure_neckline

    image = _template_silhouette("front_bodice", variation)
    mask = np.array(image.convert("L")) < 128
    assert measure_neckline(mask) == variation


def test_neckline_detector_declines_when_the_top_edge_is_entirely_flat():
    """上辺が端から端まで平らな絵では、判定せずNoneを返すこと。

    それは襟ぐりではなくベアトップのようなシルエットか、単に上辺が水平に
    描かれているだけである。当てずっぽうにタートルネックだと決めつけない。
    """
    import numpy as np

    from engine.illustration_fit import measure_neckline

    image = Image.new("RGB", (400, 700), "white")
    ImageDraw.Draw(image).polygon(
        [(140, 90), (260, 90), (230, 200), (170, 200)], fill="black")
    mask = np.array(image.convert("L")) < 128
    assert measure_neckline(mask) is None


def test_illustration_mode_uses_the_detected_neckline(tmp_path):
    """読み取った襟ぐりが、実際に生成される身頃のバリエーションになること。

    round17までは、APIキー無しの既定状態では判定器が領域ラベルから
    決め打ちするため、どんなイラストでも必ず round_neck になっていた。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    measurements = Measurements(83, 66, 91, 158, 52, 37)
    for variation in ("round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart"):
        result = pipeline.generate_from_illustration(
            _template_silhouette("front_bodice", variation), measurements)
        bodices = [p for p in result.scaled_parts
                   if p.part_type in ("front_bodice", "back_bodice")]
        assert bodices, variation
        assert all(p.variation == variation for p in bodices), (
            variation, [p.variation for p in bodices])
        assert any("襟ぐりの形" in n
                   for n in result.design_notes + result.measurement_warnings), variation
