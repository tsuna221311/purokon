"""round76: 肩先を出した形(ドロップショルダー)が引けなかった。

【round75までの状態】身頃の肩先は、常に「入力された肩幅の半分」の位置に
あった(`engine/bodice_fit.py`)。つまり引ける肩は1種類しかない。

    肩幅37cmを入れる → 肩先は必ず中心から18.5cm → セットインスリーブ

コスプレ衣装でよく作るコート・パーカ・ブルゾンは、肩先が腕の上まで
落ちている。この形を出す手段が**1つも無かった**ので、そこだけ市販の
型紙を探すか、出てきた型紙の肩を自分で描き直すことになる。

【round76で足したもの】`engine/drop_shoulder.py`。肩先を肩線の延長上へ
指定cmだけ出し、袖ぐりを引き直し、袖の袖山を低くする。

このファイルが見張るのは:

  1. 肩先が、肩線の**延長上**へ指定どおり出ること(肩線が折れない)
  2. 袖ぐりが短くならないこと(=腕が上がらなくならないこと)
  3. 袖が、低い袖山・短い袖丈で引かれること
  4. 前開き・切り替え線・フードと組み合わせても縫えること
  5. 指定しなければ、型紙が1mmも変わらないこと
"""

import math
import tempfile

import pytest

from engine import compatibility as C
from engine.drop_shoulder import (
    CAP_HEIGHT_MAX_RATIO, DROP_CAP_HEIGHT_RATIO, DROP_SLEEVE_CAP_EASE_CM,
    too_large_drop_reason,
)
from engine.blocks import ADULT_FEMALE
from engine.measurements import Measurements
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline


def _body(**kwargs):
    base = dict(bust=82, waist=62, hip=88, height=158,
                sleeve_length=54, shoulder_width=37)
    base.update(kwargs)
    return Measurements(**base)


PLAIN = GarmentSpec(parts=[
    PartRequest("front_bodice", "round_neck", 1),
    PartRequest("back_bodice", "round_neck", 1),
    PartRequest("sleeve", "straight", 2)])

FRONT_ZIP = GarmentSpec(parts=[
    PartRequest("front_bodice_zip_panel", "round_neck", 2),
    PartRequest("back_bodice", "round_neck_zip", 1),
    PartRequest("sleeve", "straight", 2)])

PRINCESS = GarmentSpec(parts=list(PLAIN.parts), princess_line=True)

HOODED = GarmentSpec(parts=list(PLAIN.parts) + [PartRequest("hood", "", 2)])


def _build(drop=None, spec=PLAIN, body=None):
    return PatternForgePipeline(
        output_dir=tempfile.mkdtemp()).generate_from_selection(
            spec, body or _body(), shoulder_drop_cm=drop)


def _by_type(result):
    out: dict = {}
    for part in result.finalized_parts:
        out.setdefault(part.part_type, []).append(part)
    return out


def _shoulder_tip(part):
    """輪郭の先頭の点。身頃は必ず左肩先から始まる(`armhole_length`参照)。"""
    return part.stitch_line[0]


def _left_neck(part):
    """左の首の付け根(首ぐりの高さにある点のうち、いちばん外側)。"""
    top = min(y for _x, y in part.stitch_line)
    return min((p for p in part.stitch_line if p[1] <= top + 0.01),
               key=lambda p: p[0])


def _armhole_per_arm(parts):
    return (C.armhole_length(parts["front_bodice"][0])
            + C.armhole_length(parts["back_bodice"][0])) / 2.0


def _cap_height(sleeve):
    return sleeve.stitch_line[0][1] - min(y for _x, y in sleeve.stitch_line)


def _length(part):
    ys = [y for _x, y in part.stitch_line]
    return max(ys) - min(ys)


# --- 1. 肩先が肩線の延長上へ出る ---------------------------------------------

