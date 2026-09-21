"""round24: 袖山の高さを、袖ぐりの寸法に比例させる。

round23まで袖山の高さは袖丈比だけで動いていた。つまり**袖ぐりが大きく
なっても袖山は高くならず**、袖山カーブの長さを袖ぐりに合わせるために
幅ばかりが広がっていた。実測(袖幅=二の腕まわり・平置き):

    バスト  袖ぐり(片腕)  round23の袖幅  袖山の高さ
      60      34.63        25.1        12.0
      83      39.72        31.7        12.0
     110      49.92        44.2        12.0
     130      58.69        54.2        12.0   ← 二の腕に対して大きすぎる

袖山の高さは袖ぐり寸法に比例させるのが製図の定石(目安は袖ぐり÷3)で、
テンプレートの12cmも「袖ぐり39.7cmに対して÷3の目安に近い値」として
選ばれている。倍率1.0のまま据え置いていたのは、その関係を実装して
いなかっただけだった。
"""

import pytest
from types import SimpleNamespace

from engine.bodice_fit import (
    SLEEVE_FIT_Y_ROLES, STANDARD_ARMHOLE_PER_ARM_CM, build_sleeve_y_map,
    sleeve_cap_height_scale,
)
from engine.compatibility import armhole_length
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import bounding_box, segments_to_polyline
from engine.templates_db import TemplateDB

SLEEVES = ("straight", "curve", "puff", "bell", "cap", "three_quarter")
BUSTS = (60, 70, 83, 95, 110, 130)


def _generate(pipeline, bust_cm, variation="straight"):
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1),
                               PartRequest("sleeve", variation, 2)])
    result = pipeline.generate_from_selection(
        spec, Measurements(bust_cm, bust_cm * 0.79, bust_cm * 1.10, 158, 52, 37))
    return result, {p.part_type: p for p in result.scaled_parts}


def _armhole_per_arm(parts) -> float:
    total = 0.0
    for part_type in ("front_bodice", "back_bodice"):
        value = armhole_length(SimpleNamespace(
            part_type=part_type, variation=parts[part_type].variation,
            stitch_line=segments_to_polyline(parts[part_type].segments)))
        assert value is not None
        total += value
    return total / 2.0


def _cap_height_cm(scaled) -> float:
    """袖山の高さ = 輪郭の先頭点(M)のy。

    `_sleeve_cap_d`(scripts/generate_templates.py)が、袖の輪郭を必ず
    「袖山の左端(y=袖山の高さ)」から書き始める規約になっている。
    """
    return scaled.segments[0][1][1]


# --- 基準値が実測と一致すること ---------------------------------------------

