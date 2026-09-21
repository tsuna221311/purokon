"""round29: 製図の資料に当たって、当てずっぽうの数字を式へ置き換える。

round28の「正直な限界」に、こう書いていた:

> - **BPの高さはバストラインで代用している。**
> - **BP間隔は式による推定。** `B/12 + 2.5`は成人女子の目安であり…
> - **ダーツの移動(回転)による統合はしていない。**
> - **摘める量の上限はround27のまま。**

新文化式原型の製図式に当たった結果、置き換えられたものと、置き換えられ
なかったもの(=正直な限界として残るもの)がはっきりした。

【資料から取った式】
    身幅          B/2 + 6
    背幅          B/8 + 7.4
    胸幅          B/8 + 6.2
    前襟ぐり幅     B/24 + 3.4      … 既にこの式を使っていた(round14)
    前襟ぐり深さ   前襟ぐり幅 + 0.5
    袖ぐり深さ     B/12 + 13.7     … 既にB/12の増分を使っていた(round23)
    BP           胸幅を二等分し、0.7cm脇側へ
    胸ぐせダーツ角 (B/4 − 2.5) 度
    総ダーツ量     (B/2+6) − (W/2+3)
    ダーツ配分     a14% b15% c11% d35% e18% f7%
                  (a・bは前身頃、cは脇線、d・e・fは後ろ身頃)

【実測: 置き換えて何が変わったか】

BPの位置(中心前から):

    バスト   round28(B/12+2.5)   新文化式(胸幅/2+0.7)   差
      83          9.42                8.99           +0.43
     110         11.67               10.68           +0.99
     125         12.92               11.61           +1.31

胸ぐせダーツの摘み量(脇線・左右合計):

    バスト   round28   round29   round29の本数
      60      0.00      2.58      1本
      83      0.00      4.91      1本   ← 標準体型に1本も入っていなかった
     110      2.70      8.56      2本
     120      3.00     10.58      2本

出来上がりのウエスト周(目標 = ウエスト + ゆとり2cm):

    B/W/H          round28   round29   目標
    83/66/91        68.68     68.06    68.0
    83/58/98        71.62     60.16    60.0
    83/50/100       72.46     54.87    52.0
    110/85/112      94.00     87.00    87.0
    120/110/130    112.00    112.24   112.0
    60/45/70        47.00     47.04    47.0
"""

from math import hypot, radians, sin

import pytest

from engine.bodice_fit import (
    BUST_POINT_OFFSET_FROM_CHEST_HALF_CM, FRONT_NECK_DEPTH_EXTRA_CM,
    apply_waist_nip, bust_point_from_cf_cm, bust_point_y_cm, chest_width_cm,
    front_neck_depth_cm, neck_half_cm,
)
from engine.compatibility import (
    NEAR_VERTICAL_MAX_DX_RATIO, _closed_points, _is_dart_notch_at,
    armhole_length, side_seam_edges, side_seam_length,
)
from engine.darts import (
    MAX_DIAMOND_DART_COUNT_PER_HALF, MAX_SIDE_BUST_DART_COUNT,
    MAX_SIDE_BUST_DART_INTAKE_CM, SIDE_SEAM_MAX_DX_RATIO,
    WAIST_DART_SHARE_BACK, WAIST_DART_SHARE_FRONT, WAIST_DART_SHARE_SIDE_SEAM,
    bust_dart_angle_deg, split_bust_dart_cm, total_bust_dart_intake_cm,
    waist_dart_share,
)
from engine.measurements import Measurements
from engine.part_specs import fit_ease
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import segments_to_polyline

BODICE_SPEC = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                                  PartRequest("back_bodice", "round_neck", 1)])

BODIES = [
    ("標準M", 83, 66, 91),
    ("くびれ強め", 83, 58, 98),
    ("洋なし型", 83, 50, 100),
    ("バスト大", 110, 85, 112),
    ("大きめ", 120, 110, 130),
    ("小柄", 60, 45, 70),
]


def _generate(tmp_path, bust, waist, hip, **extra):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    return pipeline.generate_from_selection(
        BODICE_SPEC, Measurements(bust, waist, hip, 158, 52, 37, **extra))


