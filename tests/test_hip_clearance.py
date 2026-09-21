"""round26: 身頃の裾がヒップを通らない問題を直す。

身頃の裾は**ヒップの高さ**にある(テンプレートの丈58cmは首の付け根から
ヒップまで)。ところが幅はバストだけで決まり、さらにウエストダーツが裾を
摘んでいたため、裾がヒップより細くなっていた。実測(前+後の裾の開き寸法):

    B/W/H        裾の開き   ヒップ+ゆとり     差
    83/66/91      91.00       95.0        -4.0
    83/58/98      83.97      102.0       -18.0   ← 腰を通らない
    83/50/100     72.94      104.0       -31.1   ← 到底通らない

18cm足りない服はそもそも着られない。**着られない型紙を黙って出していた**
ことになる。ここではその回帰を防ぐ。
"""

from types import SimpleNamespace

import pytest

from engine.bodice_fit import hip_widening_cm
from engine.compatibility import (
    NEAR_VERTICAL_MAX_DX_RATIO, _closed_points, _is_side_seam_edge,
    hem_or_wrist_opening_length, side_seam_length,
)
from engine.darts import compute_dart_plan
from engine.measurements import Measurements, STANDARD_M
from engine.part_specs import fit_ease
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import segments_to_polyline

#: (バスト, ウエスト, ヒップ)。最後の2つはヒップがバストより大きい体型。
BODIES = [
    ("標準M", 83, 66, 91),
    ("くびれ強め", 83, 58, 98),
    ("洋なし型", 83, 50, 100),
    ("バスト大", 110, 85, 112),
    ("大きめ", 120, 110, 130),
    ("小柄", 60, 45, 70),
]


def _bodices(pipeline, bust, waist, hip, fit=None):
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1)])
    return pipeline.generate_from_selection(
        spec, Measurements(bust, waist, hip, 158, 52, 37), fit=fit)


def _hem_opening_cm(result) -> float:
    """前身頃+後身頃の裾の開き寸法(ダーツを縫い閉じた後)。"""
    return sum(hem_or_wrist_opening_length(SimpleNamespace(
        stitch_line=segments_to_polyline(p.segments, curve_steps=300)))
        for p in result.scaled_parts)


# --- 裾がヒップを通ること ---------------------------------------------------

@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_hem_clears_the_hip(tmp_path, name, bust, waist, hip):
    """どの体型でも、裾が「ヒップ+ゆとり」以上あること。

    これが満たされないと、服が腰を通らない=着られない。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = _bodices(pipeline, bust, waist, hip)
    needed = hip + fit_ease(None).hip_cm
    assert _hem_opening_cm(result) >= needed - 0.1, (name, needed)


@pytest.mark.parametrize("fit", ["fitted", "standard", "relaxed"])
def test_the_hem_clears_the_hip_for_every_fit(tmp_path, fit):
    """ゆとりの指定を変えても、そのゆとりに応じた幅を確保すること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for _name, bust, waist, hip in BODIES:
        result = _bodices(pipeline, bust, waist, hip, fit=fit)
        needed = hip + fit_ease(fit).hip_cm
        assert _hem_opening_cm(result) >= needed - 0.1, (fit, bust, waist, hip)


