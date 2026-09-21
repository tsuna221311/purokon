"""round43: 肩の傾きが、製図した角度ではなく体型の副産物になっていた。

【round42まで何が起きていたか】このエンジンは肩先の**x**を「肩幅/2」に置き、
**y**はテンプレートの形を身長比で伸縮した結果に任せていた。製図の順序は逆で、
先に角度(前22°/後ろ18°)を引いてから肩幅を測る。結果、肩傾斜は入力した
身長と肩幅の副産物になり、実測で20.5°〜30.1°まで動いていた:

    体型                     前       後ろ
    標準M(身長158 B83 肩37)  24.48°   21.13°
    背が高い(身長185)        28.06°   24.35°
    背が低い(身長145)        22.67°   19.53°
    いかり肩(肩幅42)         20.54°   17.65°
    なで肩(肩幅32)           30.10°   26.21°

**背を高くしただけで肩の傾きが3.6°変わる**。肩幅を狭く入力した人は、
なで肩でもないのに30°の肩線を渡されていた。

【このテストが見張っていること】
  1. どんな体型でも、肩傾斜が原型の角度**ちょうど**になること。
     「だいたい22°」では意味がない——角度が体型で動かないことこそが直しの
     中身なので、0.05°まで一致を求める。
  2. 肩を動かしたせいで輪郭が壊れていないこと(round43の実装中に、
     当てる場所を1つ間違えて実際に自己交差させた)。
  3. 前後の肩線の長さの差が、いまの値から勝手に広がらないこと
     (後ろ肩ダーツが未実装なので0.3cmの差が残っている。**残っていることを
     数字で押さえておく**)。
"""

import math

import pytest
from shapely.geometry import Polygon
from shapely.validation import explain_validity

from engine.alteration import (measure_shoulder_slope_deg,
                                shoulder_slope_correction_cm)
from engine.blocks import ADULT_FEMALE, CHILD
from engine.measurements import Measurements
from engine.pipeline import (GarmentSpec, PartRequest, PatternForgePipeline,
                              _closed_points_from_segments, build_garment_spec)
from engine.svgpath import segments_to_polyline

#: 角度が体型で動かないことを見るテストなので、0.05°まで一致を求める。
ANGLE_TOL = 0.05


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("slope")))


def _top_y_at(points, x):
    """輪郭のうち、この x でのいちばん上の y(線形補間)。"""
    best = None
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 == x2 or (x1 - x) * (x2 - x) > 0:
            continue
        y = y1 + (x - x1) / (x2 - x1) * (y2 - y1)
        if best is None or y < best:
            best = y
    return best


def _shoulder(scaled):
    """(傾き°, 肩線の長さcm)。基準点の実座標から測る。"""
    points = _closed_points_from_segments(scaled.segments)
    anchors = list(scaled.fit_anchors_scaled)
    neck_x = max(x for role, x in anchors if role == "neck")
    tip_x = max(x for role, x in anchors if role == "shoulder")
    y_neck = _top_y_at(points, neck_x)
    y_tip = _top_y_at(points, tip_x)
    run = tip_x - neck_x
    rise = y_tip - y_neck
    return math.degrees(math.atan2(rise, run)), math.hypot(run, rise)


BODIES = [
    ("標準M", Measurements(83, 66, 91, 158, 52, 37), None),
    ("背が高い", Measurements(83, 66, 91, 185, 52, 37), None),
    ("背が低い", Measurements(83, 66, 91, 145, 52, 37), None),
    ("いかり肩", Measurements(83, 66, 91, 158, 52, 42), None),
    ("なで肩", Measurements(83, 66, 91, 158, 52, 32), None),
    ("バスト大", Measurements(120, 100, 124, 158, 52, 42), None),
    ("バスト小", Measurements(55, 50, 60, 150, 48, 32), None),
    ("子ども120", Measurements(60, 54, 63, 120, 30, 31), "child"),
    ("子ども80", Measurements(50, 48, 50, 80, 24, 24), "child"),
    ("子ども150", Measurements(72, 61, 78, 150, 40, 36), "child"),
]