def _width_at(segments, y) -> float:
    points = _closed_points(segments_to_polyline(segments, curve_steps=400))
    xs = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if (y1 - y) * (y2 - y) <= 0 and abs(y2 - y1) > 1e-9:
            xs.append(x1 + (y - y1) / (y2 - y1) * (x2 - x1))
    return (max(xs) - min(xs)) if xs else 0.0


def _finished_waist_cm(result) -> float:
    """縫い上げたときのウエスト周。輪郭の幅から、ダーツで摘む分を引く。"""
    total = 0.0
    for scaled in result.scaled_parts:
        total += _width_at(scaled.segments, scaled.waist_y_cm)
    for part in result.finalized_parts:
        for line in part.internal_lines:
            xs = [p[0] for p in line]
            total -= (max(xs) - min(xs))
    return total


def _bust_dart_mouths(segments) -> list[float]:
    """左の脇線に開いた胸ぐせダーツの口の幅(cm)。

    round71: 縦の差(Δy)ではなく、**口の2点の距離**で測るようにした。
    摘み量とは「口を閉じたときに消える布の幅」——つまり2点間の距離で
    あって、縦の差ではない。round70までは口が脇線(ほぼ縦の線)の上に
    並んでいたので両者がほぼ一致し、Δyで足りていた。脚を揃える
    (`engine/darts.py`の`_equalise_legs`)と口が脇線から外れるので、
    Δyは摘み量より小さく出る(実測: 5.56cmの口が4.37cmと測れた)。
    """
    from math import hypot

    points = _closed_points(segments_to_polyline(segments, curve_steps=300))
    xs = [p[0] for p in points]
    center = (min(xs) + max(xs)) / 2.0
    return [hypot(points[i + 2][0] - points[i][0],
                  points[i + 2][1] - points[i][1])
            for i in range(len(points) - 2)
            if _is_dart_notch_at(points, i, 0.5) and points[i][0] < center]


# --- 資料から取った式そのもの -----------------------------------------------

def test_the_chest_width_formula_matches_the_block():
    """胸幅が B/8 + 6.2 であること。"""
    for bust in (60.0, 83.0, 110.0, 140.0):
        assert chest_width_cm(bust) == pytest.approx(bust / 8.0 + 6.2)


def test_the_bust_point_sits_at_half_the_chest_width_plus_0_7():
    """BPが「胸幅の二等分点から0.7cm脇側」であること。"""
    assert BUST_POINT_OFFSET_FROM_CHEST_HALF_CM == pytest.approx(0.7)
    for bust in (60.0, 83.0, 110.0, 140.0):
        assert bust_point_from_cf_cm(bust) == pytest.approx(
            chest_width_cm(bust) / 2.0 + 0.7)


def test_the_new_bust_point_is_closer_to_the_centre_than_round28():
    """round28の概算(B/12+2.5)より中心寄りで、差はバストが大きいほど開くこと。

    BP間隔はバストほど速くは広がらない——傾きが 1/12 ではなく 1/16 で
    あることの帰結を、実測として固定する。
    """
    previous = {83: 9.42, 110: 11.67, 125: 12.92}
    for bust, old in previous.items():
        new = bust_point_from_cf_cm(float(bust))
        assert new < old
    gaps = [previous[b] - bust_point_from_cf_cm(float(b)) for b in (83, 110, 125)]
    assert gaps == sorted(gaps)          # バストが大きいほど差が開く
    assert gaps[0] == pytest.approx(0.43, abs=0.02)
    assert gaps[-1] == pytest.approx(1.31, abs=0.02)


def test_the_front_neck_depth_formula_matches_the_block():
    """前の襟ぐりの深さが「前襟ぐり幅 + 0.5」であること。"""
    assert FRONT_NECK_DEPTH_EXTRA_CM == pytest.approx(0.5)
    for bust in (60.0, 83.0, 140.0):
        assert front_neck_depth_cm(bust) == pytest.approx(neck_half_cm(bust) + 0.5)


def test_the_bust_dart_angle_formula_matches_the_block():
    """胸ぐせダーツの角が (B/4 − 2.5) 度であること。"""
    for bust in (60.0, 83.0, 110.0, 140.0):
        assert bust_dart_angle_deg(bust) == pytest.approx(bust / 4.0 - 2.5)
    # 角が負になる入力(バスト10cm等)でも0で止まる。
    assert bust_dart_angle_deg(8.0) == 0.0


