"""round22: 袖をシルエットから読む。

round21まで袖はまったく読めていなかった。既定の分割器は袖の領域を
「外接矩形の左右18%の帯」という固定比率で切っているだけなので、
ノースリーブの絵でも半袖の絵でも長袖の絵でも、同じ袖が同じように付いて
いた。ここでは、自前の袖テンプレート6種を実際に着せた「服だけの絵」を
合成して、袖の有無・袖丈・袖の形が読めることを固定する。

あわせて、round22で見つかった**round17以来の実バグ**——長袖が
ウエストを覆うと、袖の裾を胴のくびれと誤認してスカート丈と裾の広がりが
静かに壊れる——の回帰も防ぐ。
"""

import pytest
from PIL import Image, ImageDraw

from engine.illustration_fit import (
    BELL_WIDEST_AT_MIN,
    SLEEVE_TEMPLATE_LENGTH_CM,
    SLEEVE_TEMPLATE_WIDEST_AT,
    choose_sleeve_variation,
    measure_proportions,
    measure_sleeves,
    sleeve_hem_row,
    garment_span,
)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline
from engine.segmentation import SimpleSilhouetteSegmenter
from engine.svgpath import bounding_box, segments_to_polyline
from engine.templates_db import TemplateDB

SEG = SimpleSilhouetteSegmenter()
M = Measurements(83, 66, 91, 158, 52, 37)

# --- 「服だけの絵」の合成 ---------------------------------------------------
#
# 胴は、くびれのある立ち姿のワンピース。袖は**自前のテンプレートそのもの**を
# 使う(着た状態の見え方は平面パターンの幅の半分になるので0.5倍する)。
# 胴を手で描くのは、身頃テンプレートにはくびれが無く、くびれを基準にする
# 読み取り(round17以来)を試せないため。
PX = 6.0                       # 1cmあたりのピクセル数
CX, TOP = 350.0, 60.0          # 中心x, 上端y (px)
SHOULDER_HALF = 18.0           # cm
WAIST_Y, WAIST_HALF = 38.0, 12.0
HEM_Y, HEM_HALF = 98.0, 30.0
SHOULDER_DROP = 5.3            # 身頃テンプレートの肩下がり(前)
SLEEVE_OVERLAP = 3.0           # 袖を胴へ食い込ませる量(離すと別の塊になる)


def _p(x_cm, y_cm):
    return (CX + x_cm * PX, TOP + y_cm * PX)


def _torso_half_at(y_cm: float) -> float:
    """胴の半身幅(cm)。肩からウエストへ細くなり、ウエストから裾へ広がる。"""
    if y_cm <= WAIST_Y:
        t = y_cm / WAIST_Y
        return SHOULDER_HALF + (WAIST_HALF - SHOULDER_HALF) * t
    t = (y_cm - WAIST_Y) / (HEM_Y - WAIST_Y)
    return WAIST_HALF + (HEM_HALF - WAIST_HALF) * t


def _dress_with_sleeve(sleeve_variation: str | None, hug: bool = False) -> Image.Image:
    """くびれのある胴 + フレアスカート + 自前の袖テンプレート。

    `hug=False`(既定) … 袖を体からわずかに離して描く。イラストでは普通の
        描き方で、袖と胴の間に背景が入るぶん、胴の幅がそのまま見える。
    `hug=True` … 袖の内側の縁を胴の輪郭に沿わせる(腕を体に密着させた
        ポーズ)。前景が1つの塊になるので、袖に覆われた高さでは胴の幅を
        分離できない。
    """
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([
        _p(-SHOULDER_HALF, 0), _p(SHOULDER_HALF, 0), _p(WAIST_HALF, WAIST_Y),
        _p(HEM_HALF, HEM_Y), _p(-HEM_HALF, HEM_Y), _p(-WAIST_HALF, WAIST_Y),
    ], fill="black")
    if sleeve_variation:
        segments = TemplateDB().get("sleeve", sleeve_variation)
        assert segments is not None, sleeve_variation
        points = segments_to_polyline(segments, curve_steps=200)
        x0, y0, _x1, _y1 = bounding_box(segments)
        if not hug:
            shape = [((x - x0) * 0.5, y - y0) for x, y in points]
            base = SHOULDER_HALF - SLEEVE_OVERLAP
            for sign in (-1, 1):
                draw.polygon([_p(sign * (base + x), SHOULDER_DROP + y)
                              for x, y in shape], fill="black")
        else:
            # 腕を体に密着させた描き方。袖の内側の縁を胴の輪郭にぴったり
            # 沿わせるため、行ごとに袖の幅を測って「胴の縁 → 胴の縁+袖幅」
            # の帯として描き直す(テンプレートをそのまま置くと、袖口が
            # 内側へ細くなるぶん胴との間に隙間ができてしまう)。
            widths = _sleeve_half_widths_cm(sleeve_variation)
            for sign in (-1, 1):
                inner, outer = [], []
                for y_cm, half_w in widths:
                    top = SHOULDER_DROP + y_cm
                    edge = _torso_half_at(min(top, HEM_Y)) - 0.5
                    inner.append(_p(sign * edge, top))
                    outer.append(_p(sign * (edge + half_w), top))
                draw.polygon(outer + inner[::-1], fill="black")
    return image


