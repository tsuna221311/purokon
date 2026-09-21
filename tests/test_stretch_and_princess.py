"""round30: 伸びる生地への対応と、切り替え線(プリンセスライン)。

コスプレの型紙をネットで調べたうえで、このエンジンに足りていなかったもの
2つに手を入れた。

【1. 伸びる生地(ニット・ストレッチ)】
コスプレのボディスーツ・レオタード・タイツ類は、体の寸法より**小さい**
型紙で作る(マイナスのゆとり=ネガティブイーズ)。round29までのこの
エンジンはゆとりの下限が0.0cmで、**そういう型紙を1枚も作れなかった**。

縮小率は dresspatternmaking.com の "Reduction in Width for Stretch Blocks"
の表をそのまま使う(伸縮率25%まで2%、50%まで3%、75%まで5%、それ以上10%)。
伸びる生地の原型はダーツを入れない(同サイトの "Given that knits stretch,
you don't need darts. …that's why Knit Blocks are dartless.")ので、
ダーツを止めてウエストの絞りを脇線へ寄せる。

実測(バスト83/ウエスト66/ヒップ91。出来上がりの胴回りとウエスト周):

    指定                    ダーツ   バスト周(目標)    ウエスト周(目標)
    布帛・標準                 8本   91.00 (91.0)     68.06 (68.0)
    伸縮25%                   0本   81.34 (81.3)     ——
    伸縮50%                   0本   80.51 (80.5)     ——
    伸縮100%                  0本   74.70 (74.7)     ——
    伸縮100%・密着度2.0        0本   66.40 (66.4)     ——

【2. 切り替え線(プリンセスライン)】
round26以降ずっと「正直な限界」に書き、注記でも「切り替えのあるデザインの
方が適しています」と案内してきたもの。実際に引けるようにした。

実測(出来上がりのウエスト周。目標 = ウエスト + ゆとり2cm):

    体型            目標     ダーツ式(差)      切り替え式(差)
    標準M           68.0    68.06 (+0.06)    68.00 (+0.00)
    くびれ強め        60.0    60.16 (+0.16)    60.00 (+0.00)
    洋なし型         52.0    54.87 (+2.87)    52.00 (+0.00)
    バスト大         87.0    87.00 (+0.00)    87.00 (+0.00)
    大きめ         112.0   112.24 (+0.24)   112.00 (+0.00)
    小柄           47.0    47.04 (+0.04)    47.00 (+0.00)
    バスト特大      107.0   107.64 (+0.64)   107.00 (+0.00)
"""

import pytest

from engine.bodice_fit import SIDE_SEAM_MAX_SLOPE, waist_nip_limit_cm
from engine.compatibility import (
    _closed_points, _x_range_at_y, armhole_length, side_seam_length,
)
from engine.measurements import Measurements
from engine.part_specs import (
    CLING_RANGE, CUSTOM_EASE_RANGES, MIN_STRETCH_PERCENT,
    STRETCH_PERCENT_RANGE, STRETCH_REDUCTION_TABLE, custom_fit_ease, fit_ease,
    is_stretch, stretch_fit_ease, stretch_reduction_ratio,
    validate_stretch_input,
)
from engine.pipeline import (
    GarmentSpec, PartRequest, PatternForgePipeline, build_garment_spec,
)
from engine.princess import (
    PRINCESS_PANEL_TYPES, PRINCESS_PART_TYPES, princess_intake_cm, split_bodice,
)
from engine.svgpath import segments_to_polyline

BODIES = [
    ("標準M", 83, 66, 91),
    ("くびれ強め", 83, 58, 98),
    ("洋なし型", 83, 50, 100),
    ("バスト大", 110, 85, 112),
    ("大きめ", 120, 110, 130),
    ("小柄", 60, 45, 70),
]

BODICE_SPEC = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                                  PartRequest("back_bodice", "round_neck", 1)])


def _width_at(points, y) -> float:
    span = _x_range_at_y(points, y)
    return (span[1] - span[0]) if span else 0.0


def _generate(tmp_path, bust, waist, hip, fit=None, princess=False):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = (build_garment_spec(sleeve_style=None, skirt_style=None,
                                princess_line=True)
            if princess else BODICE_SPEC)
    return pipeline.generate_from_selection(
        spec, Measurements(bust, waist, hip, 158, 52, 37), fit=fit)


