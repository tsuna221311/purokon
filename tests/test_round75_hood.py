"""round75: フードが作れなかった。

【round74までの状態】パーツ種は身頃・袖・スカート・パンツ・衿・カフス・
ウエストバンドの7つ。衿は6種類あるが、どれも「首に巻く帯」である。
**頭を覆うものが1つも無い**。

```
    pattern_templates/collar__*.svg  … standard / shirt / peter_pan /
                                        bow / ruffle / convertible
```

フード付きの上着は、コスプレ衣装では珍しくない。作れないので、そこだけ
別の型紙を探すことになる。

【round75で足したもの】フードを**製図する**(`engine/hood.py`)。
他のパーツはテンプレートを採寸比で伸縮させるが、フードは2つの独立した
寸法に同時に従わなければならない。

  1. 頭が入ること          … 頭囲から決まる
  2. 首ぐりに縫い付くこと  … 身頃の首ぐりの長さから決まる

比率で伸ばすと、どちらか片方しか合わない。

このファイルが見張るのは:

  1. 頭囲を変えてもフードの大きさが変わらない
  2. フードの付け根が首ぐりに合わない
  3. 頭囲を測っていないのに、測ったような顔で引く
  4. 首ぐりに対して頭が小さすぎる絵を、黙って歪める
"""

import tempfile

import pytest

from engine import compatibility as C
from engine.hood import (
    DEFAULT_HEAD_CIRCUMFERENCE_CM, HOOD_DEPTH_REDUCTION_CM, HOOD_FRONT_DROP_CM,
    HOOD_HEIGHT_EASE_CM, hood_length_from_head_cm, hood_notes, hood_segments,
    plan_hood,
)
from engine.measurements import Measurements
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import bounding_box

#: 標準Mの身頃から実測した首ぐりの全長(前22.26 + 後15.04)。
NECKLINE_CM = 37.30


def _body(head=None):
    return Measurements(bust=82, waist=62, hip=88, height=158,
                        sleeve_length=54, shoulder_width=37,
                        head_circumference=head)


HOODED = GarmentSpec(parts=[
    PartRequest("front_bodice", "round_neck", 1),
    PartRequest("back_bodice", "round_neck", 1),
    PartRequest("hood", "", 2)])


def _build(head=None, spec=HOODED):
    return PatternForgePipeline(
        output_dir=tempfile.mkdtemp()).generate_from_selection(spec, _body(head))


def _hoods(result):
    return [p for p in result.finalized_parts if p.part_type == "hood"]


# --- 1. 頭囲から引く ---------------------------------------------------------

def test_the_hood_matches_the_worked_example_in_the_source():
    """資料の作例と同じ寸法になること。

    出典(MAISON DE AS「フードの製図方法」)は、幅のある指定と**作例**を
    両方書いている。作例の数字で突き合わせる——定数を書き写して
    比べると、定数を変えたときに両辺が一緒に動いて何も見張れない。

        横 … 「頭回り寸法から1〜3cm引いた寸法」
              「頭回り寸法28cmの場合、25〜27cm」
        縦 … 「フード寸法に2〜5cm足した寸法」
              「フード寸法39cmの場合、41cm〜44cm」
    """
    # 頭回り28cm = 頭囲56cm。
    plan = plan_hood(NECKLINE_CM, head_circumference_cm=56.0,
                     hood_length_cm=39.0)
    assert 25.0 <= plan.depth_cm <= 27.0, plan.depth_cm
    assert plan.depth_cm == pytest.approx(26.0), "幅のある指定は真ん中を採る"
    assert 41.0 <= plan.height_cm <= 44.0, plan.height_cm
    assert plan.height_cm == pytest.approx(42.5), "幅のある指定は真ん中を採る"


def test_the_hood_follows_the_head_measurement():
    """頭囲を変えたら、フードの大きさが変わること。"""
    previous = None
    for head in (50.0, 57.0, 64.0):
        plan = plan_hood(NECKLINE_CM, head_circumference_cm=head)
        assert plan.depth_cm == pytest.approx(head / 2 - HOOD_DEPTH_REDUCTION_CM)
        assert plan.height_cm == pytest.approx(
            hood_length_from_head_cm(head) + HOOD_HEIGHT_EASE_CM)
        if previous is not None:
            assert plan.depth_cm > previous[0] + 1.0
            assert plan.height_cm > previous[1] + 1.0
        previous = (plan.depth_cm, plan.height_cm)


def test_a_bigger_head_gives_a_bigger_pattern():
    """引いた**型紙**まで大きくなること(計算だけで終わっていないこと)。"""
    sizes = []
    for head in (52.0, 57.0, 62.0):
        part = _hoods(_build(head))[0]
        xs = [x for x, _ in part.stitch_line]
        ys = [y for _, y in part.stitch_line]
        sizes.append((max(xs) - min(xs), max(ys) - min(ys)))
    for (w1, h1), (w2, h2) in zip(sizes, sizes[1:]):
        assert w2 > w1 + 1.0, sizes
        assert h2 > h1 + 1.0, sizes


def test_the_hood_comes_in_two_pieces():
    """2枚剥ぎ(中心後で縫い合わせる)であること。"""
    assert len(_hoods(_build())) == 2


# --- 2. 付け根が首ぐりに合う -------------------------------------------------

def test_the_neck_edge_matches_the_neckline():
    """フードの付け根(2枚ぶん)が、身頃の首ぐりと一致すること。

    フードは首ぐりにぐるりと縫い付けるので、ここが合っていなければ
    そのままでは付かない。
    """
    result = _build()
    parts = {p.part_type: p for p in result.finalized_parts}
    neckline = (C.neckline_length(parts["front_bodice"])
                + C.neckline_length(parts["back_bodice"]))
    total = sum(C.hood_neck_edge_length(p) for p in _hoods(result))
    assert total == pytest.approx(neckline, abs=0.2), (total, neckline)