@pytest.mark.parametrize("drop", [3.0, 5.0, 8.0])
def test_the_shoulder_tip_moves_along_the_shoulder_line(drop):
    """肩先が、肩線の延長上へちょうど指定cmだけ出ること。

    「外へ`drop`cm」ではなく「肩線に沿って`drop`cm」である。真横へ
    動かすと肩線がそこで折れ、縫い合わせたときに肩が角張る。
    """
    plain = _by_type(_build())["front_bodice"][0]
    dropped = _by_type(_build(drop))["front_bodice"][0]
    before, after = _shoulder_tip(plain), _shoulder_tip(dropped)
    neck = _left_neck(plain)

    moved = math.dist(before, after)
    assert moved == pytest.approx(drop, abs=0.05), (before, after)

    # 首の付け根 → 元の肩先 → 出した肩先 が一直線であること。
    # (外積が0。長さで割って、角度のずれとして見る)
    ax, ay = before[0] - neck[0], before[1] - neck[1]
    bx, by = after[0] - before[0], after[1] - before[1]
    cross = abs(ax * by - ay * bx) / (math.hypot(ax, ay) * math.hypot(bx, by))
    assert cross < 0.01, ("肩線が折れている", neck, before, after)
    # 外側(脇線の方)へ出ていること。
    assert after[0] < before[0]


def test_a_bigger_drop_moves_the_shoulder_further():
    """ドロップを大きくすれば、肩先はその分だけ外へ出ること。"""
    tips = [_shoulder_tip(_by_type(_build(d))["front_bodice"][0])
            for d in (0.0001, 4.0, 8.0)]
    assert tips[1][0] < tips[0][0] - 3.0
    assert tips[2][0] < tips[1][0] - 3.0


# --- 2. 袖ぐりが短くならない -------------------------------------------------

@pytest.mark.parametrize("drop", [3.0, 5.0, 8.0])
def test_the_armhole_keeps_its_length(drop):
    """袖ぐりの長さが、ドロップ前と変わらないこと。

    【なぜ見張るか】肩線は水平ではないので、肩先を延長上へ出すと肩先は
    **下がる**。脇の下との距離が縮み、袖ぐりは逆に短くなる。実測
    (ドロップ5cm・脇の下を下げない場合):

        前身頃 41.75cm → 37.43cm / 後ろ身頃 41.34cm → 37.53cm

    4cm縮んだ袖ぐりでは腕が上がらない。資料が「袖ぐりを下げる」と
    書いているのはこのためで、下げ幅は「袖ぐりの長さを保つ」条件から
    解いている(engine/drop_shoulder.py)。
    """
    plain = _armhole_per_arm(_by_type(_build()))
    dropped = _armhole_per_arm(_by_type(_build(drop)))
    assert dropped == pytest.approx(plain, abs=0.1), (plain, dropped)


@pytest.mark.parametrize("drop", [3.0, 8.0])
def test_the_underarm_goes_down(drop):
    """脇の下が実際に下がること(袖ぐりを深くしていること)。"""
    plain = _by_type(_build())["front_bodice"][0]
    dropped = _by_type(_build(drop))["front_bodice"][0]
    assert C.underarm_y_of(dropped) > C.underarm_y_of(plain) + 0.5


# --- 3. 袖 -------------------------------------------------------------------

@pytest.mark.parametrize("drop", [3.0, 5.0, 8.0])
def test_the_sleeve_cap_is_low(drop):
    """袖山の高さが袖ぐりの25%になること(上限の30%を超えないこと)。

    出典(東レACS「No.019 ドロップショルダーの作図」)は
    「袖山の高さはアームホール寸法の30%以下が望ましい」という上限と、
    「袖山Aはアームホールの25%」という作例の両方を書いている。
    """
    parts = _by_type(_build(drop))
    armhole = _armhole_per_arm(parts)
    height = _cap_height(parts["sleeve"][0])
    assert height / armhole == pytest.approx(DROP_CAP_HEIGHT_RATIO, abs=0.01)
    assert height / armhole <= CAP_HEIGHT_MAX_RATIO


def test_the_set_in_sleeve_cap_is_not_lowered():
    """指定しなければ袖山は低くならないこと(空振りの確認)。"""
    parts = _by_type(_build())
    ratio = _cap_height(parts["sleeve"][0]) / _armhole_per_arm(parts)
    assert ratio > DROP_CAP_HEIGHT_RATIO + 0.02, ratio


@pytest.mark.parametrize("drop", [3.0, 8.0])
def test_the_ease_is_reduced(drop):
    """いせ込みが15mmになること(東レACS 第十六章)。"""
    parts = _by_type(_build(drop))
    cap = C.sleeve_cap_length(parts["sleeve"][0])
    ease = cap - _armhole_per_arm(parts)
    assert ease == pytest.approx(DROP_SLEEVE_CAP_EASE_CM, abs=0.1), ease


