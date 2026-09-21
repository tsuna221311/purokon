"""round23: 袖ぐりの深さを、バストに応じて深くする。

round22まで、身頃のY方向は身長比で一律に伸縮していた。つまり**袖ぐりの
深さがバストでほとんど変わらなかった**。実測(身長158cm固定):

    バスト  袖ぐり深さ  文化式の目安   差
      60      23.02      21.58     +1.43
      83      23.43      23.50     -0.07
     110      23.50      25.75     -2.25
     130      23.50      27.42     -3.92   ← 脇の下が4cm浅い

袖ぐりが4cm浅いと腕が上がらず脇が食い込む。小さいサイズでは逆に1.4cm深く、
袖ぐりが浮く。round14でX方向にやったのと同じ「区間ごとに違う倍率」を
Y方向にも入れて直した。
"""

import pytest

from tests.conftest import bodice_width_at_bust_cm

from engine.bodice_fit import (
    ARMHOLE_DEPTH_PER_BUST_CM, BODICE_FIT_Y_ROLES, FIT_Y_ROLES, armhole_depth_cm,
    build_y_map, parse_fit_anchors,
)
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import bounding_box, segments_to_polyline
from engine.templates_db import TemplateDB

BODICE_TYPES = ("front_bodice", "back_bodice", "front_bodice_zip_panel")
BUSTS = (60, 70, 83, 95, 110, 130)


def _bodice(pipeline, bust_cm, height_cm=158.0, variation="round_neck"):
    spec = GarmentSpec(parts=[PartRequest("front_bodice", variation, 1),
                               PartRequest("back_bodice", variation, 1)])
    result = pipeline.generate_from_selection(
        spec, Measurements(bust_cm, bust_cm * 0.79, bust_cm * 1.10, height_cm, 52, 37))
    return {p.part_type: p for p in result.scaled_parts}


def _measured_depth_cm(scaled) -> float:
    """首の付け根の線(輪郭の上端)から脇の下までの距離。

    脇の下は「脇線がいちばん上で始まる高さ」。round26で脇線が裾へ向かって
    開くようになり、最も外側のxを持つ点は**裾**になったので、
    `engine/compatibility.py`の脇線判定を使って探す。
    """
    from engine.compatibility import _closed_points, side_seam_edges

    points = _closed_points(segments_to_polyline(scaled.segments, curve_steps=300))
    _min_x, min_y, _max_x, _max_y = bounding_box(scaled.segments)
    # round29: 辺の集め方はエンジンと同じ`side_seam_edges`に揃える。ここだけ
    # 独自に集めていると、胸ぐせダーツの口の上に残る短い断片を取りこぼし、
    # 「脇の下」がダーツの口の下と判定されて袖ぐりが深く見える
    # (実測: バスト83で23.50cm→31.96cm)。
    tops = [min(a[1], b[1]) for _i, _side, a, b in side_seam_edges(points)]
    assert tops, "脇線が見つからない"
    return min(tops) - min_y


def _bust_dart_mouth_total_cm(scaled) -> float:
    """前身頃の片側の脇線に開いた、胸ぐせダーツの口の幅の合計(cm)。"""
    from engine.compatibility import _closed_points, _is_dart_notch_at

    points = _closed_points(segments_to_polyline(scaled.segments, curve_steps=300))
    xs = [p[0] for p in points]
    center_x = (min(xs) + max(xs)) / 2.0
    total = 0.0
    for i in range(len(points) - 2):
        if _is_dart_notch_at(points, i, 0.5) and points[i][0] < center_x:
            total += abs(points[i + 2][1] - points[i][1])
    return total


# --- テンプレート側の宣言 ---------------------------------------------------

@pytest.mark.parametrize("part_type", BODICE_TYPES)
def test_every_bodice_template_declares_its_fit_lines(part_type):
    """全ての身頃テンプレートが`data-fit-y`を持つこと。

    持たないテンプレートは静かに従来どおりの一律伸縮に戻る。その経路が
    あるので、「新しく足したテンプレートだけ袖ぐりが浅い」という気づき
    にくい後退を防ぐために固定する(round14で`data-fit-x`に同じ理由の
    テストを置いたのと同じ)。
    """
    db = TemplateDB()
    found = [(pt, v) for pt, v in db.available() if pt == part_type]
    assert found, part_type
    for pt, variation in found:
        anchors = db.get_fit_anchors_y(pt, variation)
        roles = {role for role, _x in anchors}
        assert roles == set(BODICE_FIT_Y_ROLES), (pt, variation, anchors)