def test_the_intake_is_the_chord_of_that_angle():
    """摘み量が 2 L sin(角/2) であること(Lは口からBPまでの距離)。"""
    for bust, length in ((83.0, 15.0), (110.0, 20.0)):
        expected = 2 * length * sin(radians(bust_dart_angle_deg(bust)) / 2)
        assert total_bust_dart_intake_cm(bust, length) == pytest.approx(expected)
    # 距離が0以下なら摘み量も0(0除算やマイナスの摘み量を作らない)。
    assert total_bust_dart_intake_cm(83.0, 0.0) == 0.0
    assert total_bust_dart_intake_cm(83.0, -5.0) == 0.0


def test_the_intake_grows_with_both_the_bust_and_the_distance():
    """同じ角なら遠いほど、同じ距離ならバストが大きいほど摘み量が増えること。"""
    assert (total_bust_dart_intake_cm(83.0, 20.0)
            > total_bust_dart_intake_cm(83.0, 15.0))
    assert (total_bust_dart_intake_cm(110.0, 15.0)
            > total_bust_dart_intake_cm(83.0, 15.0))


def test_the_waist_dart_shares_come_from_the_distribution_table():
    """ウエストダーツの前後配分が、配分表 a〜f から導かれていること。"""
    assert WAIST_DART_SHARE_FRONT == pytest.approx(0.14 + 0.15)
    assert WAIST_DART_SHARE_SIDE_SEAM == pytest.approx(0.11)
    assert WAIST_DART_SHARE_BACK == pytest.approx(0.35 + 0.18 + 0.07)
    total = (WAIST_DART_SHARE_FRONT + WAIST_DART_SHARE_SIDE_SEAM
             + WAIST_DART_SHARE_BACK)
    assert total == pytest.approx(1.0)
    # 脇線ぶんを別に絞るので、ダーツ側は前後だけで正規化する。
    assert waist_dart_share("front_bodice") + waist_dart_share("back_bodice") \
        == pytest.approx(1.0)


# --- 胸ぐせダーツが実際に入ること -------------------------------------------

@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_every_body_gets_a_bust_dart(tmp_path, name, bust, waist, hip):
    """どの体型でも胸ぐせダーツが入ること。

    round28まで摘み量は「標準Mからのバスト超過分×0.10」だったので、
    バスト83cm以下には1本も入らなかった。胸の丸みは標準サイズを超えた人
    だけのものではない。
    """
    result = _generate(tmp_path, bust, waist, hip)
    front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    mouths = _bust_dart_mouths(front.segments)
    assert mouths, name
    assert 1 <= len(mouths) <= MAX_SIDE_BUST_DART_COUNT, (name, mouths)
    assert all(m <= MAX_SIDE_BUST_DART_INTAKE_CM + 0.01 for m in mouths), (name, mouths)


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_bust_dart_matches_the_angle_formula(tmp_path, name, bust, waist, hip):
    """脇線に開いた口の合計が、角度式から求まる摘み量と一致すること。

    「ダーツが入っている」だけでなく、**その大きさが式どおりか**まで見る。
    """
    result = _generate(tmp_path, bust, waist, hip)
    front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    mouths = _bust_dart_mouths(front.segments)

    xs = [s[1][0] for s in front.segments if s[0] in ("M", "L")]
    cf = (min(xs) + max(xs)) / 2.0
    half_width = max(xs) - cf
    bp_from_cf = bust_point_from_cf_cm(bust)
    # 口の中心からBPまでの距離。ダーツを置く側と同じ測り方。
    from engine.darts import BUST_DART_MOUTH_DROP_CM
    length = hypot(half_width - bp_from_cf, BUST_DART_MOUTH_DROP_CM)
    expected = total_bust_dart_intake_cm(bust, length)
    unfitted = front.bust_dart_unfitted_cm
    # 半幅は裾を開かせた分だけ広く測れるので、1cmの幅を持たせる。
    assert sum(mouths) + unfitted == pytest.approx(expected, abs=1.0), (name, mouths)