# --- 角度そのもの ----------------------------------------------------------

def test_the_block_carries_the_shoulder_slope_the_source_states():
    """出典が数字で書いている角度を、そのまま持っていること。

    成人女子(MAISON DE AS「レディース原型作り(新文化式)」):
      「SNPを基点として水平線に対して22°の前肩傾斜をとり」
      「SNPを基点に水平線に対して18°の後ろ肩傾斜をとり」
    子ども(同「子供原型作り(新文化)」):
      「前身頃SNPを基点に水平線に対し、23°の前肩傾斜をとり」
      「SNPを基点に水平線に対して19°の後ろ肩傾斜をとり」
    """
    assert ADULT_FEMALE.shoulder_slope_front_deg == 22.0
    assert ADULT_FEMALE.shoulder_slope_back_deg == 18.0
    assert CHILD.shoulder_slope_front_deg == 23.0
    assert CHILD.shoulder_slope_back_deg == 19.0
    assert ADULT_FEMALE.shoulder_slope_deg("front_bodice") == 22.0
    assert ADULT_FEMALE.shoulder_slope_deg("back_bodice") == 18.0
    assert ADULT_FEMALE.shoulder_slope_deg("front_bodice_zip_panel") == 22.0
    assert CHILD.shoulder_slope_deg("back_bodice_center") == 19.0


@pytest.mark.parametrize("label,measurements,block",
                         BODIES, ids=[b[0] for b in BODIES])
def test_the_shoulder_slope_is_the_drafted_angle_for_every_body(
        pipeline, label, measurements, block):
    """どんな体型でも、肩傾斜が原型の角度ちょうどになること。

    round42までは20.5°〜30.1°まで動いていた(モジュールdocstringに実測)。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, measurements, skip_export=True, block_key=block)
    expected = CHILD if block == "child" else ADULT_FEMALE
    for part_type in ("front_bodice", "back_bodice"):
        scaled = next(s for s in result.scaled_parts if s.part_type == part_type)
        angle, _length = _shoulder(scaled)
        assert angle == pytest.approx(
            expected.shoulder_slope_deg(part_type), abs=ANGLE_TOL), (
            f"{label} {part_type}: {angle:.2f}°")


def test_height_alone_no_longer_changes_the_shoulder_slope(pipeline):
    """身長だけを変えても肩の傾きが動かないこと。

    round42までは身長158→185で前肩傾斜が24.48°→28.06°(+3.6°)動いた。
    丈方向の伸縮が肩先の落ちだけを伸ばし、肩幅で決まる横は伸びないためで、
    **背が高いだけの人がなで肩の型紙を渡されていた**。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    angles = []
    for height in (140, 158, 175, 190):
        result = pipeline.generate_from_selection(
            spec, Measurements(83, 66, 91, height, 52, 37), skip_export=True)
        front = next(s for s in result.scaled_parts
                     if s.part_type == "front_bodice")
        angles.append(_shoulder(front)[0])
    assert max(angles) - min(angles) < ANGLE_TOL, angles