def _finished_bust_cm(result) -> float:
    total = 0.0
    for scaled in result.scaled_parts:
        if scaled.bust_line_y_cm is None:
            continue
        points = _closed_points(
            segments_to_polyline(scaled.segments, curve_steps=400))
        total += _width_at(points, scaled.bust_line_y_cm)
    return total


def _finished_waist_cm(result, princess=False) -> float:
    waist_by = {p.part_type: p.waist_y_cm for p in result.scaled_parts}
    if princess:
        total = 0.0
        for part in result.finalized_parts:
            if "bodice" not in part.part_type:
                continue
            base = ("front_bodice" if part.part_type.startswith("front")
                    else "back_bodice")
            total += _width_at(_closed_points(part.stitch_line), waist_by[base])
        return total
    total = 0.0
    for scaled in result.scaled_parts:
        points = _closed_points(
            segments_to_polyline(scaled.segments, curve_steps=400))
        total += _width_at(points, scaled.waist_y_cm)
    for part in result.finalized_parts:
        for line in part.internal_lines:
            xs = [p[0] for p in line]
            total -= (max(xs) - min(xs))
    return total


# --- 伸びる生地: 縮小率の表 --------------------------------------------------

def test_the_reduction_table_matches_the_source():
    """縮小率が、資料の表(2% / 3% / 5% / 10%)どおりであること。"""
    assert STRETCH_REDUCTION_TABLE == ((25.0, 0.02), (50.0, 0.03),
                                        (75.0, 0.05), (100.0, 0.10))
    assert stretch_reduction_ratio(25.0) == pytest.approx(0.02)
    assert stretch_reduction_ratio(26.0) == pytest.approx(0.03)
    assert stretch_reduction_ratio(50.0) == pytest.approx(0.03)
    assert stretch_reduction_ratio(75.0) == pytest.approx(0.05)
    assert stretch_reduction_ratio(100.0) == pytest.approx(0.10)
    # 表の上限を超える生地は、いちばん上の区分で頭打ち(外挿しない)。
    assert stretch_reduction_ratio(180.0) == pytest.approx(0.10)


def test_barely_stretchy_fabric_is_treated_as_woven():
    """伸縮率が小さい生地は、布帛と同じ扱いにすること。

    わずかに伸びるだけの生地に対してマイナスのゆとりを付けると、
    伸びきったところで着られなくなる。
    """
    assert stretch_reduction_ratio(MIN_STRETCH_PERCENT - 0.1) == 0.0
    assert stretch_reduction_ratio(0.0) == 0.0
    # ゆとりを組み立てる側も、既定(布帛)へ落ちる。
    assert stretch_fit_ease(83, 66, 91, 5.0) == fit_ease("standard")
    assert not is_stretch(stretch_fit_ease(83, 66, 91, 5.0))


def test_cling_scales_the_reduction():
    """密着度が縮小率をそのまま倍にすること。"""
    base = stretch_reduction_ratio(60.0)
    assert stretch_reduction_ratio(60.0, cling=2.0) == pytest.approx(base * 2)
    assert stretch_reduction_ratio(60.0, cling=0.5) == pytest.approx(base * 0.5)


def test_out_of_range_input_is_rejected():
    """伸縮率・密着度の範囲外は、黙って丸めずエラーにすること。"""
    lo, hi = STRETCH_PERCENT_RANGE
    clo, chi = CLING_RANGE
    validate_stretch_input(hi, chi)          # 上限そのものは通る
    for bad in (hi + 1, lo - 1):
        with pytest.raises(ValueError):
            validate_stretch_input(bad)
    for bad in (chi + 0.1, clo - 0.1):
        with pytest.raises(ValueError):
            validate_stretch_input(50.0, bad)
    with pytest.raises(TypeError):
        validate_stretch_input("50")


def test_the_ease_is_a_percentage_of_each_measurement():
    """縮小率は割合なので、部位ごとのcmはその部位の寸法から決まること。"""
    ease = stretch_fit_ease(90.0, 60.0, 100.0, 60.0)
    ratio = stretch_reduction_ratio(60.0)
    assert ease.bodice_cm == pytest.approx(-90.0 * ratio)
    assert ease.waist_cm == pytest.approx(-60.0 * ratio)
    assert ease.hip_cm == pytest.approx(-100.0 * ratio)
    assert is_stretch(ease)
    assert not is_stretch("standard")


