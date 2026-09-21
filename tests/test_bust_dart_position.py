"""round28: バストダーツをBP(バストポイント)へ向ける。

【round27までの不具合】脇ダーツ(バストダーツ)の先端の位置は、脇線に
沿った比率(BUST_APEX_HEIGHT_RATIO=0.42、BUST_APEX_OFFSET_RATIO=0.45)で
決めていた。脇線は袖付けから裾までなので、0.42という比率が指す高さは
**ウエストのあたり**になる。つまり胸の丸みを作るためのダーツが、胸では
なくウエストを向いていた。

実測(前身頃・標準体型に対しバストだけを変えた場合。BPは文化式の
「中心前からB/12+2.5cm、バストラインの上」):

    バスト   BPの位置(x,y)   round27の先端      BPまで   round28の先端     BPまで
      95   (15.33,24.50)   ( 7.79,36.76)     14.40cm   (13.01,25.50)    2.53cm
     110   (17.83,25.75)   (12.98,38.52)     13.66cm   (15.46,26.75)    2.57cm
     125   (20.33,27.00)   (15.54,39.46)     13.35cm   (17.94,28.00)    2.60cm

狙いの2.5cm(BUST_APEX_SETBACK_CM。先端をBPまで刺すと布が尖って浮くので
実務では手前で止める)に対し2.53〜2.60cm。残りの数mmは、先端を脇線の
上端より上へ出さないための丸め(MIN_CLEARANCE_CM)による。

【この修正で袖ぐりのチェックが壊れかけた話】ダーツの口が脇線の上端の
すぐ下(脇の下から6cm)へ移った結果、口より上に残る脇線の断片が4.65cmに
なり、「5cm以上の縦の辺」という脇線の判定から漏れた。前身頃の脇線が
55.20cm・後ろ身頃が64.50cmと食い違って見え、縫えないという誤検出が出た。
`engine/compatibility.py`の`side_seam_edges`で、**ダーツの口をまたぐ
ときだけ**短い断片を救済するようにして直した。単純にしきい値を下げたり
隣接する辺をつないだりしなかった理由(袖ぐりを飲み込む)も、下の
test_the_rescue_does_not_swallow_the_armhole で固定している。
"""

from math import hypot

import pytest

from engine.bodice_fit import (
    BUST_POINT_FROM_CF_CONST, BUST_POINT_FROM_CF_DIVISOR, bust_point_from_cf_cm,
    chest_width_cm,
)
from engine.compatibility import (
    _closed_points, _is_dart_notch_at, armhole_length, side_seam_edges,
    side_seam_length,
)
from engine.darts import (
    BUST_APEX_SETBACK_CM, BUST_DART_MOUTH_DROP_CM, WAIST_DART_BELOW_BP_CM,
    apply_bust_dart,
)
from engine.measurements import Measurements
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.templates_db import TemplateDB
import engine.scaling as scaling_module

#: ダーツが実際に入る(=標準サイズよりバストが大きい)体型。
BUSTS = [95.0, 110.0, 125.0]

BODICE_SPEC = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                                  PartRequest("back_bodice", "round_neck", 1)])


def _front(tmp_path, bust, waist=66.0, hip=91.0):
    """前身頃(変形後・ダーツ入り)と、そのときのバストラインのyを返す。"""
    captured = {}
    original = scaling_module.apply_bust_dart

    # round42: 実物の引数が増えた(`block`)。スパイ側を固定の引数で書くと、
    # 本体の署名が変わるたびにTypeErrorで落ちる。**素通しにする**——
    # このスパイの仕事はbust_line_yを覗くことだけで、引数の検査ではない。
    def spy(*args, **kwargs):
        bust_line_y = kwargs.get("bust_line_y")
        if bust_line_y is None and len(args) >= 4:
            bust_line_y = args[3]
        if bust_line_y is not None:
            captured["bust_line_y"] = bust_line_y
        return original(*args, **kwargs)

    scaling_module.apply_bust_dart = spy
    try:
        pipeline = PatternForgePipeline(output_dir=str(tmp_path))
        result = pipeline.generate_from_selection(
            BODICE_SPEC, Measurements(bust, waist, hip, 158, 52, 37))
    finally:
        scaling_module.apply_bust_dart = original
    front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    return front, captured.get("bust_line_y"), result


