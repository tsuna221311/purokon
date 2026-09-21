import pytest

from engine.bodice_fit import BODICE_EASE_CM, bodice_bust_cm_for_scale

from engine.measurements import Measurements, STANDARD_M, _VALID_RANGES
from engine.part_specs import (
    BAND_PART_TYPES, MAX_SCALE, MAX_SCALE_BAND, MIN_SCALE, MIN_SCALE_BAND, clamp_scale_for_part,
)
from engine.scaling import (
    compute_scale_factors, measurement_clamp_warnings, scale_band_to_target_width,
    scale_template,
)
from engine.svgpath import parse_path


def test_standard_m_scales_to_one_for_every_part():
    for part_type in ("front_bodice", "back_bodice", "sleeve", "skirt",
                       "front_pants", "back_pants", "collar", "cuffs", "waistband"):
        rx, ry = compute_scale_factors(STANDARD_M, part_type)
        assert rx == pytest.approx(1.0)
        assert ry == pytest.approx(1.0)


def test_skirt_only_scales_width_not_length():
    """スカートは幅(X)だけを変形し、丈(Y)は身長に影響されない。

    round12でスカートの幅の決め方が「ヒップ比」から「ウエストとヒップの
    どちらが必要とする倍率が大きいか」に変わったため(part_specs.pyの
    `lower_garment_x_scale`参照)、期待値もその式で計算する。
    """
    from engine.part_specs import lower_garment_x_scale

    m = Measurements(bust=83, waist=66, hip=91 * 1.2, height=200, sleeve_length=52, shoulder_width=37)
    rx, ry = compute_scale_factors(m, "skirt")
    assert rx == pytest.approx(lower_garment_x_scale(m.waist, m.hip))
    assert rx > 1.0  # ヒップが大きいぶん幅は広がる
    assert ry == pytest.approx(1.0)  # スカートの丈は身長では変形しない


def test_lower_garment_width_covers_the_waist_even_for_a_straight_torso():
    """round12で修正した実害の回帰テスト。

    スカート・パンツは幅をヒップ比だけで変形していたため、標準M
    (ウエスト66/ヒップ91、ウエスト比0.725とくびれが強い)より胴が寸胴寄りの
    体型ではウエストが足りず、閉まらない型紙になっていた(ウエスト88・
    ヒップ102の体型で実測13.8cm不足)。ウエストダーツは余りを摘むことしか
    できず、足りない分を足せないため、幅の決め方自体を直した。
    """
    from engine.part_specs import (
        LOWER_BASE_WAIST_CM, LOWER_WAIST_EASE_CM, lower_garment_x_scale,
    )

    for waist, hip in ((66, 91), (70, 92), (76, 96), (84, 105), (88, 102)):
        m = Measurements(bust=83, waist=waist, hip=hip, height=158,
                          sleeve_length=52, shoulder_width=37)
        rx, _ = compute_scale_factors(m, "skirt")
        assert rx == pytest.approx(lower_garment_x_scale(waist, hip))
        # 得られるウエスト周が、必要な寸法(採寸+ゆとり)を満たすこと。
        assert LOWER_BASE_WAIST_CM * rx >= waist + LOWER_WAIST_EASE_CM - 1e-6, (waist, hip)


def test_lower_garment_width_still_follows_the_hip_for_an_hourglass_figure():
    """くびれの強い体型では従来通りヒップ側が効き、余ったウエスト幅は
    ウエストダーツが摘む(round12の変更が、この従来の挙動を壊していないこと)。
    """
    from engine.part_specs import LOWER_BASE_HIP_CM, LOWER_HIP_EASE_CM, lower_garment_x_scale

    m = Measurements(bust=83, waist=58, hip=98, height=158, sleeve_length=52, shoulder_width=37)
    rx, _ = compute_scale_factors(m, "skirt")
    assert rx == pytest.approx((m.hip + LOWER_HIP_EASE_CM) / LOWER_BASE_HIP_CM)
    assert rx == pytest.approx(lower_garment_x_scale(m.waist, m.hip))


def test_sleeve_scales_both_axes():
    m = Measurements(bust=83, waist=66, hip=91, height=158,
                      sleeve_length=52 * 1.1, shoulder_width=37 * 0.9)
    rx, ry = compute_scale_factors(m, "sleeve")
    assert rx == pytest.approx(0.9)
    assert ry == pytest.approx(1.1)


def test_extreme_measurements_are_clamped():
    m = Measurements(bust=83, waist=66, hip=170, height=158, sleeve_length=52, shoulder_width=37)
    rx, _ = compute_scale_factors(m, "skirt")
    assert rx <= 1.6  # part_specs.MAX_SCALE


def test_measurements_rejects_out_of_range_values():
    with pytest.raises(ValueError):
        Measurements(bust=5, waist=66, hip=91, height=158, sleeve_length=52, shoulder_width=37)


def test_measurement_clamp_warnings_empty_for_standard_m():
    assert measurement_clamp_warnings(STANDARD_M) == []