def test_shoulder_width_alone_no_longer_changes_the_slope(pipeline):
    """肩幅だけを変えても肩の傾きが動かないこと。

    round42までは肩幅42→32で前肩傾斜が20.54°→30.10°(9.6°)動いた。
    肩幅は「肩線の長さ」を決める量であって、傾きを決める量ではない。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    angles, lengths = [], []
    for shoulder in (32, 35, 37, 40, 42):
        result = pipeline.generate_from_selection(
            spec, Measurements(83, 66, 91, 158, 52, shoulder), skip_export=True)
        front = next(s for s in result.scaled_parts
                     if s.part_type == "front_bodice")
        angle, length = _shoulder(front)
        angles.append(angle)
        lengths.append(length)
    assert max(angles) - min(angles) < ANGLE_TOL, angles
    # 傾きは動かないが、肩線の長さは肩幅に応じて伸びる(そちらが肩幅の役目)。
    assert all(b > a for a, b in zip(lengths, lengths[1:])), lengths


@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "square_neck",
                                       "boat_neck", "sweetheart", "turtle_neck"])
def test_the_slope_holds_for_every_neckline(pipeline, neckline):
    """襟ぐりの形を変えても角度が変わらないこと。

    首の付け根の位置は襟ぐりのデザインで前後に動く(ボートネックは標準の
    1.75倍開く)。角度を「首の付け根から肩先まで」で引いているので、
    どのデザインでも同じ角度にならなければならない。
    """
    spec = build_garment_spec(neckline=neckline, sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, Measurements(83, 66, 91, 158, 52, 37), skip_export=True)
    for part_type in ("front_bodice", "back_bodice"):
        scaled = next(s for s in result.scaled_parts if s.part_type == part_type)
        angle, _length = _shoulder(scaled)
        assert angle == pytest.approx(
            ADULT_FEMALE.shoulder_slope_deg(part_type), abs=ANGLE_TOL), neckline


# --- 測る道具そのもの ------------------------------------------------------

def test_the_slope_is_measured_at_the_anchor_not_in_a_window(pipeline):
    """肩先の高さを「±1cmの窓のなかの最小」で拾っていないこと。

    round43の実装中に実際に踏んだ間違い。窓のなかの最小/最大で拾うと、
    肩線が傾いているぶん最大0.45cmずれ、角度にして2.2°の誤差になる
    (肩幅の半分は11.6cm)。さらに窓には袖ぐりの点も入るので、最初の実装は
    **袖ぐり上の点を肩先だと思って57°と答えていた**。
    輪郭とその縦線の交点をそのまま取る。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, Measurements(83, 66, 91, 158, 52, 37), skip_export=True)
    front = next(s for s in result.scaled_parts if s.part_type == "front_bodice")
    measured = measure_shoulder_slope_deg(
        front.segments, "front_bodice", list(front.fit_anchors_scaled),
        list(front.fit_anchors_y_scaled), front.bust_line_y_cm)
    assert measured == pytest.approx(_shoulder(front)[0], abs=ANGLE_TOL)


def test_the_correction_is_zero_once_the_angle_is_already_right(pipeline):
    """すでに角度が合っている輪郭に、二度目の補正をかけないこと。

    かかると、生成のたびに肩が下がり続ける。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, Measurements(83, 66, 91, 158, 52, 37), skip_export=True)
    for part_type, target in (("front_bodice", 22.0), ("back_bodice", 18.0)):
        scaled = next(s for s in result.scaled_parts if s.part_type == part_type)
        again = shoulder_slope_correction_cm(
            scaled.segments, part_type, list(scaled.fit_anchors_scaled),
            list(scaled.fit_anchors_y_scaled), target, scaled.bust_line_y_cm)
        assert abs(again) < 0.01, (part_type, again)


def test_a_part_without_anchors_is_left_alone():
    """基準点を持たない形では、当てずっぽうで動かさず0を返すこと。"""
    square = [("M", [0.0, 0.0]), ("L", [10.0, 0.0]), ("L", [10.0, 10.0]),
              ("L", [0.0, 10.0]), ("Z", [])]
    assert measure_shoulder_slope_deg(square, "front_bodice", [], []) is None
    assert shoulder_slope_correction_cm(square, "front_bodice", [], [], 22.0) == 0.0
    # 身頃でないパーツも対象外。
    assert measure_shoulder_slope_deg(square, "sleeve", [("neck", 1.0)],
                                       [("underarm", 5.0)]) is None


# --- 壊していないこと ------------------------------------------------------

@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "square_neck",
                                       "boat_neck", "sweetheart", "turtle_neck"])
def test_the_outline_stays_valid_at_the_extremes(pipeline, neckline):
    """極端な体型でも輪郭が自己交差しないこと。

    【round43で実際に壊した】肩の補正を変形の**途中**(ヒップを開かせる前)で
    当てていたとき、バスト50・ヒップ170・身長210の前身頃が自己交差した——
    補正のために輪郭を高さで分割した結果を、ヒップの開きがそのまま引き継いだ
    ためである。利用者の補正(round40)と同じ場所・同じ1回の写像にまとめて解決した。
    """
    spec = GarmentSpec(parts=[PartRequest("front_bodice", neckline, 1),
                               PartRequest("back_bodice", neckline, 1)])
    for bust, waist, hip in ((50, 40, 50), (83, 66, 91), (160, 150, 170),
                              (50, 40, 170)):
        for height in (120, 158, 210):
            result = pipeline.generate_from_selection(
                spec, Measurements(bust, waist, hip, height, 52, 37),
                skip_export=True)
            for part in result.scaled_parts:
                polygon = Polygon(segments_to_polyline(part.segments,
                                                        curve_steps=120))
                assert polygon.is_valid, (
                    neckline, bust, hip, height, part.part_type,
                    explain_validity(polygon))


def test_the_user_alteration_still_lands_on_top_of_the_drafted_slope(pipeline):
    """利用者の肩の補正が、製図の角度の**上に**そのまま効くこと。

    round43で肩の補正を2つ(製図の角度合わせ+利用者の入力)同じ仕組みに
    まとめた。まとめたせいで利用者の入力が薄まっては意味がない。
    1.0cm下げたら1.0cm下がること。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    body = Measurements(83, 66, 91, 158, 52, 37)

    def tip_y(alterations):
        result = pipeline.generate_from_selection(
            spec, body, skip_export=True, alterations=alterations)
        front = next(s for s in result.scaled_parts
                     if s.part_type == "front_bodice")
        points = _closed_points_from_segments(front.segments)
        tip_x = max(x for role, x in front.fit_anchors_scaled
                    if role == "shoulder")
        return _top_y_at(points, tip_x)

    plain = tip_y(None)
    lowered = tip_y({"shoulder_slope": 1.0})
    raised = tip_y({"shoulder_slope": -1.0})
    assert lowered - plain == pytest.approx(1.0, abs=0.05)
    assert raised - plain == pytest.approx(-1.0, abs=0.05)