@pytest.mark.parametrize("head", [52.0, 57.0, 62.0], ids=["小さい頭", "標準", "大きい頭"])
def test_no_warning_whatever_the_head_size(head):
    """頭の大きさを変えても、縫い合わせの警告が出ないこと。"""
    assert not _build(head).summary()["compatibility_warnings"]


def test_the_neck_edge_is_measured_along_the_curve_not_the_bounding_box():
    """付け根を、帯パーツの汎用判定で測らないこと。

    汎用判定(`seam_edge_path`)は「x最小の点とx最大の点を下側を通って
    結ぶ経路」に落ちる。フードのx最小の点は**前上の角**(顔の開きの
    いちばん上)なので、付け根18.6cmに対して121.4cmという値が返り、
    「84.1cm一致していません」という警告が必ず出ていた。
    """
    part = _hoods(_build())[0]
    generic = C.seam_edge_length(part)
    specific = C.hood_neck_edge_length(part)
    assert specific is not None
    assert specific < generic / 2, (specific, generic)
    assert specific == pytest.approx(NECKLINE_CM / 2, abs=0.2)


def test_the_front_centre_is_dropped():
    """前中心が下がっていること(玉置「平面的フード 2.5cm」)。

    下がっていないと、フードが首から立ち上がったまま後ろへ倒れない。
    """
    plan = plan_hood(NECKLINE_CM)
    _min_x, _min_y, _max_x, max_y = bounding_box(hood_segments(plan))
    assert max_y == pytest.approx(plan.height_cm + HOOD_FRONT_DROP_CM, abs=0.05)


# --- 3. 測っていないことを言う -----------------------------------------------

def test_it_says_when_the_head_was_not_measured():
    """頭囲を測っていないなら、既定値を使ったと言うこと。

    黙って57cmで引くと、頭の大きい人のフードが入らないまま縫い上がる。
    """
    notes = "\n".join(_build(head=None).summary()["design_notes"])
    assert "頭囲を測っていない" in notes, notes
    assert f"{DEFAULT_HEAD_CIRCUMFERENCE_CM:.0f}cm" in notes
    assert "ライオン堂" in notes, "どこから来た数字かを書くこと"


def test_it_does_not_say_that_when_the_head_was_measured():
    """測った人にその注記を出さないこと(空振りしていないか)。"""
    notes = "\n".join(_build(head=56.0).summary()["design_notes"])
    assert "頭囲を測っていない" not in notes
    assert "頭囲56cm" in notes, notes


def test_it_says_the_hood_length_is_an_estimate():
    """フード寸法を頭囲から見積もったことを言うこと。

    比0.696は資料の**作例1つ**から当てはめた値で、資料がその比を
    書いているわけではない。
    """
    notes = "\n".join(_build().summary()["design_notes"])
    assert "見積" in notes
    assert "作例1つ" in notes or "1つから当てはめた" in notes, notes


def test_a_measured_hood_length_wins():
    """フード寸法を測って渡したら、そちらを使うこと。"""
    plan = plan_hood(NECKLINE_CM, head_circumference_cm=57.0, hood_length_cm=44.0)
    assert plan.hood_length_cm == 44.0
    assert plan.height_cm == pytest.approx(44.0 + HOOD_HEIGHT_EASE_CM)
    assert not plan.length_estimated


# --- 4. 引けない組み合わせを歪めない -----------------------------------------

def test_it_refuses_when_the_head_is_too_small_for_the_neckline():
    """首ぐりに対して頭が小さすぎる指定を、黙って歪めないこと。

    付け根(首ぐりの半分)が奥行きに追いつくと、前端が立ってしまい頭が
    入らない。形にならないので、そう言う。
    """
    plan = plan_hood(neckline_cm=60.0, head_circumference_cm=50.0)
    assert not plan.usable
    assert "頭" in plan.reason, plan.reason
    assert hood_notes(plan) == [f"フードは引けませんでした({plan.reason})。"]


def test_a_normal_combination_is_not_refused():
    """まともな組み合わせまで弾いていないこと(空振りの確認)。"""
    for neck, head in ((37.3, 57.0), (33.0, 54.0), (42.0, 62.0)):
        plan = plan_hood(neckline_cm=neck, head_circumference_cm=head)
        assert plan.usable, (neck, head, plan.reason)


# --- 5. 縫う手順に出る -------------------------------------------------------

def test_the_hood_has_its_own_sewing_steps():
    """フードを作る手順・付ける手順が、縫う順番に入ること。"""
    steps = str(_build().summary()["assembly_steps"])
    assert "フードを作る" in steps
    assert "フードを付ける" in steps
    assert "中心後" in steps, "2枚をどこで縫うかを書くこと"


def test_a_wrong_neck_edge_is_caught():
    """フードの付け根が首ぐりと違っていたら、警告が出ること。

    round74まで、この突き合わせは衿にしか掛かっていなかった。
    フードを対象に入れていなければ、付け根がどれだけ違っていても
    「警告なし」で通る。
    """
    from dataclasses import replace

    result = _build()
    hoods = _hoods(result)
    # 付け根を5cm縮めたフードに差し替える(他は触らない)。
    shrunk = [replace(h, stitch_line=[(x * 0.7, y) for x, y in h.stitch_line])
              for h in hoods]
    others = [p for p in result.finalized_parts if p.part_type != "hood"]
    warnings = C.check_seam_compatibility(others + shrunk)
    kinds = {w.kind for w in warnings}
    assert "neckline_collar" in kinds, warnings
    message = next(w.message for w in warnings if w.kind == "neckline_collar")
    assert "フード" in message, message