def test_the_ease_is_not_reduced_without_a_drop():
    """指定しなければ、いせ込みは従来どおりであること(空振りの確認)。"""
    parts = _by_type(_build())
    ease = C.sleeve_cap_length(parts["sleeve"][0]) - _armhole_per_arm(parts)
    assert ease > DROP_SLEEVE_CAP_EASE_CM + 0.3, ease


@pytest.mark.parametrize("drop", [3.0, 5.0, 8.0])
def test_the_sleeve_gets_shorter_by_the_drop(drop):
    """袖丈が、肩先を出した分だけ短くなること。

    袖丈は肩先から手首までの寸法である。肩先が`drop`cm腕の上へ出た
    のだから、袖はその分だけ短く引かないと出来上がりが長くなる。
    """
    plain = _length(_by_type(_build())["sleeve"][0])
    dropped = _length(_by_type(_build(drop))["sleeve"][0])
    assert dropped == pytest.approx(plain - drop, abs=0.1), (plain, dropped)


def test_the_upper_arm_measurement_is_not_used_but_is_disclosed():
    """二の腕を測っていても、ドロップの方を採ること(黙って採らない)。

    二の腕から袖幅を決めると、袖山の高さが探索変数になる
    (`scale_sleeve_to_cap_length`)。袖山を25%に**決める**のと両立
    しないので、ドロップを優先し、そのことを利用者へ言う。
    """
    result = _build(5.0, body=_body(upper_arm=28.0))
    parts = _by_type(result)
    # 二の腕から幅を決める経路へ入ると、袖山の高さが探索変数になり
    # 25%から外れる(実測: 28.7%相当まで高くなる)。
    ratio = _cap_height(parts["sleeve"][0]) / _armhole_per_arm(parts)
    assert ratio == pytest.approx(DROP_CAP_HEIGHT_RATIO, abs=0.01), ratio
    notes = "\n".join(result.summary()["design_notes"])
    assert "二の腕" in notes, notes
    assert "袖幅をそこから決めていません" in notes


# --- 4. 他の指定と組み合わせても縫える ---------------------------------------

@pytest.mark.parametrize("spec,label",
                         [(PLAIN, "普通"), (FRONT_ZIP, "前開き"),
                          (PRINCESS, "切り替え線"), (HOODED, "フード")],
                         ids=["普通", "前開き", "切り替え線", "フード"])
@pytest.mark.parametrize("drop", [3.0, 8.0])
def test_no_warning_with_a_drop(spec, label, drop):
    """ドロップを付けても、縫い合わせの警告が出ないこと。"""
    assert not _build(drop, spec=spec).summary()["compatibility_warnings"], label


def test_the_sleeve_follows_the_armhole_on_a_front_opening_bodice():
    """前開きでも、袖が**ドロップ後の**袖ぐりに合わせて引かれること。

    前開きの袖ぐりは「割る前の前身頃」を作って測っている
    (round74)。そこへドロップを当て忘れると、身頃だけが変わって
    袖はドロップ前の袖ぐりに合わせたまま出る。
    """
    plain = C.sleeve_cap_length(_by_type(_build(spec=FRONT_ZIP))["sleeve"][0])
    dropped = C.sleeve_cap_length(
        _by_type(_build(5.0, spec=FRONT_ZIP))["sleeve"][0])
    assert abs(dropped - plain) > 0.3, (plain, dropped)
    # 普通の身頃と同じだけ変わること(測る前身頃が同じものだから)。
    plain_normal = C.sleeve_cap_length(_by_type(_build())["sleeve"][0])
    dropped_normal = C.sleeve_cap_length(_by_type(_build(5.0))["sleeve"][0])
    assert (dropped - plain) == pytest.approx(dropped_normal - plain_normal,
                                              abs=0.2)


# --- 5. 指定しなければ何も変わらない -----------------------------------------

def test_nothing_changes_without_a_drop():
    """ドロップを指定しなければ、輪郭が1点も動かないこと。"""
    a = _by_type(_build())
    b = _by_type(_build(None))
    for part_type in ("front_bodice", "back_bodice", "sleeve"):
        assert (a[part_type][0].stitch_line
                == b[part_type][0].stitch_line), part_type


# --- 6. 引けない指定を歪めない -----------------------------------------------

def test_it_refuses_a_drop_that_is_too_large():
    """肩幅の半分を超えるドロップを、黙って頭打ちにしないこと。"""
    with pytest.raises(ValueError) as excinfo:
        _build(30.0)
    assert "肩幅" in str(excinfo.value)