def test_unknown_fit_y_roles_are_rejected_rather_than_ignored():
    """未知の役割名を黙って無視しないこと(無視すると古い挙動へ静かに戻る)。"""
    from engine.bodice_fit import BodiceFitError

    with pytest.raises(BodiceFitError):
        parse_fit_anchors("neck:0 armhole:23.5 hem:58", roles=FIT_Y_ROLES)


# --- 深さの式 ---------------------------------------------------------------

def test_the_standard_size_keeps_the_template_depth():
    """標準M(バスト83)では増分0で、テンプレートの深さそのままになること。"""
    assert armhole_depth_cm(23.5, STANDARD_M.bust, 1.0) == pytest.approx(23.5)


def test_the_depth_follows_the_bunka_increment():
    """バスト1cmあたりの深さの増え方が、文化式(B/12)と一致すること。"""
    assert ARMHOLE_DEPTH_PER_BUST_CM == pytest.approx(1.0 / 12.0)
    base = armhole_depth_cm(23.5, 83, 1.0)
    assert armhole_depth_cm(23.5, 95, 1.0) - base == pytest.approx(12 / 12.0)
    assert armhole_depth_cm(23.5, 130, 1.0) - base == pytest.approx(47 / 12.0)


def test_the_height_scale_still_applies():
    """身長比が効かなくなっていないこと(丈の基準は引き続き身長)。"""
    assert armhole_depth_cm(23.5, 83, 1.2) == pytest.approx(23.5 * 1.2)


def test_a_broken_order_produces_no_map_rather_than_a_broken_pattern():
    """節点の順序が崩れる入力では写像を作らないこと。

    深さが着丈を超えるような値では、Y方向の写像が輪郭を裏返してしまう。
    そういう場合は写像を作らず(空リスト)、呼び出し側が従来どおりの
    一律伸縮に落ちる方が安全である。
    """
    anchors = [("neck", 0.0), ("underarm", 23.5), ("hem", 24.0)]
    assert build_y_map(anchors, 200.0, 1.0) == []
    assert build_y_map([("neck", 0.0), ("hem", 58.0)], 83.0, 1.0) == []


# --- 実際に生成される型紙 ---------------------------------------------------

@pytest.mark.parametrize("bust", BUSTS)
def test_the_generated_armhole_depth_tracks_the_guideline(tmp_path, bust):
    """生成された前身頃の袖ぐり深さが、文化式の目安どおりに深くなること。

    round22までは身長比だけで決まっていて、バスト130で目安より3.9cm浅かった。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    front = _bodice(pipeline, bust)["front_bodice"]
    expected = armhole_depth_cm(23.5, bust, 1.0)
    assert _measured_depth_cm(front) == pytest.approx(expected, abs=0.5), bust


def test_the_standard_size_pattern_is_unchanged(tmp_path):
    """標準Mの型紙は、round22までとまったく同じ寸法であること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    # ここだけは標準Mそのもの(バスト83・ヒップ91)で作る。`_bodice`は
    # ヒップをバスト×1.10で作るため91.3cmになり、裾の開き量が0.075cmずれる。
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1)])
    result = pipeline.generate_from_selection(spec, STANDARD_M)
    parts = {p.part_type: p for p in result.scaled_parts}
    front = parts["front_bodice"]
    # round26で測り方を「最も外側のxを持つ点」から「脇線の上端」へ変えた。
    # テンプレートの設計値(BODICE_AH_DEPTH=23.5)ちょうどになる。round25まで
    # 23.43と出ていたのは、袖ぐりカーブを折れ線で近似したぶんのずれである。
    assert _measured_depth_cm(front) == pytest.approx(23.5, abs=0.05)
    min_x, min_y, max_x, max_y = bounding_box(front.segments)
    # round26: 裾はヒップ(91+ゆとり4=95cm)が通る幅まで開くので、外接矩形の
    # 幅は 95/2 = 47.5cm になる。バストの高さでの幅は 45.5cm のまま
    # (tests/conftest.py の bodice_width_at_bust_cm で測っている)。
    assert (max_x - min_x) == pytest.approx(47.5, abs=0.05)
    assert bodice_width_at_bust_cm(front) == pytest.approx(45.5, abs=0.1)
    # round29: 前身頃の**紙の上の**丈は、胸ぐせダーツの口の幅ぶんだけ
    # 後ろ身頃より長い。ダーツを縫い閉じるとその分が畳まれて消え、
    # 後ろ身頃(58.0cm)と釣り合う。round28まで標準Mにはダーツが1本も
    # 入っていなかったので58.0cmのままだった(新文化式では、標準体型にも
    # 18.25度の胸ぐせダーツが入る)。
    back = parts["back_bodice"]
    _bx0, back_min_y, _bx1, back_max_y = bounding_box(back.segments)
    assert (back_max_y - back_min_y) == pytest.approx(58.0, abs=0.05)
    # round71: 長くする量は「口の幅」ではなく「縫って閉じたときに脇線が
    # 縮む量」である。脚を揃える(`engine/darts.py`の`_equalise_legs`)と
    # 口が脇線から外れるので、両者はもう一致しない(実測で0.27cmの差)。
    # 前身頃の丈は、後ろ身頃に**その縮む量**を足した長さになる。
    mouth = _bust_dart_mouth_total_cm(front)
    assert mouth > 0
    shrink = (max_y - min_y) - 58.0
    assert 0 < shrink < mouth, (shrink, mouth)
    # 「縮む量ぶん長くしたので、縫うと前後が釣り合う」という肝心のところは、
    # 縫った後の脇線を実測して確かめている
    # (tests/test_round71_dart_truing.py の
    #  test_the_front_and_back_side_seams_still_match)。ここでは
    # 「後ろより長い」「ただし口の幅より小さい」だけを押さえる。