def _dart_notches(segments):
    """脇線に開いたV字ノッチを [(口の上端, 先端, 口の下端), ...] で返す。

    round29: ダーツは1本とは限らず(胸が大きいと2本に分散する)、脇線も
    厳密な垂直とは限らない(裾をヒップに合わせて開かせる)。判定は
    エンジンと同じ`_is_dart_notch_at`を使う。
    """
    from engine.svgpath import segments_to_polyline

    points = _closed_points(segments_to_polyline(segments, curve_steps=300))
    return [(points[i], points[i + 1], points[i + 2])
            for i in range(len(points) - 2)
            if _is_dart_notch_at(points, i, 0.5)]


def _dart_tips(segments):
    """脇線に開いたV字ノッチの先端を返す。"""
    return [tip for _a, tip, _b in _dart_notches(segments)]


# --- BPの式そのもの ---------------------------------------------------------

def test_bust_point_follows_the_bunka_formula():
    """中心前からBPまでの距離が、新文化式の 胸幅/2 + 0.7 であること。

    round28は「B/12 + 2.5」という概算を使っていた。製図の資料に当たった
    結果、新文化式は胸幅(B/8 + 6.2)を二等分して0.7cm脇へ寄せた点をBPと
    するので、傾きは1/12ではなく1/16になる(round29で置き換え)。
    """
    assert BUST_POINT_FROM_CF_DIVISOR == 16.0
    assert BUST_POINT_FROM_CF_CONST == pytest.approx(3.8)
    for bust in (60.0, 83.0, 110.0, 130.0):
        assert chest_width_cm(bust) == pytest.approx(bust / 8.0 + 6.2)
        assert bust_point_from_cf_cm(bust) == pytest.approx(
            chest_width_cm(bust) / 2.0 + 0.7)


def test_a_measured_bust_point_spacing_wins_over_the_formula():
    """乳間を採寸してもらえた場合は、推定式ではなくその実測を使うこと。"""
    assert bust_point_from_cf_cm(83.0, bust_point_spacing_cm=22.0) == pytest.approx(11.0)
    # 未指定・0・負値は推定式へ戻る(黙って0cmにしない)。
    for bad in (None, 0.0, -1.0):
        assert bust_point_from_cf_cm(83.0, bust_point_spacing_cm=bad) == pytest.approx(
            chest_width_cm(83.0) / 2.0 + 0.7)


def test_bust_point_moves_outward_as_the_bust_grows():
    """バストが大きいほどBPは中心前から遠い(=左右のBP間隔が広がる)こと。"""
    distances = [bust_point_from_cf_cm(b) for b in (60.0, 83.0, 110.0, 130.0)]
    assert distances == sorted(distances)
    assert distances[0] < distances[-1]


# --- ダーツが実際にBPを向いていること ---------------------------------------