def _sleeve_half_widths_cm(variation: str) -> list[tuple[float, float]]:
    """袖テンプレートの、行ごとの (袖山からの距離cm, 着た状態の幅cm)。

    着た状態の見え方は平面パターンの幅の半分になるので0.5倍する。
    """
    import numpy as np

    segments = TemplateDB().get("sleeve", variation)
    x0, y0, x1, y1 = bounding_box(segments)
    scale = 8
    points = segments_to_polyline(segments, curve_steps=400)
    canvas = Image.new("L", (int((x1 - x0) * scale) + 4, int((y1 - y0) * scale) + 4), 0)
    ImageDraw.Draw(canvas).polygon(
        [((x - x0) * scale + 2, (y - y0) * scale + 2) for x, y in points], fill=255)
    widths = (np.array(canvas) > 128).sum(axis=1)
    rows = np.where(widths > 0)[0]
    top, bottom = int(rows[0]), int(rows[-1])
    out = []
    for y in range(top, bottom + 1):
        if widths[y] <= 0:
            continue
        out.append(((y - top) / scale, float(widths[y]) / scale * 0.5))
    return out


def _mask(sleeve_variation, hug: bool = False):
    mask = SEG.silhouette_mask(_dress_with_sleeve(sleeve_variation, hug=hug))
    assert mask is not None, sleeve_variation
    return mask


# --- テンプレート側の指標が実測値であること ---------------------------------

@pytest.mark.parametrize("variation", sorted(SLEEVE_TEMPLATE_LENGTH_CM))
def test_sleeve_template_table_matches_the_actual_templates(variation):
    """袖丈と「いちばん太い位置」の表が、テンプレートの実測と一致すること。

    しきい値はこの表の値の中点で決めているので、テンプレートを描き変えたら
    ここで気付ける(当てずっぽうの数値を置かないため)。
    """
    import numpy as np

    segments = TemplateDB().get("sleeve", variation)
    assert segments is not None
    x0, y0, x1, y1 = bounding_box(segments)
    assert (y1 - y0) == pytest.approx(SLEEVE_TEMPLATE_LENGTH_CM[variation], abs=0.1)

    scale = 8
    points = segments_to_polyline(segments, curve_steps=400)
    canvas = Image.new("L", (int((x1 - x0) * scale) + 4, int((y1 - y0) * scale) + 4), 0)
    ImageDraw.Draw(canvas).polygon(
        [((x - x0) * scale + 2, (y - y0) * scale + 2) for x, y in points], fill=255)
    widths = (np.array(canvas) > 128).sum(axis=1)
    rows = np.where(widths > 0)[0]
    top, bottom = int(rows[0]), int(rows[-1])
    profile = [widths[min(bottom, top + int((bottom - top) * i / 10))] for i in range(11)]
    widest_at = profile.index(max(profile)) / 10
    assert widest_at == pytest.approx(SLEEVE_TEMPLATE_WIDEST_AT[variation], abs=0.05)


# --- 袖の有無 ---------------------------------------------------------------

def test_a_sleeveless_drawing_is_read_as_sleeveless():
    """袖を描いていない絵では、袖の裾の段差が見つからないこと。"""
    mask = _mask(None)
    top, bottom, _figure = garment_span(mask)
    assert sleeve_hem_row(mask, top, bottom) is None
    reading = measure_sleeves(mask, M.height)
    assert reading.sleeveless
    assert choose_sleeve_variation(reading, "straight") is None


