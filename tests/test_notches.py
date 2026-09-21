"""round16: 合印を「実際に縫い合わせる辺の上」に、相手と対応する位置で打つ。

round15までの合印は、パーツ自身の周長比(0.0と0.5など)で打たれていた。
相手パーツとの関係が無いので、縫い合わせる2枚の合印が別々の場所に来る。
実測では後ろ身頃の2つ目が裾の上、ウエストバンドの2つ目が縫い付けない側の
下端、という状態だった。ここではその回帰を防ぐ。
"""

import math

import pytest

from engine.compatibility import neckline_length, seam_edge_length, seam_edge_path
from engine.measurements import Measurements, STANDARD_M
from engine.notches import (
    ARMHOLE_NOTCH_RATIO,
    SIDE_SEAM_NOTCH_RATIO,
    armhole_notch_distance_cm,
    armhole_notch_points,
    side_seam_notch_points,
    sleeve_cap_notch_points,
)
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.svgpath import segments_to_polyline
from engine.templates_db import TemplateDB

DB = TemplateDB()
TOL = 0.15

BODIES = [
    ("標準M", STANDARD_M),
    ("細身", Measurements(76, 60, 86, 152, 49, 35)),
    ("バスト大", Measurements(100, 80, 104, 160, 53, 38)),
    ("バスト特大", Measurements(112, 95, 115, 163, 54, 39)),
]


def _generate(tmp_path, measurements, **kwargs):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(**kwargs)
    return pipeline.generate_from_selection(spec, measurements)


def _by_type(result, part_type):
    return [p for p in result.finalized_parts if p.part_type == part_type]


def _on_vertical_side_seam(part, point) -> bool:
    """点が脇線の上にあるか。

    round26で脇線は厳密な垂直ではなくなった(裾をヒップに合わせて開かせる
    ため)。そのため「x座標がパーツの左端/右端と一致するか」ではなく、
    **その高さでの**外側と一致するかで見る(engine側の
    `_is_side_seam_edge`と同じ考え方)。
    """
    from engine.compatibility import _closed_points, _is_side_seam_edge, _x_range_at_y

    pts = _closed_points(part.stitch_line)
    tops = [min(a[1], b[1]) for a, b in zip(pts, pts[1:])
            if _is_side_seam_edge(pts, a, b) is not None]
    if not tops:
        return False
    # 袖ぐりの合印も輪郭の外周に乗っているので、高さで区別する
    # (脇線は脇の下から下、袖ぐりはそれより上)。
    if point[1] < min(tops) - TOL:
        return False
    span = _x_range_at_y(pts, point[1])
    if span is None:
        return False
    return min(abs(point[0] - span[0]), abs(point[0] - span[1])) <= 0.6


def _sewn_distance_from_underarm(part, point) -> float:
    """脇線上の点について、脇の下から縫い線に沿った距離を返す。

    ダーツで脇線が分かれている場合、ダーツの口(縫うと消える区間)は
    距離に数えない。前身頃と後ろ身頃でこの値が一致していれば、
    縫い合わせたときに合印が突き合う。
    """
    from math import hypot

    from engine.compatibility import _closed_points, side_seam_edges

    pts = _closed_points(part.stitch_line)
    # 点がどちら側の脇線に乗っているかを決め、その側の辺だけを上から辿る。
    # round28: 辺の集め方はエンジンと同じ`side_seam_edges`を使う。ここだけ
    # 独自に集めていると、ダーツの口の上に残る短い断片(4.6cm)を取りこぼし、
    # 「脇の下からの距離」の起点が前身頃だけ下にずれる(実測で4.55cmずれた)。
    target_side = None
    edges = {"left": [], "right": []}
    for _i, side, a, b in side_seam_edges(pts):
        lo, hi = (a, b) if a[1] <= b[1] else (b, a)
        edges[side].append((lo, hi))
        if lo[1] - TOL <= point[1] <= hi[1] + TOL and abs(point[0] - (lo[0] + hi[0]) / 2) < 3.0:
            target_side = side
    if target_side is None:
        return float("nan")
    acc = 0.0
    for lo, hi in sorted(edges[target_side], key=lambda e: e[0][1]):
        length = hypot(hi[0] - lo[0], hi[1] - lo[1])
        if lo[1] - TOL <= point[1] <= hi[1] + TOL:
            return acc + hypot(point[0] - lo[0], point[1] - lo[1])
        acc += length
    return float("nan")


