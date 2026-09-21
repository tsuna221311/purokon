"""round74: 上に羽織るコートが、中に着るワンピースと同じ太さで出てきた。

1着の衣装を「中に着るワンピース」と「上に羽織るコート」に分けて作ると、
round73まではこうなった(素体バスト82cm)。

```
    ニットワンピース (中に着る)   出来上がりバスト 90.0cm
    コート           (上に羽織る) 出来上がりバスト 90.0cm  ← まったく同じ
    コート(ゆったり)              出来上がりバスト 96.0cm  ← +6.0cm
```

**物理的に重ねて着られない。** ゆとりは`FIT_PRESETS`(+4/+8/+14cm)しか無く、
どれも**素体**に足す量で、中に何を着るかはどこにも入らなかった。しかも
画面には何も出ない——2着とも「標準のゆとりで作りました」としか言わない。

そのうえ、この衣装の外側は**前開き**である。前開きにすると、袖が袖ぐりに
追従しなくなっていた(`_armhole_per_arm_cm`のコメントに実測)。ゆとりを
足せば足すほど、袖だけ取り残される。

このファイルが見張るのは:

  1. 上に羽織る服が、中の服と同じ(か細い)太さで出てくる
  2. 重ねられない組み合わせを、黙って出す
  3. 前開きにすると袖が袖ぐりから外れる
  4. 重ね着のゆとりが、身頃だけでスカートに届かない
"""

import tempfile

import pytest

from engine import compatibility as C
from engine.layering import (
    LAYER_MIN_EASE_CM, LAYER_OVER_SLEEVED_CM, finished_bust_cm, layering_notes,
    plan_layer, too_tight_to_layer,
)
from engine.measurements import Measurements
from engine.part_specs import FIT_PRESETS, fit_ease
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline

BODY = Measurements(bust=82, waist=62, hip=88, height=158,
                    sleeve_length=54, shoulder_width=37)

#: 中に着るニットのワンピース。
INNER = GarmentSpec(parts=[
    PartRequest("front_bodice", "round_neck", 1),
    PartRequest("back_bodice", "round_neck", 1),
    PartRequest("sleeve", "straight", 2),
    PartRequest("skirt", "tight", 2)])

#: 上に羽織る前開きのコート。
OUTER = GarmentSpec(parts=[
    PartRequest("front_bodice_zip_panel", "round_neck", 2),
    PartRequest("back_bodice", "round_neck", 1),
    PartRequest("sleeve", "straight", 2),
    PartRequest("skirt", "flare", 2)])


def _build(spec, **kwargs):
    return PatternForgePipeline(
        output_dir=tempfile.mkdtemp()).generate_from_selection(spec, BODY, **kwargs)


def _by_type(result):
    out: dict[str, list] = {}
    for part in result.finalized_parts:
        out.setdefault(part.part_type, []).append(part)
    return out


# --- 1. 重ね着のゆとりを、中の服の出来上がり寸法から決める -------------------

def test_the_default_outer_garment_is_no_bigger_than_the_inner_one():
    """round73までの状態を、数字で固定しておく。

    ここが「直した」の出発点である。中も外も素体+8cmなので、出来上がりは
    まったく同じになる。
    """
    inner = finished_bust_cm(BODY.bust, fit_ease("standard").bodice_cm)
    outer = finished_bust_cm(BODY.bust, fit_ease("standard").bodice_cm)
    assert inner == outer == 90.0
    assert too_tight_to_layer(outer, inner), "重ねられないことに気づけていません"


def test_layering_adds_ten_centimetres_over_a_sleeved_garment():
    """袖のある服の上に羽織るなら、その出来上がり寸法に10cm足すこと。

    出典: Sewingplums「Ease levels」
      "For layering a lined jacket over a sleeved shirt/blouse,
       many people prefer at least 4 in / 10 cm"
    """
    plan = plan_layer(82.0, 90.0, inner_has_sleeves=True)
    assert plan.layer_cm == LAYER_OVER_SLEEVED_CM
    assert plan.outer_bust_cm == pytest.approx(100.0)
    assert plan.bodice_ease_cm == pytest.approx(18.0)


def test_layering_over_a_sleeveless_garment_adds_only_one_inch():
    """袖の無い服の上なら、最低限の1インチ。

    出典: 同上 "A jacket needs to be at least 1 inch larger than
    what it's layered over"
    """
    plan = plan_layer(82.0, 86.0, inner_has_sleeves=False)
    assert plan.layer_cm == pytest.approx(LAYER_MIN_EASE_CM)
    assert plan.outer_bust_cm == pytest.approx(88.54)


def test_the_plan_reaches_the_actual_pattern():
    """計算しただけで終わらせず、**型紙が本当にその幅になる**こと。

    `_prepare_settings`が計算したゆとりは、round73まで変形へ渡って
    いなかった(変形は引数の`fit`をそのまま使っていた)。注記には
    「バスト100cmで引いています」と出るのに型紙は90cmのまま、という
    食い違いが実際に出た。
    """
    inner = finished_bust_cm(BODY.bust, fit_ease("standard").bodice_cm)
    plain = _by_type(_build(OUTER))["back_bodice"][0]
    layered = _by_type(_build(OUTER, worn_over_bust_cm=inner))["back_bodice"][0]

    def width(part):
        xs = [x for x, _ in part.stitch_line]
        return max(xs) - min(xs)

    assert width(layered) - width(plain) == pytest.approx(5.0, abs=0.6), (
        width(plain), width(layered))