def test_a_large_bust_dart_is_split_in_two():
    """1本の上限を超える摘み量は、均等な2本に分かれること。"""
    one, unfitted = split_bust_dart_cm(MAX_SIDE_BUST_DART_INTAKE_CM - 0.5)
    assert len(one) == 1 and unfitted == 0.0

    two, unfitted = split_bust_dart_cm(MAX_SIDE_BUST_DART_INTAKE_CM + 2.0)
    assert len(two) == 2
    assert two[0] == pytest.approx(two[1])       # 片方だけ深い2本にはしない
    assert sum(two) == pytest.approx(MAX_SIDE_BUST_DART_INTAKE_CM + 2.0)
    assert unfitted == 0.0

    capacity = MAX_SIDE_BUST_DART_INTAKE_CM * MAX_SIDE_BUST_DART_COUNT
    over, unfitted = split_bust_dart_cm(capacity + 3.0)
    assert len(over) == MAX_SIDE_BUST_DART_COUNT
    assert sum(over) == pytest.approx(capacity)
    assert unfitted == pytest.approx(3.0)        # 諦めた分は捨てずに返す

    assert split_bust_dart_cm(0.0) == ([], 0.0)


def test_an_unfittable_bust_dart_is_disclosed(tmp_path):
    """脇線に収まりきらなかった胸ぐせダーツを、黙って捨てないこと。"""
    over = _generate(tmp_path, 140, 105, 154)
    notes = [n for n in over.measurement_warnings if "胸ぐせダーツ" in n]
    assert notes, over.measurement_warnings
    assert "プリンセスライン" in notes[0]

    ok = _generate(tmp_path, 83, 66, 91)
    assert not [n for n in ok.measurement_warnings if "胸ぐせダーツ" in n]


# --- 任意の採寸(乳間・乳下がり) ---------------------------------------------

def test_a_measured_spacing_moves_the_dart_sideways(tmp_path):
    """乳間を入力すると、ダーツの先端が左右に動くこと。"""
    def tip_from_cf(**extra):
        result = _generate(tmp_path, 90, 70, 95, **extra)
        front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
        points = _closed_points(segments_to_polyline(front.segments, curve_steps=300))
        xs = [p[0] for p in points]
        cf = (min(xs) + max(xs)) / 2.0
        tips = [points[i + 1] for i in range(len(points) - 2)
                if _is_dart_notch_at(points, i, 0.5)]
        return cf - min(t[0] for t in tips)

    wide = tip_from_cf(bust_point_spacing=22.0)
    default = tip_from_cf()
    narrow = tip_from_cf(bust_point_spacing=15.0)
    assert wide > default > narrow


def test_a_measured_drop_moves_the_dart_up_and_down(tmp_path):
    """乳下がりを入力すると、ダーツの先端の高さが変わること。"""
    def tip_y(**extra):
        result = _generate(tmp_path, 90, 70, 95, **extra)
        front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
        points = _closed_points(segments_to_polyline(front.segments, curve_steps=300))
        tips = [points[i + 1] for i in range(len(points) - 2)
                if _is_dart_notch_at(points, i, 0.5)]
        return min(t[1] for t in tips)

    low = tip_y(bust_point_drop=22.0)
    default = tip_y()
    assert low > default + 3.0           # 低い胸ほど、ダーツも下を向く


def test_the_bust_point_never_rises_above_the_bust_line():
    """実測がバストラインより上を指しても、そこで止めること。

    バストラインは袖ぐりの底でもある。その上にダーツの口を開けると
    袖ぐりを壊すので、上へは動かさない(その旨は`bust_point_y_cm`の
    docstringに正直に書いてある)。
    """
    assert bust_point_y_cm(24.0, 7.4, 22.0) == pytest.approx(29.4)
    assert bust_point_y_cm(24.0, 7.4, 14.0) == pytest.approx(24.0)   # 21.4 → 止まる
    # 採寸が無い/首の付け根が分からない場合はバストラインそのもの。
    assert bust_point_y_cm(24.0, 7.4, None) == 24.0
    assert bust_point_y_cm(24.0, None, 22.0) == 24.0
    assert bust_point_y_cm(24.0, 7.4, 0.0) == 24.0


# --- ウエストの絞り ---------------------------------------------------------

@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_finished_waist_is_close_to_the_measurement(tmp_path, name, bust, waist, hip):
    """出来上がりのウエスト周が「ウエスト + ゆとり」に近いこと。

    round28の実測では 83/58/98 で+11.6cm、83/50/100 で+20.5cm余っていた。
    """
    result = _generate(tmp_path, bust, waist, hip)
    target = waist + fit_ease(None).waist_cm
    slack = _finished_waist_cm(result) - target
    assert -1.0 <= slack <= 3.0, (name, slack)