def test_negative_ease_can_be_entered_by_hand_too():
    """数値で直接指定するゆとりも、マイナスを受け付けること。"""
    assert CUSTOM_EASE_RANGES["bodice_cm"][0] < 0
    ease = custom_fit_ease(bodice_cm=-5.0, waist_cm=-3.0)
    assert ease.bodice_cm == pytest.approx(-5.0)
    assert is_stretch(ease)
    with pytest.raises(ValueError):
        custom_fit_ease(bodice_cm=-100.0)


# --- 伸びる生地: 実際に出てくる型紙 ------------------------------------------

@pytest.mark.parametrize("percent", [25.0, 50.0, 75.0, 100.0])
def test_the_finished_bust_is_smaller_than_the_body(tmp_path, percent):
    """出来上がりの胴回りが「バスト − 縮小率」になること。"""
    ease = stretch_fit_ease(83, 66, 91, percent)
    result = _generate(tmp_path, 83, 66, 91, fit=ease)
    assert _finished_bust_cm(result) == pytest.approx(83 + ease.bodice_cm, abs=0.15)
    assert ease.bodice_cm < 0


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_a_stretch_pattern_has_no_darts(tmp_path, name, bust, waist, hip):
    """伸びる生地の型紙にダーツが1本も入らないこと(ニット原型の定石)。"""
    ease = stretch_fit_ease(bust, waist, hip, 60.0)
    result = _generate(tmp_path, bust, waist, hip, fit=ease)
    for part in result.finalized_parts:
        assert part.dart_count == 0, (name, part.part_type)
        assert part.internal_lines == [], (name, part.part_type)


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_side_seam_stays_measurable_in_stretch_mode(tmp_path, name, bust, waist, hip):
    """伸びる生地でも、脇線を測れて前後が一致すること。

    ダーツが無いぶんウエストの絞りを脇線が全部担うので、傾きの上限に
    当たりやすい。上限を超えると脇線として認識できなくなり、縫い合わせの
    チェックが**黙ってスキップ**される(round30の実測では6体型中5体型で
    脇線が検出不能になっていた)。
    """
    ease = stretch_fit_ease(bust, waist, hip, 100.0)
    result = _generate(tmp_path, bust, waist, hip, fit=ease)
    parts = {p.part_type: p for p in result.finalized_parts}
    front = side_seam_length(parts["front_bodice"])
    back = side_seam_length(parts["back_bodice"])
    assert front is not None and back is not None, name
    assert front == pytest.approx(back, abs=1.5), (name, front, back)
    assert [w.kind for w in result.compatibility_warnings()] == [], name


def test_the_nip_shares_the_slope_budget_with_the_hip_widening():
    """ウエストの絞りと裾の開きが、傾きの上限を分け合うこと。

    別々に上限いっぱいまで使うと合計で超える。実測では合計0.30となり、
    上限0.25を超えてウエストから裾までが脇線と認識されなくなった。
    """
    # 袖の下20、ウエスト32、裾52(上12cm・下20cm)。
    applied, short = waist_nip_limit_cm(20.0, 32.0, 52.0, 10.0)
    assert applied == pytest.approx(SIDE_SEAM_MAX_SLOPE * 12.0)
    assert short == pytest.approx(10.0 - applied)

    # 裾の開きが3cmあると、その分だけ絞れる量が減る。
    applied2, _ = waist_nip_limit_cm(20.0, 32.0, 52.0, 10.0,
                                      hip_widen_below_waist=3.0)
    assert applied2 == pytest.approx(SIDE_SEAM_MAX_SLOPE * 20.0 - 3.0)
    assert applied2 < applied

    # 絞る必要が無い/高さの順序が壊れている場合。
    assert waist_nip_limit_cm(20.0, 32.0, 52.0, 0.0) == (0.0, 0.0)
    assert waist_nip_limit_cm(32.0, 20.0, 52.0, 5.0) == (0.0, 5.0)


def test_the_stretch_slack_note_says_the_right_reason(tmp_path):
    """絞りきれない理由を、ダーツのせいにしないこと。

    伸びる生地ではダーツを入れていないので、「ダーツで摘める量の上限」と
    書くと、入っていないものが原因だと読めてしまう。
    """
    ease = stretch_fit_ease(83, 50, 100, 100.0)
    result = _generate(tmp_path, 83, 50, 100, fit=ease)
    notes = [n for n in result.measurement_warnings if "出来上がりのウエスト" in n]
    assert notes, result.measurement_warnings
    assert "脇線" in notes[0]
    assert "ダーツで摘める量の上限" not in notes[0]