def test_measurement_clamp_warnings_flags_values_beyond_the_effective_scale_range():
    """実際に見つかった不具合の回帰テスト。

    `Measurements`の入力検証(measurements.py)はbust=160cmまで許容しているが、
    テンプレートを実際に変形できる範囲はMIN_SCALE〜MAX_SCALE(標準サイズの
    0.7〜1.6倍 ≒ 58.1〜132.8cm)に限られる。実際に`/api/generate`へ
    bust=160cmとbust=132.8cmを送って比較したところ、生成される前身頃・
    後身頃の型紙が完全に同一になってしまうことを確認した(=bust=160cmと
    入力しても実際には132.8cm相当の型紙しか生成されず、しかもその食い違い
    について何の警告も無かった)。この関数はその食い違いを検出して
    利用者向けの注記を返す。
    """
    m = Measurements(bust=160, waist=66, hip=91, height=158, sleeve_length=52, shoulder_width=37)
    warnings = measurement_clamp_warnings(m)
    assert len(warnings) == 1
    assert "バスト" in warnings[0]
    # round23: 身頃の幅は「バスト + 一定のゆとり」で決まるので、クランプに
    # 当たるバストも 83×1.6=132.8cm から (83+8)×1.6-8=137.6cm へ動いた。
    # 注記は倍率の決め方と同じ式から作らないと、実際には正しく生成できて
    # いる値に対して嘘の数値を出すことになる(round23で実際に起きた)。
    assert f"{bodice_bust_cm_for_scale(MAX_SCALE):.1f}" in warnings[0], warnings[0]


def test_measurement_clamp_warnings_flags_values_below_the_effective_scale_range():
    m = Measurements(bust=50, waist=66, hip=91, height=158, sleeve_length=52, shoulder_width=37)
    warnings = measurement_clamp_warnings(m)
    assert len(warnings) == 1
    assert "バスト" in warnings[0]


def test_measurement_clamp_warnings_can_flag_multiple_fields_at_once():
    m = Measurements(bust=160, waist=150, hip=170, height=158, sleeve_length=52, shoulder_width=37)
    warnings = measurement_clamp_warnings(m)
    assert len(warnings) == 3  # bust, waist, hip の3項目とも範囲外
    assert any("バスト" in w for w in warnings)
    assert any("ウエスト" in w for w in warnings)
    assert any("ヒップ" in w for w in warnings)


def test_scale_template_reports_new_dimensions():
    segments = parse_path("M 0 0 L 10 0 L 10 20 L 0 20 Z")
    m = Measurements(bust=83 * 1.3, waist=66, hip=91, height=158 * 1.2,
                      sleeve_length=52, shoulder_width=37)
    scaled = scale_template("front_bodice", "round_neck", segments, m)
    # round23: 身頃の幅は「バスト + 一定のゆとり(8cm)」で決める。
    # バスト比そのままの1.3倍ではなく (83×1.3 + 8) / (83 + 8) = 1.2736倍。
    expected_x = (83 * 1.3 + BODICE_EASE_CM) / (83 + BODICE_EASE_CM)
    assert scaled.width_cm == pytest.approx(10.0 * expected_x)
    assert scaled.height_cm == pytest.approx(24.0)  # height比1.2倍


# --- round7: scale_band_to_target_width() ----------------------------------

def test_scale_band_to_target_width_matches_the_requested_width_exactly():
    # 原寸70cmの帯を、相手パーツ側の目標幅43cmに合わせる。
    segments = parse_path("M 0 0 L 70 0 L 70 5 L 0 5 Z")
    scaled = scale_band_to_target_width("waistband", "", segments, target_width_cm=43.0)
    assert scaled.width_cm == pytest.approx(43.0)
    assert scaled.scale_x == pytest.approx(43.0 / 70.0)
    assert scaled.scale_y == pytest.approx(1.0)  # 帯の高さ(幅員)は変形しない


def test_scale_band_to_target_width_is_not_clamped_to_the_measurement_scale_range():
    # target/raw比が0.7(part_specs.MIN_SCALE)を下回っていても、
    # 独立した採寸クランプ(measurement_clamp_warnings対象)ではなく
    # 相手パーツの実測値に基づく変形なので、そのまま適用されるべき
    # (round7で見つかった不具合の再発防止テスト。修正前はclamp_scale()を
    # 通していたため、比率が0.7未満のケースで常に0.7に張り付いていた)。
    segments = parse_path("M 0 0 L 70 0 L 70 5 L 0 5 Z")
    target = 70.0 * 0.5  # 比率0.5 < MIN_SCALE(0.7)
    scaled = scale_band_to_target_width("waistband", "", segments, target_width_cm=target)
    assert scaled.width_cm == pytest.approx(target)
    assert scaled.scale_x == pytest.approx(0.5)