def test_the_back_takes_more_of_the_waist_than_the_front(tmp_path):
    """後ろ身頃の方が前身頃より多く絞ること(配分表 29% 対 60%)。"""
    result = _generate(tmp_path, 83, 58, 98)
    taken = {}
    for part in result.finalized_parts:
        taken[part.part_type] = sum(
            max(p[0] for p in line) - min(p[0] for p in line)
            for line in part.internal_lines)
    assert taken["back_bodice"] > taken["front_bodice"]
    ratio = taken["back_bodice"] / taken["front_bodice"]
    assert ratio == pytest.approx(WAIST_DART_SHARE_BACK / WAIST_DART_SHARE_FRONT,
                                  rel=0.15)


def test_the_side_seam_is_nipped_at_the_waist(tmp_path):
    """脇線がウエストの高さでいちばん細くなること(配分表の c=11%)。

    round28まで脇線は袖の下から裾までまっすぐで、ウエストで絞られて
    いなかった。
    """
    result = _generate(tmp_path, 83, 58, 98)
    back = next(p for p in result.scaled_parts if p.part_type == "back_bodice")
    points = _closed_points(segments_to_polyline(back.segments, curve_steps=400))
    underarm_y = back.bust_line_y_cm + 0.5
    hem_y = max(p[1] for p in points) - 0.5
    waist_y = back.waist_y_cm

    at_underarm = _width_at(back.segments, underarm_y)
    at_hem = _width_at(back.segments, hem_y)
    at_waist = _width_at(back.segments, waist_y)
    # 絞っていなければ、脇線は袖の下から裾まで一直線になる。その直線上の
    # 幅より細ければ、ウエストでくびれている。
    t = (waist_y - underarm_y) / (hem_y - underarm_y)
    straight = at_underarm + (at_hem - at_underarm) * t
    assert at_waist < straight - 1.0, (at_waist, straight)


def test_nipping_needs_a_point_at_the_waist():
    """絞る前に、ウエストの高さで直線を割っていること。

    割らずに点だけ動かしても、両端しか動かないので直線は直線のまま。
    実測では絞り量1.22cmを計算しておきながら半幅が1mmも動かなかった。
    """
    # 中心x=10、脇線 x=0 と x=20、袖の下 y=10、ウエスト y=30、裾 y=50。
    segments = [("M", [0.0, 10.0]), ("L", [0.0, 50.0]),
                ("L", [20.0, 50.0]), ("L", [20.0, 10.0]),
                ("L", [0.0, 10.0]), ("Z", [])]
    nipped = apply_waist_nip(segments, 10.0, 10.0, 30.0, 50.0, 2.0)
    ys = [n[1] for _cmd, n in nipped if len(n) >= 2]
    assert 30.0 in ys, nipped        # ウエストの高さに点が足されている
    at_waist = [n[0] for _cmd, n in nipped if len(n) >= 2 and n[1] == 30.0]
    assert min(at_waist) == pytest.approx(2.0)     # 0 → +2
    assert max(at_waist) == pytest.approx(18.0)    # 20 → −2
    # 袖の下と裾は動かさない(バスト周・ヒップ周を崩さない)。
    assert [n[0] for _cmd, n in nipped if len(n) >= 2 and n[1] == 10.0] == [0.0, 20.0, 0.0]
    assert [n[0] for _cmd, n in nipped if len(n) >= 2 and n[1] == 50.0] == [0.0, 20.0]


def test_nipping_does_nothing_without_a_sensible_order():
    """高さの順序が壊れている/絞り量が0以下なら、何もしないこと。"""
    segments = [("M", [0.0, 10.0]), ("L", [0.0, 50.0]), ("Z", [])]
    assert apply_waist_nip(segments, 10.0, 10.0, 30.0, 50.0, 0.0) is segments
    assert apply_waist_nip(segments, 10.0, 30.0, 10.0, 50.0, 2.0) is segments
    assert apply_waist_nip(segments, 10.0, 10.0, 60.0, 50.0, 2.0) is segments


# --- 検出の穴(round29で塞いだもの) ------------------------------------------