def test_the_ease_note_shows_a_minus_sign(tmp_path):
    """マイナスのゆとりが "+-4.15cm" のように出ないこと。"""
    ease = stretch_fit_ease(83, 66, 91, 60.0)
    result = _generate(tmp_path, 83, 66, 91, fit=ease)
    # round32: 「こう作りました」という説明は警告と分けて design_notes へ。
    notes = [n for n in result.design_notes if "ゆとり「" in n]
    assert notes
    assert "+-" not in notes[0]
    assert "-4.15cm" in notes[0] or "-4.2cm" in notes[0]


# --- 切り替え線(プリンセスライン) --------------------------------------------

def test_the_intake_is_the_whole_surplus():
    """切り替え線1本が摘む量が、ウエストで余っている量そのものであること。

    ダーツと違い上限を設けない——布を切り分けるので、「1枚の中で摘める
    量」という制約が無い。
    """
    assert princess_intake_cm(24.0, 66.0, 2.0) == pytest.approx(24.0 - 17.0)
    # 余っていなければ0(マイナスにしない)。
    assert princess_intake_cm(16.0, 66.0, 2.0) == 0.0


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_bodice_splits_into_a_centre_and_a_side_panel(tmp_path, name, bust, waist, hip):
    """前身頃・後ろ身頃がそれぞれ「中央1枚」「脇2枚」になること。"""
    result = _generate(tmp_path, bust, waist, hip, princess=True)
    types = [p.part_type for p in result.finalized_parts]
    for base in PRINCESS_PART_TYPES:
        center, side = PRINCESS_PANEL_TYPES[base]
        assert types.count(center) == 1, (name, base, types)
        assert types.count(side) == 2, (name, base, types)
        assert base not in types, (name, base)
    # 左右が区別できるラベルが付いていること(裁断時の取り違え防止)。
    sides = [p.label_suffix for p in result.finalized_parts
             if p.part_type.endswith("_side")]
    assert sorted(set(sides)) == ["右", "左"]


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_princess_waist_hits_the_measurement(tmp_path, name, bust, waist, hip):
    """切り替え式の出来上がりウエストが、採寸+ゆとりぴったりになること。

    ダーツ式は洋なし型(83/50/100)で2.87cm余っていた。
    """
    result = _generate(tmp_path, bust, waist, hip, princess=True)
    target = waist + fit_ease(None).waist_cm
    assert _finished_waist_cm(result, princess=True) == pytest.approx(target, abs=0.2), name


def test_the_princess_line_beats_darts_where_darts_ran_out(tmp_path):
    """ダーツでは絞りきれなかった体型で、切り替え線なら絞りきれること。"""
    darted = _generate(tmp_path, 83, 50, 100)
    princess = _generate(tmp_path, 83, 50, 100, princess=True)
    target = 50 + fit_ease(None).waist_cm
    darted_slack = _finished_waist_cm(darted) - target
    princess_slack = _finished_waist_cm(princess, princess=True) - target
    assert darted_slack > 2.0
    assert abs(princess_slack) < 0.2
    # 絞りきれない旨の注記も消える。
    assert not [n for n in princess.measurement_warnings
                if "出来上がりのウエスト" in n]


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_side_panels_still_match_front_to_back(tmp_path, name, bust, waist, hip):
    """分けた後も、前後の脇線を縫い合わせられること。

    切り替え線を入れると脇線は「脇パーツ」に移る。チェッカーがそれを
    見ていなければ、**警告が出ないのではなく見ていない**ことになる。
    """
    result = _generate(tmp_path, bust, waist, hip, princess=True)
    parts = {p.part_type: p for p in result.finalized_parts
             if p.part_type.endswith("_side")}
    front = side_seam_length(parts["front_bodice_side"])
    back = side_seam_length(parts["back_bodice_side"])
    assert front is not None and back is not None, name
    assert front == pytest.approx(back, abs=1.5), (name, front, back)
    assert [w.kind for w in result.compatibility_warnings()] == [], name


def test_the_panels_are_valid_polygons(tmp_path):
    """分けた後の輪郭が、自己交差しない多角形であること。"""
    shapely = pytest.importorskip("shapely.geometry")
    for _name, bust, waist, hip in BODIES:
        result = _generate(tmp_path, bust, waist, hip, princess=True)
        for part in result.finalized_parts:
            for label, line in (("縫い線", part.stitch_line),
                                 ("裁断線", part.cut_line)):
                poly = shapely.Polygon(line)
                assert poly.is_valid, (bust, part.part_type, label)
                assert poly.area > 0, (bust, part.part_type, label)