def test_the_reference_armhole_matches_the_actual_standard_bodice(tmp_path):
    """`STANDARD_ARMHOLE_PER_ARM_CM`が、実際に生成される標準Mの袖ぐりと
    一致すること。

    この値は袖山の倍率の分母なので、身頃を作り変えたのにここが古いままだと
    標準サイズの袖が静かにずれる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _generate(pipeline, STANDARD_M.bust)
    assert _armhole_per_arm(parts) == pytest.approx(
        STANDARD_ARMHOLE_PER_ARM_CM, abs=0.1)


@pytest.mark.parametrize("variation", SLEEVES)
def test_every_sleeve_template_declares_its_fit_lines(variation):
    """全ての袖テンプレートが`data-fit-y`を持つこと。

    持たないテンプレートは静かに従来どおり(袖山の高さが袖丈比)に戻るので、
    「新しく足した袖だけ袖山が動かない」という後退を防ぐ。
    """
    anchors = TemplateDB().get_fit_anchors_y("sleeve", variation)
    assert {role for role, _y in anchors} == set(SLEEVE_FIT_Y_ROLES), (variation, anchors)


# --- 倍率の式 ---------------------------------------------------------------

def test_the_standard_armhole_gives_scale_one():
    assert sleeve_cap_height_scale(STANDARD_ARMHOLE_PER_ARM_CM) == pytest.approx(1.0)


def test_the_scale_is_proportional_to_the_armhole():
    assert sleeve_cap_height_scale(STANDARD_ARMHOLE_PER_ARM_CM * 1.5) == pytest.approx(1.5)
    assert sleeve_cap_height_scale(0.0) == pytest.approx(1.0)   # 退化した入力


def test_a_broken_order_produces_no_map():
    """節点の順序が崩れる入力では写像を作らず、一律倍率へ落ちること。"""
    anchors = [("cap", 0.0), ("underarm", 12.0), ("hem", 17.0)]
    assert build_sleeve_y_map(anchors, 3.0, 1.0) == []      # 袖山が袖口より下
    assert build_sleeve_y_map([("cap", 0.0), ("hem", 52.0)], 1.0, 1.0) == []


# --- 実際に生成される袖 -----------------------------------------------------

def test_the_standard_size_keeps_the_template_cap_height(tmp_path):
    """標準Mの袖山の高さが、テンプレートの12cm(倍率1.0)のままであること。

    【round31で幅の期待値を書き換えた理由】round30までこのテストは
    「標準Mの袖はround23までとまったく同じ(高さ12.0cm・幅31.70cm)」を
    確かめていた。round31で袖ぐりの点を新文化式の胸幅・背幅の位置へ
    合わせた結果、標準Mの袖ぐりが片腕39.72→40.59cmへ実際に0.87cm伸び、
    袖山カーブもいせ込みぶんを含めて0.90cm伸ばす必要が出た。袖山の
    高さは基準(STANDARD_ARMHOLE_PER_ARM_CM)を実物へ追随させたので
    12.0cmのままだが、その高さで長さを稼ぐには幅が広がる——実測で
    31.70→32.82cm(二の腕27cmに対するゆとりが4.7→5.8cm)。

    **袖ぐりが変わったのだから袖も変わる**のであって、数字を合わせに
    行ったのではない。高さが倍率1.0であることは基準と実物が一致して
    いることの確認になるので、そちらを主眼にした名前へ変えてある。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _generate(pipeline, STANDARD_M.bust)
    sleeve = parts["sleeve"]
    min_x, _min_y, max_x, _max_y = bounding_box(sleeve.segments)
    assert _cap_height_cm(sleeve) == pytest.approx(12.0, abs=0.05)
    # round43で32.82→34.32へ更新。肩傾斜を製図の角度で引き直した結果、
    # 標準Mの袖ぐりが片腕1.16cm長くなった(`STANDARD_ARMHOLE_PER_ARM_CM`)。
    # 袖はその袖ぐりに合わせて作られるので、幅も追随する。
    assert (max_x - min_x) == pytest.approx(34.32, abs=0.1)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_cap_height_tracks_the_armhole(tmp_path, bust):
    """袖山の高さが、実際の袖ぐりに比例していること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _generate(pipeline, bust)
    expected = 12.0 * _armhole_per_arm(parts) / STANDARD_ARMHOLE_PER_ARM_CM
    assert _cap_height_cm(parts["sleeve"]) == pytest.approx(expected, abs=0.1), bust


def test_a_large_size_sleeve_is_no_longer_a_balloon(tmp_path):
    """バスト130で、袖幅が二の腕に対して大きすぎなくなったこと。

    round23までは54.2cmだった(袖山が12cmのまま据え置かれたぶん、袖山
    カーブの長さを袖ぐり58.7cmに合わせるには幅を広げるしかなかった)。
    袖山を袖ぐりに比例させると、袖ぐりに対して相似な形になる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _generate(pipeline, 130)
    min_x, _min_y, max_x, _max_y = bounding_box(parts["sleeve"].segments)
    width = max_x - min_x
    # round23の不具合は54.2cm。round24の修正後45.98cm、round43の肩傾斜の
    # 直しで袖ぐりが伸びたぶん50.80cmになった。しきい値は「round23の
    # 壊れ方(54.2cm)を必ず捕らえる」ために置いてあるので、実測に合わせて
    # 52.0へ上げる——**壊れ方を捕らえる力は残したまま**、実物が動いたぶんだけ
    # 追随させている。
    assert width < 52.0, width
    # 袖ぐりに対して標準Mと同じ相似比になっていること。
    ratio = _armhole_per_arm(parts) / STANDARD_ARMHOLE_PER_ARM_CM
    # 基準の34.32cmはround43の実測(標準Mの袖幅。上のテストと同じ値)。
    # 相似であることを見るテストなので、基準が動いたら一緒に動かす。
    assert width == pytest.approx(34.32 * ratio, rel=0.05)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_sleeve_length_does_not_change(tmp_path, bust):
    """袖山を高くしても、袖丈は採寸どおりのままであること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _generate(pipeline, bust)
    _min_x, min_y, _max_x, max_y = bounding_box(parts["sleeve"].segments)
    assert (max_y - min_y) == pytest.approx(52.0, abs=0.05), bust


@pytest.mark.parametrize("bust", BUSTS)
@pytest.mark.parametrize("variation", SLEEVES)
def test_the_sleeve_still_fits_the_armhole(tmp_path, bust, variation):
    """袖山の高さを変えても、袖山カーブが袖ぐりに合っていること。

    袖山の高さを先に決め、そのうえで幅を二分探索して袖山カーブの長さを
    袖ぐりに合わせる、という順序が保たれていることの確認。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result, _parts = _generate(pipeline, bust, variation)
    kinds = [w.kind for w in result.compatibility_warnings()]
    assert "armhole_sleeve_cap" not in kinds, (bust, variation, kinds)


def test_a_sleeve_without_a_bodice_still_falls_back(tmp_path):
    """身頃を選ばず袖だけ生成した場合も、従来どおり生成できること。

    袖ぐりが分からないので袖山の比例も効かせられない。落ちたり無効な
    型紙になったりせず、採寸比の独立スケーリングへ落ちる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("sleeve", "straight", 2)])
    result = pipeline.generate_from_selection(spec, STANDARD_M)
    sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert len(sleeves) == 2
    assert all(p.width_cm > 0 and p.height_cm > 0 for p in sleeves)