@pytest.mark.parametrize("bust", BUSTS)
def test_the_dart_tip_stops_just_short_of_the_bust_point(tmp_path, bust):
    """先端がBPの手前 BUST_APEX_SETBACK_CM で止まっていること。

    round27まではBPから13〜14cm離れた場所(ウエストの高さ)を向いていた。
    """
    front, bust_line_y, _ = _front(tmp_path, bust)
    assert bust_line_y is not None, "バストラインが渡っていない(古い経路に落ちている)"
    xs = [s[1][0] for s in front.segments if s[0] in ("M", "L")]
    cf = (min(xs) + max(xs)) / 2.0
    offset = bust_point_from_cf_cm(bust)

    tips = _dart_tips(front.segments)
    # round29: 胸が大きいと1本では摘みきれず、脇線に2本並ぶ(左右で最大4本)。
    assert len(tips) in (2, 4), (bust, tips)
    for tip in tips:
        sign = -1.0 if tip[0] < cf else 1.0
        bp = (cf + sign * offset, bust_line_y)
        distance = hypot(tip[0] - bp[0], tip[1] - bp[1])
        # 狙いは2.5cm。前後に数mmの幅がある:
        #   + 先端を脇線の上端より上へ出さない丸め
        #   − round29でウエストの絞り(`apply_waist_nip`)を胸ぐせダーツの後に
        #     掛けるようにしたため、先端も内側へわずかに引かれる
        assert BUST_APEX_SETBACK_CM - 0.15 <= distance <= BUST_APEX_SETBACK_CM + 0.3, \
            (bust, tip, bp, distance)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_dart_points_at_the_bust_not_at_the_waist(tmp_path, bust):
    """先端がバストの高さにあり、ウエストの高さではないこと。

    round27の実測(バスト110)では先端がy=38.52——ウエストの高さ——にあった。
    """
    front, bust_line_y, _ = _front(tmp_path, bust)
    waist_y = front.waist_y_cm
    assert waist_y is not None
    for tip in _dart_tips(front.segments):
        assert abs(tip[1] - bust_line_y) <= 2.0, (bust, tip, bust_line_y)
        assert tip[1] < waist_y - 5.0, (bust, tip, waist_y)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_dart_mouth_sits_below_the_underarm(tmp_path, bust):
    """ダーツの口が脇の下すれすれではなく、縫える位置まで下がっていること。"""
    front, bust_line_y, _ = _front(tmp_path, bust)
    notches = _dart_notches(front.segments)
    assert notches, bust
    # いちばん上の口の上端。ここが脇の下(バストライン)より下にあること。
    top = min(min(a[1], b[1]) for a, _tip, b in notches)
    assert top >= bust_line_y - 0.01
    assert top - bust_line_y >= 2.0, (bust, top, bust_line_y)
    # 口の中心はバストラインから BUST_DART_MOUTH_DROP_CM 下。上端はそこから
    # 口の幅の半分だけ上になるので、下がり量より小さい。
    assert top - bust_line_y <= BUST_DART_MOUTH_DROP_CM + 0.01, (bust, top, bust_line_y)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_two_darts_stay_symmetric(tmp_path, bust):
    """左右のダーツが中心前について対称であること。

    本数が1本でも2本でも(round29で分散するようになった)、左側のダーツを
    中心前で鏡映すると右側のダーツにぴったり重なること。
    """
    front, _bust_line_y, _ = _front(tmp_path, bust)
    xs = [s[1][0] for s in front.segments if s[0] in ("M", "L")]
    cf = (min(xs) + max(xs)) / 2.0
    tips = _dart_tips(front.segments)
    assert len(tips) >= 2 and len(tips) % 2 == 0, tips
    left = sorted((t for t in tips if t[0] < cf), key=lambda t: t[1])
    right = sorted((t for t in tips if t[0] > cf), key=lambda t: t[1])
    assert len(left) == len(right) == len(tips) // 2
    for a, b in zip(left, right):
        assert (cf - a[0]) == pytest.approx(b[0] - cf, abs=1e-6)
        assert a[1] == pytest.approx(b[1], abs=1e-6)


def test_without_a_bust_line_the_old_ratio_geometry_is_used():
    """基準線を渡さない呼び出しは、round27までの比率でダーツを作ること。

    ダーツの幾何だけを単体で確かめるテストが、パイプライン抜きでも
    動き続けるためのフォールバック。**静かに古い挙動へ戻る**経路なので、
    パイプラインが実際に基準線を渡していることは
    test_the_dart_tip_stops_just_short_of_the_bust_point 側で固定している。
    """
    segments = TemplateDB().get("front_bodice", "round_neck")
    m = Measurements(110, 66, 91, 158, 52, 37)
    without, count_a = apply_bust_dart("front_bodice", segments, m)
    with_line, count_b = apply_bust_dart("front_bodice", segments, m, bust_line_y=25.75)
    assert count_a == count_b == 2
    assert _dart_tips(without) != _dart_tips(with_line)


