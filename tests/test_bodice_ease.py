"""round23: 身頃の着用ゆとりを、体の大きさによらず一定に保つ。

round22まで身頃の幅はバスト比で一律に拡大縮小していた。テンプレート
(バスト83 + ゆとり8cm)ごと引き伸ばすので、**ゆとりまでバストに比例して
増減していた**——小さい人はきつく、大きい人はぶかぶかになる。

ゆとりは「そのデザインをどれだけゆったり着るか」という設計上の量であって、
体の大きさに比例して増えるものではない。同じ考え方は下半身パーツが以前から
採用していて(`lower_garment_x_scale`はウエスト+2cm・ヒップ+4cmという一定の
ゆとり)、身頃だけが取り残されていた。
"""

import pytest

from tests.conftest import bodice_width_at_bust_cm

from engine.bodice_fit import (
    BODICE_EASE_CM, bodice_bust_cm_for_scale, bodice_x_scale,
)
from engine.measurements import Measurements, STANDARD_M
from engine.part_specs import MAX_SCALE, MIN_SCALE
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.scaling import measurement_clamp_warnings
from engine.svgpath import bounding_box

#: クランプに当たらない範囲のバスト(下の`test_...`で使う)。
BUSTS = (60, 70, 83, 95, 110, 130)


def _finished_girth_cm(pipeline, bust_cm: float) -> float:
    """前身頃+後身頃の幅の合計 = 出来上がりの胴回り。"""
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1)])
    result = pipeline.generate_from_selection(
        spec, Measurements(bust_cm, bust_cm * 0.79, bust_cm * 1.10, 158, 52, 37))
    # round26: 外接矩形の幅は裾(ヒップ)の幅になったので、バストのゆとりは
    # バストの高さで測る(tests/conftest.py の bodice_width_at_bust_cm)。
    return sum(bodice_width_at_bust_cm(part) for part in result.scaled_parts)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_wearing_ease_is_the_same_at_every_size(tmp_path, bust):
    """出来上がりの胴回りが、どのバストでも「バスト + 8cm」になること。

    round22までの実測(同じ入力):

        バスト   出来上がり   ゆとり
          60       65.8       5.8   ← 布帛の身頃としてはきつい
          83       91.0       8.0
         110      120.6      10.6
         130      142.5      12.5   ← ぶかぶか
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    girth = _finished_girth_cm(pipeline, bust)
    assert girth == pytest.approx(bust + BODICE_EASE_CM, abs=0.15), (bust, girth)


def test_the_standard_size_is_unchanged(tmp_path):
    """標準Mサイズの型紙は、round22までとまったく同じであること。

    ゆとりの決め方を変えたので、標準サイズだけは変わらない(倍率1.0)ことを
    確かめておく。ここが動いていたら、テンプレートの設計値そのものを
    変えてしまっている。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    assert bodice_x_scale(STANDARD_M.bust) == pytest.approx(1.0)
    # 許容0.1cmは測り方の分解能(バストの高さを脇の下の0.5cm下で取り、
    # 輪郭を折れ線で近似しているぶんの誤差)。
    assert _finished_girth_cm(pipeline, STANDARD_M.bust) == pytest.approx(91.0, abs=0.1)


def test_the_ease_rule_and_its_inverse_agree():
    """倍率の式とその逆算が一致すること。

    クランプの境界を利用者へ説明する文言はこの逆算から作る。ずれると、
    実際には正しく生成できている値に「別の値にしました」と嘘の注記が出る
    (round23で実際に起きた)。
    """
    for scale in (MIN_SCALE, 1.0, MAX_SCALE, 1.23):
        assert bodice_x_scale(bodice_bust_cm_for_scale(scale)) == pytest.approx(scale)


def test_the_clamp_warning_names_the_boundary_that_is_actually_used():
    """注記に出る境界の数値が、実際にクランプされる値と一致すること。"""
    boundary = bodice_bust_cm_for_scale(MAX_SCALE)
    just_inside = Measurements(boundary - 0.5, 66, 91, 158, 52, 37)
    just_outside = Measurements(boundary + 0.5, 66, 91, 158, 52, 37)

    assert not [w for w in measurement_clamp_warnings(just_inside) if "バスト" in w]
    outside = [w for w in measurement_clamp_warnings(just_outside) if "バスト" in w]
    assert outside, "境界を超えたら開示すること"
    assert f"{boundary:.1f}" in outside[0], outside[0]


def test_a_smaller_person_is_no_longer_squeezed(tmp_path):
    """小さいサイズで、ゆとりが実際に増えていること(修正の効き目)。

    バスト60cmでは5.8cm→8.0cmへ2.2cm増える。布帛の身頃で5.8cmは
    腕を動かしにくい寸法なので、これは着心地に直接効く差である。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    girth = _finished_girth_cm(pipeline, 60)
    assert girth - 60 == pytest.approx(BODICE_EASE_CM, abs=0.15)
    assert girth > 65.8 + 1.0, "round22までの65.8cmより明確に広いこと"