@pytest.mark.parametrize("bust", BUSTS)
def test_the_hem_stays_where_the_height_puts_it(tmp_path, bust):
    """袖ぐりを深くしても、着丈は変わらないこと。

    深くなった分は脇線が短くなって吸収される。着丈まで一緒に伸びると
    「バストが大きい人だけ裾が長い」という別の破綻になる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    back = _bodice(pipeline, bust)["back_bodice"]   # 後身頃は脇ダーツで
    _min_x, min_y, _max_x, max_y = bounding_box(back.segments)  # 丈が伸びない
    assert (max_y - min_y) == pytest.approx(58.0, abs=0.05), bust


@pytest.mark.parametrize("bust", BUSTS)
def test_the_side_seams_still_match_front_to_back(tmp_path, bust):
    """袖ぐりを深くしても、前後の脇線が縫い合わせられること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1)])
    result = pipeline.generate_from_selection(
        spec, Measurements(bust, bust * 0.79, bust * 1.10, 158, 52, 37))
    kinds = [w.kind for w in result.compatibility_warnings()]
    assert "side_seam" not in kinds, (bust, kinds)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_sleeve_still_fits_the_deeper_armhole(tmp_path, bust):
    """深くなった袖ぐりにも、袖が縫い付けられること。

    袖は「実測した袖ぐりの長さ」に合わせて幅を決める(round14の
    `scale_sleeve_to_cap_length`)。袖ぐりを深くすると袖ぐりの弧長が
    伸びるので、その仕組みが引き続き効いていることを確かめる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1),
                               PartRequest("sleeve", "straight", 2)])
    result = pipeline.generate_from_selection(
        spec, Measurements(bust, bust * 0.79, bust * 1.10, 158, 52, 37))
    kinds = [w.kind for w in result.compatibility_warnings()]
    assert "armhole_sleeve_cap" not in kinds, (bust, kinds)


@pytest.mark.parametrize("variation", ["round_neck", "v_neck", "square_neck",
                                        "boat_neck", "sweetheart", "turtle_neck"])
def test_the_outline_stays_a_valid_polygon_across_the_range(tmp_path, variation):
    """全ネックライン×採寸の両端で、輪郭が自己交差しないこと。

    Y方向にも区間ごとに違う倍率を掛けるようにしたので、輪郭が折り返して
    型紙として成立しなくなる可能性を実際に潰しておく。台襟が首ぐりより
    上にあるタートルネック(節点の外側)も含める。
    """
    shapely = pytest.importorskip("shapely.geometry")

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    # Measurements の有効範囲(engine/measurements.py の _VALID_RANGES)の
    # 両端まで振る。ウエスト/ヒップにも独自の範囲があるので、比例では
    # なく範囲内へ丸めた値を組み合わせる。
    for bust in (50, 60, 83, 120, 160):
        for height in (140, 158, 190):
            waist = min(150.0, max(40.0, bust * 0.79))
            hip = min(160.0, max(50.0, bust * 1.10))
            spec = GarmentSpec(parts=[PartRequest("front_bodice", variation, 1),
                                       PartRequest("back_bodice", variation, 1)])
            result = pipeline.generate_from_selection(
                spec, Measurements(bust, waist, hip, height, 52, 37))
            parts = {p.part_type: p for p in result.scaled_parts}
            for scaled in parts.values():
                points = segments_to_polyline(scaled.segments, curve_steps=120)
                polygon = shapely.Polygon(points)
                assert polygon.is_valid, (variation, bust, height, scaled.part_type)
                assert polygon.area > 0