# --- 脇線 -------------------------------------------------------------------

@pytest.mark.parametrize("name,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_side_seam_notches_are_on_the_side_seam_and_match_front_to_back(tmp_path, name, measurements):
    """前身頃と後ろ身頃の脇線の合印が、脇の下から同じ距離にあること。

    round15までは、前身頃の2つ目が右脇線の裾から1.2cm上、後ろ身頃の2つ目は
    **裾の上**(脇線ですらない)だった。
    """
    result = _generate(tmp_path, measurements, neckline="round_neck",
                        sleeve_style=None, skirt_style=None)
    front = _by_type(result, "front_bodice")[0]
    back = _by_type(result, "back_bodice")[0]

    front_side = [a for a, _b in front.notches if _on_vertical_side_seam(front, a)]
    back_side = [a for a, _b in back.notches if _on_vertical_side_seam(back, a)]
    assert len(front_side) == 2, name  # 左右の脇線に1つずつ
    assert len(back_side) == 2, name

    front_d = sorted(_sewn_distance_from_underarm(front, p) for p in front_side)
    back_d = sorted(_sewn_distance_from_underarm(back, p) for p in back_side)
    for fd, bd in zip(front_d, back_d):
        assert fd == pytest.approx(bd, abs=0.05), (name, fd, bd)


def test_side_seam_notch_sits_at_the_configured_ratio():
    """合印が、脇線(縫い閉じた後の長さ)の指定した比率の位置にあること。"""
    segments = DB.get("back_bodice", "round_neck")
    points = segments_to_polyline(segments, curve_steps=64)
    notches = side_seam_notch_points(points)
    assert len(notches) == 2
    xs = [p[0] for p in points]
    for x, y in notches:
        ys = [p[1] for p in points if abs(p[0] - x) <= TOL]
        top, bottom = min(ys), max(ys)
        assert (y - top) / (bottom - top) == pytest.approx(SIDE_SEAM_NOTCH_RATIO, abs=0.01)
    assert {round(p[0], 3) for p in notches} == {round(min(xs), 3), round(max(xs), 3)}



def _bust_dart_mouth_total_cm(part) -> float:
    """前身頃の片側の脇線に開いた、胸ぐせダーツの口の幅の合計(cm)。

    輪郭の上で「ほぼ同じxにある2点の間に、大きく内側へ離れた1点(先端)が
    ある」箇所をV字ノッチとみなす(engine/compatibility.pyの
    `_is_dart_notch_at`と同じ見方)。左側だけを数える。
    """
    from engine.compatibility import _closed_points, _is_dart_notch_at

    points = _closed_points(part.stitch_line)
    xs = [p[0] for p in points]
    center_x = (min(xs) + max(xs)) / 2.0
    total = 0.0
    for i in range(len(points) - 2):
        if not _is_dart_notch_at(points, i, 0.5):
            continue
        if points[i][0] < center_x:
            total += abs(points[i + 2][1] - points[i][1])
    return total


def _bust_dart_seam_shrink_cm(part) -> float:
    """前身頃の片側の脇線が、ダーツを縫い閉じたときに**縮む量**(cm)。

    round71まで、この量は「口の縦幅」で足りていた——口が脇線の上に
    並んでいたからである。脚を揃える(`engine/darts.py`の`_equalise_legs`)と
    口が脇線から外れるようになったので、定義どおりに測る:

        縮む量 ＝ ダーツが無いときの脇線 −(実際に縫う区間の合計)

    `engine/darts.py`の`_mouth_span`が使っているのと同じ式である。
    """
    from math import hypot

    from engine.compatibility import (_closed_points, _is_dart_notch_at,
                                       underarm_y_of)

    points = _closed_points(part.stitch_line)
    xs = [p[0] for p in points]
    center_x = (min(xs) + max(xs)) / 2.0
    underarm = underarm_y_of(part)
    start = next(i for i, q in enumerate(points)
                 if abs(q[1] - underarm) < 1e-6 and q[0] < center_x)

    mouths = []
    i = start
    while i < len(points) - 3:
        if _is_dart_notch_at(points, i, 0.5) and points[i][0] < center_x:
            mouths.append((points[i], points[i + 2]))
            i += 3
            continue
        if mouths and not _is_dart_notch_at(points, i, 0.5):
            # ダーツを抜けたら、その次の輪郭上の点までを縫う区間とする。
            if i > start and points[i][1] > mouths[-1][1][1] + 1e-9:
                end = points[i]
                break
        i += 1
    else:
        return 0.0
    if not mouths:
        return 0.0

    begin = points[start]
    sewn = 0.0
    cursor = begin
    for mouth_a, mouth_b in mouths:
        sewn += hypot(mouth_a[0] - cursor[0], mouth_a[1] - cursor[1])
        cursor = mouth_b
    sewn += hypot(end[0] - cursor[0], end[1] - cursor[1])
    return hypot(end[0] - begin[0], end[1] - begin[1]) - sewn


def test_bust_dart_shifts_the_front_notch_by_exactly_the_dart_intake(tmp_path):
    """脇ダーツが入ると、前身頃の合印のy座標だけがダーツの摘み量ぶん下がること。

    ダーツを縫い閉じるとその布は畳まれて消えるので、この「ずれ」があって
    初めて後ろ身頃と突き合う。ずれが摘み量と一致することを確認する
    (単純に上端からの比率で打つと、この分だけ合印が合わなくなる)。
    """
    measurements = Measurements(100, 80, 104, 160, 53, 38)
    result = _generate(tmp_path, measurements, neckline="round_neck",
                        sleeve_style=None, skirt_style=None)
    front = _by_type(result, "front_bodice")[0]
    back = _by_type(result, "back_bodice")[0]
    front_y = [a[1] for a, _b in front.notches if _on_vertical_side_seam(front, a)]
    back_y = [a[1] for a, _b in back.notches if _on_vertical_side_seam(back, a)]
    # round29: 摘み量は新文化式の角度式で決まり、本数も体型で変わる。
    # 期待値を式から再計算すると、式を変えたときに両方を同じ間違いへ
    # 揃えてしまうので、**出来上がった型紙から実測**して比べる。
    #
    # round71: 測るものを「口の縦幅」から「縫い閉じたときに縮む量」へ
    # 変えた。脚を揃える(`engine/darts.py`の`_equalise_legs`)と口が脇線から
    # 外れるので、口の縦幅はもう縮む量ではない。前身頃を下げるのは
    # **縮む量ぶん**なので、そちらが正しい比較対象である。
    shrink = _bust_dart_seam_shrink_cm(front)
    assert shrink > 0
    mouth = _bust_dart_mouth_total_cm(front)
    assert shrink < mouth, "たたみ出しをしていれば、縮む量は口の縦幅より小さい"
    assert min(front_y) - min(back_y) == pytest.approx(shrink, abs=0.05)


# --- 袖ぐり ⇔ 袖山 ----------------------------------------------------------

@pytest.mark.parametrize("name,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_sleeve_cap_notches_match_the_armhole_notches(tmp_path, name, measurements):
    """袖山の合印が、身頃の袖ぐりの合印と同じ「脇の下からの弧長」にあること。

    round15までは、身頃の袖ぐりには合印が無く、袖には袖山カーブ上の
    無関係な位置に1つあるだけだった。
    """
    result = _generate(tmp_path, measurements, neckline="round_neck",
                        sleeve_style="straight", skirt_style=None)
    front = _by_type(result, "front_bodice")[0]
    sleeve = _by_type(result, "sleeve")[0]

    distance = armhole_notch_distance_cm(front.stitch_line)
    assert distance > 0, name

    # 袖山の端(脇の下に来る点)から各合印までの弧長を測る。
    cap = _cap_path(sleeve.stitch_line)
    measured = sorted(_arc_distance_from_either_end(cap, a) for a, _b in sleeve.notches)
    assert len(measured) == 3, name  # 前1本 + 後ろ2本
    # 前側の1本と、後ろ側の外側の1本が、身頃と同じ距離にある。
    # 残る1本は後ろを示す2本目で、BACK_DOUBLE_NOTCH_GAP_CMだけ内側。
    from engine.notches import BACK_DOUBLE_NOTCH_GAP_CM
    assert measured[-1] == pytest.approx(distance, abs=0.1), (name, measured)
    assert measured[-2] == pytest.approx(distance, abs=0.1), (name, measured)
    assert measured[0] == pytest.approx(distance - BACK_DOUBLE_NOTCH_GAP_CM, abs=0.1), (
        name, measured)


def _cap_path(stitch_line):
    y0 = stitch_line[0][1]
    cap = [stitch_line[0]]
    for point in stitch_line[1:]:
        cap.append(point)
        if abs(point[1] - y0) <= 1e-2:
            break
    return cap


def _arc_distance_from_either_end(path, point) -> float:
    """点列に沿った、両端のうち近い方から`point`までの弧長。

    最寄りの**頂点**ではなく、最寄りの辺へ下ろした足までの距離で測る。
    袖山はポリライン近似なので頂点間隔が1cm以上あり、頂点に丸めると
    0.8cm差の2本の合印が同じ値に潰れてしまう。
    """
    cumulative = [0.0]
    for a, b in zip(path, path[1:]):
        cumulative.append(cumulative[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    best = None
    for i, (a, b) in enumerate(zip(path, path[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        denom = dx * dx + dy * dy
        t = 0.0 if denom <= 0 else max(0.0, min(
            1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denom))
        proj = (a[0] + dx * t, a[1] + dy * t)
        d = math.hypot(proj[0] - point[0], proj[1] - point[1])
        along = cumulative[i] + math.hypot(proj[0] - a[0], proj[1] - a[1])
        if best is None or d < best[0]:
            best = (d, along)
    total = cumulative[-1]
    return min(best[1], total - best[1])


def test_back_bodice_gets_double_notches_to_prevent_a_reversed_sleeve(tmp_path):
    """後ろ身頃の袖ぐりは合印2本、前身頃は1本であること(前後の取り違え防止)。

    洋裁の定石をそのまま実装している。袖側も同じく片側1本・反対側2本。
    """
    result = _generate(tmp_path, STANDARD_M, neckline="round_neck",
                        sleeve_style="straight", skirt_style=None)
    front = _by_type(result, "front_bodice")[0]
    back = _by_type(result, "back_bodice")[0]
    front_arm = [a for a, _b in front.notches if not _on_vertical_side_seam(front, a)]
    back_arm = [a for a, _b in back.notches if not _on_vertical_side_seam(back, a)]
    assert len(front_arm) == 2   # 左右の袖ぐりに1本ずつ
    assert len(back_arm) == 4    # 左右の袖ぐりに2本ずつ
    sleeve = _by_type(result, "sleeve")[0]
    assert len(sleeve.notches) == 3


def test_sleeve_ease_falls_between_the_notches(tmp_path):
    """いせ込み(袖山が袖ぐりより長い分)が、合印より肩寄りに集まること。

    両端から同じ距離に合印を打つので、差はすべて合印どうしの間に入る。
    実際の縫製でもいせ込みは肩寄りに配分し脇の下には入れないので、
    この置き方はその配分を型紙上に表現していることになる。
    """
    from engine.compatibility import SLEEVE_CAP_EASE_CM, armhole_length, sleeve_cap_length

    result = _generate(tmp_path, STANDARD_M, neckline="round_neck",
                        sleeve_style="straight", skirt_style=None)
    front = _by_type(result, "front_bodice")[0]
    back = _by_type(result, "back_bodice")[0]
    sleeve = _by_type(result, "sleeve")[0]
    armhole = (armhole_length(front) + armhole_length(back)) / 2.0
    cap = sleeve_cap_length(sleeve)
    assert cap - armhole == pytest.approx(SLEEVE_CAP_EASE_CM, abs=0.1)

    # 合印より下(脇の下側)の区間は、身頃と袖で同じ長さ=いせ込みが無い。
    distance = armhole_notch_distance_cm(front.stitch_line)
    cap_path = _cap_path(sleeve.stitch_line)
    inner = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                for a, b in zip(cap_path, cap_path[1:])) - 2 * distance
    armhole_inner = armhole - 2 * distance
    assert inner - armhole_inner == pytest.approx(SLEEVE_CAP_EASE_CM, abs=0.1)


def test_armhole_notch_points_are_symmetric_about_the_center():
    """左右の袖ぐりの合印が中心について対称であること。"""
    points = segments_to_polyline(DB.get("front_bodice", "round_neck"), curve_steps=64)
    notches = armhole_notch_points(points, is_back=False)
    assert len(notches) == 2
    xs = [p[0] for p in points]
    center = (min(xs) + max(xs)) / 2.0
    assert notches[0][0] + notches[1][0] == pytest.approx(2 * center, abs=0.01)
    assert notches[0][1] == pytest.approx(notches[1][1], abs=0.01)
    assert 0.0 < ARMHOLE_NOTCH_RATIO < 1.0


# --- 帯状パーツ -------------------------------------------------------------

@pytest.mark.parametrize("name,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_band_notches_sit_on_the_edge_that_is_actually_sewn(tmp_path, name, measurements):
    """ウエストバンド・カフス・衿の合印が、縫い付ける辺の上にあること。

    round15までは、これらの2つ目の合印が反対側(縫い付けない自由端)の角に
    落ちていた。合印は縫い代への切り込みなので、自由端に打っても意味が無い
    どころか紛らわしい。
    """
    result = _generate(tmp_path, measurements, neckline="round_neck",
                        sleeve_style="straight", skirt_style="tight",
                        include_waistband=True, include_cuffs=True, include_collar=True)
    for part_type in ("waistband", "cuffs", "collar"):
        for part in _by_type(result, part_type):
            assert part.seam_edge in ("top", "bottom"), part_type
            path = seam_edge_path(part.stitch_line, part.seam_edge)
            assert len(path) >= 2, part_type
            assert part.notches, (name, part_type)
            for point, _outer in part.notches:
                distance = min(_distance_to_segment(point, a, b)
                                for a, b in zip(path, path[1:]))
                assert distance <= 0.05, (name, part_type, point)


def _distance_to_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom <= 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
    return math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t))


def test_waistband_notch_marks_the_skirt_side_seam(tmp_path):
    """ウエストバンドの合印が、前スカートと後ろスカートの継ぎ目に来ること。"""
    from engine.compatibility import waist_opening_length

    result = _generate(tmp_path, STANDARD_M, neckline="round_neck", sleeve_style=None,
                        skirt_style="tight", include_waistband=True)
    band = _by_type(result, "waistband")[0]
    skirts = _by_type(result, "skirt")
    assert len(band.notches) == 1
    path = seam_edge_path(band.stitch_line, band.seam_edge)
    point = band.notches[0][0]
    travelled = 0.0
    for a, b in zip(path, path[1:]):
        if _distance_to_segment(point, a, b) <= 0.05:
            travelled += math.hypot(point[0] - a[0], point[1] - a[1])
            break
        travelled += math.hypot(b[0] - a[0], b[1] - a[1])
    assert travelled == pytest.approx(waist_opening_length(skirts[0]), abs=0.1)


def test_collar_notches_mark_the_shoulder_seams(tmp_path):
    """衿の合印2つが、左右の肩の継ぎ目に来ること。

    衿は後ろ中心→肩→前中心→肩→後ろ中心と回るので、片端からの距離が
    「後ろ首ぐりの半分」と「そこから前首ぐり1枚分」の2点が肩にあたる。
    """
    result = _generate(tmp_path, STANDARD_M, neckline="round_neck", sleeve_style=None,
                        skirt_style=None, include_collar=True)
    collar = _by_type(result, "collar")[0]
    front = _by_type(result, "front_bodice")[0]
    back = _by_type(result, "back_bodice")[0]
    assert len(collar.notches) == 2
    front_neck = neckline_length(front)
    back_neck = neckline_length(back)
    # 2つの合印の間隔が、前身頃の首ぐりの長さと一致する。
    a, b = sorted(p for p, _o in collar.notches)
    assert math.hypot(b[0] - a[0], b[1] - a[1]) == pytest.approx(front_neck, abs=0.15)
    assert seam_edge_length(collar) == pytest.approx(front_neck + back_neck, abs=0.15)


def test_notches_fall_back_to_the_default_positions_without_a_partner(tmp_path):
    """相手パーツが居ない構成でも例外にならず、合印が付くこと。

    身頃だけ、袖だけ、といった構成では相手から位置を決められないので、
    round15までの既定位置へフォールバックする(黙って合印を消さない)。
    """
    from engine.pipeline import GarmentSpec, PartRequest

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(
        GarmentSpec(parts=[PartRequest("sleeve", "straight", 2)]), STANDARD_M)
    for part in result.finalized_parts:
        assert part.notches