# --- 脇線の数え方(ダーツで断片化した脇線の救済) ----------------------------

BODIES = [
    ("標準M", 83, 66, 91),
    ("バスト大", 110, 85, 112),
    ("大きめ", 120, 110, 130),
    ("小柄", 60, 45, 70),
]


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_front_and_back_side_seams_still_match(tmp_path, name, bust, waist, hip):
    """ダーツの口が脇線の上端近くへ移っても、前後の脇線長が一致すること。

    実測(バスト110/85/112)では、救済前は前55.20cm・後64.50cmだった。
    """
    _front_part, _y, result = _front(tmp_path, bust, waist, hip)
    parts = {p.part_type: p for p in result.finalized_parts}
    front = side_seam_length(parts["front_bodice"])
    back = side_seam_length(parts["back_bodice"])
    assert front is not None and back is not None, name
    assert front == pytest.approx(back, abs=1.5), (name, front, back)
    assert [w.kind for w in result.compatibility_warnings()] == [], name


def test_the_short_fragment_above_the_dart_is_counted(tmp_path):
    """ダーツの口の上に残る短い断片が、脇線として数えられていること。

    これが数えられないと上の一致テストが壊れる。「一致した」だけでは
    数え方が正しいことの証明にならないので、断片そのものを見る。
    """
    _front_part, _y, result = _front(tmp_path, 110.0, 85.0, 112.0)
    front = next(p for p in result.finalized_parts if p.part_type == "front_bodice")
    points = _closed_points(front.stitch_line)
    edges = side_seam_edges(points)
    left = [(i, p1, p2) for i, side, p1, p2 in edges if side == "left"]
    assert len(left) >= 2, "ダーツで分かれた2本が両方とも数えられていない"
    short = [abs(p2[1] - p1[1]) for _i, p1, p2 in left if abs(p2[1] - p1[1]) < 5.0]
    assert short, "5cm未満の断片が1本も救済されていない(判定が効いていない)"


def test_the_rescue_does_not_swallow_the_armhole(tmp_path):
    """救済が袖ぐりを脇線として飲み込んでいないこと。

    バストが小さく肩幅が広い体型では、袖ぐりのカーブがほぼ垂直になり、
    「ほぼ垂直で輪郭の外側」という脇線の条件を袖ぐりの辺も満たしてしまう。
    しきい値を下げる/隣接する辺を無条件につなぐ、という直し方をすると
    ここが壊れる(実測: 袖ぐり33.9cm → 3.45cm)。
    """
    _front_part, _y, result = _front(tmp_path, 60.0, 45.0, 70.0)
    parts = {p.part_type: p for p in result.finalized_parts}
    for part_type in ("front_bodice", "back_bodice"):
        length = armhole_length(parts[part_type])
        assert length is not None
        assert length > 25.0, (part_type, length)


def test_a_dart_notch_is_only_recognised_as_a_v_on_the_seam():
    """ダーツの口の判定が、実際のV字にだけ当たること。

    口の2点は脇線上(ほぼ同じx)にあり、先端だけが大きく内側へ離れている。
    裾のウエストダーツのように左右へ広がるV字は当たらない。
    """
    on_seam = [(0.0, 10.0), (12.0, 12.0), (0.0, 14.0), (0.0, 40.0)]
    assert _is_dart_notch_at(on_seam, 0, 0.5)

    straight = [(0.0, 10.0), (0.0, 14.0), (0.0, 40.0)]
    assert not _is_dart_notch_at(straight, 0, 0.5)

    # 裾のダーツ: 口の2点のxが離れている。
    on_hem = [(10.0, 58.0), (12.0, 46.0), (14.0, 58.0), (30.0, 58.0)]
    assert not _is_dart_notch_at(on_hem, 0, 0.5)

    # 末尾に3点そろわない場合は当たらない。
    assert not _is_dart_notch_at(on_seam, 2, 0.5)