@pytest.mark.parametrize("variation", sorted(SLEEVE_TEMPLATE_LENGTH_CM))
def test_every_sleeve_template_is_seen_as_a_sleeve(variation):
    """6種すべてで、袖があること自体は必ず読めること。

    ノースリーブ(段差1px)と袖あり(段差34px以上)は2桁違う、という
    このモジュールの前提そのものを固定する。
    """
    reading = measure_sleeves(_mask(variation), M.height)
    assert not reading.sleeveless, variation
    assert choose_sleeve_variation(reading, "straight") is not None


# --- 袖丈と袖の形 -----------------------------------------------------------

@pytest.mark.parametrize("variation,expected_cm", sorted(SLEEVE_TEMPLATE_LENGTH_CM.items()))
def test_every_sleeve_length_is_measured_in_cm(variation, expected_cm):
    """6種すべてで、袖丈をcmで測れること(誤差2cm以内)。

    round22では、袖がウエストより下まである絵(straight/curve/bell、および
    ウエストのすぐ下で終わるpuff/7分袖)で袖丈を測れなかった。cmへ換算する
    基準の「くびれ」が袖に隠れると考えていたためである。round23で、
    **袖が体から離れて描かれている行では胴が見えている**ことを使うように
    したので、6種すべてで測れるようになった。実測:

        入力            読んだ袖丈   テンプレート
        cap               17.6         17.0
        puff              31.9         30.8
        three_quarter     39.3         38.0
        straight/curve    53.7         52.0
        bell              53.7         52.0
    """
    reading = measure_sleeves(_mask(variation), M.height)
    assert reading.length_cm == pytest.approx(expected_cm, abs=2.0), variation


@pytest.mark.parametrize("variation,expected", [
    ("cap", "cap"),
    ("puff", "puff"),
    ("three_quarter", "three_quarter"),
    ("straight", "straight"),
    ("curve", "straight"),      # straightと見分けられない(下のテストで固定)
    ("bell", "bell"),
])
def test_the_right_sleeve_template_is_chosen(variation, expected):
    """描いた袖に対して、いちばん近いテンプレートが選ばれること。

    round22ではcap/bell/長袖の3通りしか分けられず、puffと7分袖は長袖に
    まとめられていた(袖の裾がちょうどウエストの高さで終わるため)。
    """
    reading = measure_sleeves(_mask(variation), M.height)
    assert choose_sleeve_variation(reading, "?") == expected, variation


@pytest.mark.parametrize("variation,expected", [
    ("straight", "straight"),
    ("curve", "straight"),
    ("bell", "bell"),
])
def test_a_sleeve_hugging_the_body_still_reads_as_a_long_sleeve(variation, expected):
    """腕を体に密着させた絵では、袖丈は測らず「長袖」とだけ判断すること。

    密着していると前景が1つの塊になり、袖に覆われた高さでは胴の幅を
    分離できない=cmへ換算する基準(背丈)がシルエットに現れない。
    当てずっぽうの袖丈を出すよりは、読める範囲(長袖であること、
    ベルスリーブかどうか)だけを使う。
    """
    reading = measure_sleeves(_mask(variation, hug=True), M.height)
    assert reading.covers_waist, variation
    assert reading.length_cm is None
    assert choose_sleeve_variation(reading, "?") == expected


def test_straight_and_curve_are_honestly_not_distinguished():
    """straightとcurveが見分けられないことを、事実として固定する。

    両者の違いは袖口の細まり方だけ(袖口/最大幅が0.77と0.71)で、絵から
    読み取れる精度では区別できない。「読めているつもり」にならないよう、
    区別できないこと自体をテストに書いておく。
    """
    straight = measure_sleeves(_mask("straight"), M.height)
    curve = measure_sleeves(_mask("curve"), M.height)
    assert straight.widest_at == pytest.approx(curve.widest_at, abs=0.05)
    assert (choose_sleeve_variation(straight, "?")
            == choose_sleeve_variation(curve, "?") == "straight")