def test_the_side_seam_detector_tolerates_the_slant():
    """脇線の判定が、ダーツ側と縫い合わせチェック側で同じ傾きを許すこと。

    round28まで`engine/darts.py`だけが「厳密な垂直」を要求していたため、
    裾をヒップに合わせて開かせた体型では脇線が見つからず、**胸ぐせダーツが
    黙って消えていた**。2か所の上限が一致していることを固定する。
    """
    assert SIDE_SEAM_MAX_DX_RATIO == NEAR_VERTICAL_MAX_DX_RATIO


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_bust_dart_survives_hip_widening(tmp_path, name, bust, waist, hip):
    """裾をヒップに合わせて開かせても、胸ぐせダーツが消えないこと。"""
    result = _generate(tmp_path, bust, waist, hip)
    front = next(p for p in result.scaled_parts if p.part_type == "front_bodice")
    assert _bust_dart_mouths(front.segments), name


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_seams_still_match_after_all_of_this(tmp_path, name, bust, waist, hip):
    """ダーツも絞りも入れた上で、前後の脇線が縫い合わせられること。"""
    result = _generate(tmp_path, bust, waist, hip)
    parts = {p.part_type: p for p in result.finalized_parts}
    front = side_seam_length(parts["front_bodice"])
    back = side_seam_length(parts["back_bodice"])
    assert front is not None and back is not None, name
    assert front == pytest.approx(back, abs=1.5), (name, front, back)
    assert [w.kind for w in result.compatibility_warnings()] == [], name


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_armhole_is_never_swallowed_by_the_side_seam(tmp_path, name, bust, waist, hip):
    """袖ぐりが脇線に飲み込まれていないこと。

    脇線はウエストで折れ、ダーツで断片化する。それらを1本にまとめる規則を
    緩めすぎると、ほぼ垂直になった袖ぐりのカーブまで巻き込む(実測:
    バスト60・肩幅37で袖ぐりが33.9cm→3.45cmになった)。
    """
    result = _generate(tmp_path, bust, waist, hip)
    parts = {p.part_type: p for p in result.finalized_parts}
    for part_type in ("front_bodice", "back_bodice"):
        length = armhole_length(parts[part_type])
        assert length is not None, (name, part_type)
        assert length > 20.0, (name, part_type, length)


def test_the_side_seam_runs_from_the_underarm_to_the_hem(tmp_path):
    """脇線として数えた辺が、脇の下から裾までを覆っていること。

    「長さが前後で一致した」だけでは、両方が同じだけ取りこぼしていても
    通ってしまう。実際に覆っている範囲を見る。
    """
    result = _generate(tmp_path, 110, 85, 112)
    for part in result.finalized_parts:
        if "bodice" not in part.part_type:
            continue
        points = _closed_points(part.stitch_line)
        edges = side_seam_edges(points)
        assert edges, part.part_type
        covered_top = min(min(a[1], b[1]) for _i, _s, a, b in edges)
        covered_bottom = max(max(a[1], b[1]) for _i, _s, a, b in edges)
        hem_y = max(p[1] for p in points)
        assert covered_bottom == pytest.approx(hem_y, abs=0.01), part.part_type
        # 上端は袖ぐりの底(=いちばん外側のxを持つ最上部)の近く。
        assert covered_top < hem_y * 0.5, (part.part_type, covered_top, hem_y)


def test_a_bust_dart_notch_is_recognised_even_on_a_slanted_seam():
    """傾いた脇線に開いた大きなダーツも、V字ノッチと認識されること。

    口の2点は脇線の傾き(最大0.25)ぶんだけxがずれる。口の幅が6cmなら
    1.5cmずれるので、固定の許容0.5cmでは認識できなかった。
    """
    # 傾き0.2の脇線に、口の幅6cmのダーツ。
    on_slanted = [(0.0, 10.0), (12.0, 12.0), (1.2, 16.0), (2.0, 30.0)]
    assert _is_dart_notch_at(on_slanted, 0, 0.5)
    # 先端が口とほとんど変わらない位置なら、ノッチではない(傾きのゆらぎ)。
    not_a_notch = [(0.0, 10.0), (1.0, 12.0), (1.2, 16.0), (2.0, 30.0)]
    assert not _is_dart_notch_at(not_a_notch, 0, 0.5)