# --- ウエストダーツの上の先端をBPの手前で止める ------------------------------

def _diamond_top_y(result, part_type):
    """内部の縫い線(ダイヤモンドダーツ)の上の先端の高さ。"""
    tops = [min(p[1] for p in line)
            for part in result.finalized_parts if part.part_type == part_type
            for line in part.internal_lines]
    return min(tops) if tops else None


@pytest.mark.parametrize("bust", [83.0, 110.0, 120.0])
def test_the_waist_dart_stops_below_the_bust_point(tmp_path, bust):
    """ウエストダーツの上の先端がBPを越えていないこと。

    round27は上下とも一律12cm伸ばしていたので、バストが大きい体型ほど
    先端がBPを越えていた(実測: バスト120でBPがy=26.58、先端がy=26.00)。
    先端がBPを越えると、胸の頂点の真上で布が尖って浮く。
    """
    _front_part, bust_line_y, result = _front(tmp_path, bust, 66.0, 91.0)
    top = _diamond_top_y(result, "front_bodice")
    assert top is not None, bust
    # round29: 紙の上のyで比べるので、胸ぐせダーツの口の幅ぶん下へずらす。
    front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    limit = bust_line_y + WAIST_DART_BELOW_BP_CM + front.bust_dart_shift_cm
    assert top >= limit - 1e-6, (bust, top, limit)


def test_the_back_waist_dart_is_not_limited_by_the_bust_point(tmp_path):
    """後ろ身頃のウエストダーツは、BPで制限されないこと。

    BPは前身頃にしか無い。後ろまで一緒に短くすると、肩甲骨のあたりで
    絞れなくなる。
    """
    _front_part, bust_line_y, result = _front(tmp_path, 120.0, 66.0, 91.0)
    front_top = _diamond_top_y(result, "front_bodice")
    back_top = _diamond_top_y(result, "back_bodice")
    assert front_top is not None and back_top is not None
    front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    # 前身頃は紙の上で胸ぐせダーツのぶん下がっているので、出来上がりの高さで
    # 比べる。後ろ身頃にはそのずれが無い。
    assert front_top - front.bust_dart_shift_cm > back_top, (front_top, back_top)
    assert back_top < bust_line_y + WAIST_DART_BELOW_BP_CM


def test_limiting_the_apex_does_not_change_how_much_the_waist_takes_in(tmp_path):
    """先端を短くしても、ウエストで摘む量は変わらないこと。

    摘み量はウエストの線の上の口の幅で決まる。先端の長さはそこに
    関係しない——という関係を固定する(短くしたついでにウエストが
    絞れなくなっていた、という壊れ方を防ぐ)。
    """
    from engine.darts import waist_diamond_dart_lines

    _front_part, bust_line_y, result = _front(tmp_path, 120.0, 66.0, 91.0)
    scaled = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    unlimited, count_a = waist_diamond_dart_lines(
        scaled.segments, Measurements(120, 66, 91, 158, 52, 37),
        scaled.waist_y_cm, 2.0)
    limited, count_b = waist_diamond_dart_lines(
        scaled.segments, Measurements(120, 66, 91, 158, 52, 37),
        scaled.waist_y_cm, 2.0,
        apex_limit_y=(bust_line_y + WAIST_DART_BELOW_BP_CM
                      + scaled.bust_dart_shift_cm))
    assert count_a == count_b > 0
    for a, b in zip(unlimited, limited):
        # 口(ウエストの線の上の左右2点)は同じ。
        mouth_a = sorted(p for p in a if abs(p[1] - scaled.waist_y_cm) < 1e-6)
        mouth_b = sorted(p for p in b if abs(p[1] - scaled.waist_y_cm) < 1e-6)
        assert mouth_a == mouth_b
    assert min(p[1] for p in limited[0]) > min(p[1] for p in unlimited[0])