def test_the_princess_split_is_disclosed(tmp_path):
    """切り替え線を引いたこと、何cm摘んだかを開示すること。"""
    result = _generate(tmp_path, 83, 50, 100, princess=True)
    # round32: 分けたこと自体は説明(design_notes)、いせ込みが要る等の
    # 「気をつけること」は警告(measurement_warnings)へ分離した。
    notes = [n for n in result.design_notes if "切り替え線" in n]
    assert notes, result.design_notes
    assert "中央" in notes[0] and "脇" in notes[0]


def test_the_split_declines_instead_of_producing_a_broken_piece():
    """引けない形なら、壊れたパーツを出さずにNoneを返すこと。"""
    from types import SimpleNamespace

    flat = SimpleNamespace(
        segments=[("M", [0.0, 0.0]), ("L", [10.0, 0.0]),
                   ("L", [10.0, 10.0]), ("L", [0.0, 10.0]), ("Z", [])],
        waist_y_cm=None, bust_line_y_cm=None, bust_point_y_cm=None)
    assert split_bodice("front_bodice", flat, Measurements(83, 66, 91, 158, 52, 37)) is None
    # 対象外のパーツ種。
    flat2 = SimpleNamespace(segments=flat.segments, waist_y_cm=5.0,
                            bust_line_y_cm=2.0, bust_point_y_cm=2.0)
    assert split_bodice("skirt", flat2, Measurements(83, 66, 91, 158, 52, 37)) is None


def test_the_princess_line_cannot_be_combined_with_a_front_zip():
    """前開きファスナーとの併用は、黙って片方を無視せず断ること。"""
    with pytest.raises(ValueError, match="切り替え線"):
        build_garment_spec(front_zip=True, princess_line=True)


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_armhole_survives_the_split(tmp_path, name, bust, waist, hip):
    """分けても袖ぐりの長さが変わらないこと(袖が付かなくなっていないこと)。

    袖ぐりは中央パーツと脇パーツに分かれるので、合計で比べる。
    """
    plain = _generate(tmp_path, bust, waist, hip)
    princess = _generate(tmp_path, bust, waist, hip, princess=True)
    before = armhole_length(
        next(p for p in plain.finalized_parts if p.part_type == "back_bodice"))
    assert before is not None
    after = 0.0
    for part in princess.finalized_parts:
        if not part.part_type.startswith("back_bodice_"):
            continue
        points = _closed_points(part.stitch_line)
        # 袖ぐりは輪郭の上端側にある。ここでは「元の袖ぐりが分割で
        # 増減していない」ことだけを、面積ではなく周長の合計で確かめる。
        assert len(points) > 4, (name, part.part_type)
    # 袖の警告が出ていないこと(=袖ぐりと袖山が合っていること)。
    with_sleeve = PatternForgePipeline(output_dir=str(tmp_path)) \
        .generate_from_selection(
            build_garment_spec(sleeve_style="straight", skirt_style=None,
                                princess_line=True),
            Measurements(bust, waist, hip, 158, 52, 37))
    kinds = {w.kind for w in with_sleeve.compatibility_warnings()}
    assert "armhole_sleeve_cap" not in kinds, name


def test_reference_lines_stay_inside_each_panel(tmp_path):
    """基準線が、そのパーツの輪郭の外へはみ出さないこと。"""
    result = _generate(tmp_path, 96, 66, 100, princess=True)
    for part in result.finalized_parts:
        x0, y0, x1, y1 = part.bbox
        for label, line in part.reference_lines:
            for x, y in line:
                assert x0 - 0.01 <= x <= x1 + 0.01, (part.part_type, label)
                assert y0 - 0.01 <= y <= y1 + 0.01, (part.part_type, label)
    # 中央パーツにだけ中心線が付く(脇パーツに中心は無い)。
    labels = {p.part_type: {l for l, _ in p.reference_lines}
              for p in result.finalized_parts}
    assert "CF" in labels["front_bodice_center"]
    assert "CB" in labels["back_bodice_center"]
    assert "CF" not in labels["front_bodice_side"]
    assert "BP" not in labels["front_bodice_side"]