def test_the_front_and_back_shoulder_seams_stay_within_the_known_gap(pipeline):
    """前後の肩線の長さの差が、いまの0.35cmから広がらないこと。

    【なぜ差があるか】前22°・後ろ18°で、横の長さ(肩幅/2−ネック幅)は前後で
    同じなので、傾きが急な前の方が長くなる。本来の新文化式は後ろ肩線を
    「前肩線 + 後ろ肩ダーツ(B/32−0.8)」として引き、その差をダーツが摘む。
    **このエンジンは後ろ肩ダーツをまだ引いていない**ので、差がそのまま残る。

    差はround42(24.48°/21.13°)でも0.31cmあり、round43で0.32cmになった——
    **もとからあった差で、今回広げたわけではない**。縫い合わせ長さの許容
    (`_ABS_TOLERANCE_CM`=1.5cm)の中に収まっているので警告は出ないが、
    黙って広がっては困るので、ここで数字を押さえておく。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    for measurements in (Measurements(83, 66, 91, 158, 52, 37),
                          Measurements(120, 100, 124, 158, 52, 42),
                          Measurements(60, 50, 66, 150, 48, 32)):
        result = pipeline.generate_from_selection(spec, measurements,
                                                   skip_export=True)
        front = next(s for s in result.scaled_parts
                     if s.part_type == "front_bodice")
        back = next(s for s in result.scaled_parts
                    if s.part_type == "back_bodice")
        gap = _shoulder(front)[1] - _shoulder(back)[1]
        assert 0.0 < gap < 0.40, (measurements.bust, gap)


def test_no_pattern_gains_a_seam_length_warning_from_the_new_slope(pipeline):
    """肩を引き直したせいで、縫い合わせ長さの警告が増えていないこと。"""
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare", include_collar=True,
                              include_cuffs=True)
    for measurements in (Measurements(83, 66, 91, 158, 52, 37),
                          Measurements(110, 92, 118, 168, 56, 40),
                          Measurements(65, 55, 72, 148, 48, 33)):
        result = pipeline.generate_from_selection(spec, measurements,
                                                   skip_export=True)
        assert result.compatibility_warnings() == [], measurements.bust