def test_the_standard_size_hem_is_exactly_the_hip_requirement(tmp_path):
    """標準Mで、裾がちょうど「ヒップ91+ゆとり4=95cm」になること。

    round25までは91.00cmで、ヒップに対して4cm足りなかった。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(
        GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                            PartRequest("back_bodice", "round_neck", 1)]), STANDARD_M)
    assert _hem_opening_cm(result) == pytest.approx(95.0, abs=0.1)


# --- 開かせ方の式 -----------------------------------------------------------

def test_the_widening_is_zero_when_the_bust_already_covers_the_hip():
    """バストの方が大きい体型では開かせないこと(従来どおり裾までまっすぐ)。"""
    assert hip_widening_cm(110, 112, 8.0, 4.0) == pytest.approx(0.0)
    assert hip_widening_cm(120, 110, 8.0, 4.0) == pytest.approx(0.0)


def test_the_widening_covers_exactly_the_shortfall():
    """足りない分を、前後2枚×左右2辺の4辺で等分すること。"""
    # (98+4) - (83+8) = 11cm 足りない → 1辺あたり 2.75cm
    assert hip_widening_cm(83, 98, 8.0, 4.0) == pytest.approx(11 / 4)
    assert hip_widening_cm(83, 91, 8.0, 4.0) == pytest.approx(4 / 4)


# --- ダーツの上限 -----------------------------------------------------------

def test_the_dart_is_capped_so_the_hem_still_clears_the_hip():
    """ヒップを通す幅を割り込むまでは摘まないこと。"""
    body = Measurements(83, 58, 98, 158, 52, 37)
    half = (98 + 4) / 4          # 裾の半幅がちょうどヒップ必要量のとき
    plan = compute_dart_plan("front_bodice", half, body, hip_ease_cm=4.0)
    assert plan.is_empty()
    assert plan.limited_by_hip


def test_the_dart_still_works_when_there_is_room():
    """余裕があるときは従来どおり摘むこと(上限が効きすぎていないこと)。"""
    body = Measurements(110, 75, 100, 158, 52, 37)
    half = (110 + 8) / 4          # 裾の半幅29.5cm、ヒップ必要量は26.0cm
    capped = compute_dart_plan("front_bodice", half, body, hip_ease_cm=4.0)
    uncapped = compute_dart_plan("front_bodice", half, body)
    assert not capped.is_empty()
    assert not capped.limited_by_hip
    assert capped == uncapped     # 余裕があるので上限は結果を変えない


def test_without_the_hip_limit_the_old_behaviour_is_kept():
    """hip_ease_cm を渡さなければ上限を適用しないこと。

    ダーツの幾何だけを単体で確かめるテストなど、身頃以外の文脈から
    呼ばれる場合のため。
    """
    body = Measurements(83, 58, 98, 158, 52, 37)
    half = (98 + 4) / 4
    assert not compute_dart_plan("front_bodice", half, body).is_empty()


def test_the_hem_dart_stops_at_the_hip_requirement(tmp_path):
    """裾のダーツが、ヒップを通す幅で止まっていること。

    round26ではこれを「ウエストが絞れない」として利用者へ開示していたが、
    round27でウエストの線にダイヤモンドダーツを置けるようになり、裾の
    ダーツが止まること自体は**正常な状態**になった(ウエストはそちらで
    絞る)。ここでは、止まっているという事実だけを引き続き固定する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    limited = _bodices(pipeline, 83, 58, 98)
    assert any(p.waist_shaping_limited for p in limited.scaled_parts)
    # 裾はヒップが通る幅のまま。
    assert _hem_opening_cm(limited) >= 98 + fit_ease(None).hip_cm - 0.1

    # 余裕がある体型では止まらない。
    roomy = _bodices(pipeline, 120, 110, 130)
    assert not any(p.waist_shaping_limited for p in roomy.scaled_parts)


# --- 脇線が「ほぼ垂直」として扱えていること ---------------------------------

@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_side_seam_is_still_found_and_matches_front_to_back(tmp_path, name, bust, waist, hip):
    """脇線が傾いても、長さを測れて前後で一致すること。

    傾きを許すようにした判定(`_is_side_seam_edge`)が、実際に脇線を
    見つけられていることの確認。見つけられないとNoneになり、
    縫い合わせのチェックが黙ってスキップされる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = _bodices(pipeline, bust, waist, hip)
    parts = {p.part_type: p for p in result.finalized_parts}
    front = side_seam_length(parts["front_bodice"])
    back = side_seam_length(parts["back_bodice"])
    assert front is not None and back is not None, name
    assert front == pytest.approx(back, abs=1.5), (name, front, back)
    assert [w.kind for w in result.compatibility_warnings()] == [], name


@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_side_seam_slant_stays_within_the_allowed_ratio(tmp_path, name, bust, waist, hip):
    """脇線の傾きが、判定で許している範囲に収まっていること。

    実測では最大でも縦34cmに対し横3cm弱(比0.09)。しきい値0.25はそれを
    十分に含み、かつ裾や首ぐりを拾うほど緩くない——という関係を固定する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = _bodices(pipeline, bust, waist, hip)
    for part in result.finalized_parts:
        points = _closed_points(part.stitch_line)
        for a, b in zip(points, points[1:]):
            if _is_side_seam_edge(points, a, b) is None:
                continue
            dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
            assert dx <= NEAR_VERTICAL_MAX_DX_RATIO * dy, (name, a, b)


@pytest.mark.parametrize("variation", ["round_neck", "v_neck", "square_neck",
                                        "boat_neck", "sweetheart", "turtle_neck"])
def test_the_outline_stays_valid_after_widening(tmp_path, variation):
    """開かせた後も、輪郭が自己交差しないこと(全ネックライン×採寸の両端)。"""
    shapely = pytest.importorskip("shapely.geometry")

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("front_bodice", variation, 1),
                               PartRequest("back_bodice", variation, 1)])
    for bust, waist, hip in ((50, 40, 50), (83, 66, 91), (160, 150, 170), (50, 40, 170)):
        for height in (120, 158, 210):
            result = pipeline.generate_from_selection(
                spec, Measurements(bust, waist, hip, height, 52, 37))
            for part in result.scaled_parts:
                polygon = shapely.Polygon(
                    segments_to_polyline(part.segments, curve_steps=120))
                assert polygon.is_valid, (variation, bust, hip, height, part.part_type)
                assert polygon.area > 0