def test_bell_is_the_only_long_sleeve_above_the_shape_threshold():
    """ベルスリーブだけがしきい値を超えること(しきい値が効いている証拠)。"""
    values = {v: measure_sleeves(_mask(v), M.height).widest_at
              for v in ("straight", "curve", "bell")}
    assert values["bell"] >= BELL_WIDEST_AT_MIN
    assert values["straight"] < BELL_WIDEST_AT_MIN
    assert values["curve"] < BELL_WIDEST_AT_MIN


# --- round17以来の実バグ: 長袖がスカートの読み取りを壊していた ---------------

def test_a_long_sleeve_no_longer_corrupts_the_skirt_reading():
    """長袖の絵で、スカート丈と裾の広がりに**誤った値**が出ないこと。

    round21まではこうだった(同じ胴・同じスカートで、袖だけ差し替えた実測):

        袖            検出したくびれy  真値  丈比  広がり
        なし/cap            285        288  1.61   2.49  (正しい)
        three_quarter       320        288  1.26   2.19
        straight/bell       404        288  0.71   1.68  (大きく誤り)

    袖の裾がいちばん細い行になるため、そこをウエストと誤認していた。
    もっともらしい別の値が出るので利用者は気付けない。読めないときは
    読まず、その旨を開示する。
    """
    reference = measure_proportions(_mask(None))
    assert reference.skirt_ratio is not None and reference.hem_flare is not None

    # 袖を体から離して描いた絵(イラストでは普通)では、胴が見えているので
    # round23から袖なしの絵とまったく同じ値が読める。
    long_sleeved = measure_proportions(_mask("straight"))
    assert not long_sleeved.waist_hidden_by_sleeve
    assert long_sleeved.skirt_ratio == pytest.approx(reference.skirt_ratio, abs=0.05)
    assert long_sleeved.hem_flare == pytest.approx(reference.hem_flare, abs=0.05)

    # 腕を体に密着させた絵では胴が隠れる。誤った値を出さず、理由を開示する。
    hugging = measure_proportions(_mask("straight", hug=True))
    assert hugging.waist_hidden_by_sleeve
    assert hugging.skirt_ratio is None
    assert hugging.hem_flare is None
    assert any("長袖" in n for n in hugging.notes()), hugging.notes()


def test_a_short_sleeve_still_lets_the_skirt_be_read():
    """短い袖では、スカートの読み取りが従来どおり効くこと。

    上の修正が「長袖のときだけ」効いていることの裏返し。ここが一緒に
    読めなくなると、round17〜19の成果を丸ごと失う。
    """
    reference = measure_proportions(_mask(None))
    capped = measure_proportions(_mask("cap"))
    assert not capped.waist_hidden_by_sleeve
    assert capped.skirt_ratio == pytest.approx(reference.skirt_ratio, abs=0.05)
    assert capped.hem_flare == pytest.approx(reference.hem_flare, abs=0.05)


# --- パイプラインまで届いていること -----------------------------------------

def test_the_pattern_has_no_sleeve_when_the_drawing_has_none(tmp_path):
    """ノースリーブの絵から、袖もカフスも付かない型紙が出ること。

    round21までは、ノースリーブの絵でも判定器が既定で袖を足していた。
    袖を外すときにカフスも一緒に外すのは、縫い付ける相手の無いパーツが
    1枚混ざった型紙にしないため。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(_dress_with_sleeve(None), M)
    kinds = {p.part_type for p in result.finalized_parts}
    assert "sleeve" not in kinds
    assert "cuffs" not in kinds
    assert any("ノースリーブ" in n for n in result.measurement_warnings), \
        result.measurement_warnings


@pytest.mark.parametrize("drawn,expected", [
    ("cap", "cap"),
    ("bell", "bell"),
    ("straight", "straight"),
])
def test_the_drawn_sleeve_reaches_the_generated_pattern(tmp_path, drawn, expected):
    """絵に描いた袖が、実際に生成される袖のバリエーションになること。

    round21までは、どの絵を渡しても判定器の既定値(straight)のままだった。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(_dress_with_sleeve(drawn), M)
    sleeves = {p.variation for p in result.finalized_parts if p.part_type == "sleeve"}
    assert sleeves == {expected}, (drawn, sleeves)