def test_scale_band_to_target_width_falls_back_gracefully_for_degenerate_input():
    zero_width_segments = parse_path("M 5 0 L 5 10")  # x方向の幅が0の退化した図形
    scaled = scale_band_to_target_width("waistband", "", zero_width_segments, target_width_cm=43.0)
    assert scaled.width_cm == pytest.approx(0.0)
    assert scaled.scale_x == pytest.approx(1.0)

    segments = parse_path("M 0 0 L 70 0 L 70 5 L 0 5 Z")
    scaled = scale_band_to_target_width("waistband", "", segments, target_width_cm=0.0)
    assert scaled.width_cm == pytest.approx(70.0)  # 変形せずそのまま返す
    assert scaled.scale_x == pytest.approx(1.0)


# --- round11: 帯状パーツ(collar/cuffs/waistband)専用の広いクランプ範囲 -----

def test_clamp_scale_for_part_uses_the_wide_range_for_band_parts():
    for part_type in BAND_PART_TYPES:
        # 身頃用の範囲(0.7〜1.6)の外でも、帯状パーツならそのまま通る。
        assert clamp_scale_for_part(0.62, part_type) == pytest.approx(0.62)
        assert clamp_scale_for_part(2.0, part_type) == pytest.approx(2.0)
        # 広い範囲そのものは超えない。
        assert clamp_scale_for_part(MIN_SCALE_BAND - 0.1, part_type) == pytest.approx(MIN_SCALE_BAND)
        assert clamp_scale_for_part(MAX_SCALE_BAND + 0.1, part_type) == pytest.approx(MAX_SCALE_BAND)


def test_clamp_scale_for_part_keeps_the_narrow_range_for_curved_parts():
    for part_type in ("front_bodice", "back_bodice", "sleeve", "skirt", "front_pants", "back_pants"):
        assert clamp_scale_for_part(0.6, part_type) == pytest.approx(MIN_SCALE)
        assert clamp_scale_for_part(2.0, part_type) == pytest.approx(MAX_SCALE)


@pytest.mark.parametrize("part_type,measure", [
    ("collar", "bust"),
    ("cuffs", "sleeve_length"),
    ("waistband", "waist"),
])
def test_band_parts_are_not_clamped_anywhere_in_the_valid_measurement_range(part_type, measure):
    """round11で修正した実害の回帰テスト。

    Measurementsが受け付ける有効な採寸値の両端でも、帯状パーツの幅倍率が
    クランプされない(=入力した採寸値どおりの型紙になる)ことを確認する。
    修正前は、例えばウエスト150cmでもウエストバンドが1.6倍で頭打ちになり、
    本来の2.273倍に対して約3割短い型紙が生成されていた。
    """
    lo, hi = _VALID_RANGES[measure]
    standard = getattr(STANDARD_M, measure)
    for value in (lo, hi):
        kwargs = {f: getattr(STANDARD_M, f) for f in
                  ("bust", "waist", "hip", "height", "sleeve_length", "shoulder_width")}
        kwargs[measure] = value
        rx, ry = compute_scale_factors(Measurements(**kwargs), part_type)
        assert rx == pytest.approx(value / standard), f"{part_type} {measure}={value}"
        assert ry == pytest.approx(1.0)  # 帯の幅員(Y)は変形しない


def test_waistband_at_the_widest_valid_waist_is_actually_longer_than_before(tmp_path):
    """クランプ緩和が実際の型紙寸法に効いていることを、生成結果の幅で確認する。"""
    from engine.templates_db import TemplateDB

    db = TemplateDB()
    segments = db.get("waistband", "")
    wide = Measurements(bust=83, waist=150, hip=91, height=158, sleeve_length=52, shoulder_width=37)
    scaled = scale_template("waistband", "", segments, wide)
    assert scaled.scale_x == pytest.approx(150.0 / 66.0)
    # 旧クランプ(1.6倍)なら得られなかった幅になっている。
    from engine.svgpath import bounding_box
    raw_w = bounding_box(segments)[2] - bounding_box(segments)[0]
    assert scaled.width_cm > raw_w * MAX_SCALE


def test_band_parts_stay_valid_simple_polygons_at_the_wide_clamp_extremes():
    """クランプを広げても形状が破綻しないことを、実際のテンプレートで確認する
    (根拠は「矩形のX方向スケーリングは自己交差しない」という幾何的事実だが、
    同梱テンプレートで実際に裏付けを取る)。
    """
    shapely = pytest.importorskip("shapely.geometry")
    from engine.templates_db import TemplateDB
    from engine.svgpath import segments_to_polyline

    db = TemplateDB()
    extremes = [
        Measurements(bust=50, waist=40, hip=91, height=158, sleeve_length=30, shoulder_width=37),
        Measurements(bust=160, waist=150, hip=91, height=158, sleeve_length=90, shoulder_width=37),
    ]
    for part_type, variation in (("collar", "shirt_collar"), ("cuffs", ""), ("waistband", "")):
        segments = db.get(part_type, variation)
        for m in extremes:
            scaled = scale_template(part_type, variation, segments, m)
            points = segments_to_polyline(scaled.segments)
            closed = points[:-1] if points[0] == points[-1] else points
            assert shapely.Polygon(closed).is_valid, f"{part_type}/{variation}"