def test_the_layering_is_disclosed():
    """何cmで引いたのか、なぜその数字なのかを画面に出すこと。"""
    notes = "\n".join(_build(OUTER, worn_over_bust_cm=90.0).summary()["design_notes"])
    assert "中に着る服" in notes
    assert "100.0cm" in notes, notes
    assert "Sewingplums" in notes, "出典を書くこと"
    assert "布の厚み" in notes, "見込んでいない分を言うこと"


def test_the_skirt_grows_too():
    """身頃だけ太らせて、スカートを置き去りにしないこと。

    上着の裾が、中のスカートの上に乗らなければ意味が無い。
    """
    plain = _by_type(_build(OUTER))["skirt"][0]
    layered = _by_type(_build(OUTER, worn_over_bust_cm=90.0))["skirt"][0]

    def width(part):
        xs = [x for x, _ in part.stitch_line]
        return max(xs) - min(xs)

    assert width(layered) > width(plain) + 5.0, (width(plain), width(layered))


# --- 2. 重ねられない組み合わせを言う -----------------------------------------

@pytest.mark.parametrize("outer,inner,expect", [
    (88.5, 90.0, "細い"),
    (91.0, 90.0, "しかありません"),
    (100.0, 90.0, ""),
], ids=["外が細い", "差が足りない", "足りている"])
def test_it_says_when_two_garments_cannot_be_layered(outer, inner, expect):
    message = too_tight_to_layer(outer, inner)
    if expect:
        assert expect in message, message
    else:
        assert message == ""


def test_the_note_is_empty_without_a_plan():
    assert layering_notes(None) == []


# --- 3. 前開きでも袖が袖ぐりに付く -------------------------------------------

def _cap_and_armhole(spec, **kwargs):
    parts = _by_type(_build(spec, **kwargs))
    cap = C.sleeve_cap_length(parts["sleeve"][0])
    back = C.armhole_length(parts["back_bodice"][0])
    return cap, back


@pytest.mark.parametrize("kwargs,label", [
    ({}, "標準"),
    ({"worn_over_bust_cm": 90.0}, "重ね着"),
], ids=["標準", "重ね着"])
def test_a_front_opening_sleeve_follows_the_armhole(kwargs, label):
    """前開きの身頃でも、袖が袖ぐりと一緒に大きくなること。

    round73までは`front_bodice_zip_panel`から袖ぐりを測れず、袖は
    肩幅比の独立スケーリングへ落ちていた。実測で袖山線は標準でも
    重ね着でも**42.60cmのまま**動かず、袖ぐりが43.70cmまで広がった
    重ね着では3.9cm足りなかった。
    """
    zip_cap, zip_back = _cap_and_armhole(OUTER, **kwargs)
    plain_spec = GarmentSpec(parts=[
        PartRequest("front_bodice", "round_neck", 1),
        PartRequest("back_bodice", "round_neck", 1),
        PartRequest("sleeve", "straight", 2)])
    plain_cap, plain_back = _cap_and_armhole(plain_spec, **kwargs)

    assert zip_back == pytest.approx(plain_back, abs=0.01), "後ろ身頃は同じはず"
    # 割る前と割った後で袖山長が1%以内に収まっていること。
    assert zip_cap == pytest.approx(plain_cap, rel=0.02), (zip_cap, plain_cap)


def test_a_front_opening_sleeve_grows_with_the_layering_ease():
    """ゆとりを足したら、前開きの袖も一緒に大きくなること。"""
    plain_cap, _ = _cap_and_armhole(OUTER)
    layered_cap, _ = _cap_and_armhole(OUTER, worn_over_bust_cm=90.0)
    assert layered_cap > plain_cap + 2.0, (plain_cap, layered_cap)


def test_the_two_garments_can_actually_be_layered():
    """最後に、2着を作って重ねられることを確かめる。"""
    inner_ease = fit_ease("standard").bodice_cm
    inner = finished_bust_cm(BODY.bust, inner_ease)
    result = _build(OUTER, worn_over_bust_cm=inner)
    outer = finished_bust_cm(BODY.bust,
                             inner_ease + LAYER_OVER_SLEEVED_CM)
    assert too_tight_to_layer(outer, inner) == ""
    assert not result.summary()["compatibility_warnings"], \
        result.summary()["compatibility_warnings"]


# --- 4. 重ね着を使わない呼び出しは、1mmも変わらない --------------------------

def test_not_asking_for_layering_changes_nothing():
    """`worn_over_bust_cm`を渡さなければ、round73と同じ型紙が出ること。"""
    before = _by_type(_build(INNER))
    after = _by_type(_build(INNER, worn_over_bust_cm=None))
    for kind, parts in before.items():
        for i, part in enumerate(parts):
            assert part.stitch_line == after[kind][i].stitch_line, kind


def test_the_preset_note_is_not_printed_twice():
    """重ね着の注記と「ゆとり◯◯で作成しました」を二重に出さないこと。"""
    notes = _build(OUTER, worn_over_bust_cm=90.0).summary()["design_notes"]
    assert not [n for n in notes if n.startswith("ゆとり「")], notes
    assert FIT_PRESETS["standard"].label not in "\n".join(notes)


def test_the_sleeveless_flag_shows_up_in_the_restored_settings():
    """「中は袖なし」も、再生成の説明文に出ること。

    足す量が10cmと2.54cmで4倍違う。落ちると、袖なしの上に着る前提で
    引いたコートが、次に再生成したとき7cm太くなる。
    """
    from app import _describe_restored_settings

    with_sleeves = _describe_restored_settings(
        {"worn_over_bust_cm": 90.0, "worn_over_has_sleeves": True})
    without = _describe_restored_settings(
        {"worn_over_bust_cm": 90.0, "worn_over_has_sleeves": False})
    assert "羽織る" in with_sleeves
    assert "袖なし" in without, without
    assert "袖なし" not in with_sleeves