def test_the_generated_sleeve_still_fits_the_armhole(tmp_path):
    """袖を絵から差し替えても、袖山と袖ぐりが合っていること。

    袖の形を変えると袖山カーブの長さが変わる。round14の`scale_sleeve_to_
    cap_length`が働いて袖ぐりに合わせ直されるはずで、ここが崩れると
    「絵には近いが縫えない型紙」になる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for drawn in ("cap", "bell", "straight"):
        result = pipeline.generate_from_illustration(_dress_with_sleeve(drawn), M)
        kinds = [w.kind for w in result.compatibility_warnings()]
        assert "armhole_sleeve_cap" not in kinds, (drawn, kinds)


# --- round24: 「見分けられない」ことを、測って固定する ----------------------

def test_straight_and_curve_cannot_be_told_apart_across_drawing_conditions():
    """straightとcurveは、絵の描かれ方が変わると値の範囲が重なること。

    round22以来「袖口/最大幅が0.77と0.71で差が小さいので区別できない」と
    書いてきたが、それは**テンプレートの値**を見ての判断だった。round23で
    袖が体から離れている行から袖そのものの幅を直接測れるようになったので、
    改めて「しきい値で分けられないか」を確かめた。

    袖を分離して測ると確かに近い値が出る(1枚の絵での実測:
    straight 0.789 / curve 0.723、テンプレートは0.77 / 0.71)。しかし
    **解像度・袖の重なり具合・袖の大きさを振ると、両者の範囲は重なる**:

        straight 0.757〜0.869
        curve    0.706〜0.817

    同じ描かれ方どうしなら必ず straight > curve になるが、1枚の絵から
    どちらかを言い当てることはできない。しきい値を1つ置けば、たまたま
    その絵で当たるだけである。ここではその重なりを実際に測って固定し、
    「1枚のテスト画像で通るしきい値」を後から入れてしまわないようにする。
    """
    pairs = []
    for px in (4.0, 6.0, 8.0):
        for overlap in (3.0, 4.5):
            for scale in (0.9, 1.0):
                a = _wrist_to_widest_ratio("straight", px, overlap, scale)
                b = _wrist_to_widest_ratio("curve", px, overlap, scale)
                if a is not None and b is not None:
                    pairs.append((a, b))

    assert len(pairs) >= 8, len(pairs)
    straights = [a for a, _b in pairs]
    curves = [b for _a, b in pairs]
    # 同じ条件どうしなら必ず straight のほうが袖口が太い(形の差は実在する)。
    assert all(a > b for a, b in pairs)
    # それでも、条件をまたぐと範囲が重なる=1枚の絵からは決められない。
    assert min(straights) <= max(curves), (min(straights), max(curves))


def _wrist_to_widest_ratio(variation: str, px: float, overlap: float,
                            sleeve_scale: float) -> float | None:
    """描かれ方を変えて合成した絵から、袖の「袖口幅 ÷ 最大幅」を測る。"""
    import numpy as np

    from engine.illustration_fit import _row_runs, garment_span, sleeve_hem_row

    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    point = lambda x, y: (CX + x * px, TOP + y * px)   # noqa: E731
    draw.polygon([
        point(-SHOULDER_HALF, 0), point(SHOULDER_HALF, 0), point(WAIST_HALF, WAIST_Y),
        point(HEM_HALF, HEM_Y), point(-HEM_HALF, HEM_Y), point(-WAIST_HALF, WAIST_Y),
    ], fill="black")
    segments = TemplateDB().get("sleeve", variation)
    points = segments_to_polyline(segments, curve_steps=200)
    x0, y0, _x1, _y1 = bounding_box(segments)
    shape = [((x - x0) * 0.5 * sleeve_scale, (y - y0) * sleeve_scale) for x, y in points]
    for sign in (-1, 1):
        draw.polygon([point(sign * (SHOULDER_HALF - overlap + x), SHOULDER_DROP + y)
                      for x, y in shape], fill="black")

    mask = SEG.silhouette_mask(image)
    if mask is None:
        return None
    top, bottom, _figure = garment_span(mask)
    found = sleeve_hem_row(mask, top, bottom)
    if found is None:
        return None
    widths = []
    for y in range(top, found[0] + 1):
        runs = _row_runs(mask[y])
        if len(runs) == 3:
            widths.append(runs[0][1] - runs[0][0] + 1)
    if len(widths) < 10 or max(widths) <= 0:
        return None
    return widths[-1] / max(widths)