def test_a_normal_drop_is_not_refused():
    """まともなドロップまで弾いていないこと(空振りの確認)。"""
    for drop in (1.0, 5.0, 18.0):
        assert too_large_drop_reason(drop, 37.0) is None, drop
    assert too_large_drop_reason(19.0, 37.0) is not None


# --- 7. 何をしたかを言う -----------------------------------------------------

def test_it_says_what_it_did():
    """ドロップの量・袖山の比・いせ込み・脇の下を、注記に出すこと。"""
    notes = "\n".join(_build(5.0).summary()["design_notes"])
    assert "ドロップショルダー" in notes
    assert "5cm" in notes
    assert "25%" in notes, notes
    assert "東レACS" in notes, "どこから来た数字かを書くこと"
    assert f"{DROP_SLEEVE_CAP_EASE_CM:g}cm" in notes
    assert "脇の下" in notes


def test_it_says_the_cap_ratio_on_a_front_opening_bodice_too():
    """前開きでも、袖山の高さの注記が出ること。

    前開きの袖ぐりは`scaled_by_type`だけでは測れない(割る前の前身頃が
    要る)。注記の側でもう一度測ろうとすると、**前開きのときだけ**
    袖山の注記が黙って消える(実測で消えていた)。
    """
    for spec, label in ((PLAIN, "普通"), (FRONT_ZIP, "前開き")):
        notes = "\n".join(_build(5.0, spec=spec).summary()["design_notes"])
        assert "袖山の高さ" in notes, label
        assert f"{DROP_CAP_HEIGHT_RATIO * 100:.0f}%" in notes, label


def test_it_does_not_say_that_without_a_drop():
    """指定していない人に、その注記を出さないこと(空振りの確認)。"""
    notes = "\n".join(_build().summary()["design_notes"])
    assert "ドロップショルダー" not in notes


def test_the_check_expects_the_reduced_ease_too():
    """縫い合わせのチェック側も、減らしたいせ込みを期待すること。

    引く側(`_sleeve_target_cap_cm`)とチェック側
    (`engine/compatibility.py`のチェック5)が別々のいせ込み量を持つと、
    **自分が引いた袖に対して自分で警告を出す**。許容(1.5cm)の内側に
    収まっているうちは表に出ないので、わざと合わない袖に差し替えて、
    警告文が名乗るいせ込み量を確かめる。
    """
    from dataclasses import replace

    result = _build(5.0)
    parts = _by_type(result)
    # 袖山を1割縮めた袖に差し替える(他は触らない)。
    shrunk = [replace(s, stitch_line=[(x * 0.9, y) for x, y in s.stitch_line])
              for s in parts["sleeve"]]
    others = [p for p in result.finalized_parts if p.part_type != "sleeve"]
    warnings = C.check_seam_compatibility(others + shrunk)
    message = next(w.message for w in warnings if w.kind == "armhole_sleeve_cap")
    assert f"いせ込み{DROP_SLEEVE_CAP_EASE_CM:.1f}cm" in message, message


def test_the_front_measured_only_bodice_is_dropped_too():
    """前開きで「袖ぐりを測るためだけに作る前身頃」にも、ドロップが
    当たっていること。

    当て忘れても、いまは袖ぐりの長さを保つ作りなので**出来上がりの
    数字が同じ**になり、外からは見えない(実測で差0.00cm)。
    見えないまま残すと、袖ぐりの長さを保たない引き方に変えた瞬間に
    前開きだけ袖が合わなくなる。ここで直接確かめる。
    """
    pipeline = PatternForgePipeline(output_dir=tempfile.mkdtemp())
    result = pipeline.generate_from_selection(FRONT_ZIP, _body(),
                                              shoulder_drop_cm=5.0)
    scaled_by_type: dict = {}
    for part in result.scaled_parts:
        scaled_by_type.setdefault(part.part_type, []).append(part)
    fronts = pipeline._unsplit_fronts_for_measuring(
        FRONT_ZIP, scaled_by_type, _body(), None, ADULT_FEMALE,
        shoulder_drop_cm=5.0)
    assert fronts, "測るための前身頃が作られていません"
    assert fronts[0].underarm_y_cm is not None, "ドロップが当たっていません"

    plain = pipeline._unsplit_fronts_for_measuring(
        FRONT_ZIP, scaled_by_type, _body(), None, ADULT_FEMALE)
    assert plain[0].underarm_y_cm is None, "指定していないのに当たっています"
