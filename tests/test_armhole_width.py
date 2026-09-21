"""round31: 袖ぐりの点(胸幅・背幅)を新文化式の位置へ合わせる / いせ込みを袖ぐり比にする。

【round30までの何が足りなかったか】
袖ぐりのえぐれ量はテンプレートの定数(2.5cm)のままだったので、袖ぐりの点
(中心から胸幅・背幅だけ離れた点)は「肩先からえぐれ量ぶん内側」——つまり
**バストではなく肩幅**で決まっていた。実測(肩幅37cm固定):

    バスト   胸幅の式  実測   差      背幅の式  実測   差
      60     13.70   15.48  +1.78    14.90   15.48  +0.58
      83     16.57   17.61  +1.04    17.77   17.61  −0.16
     110     19.95   17.93  −2.02    21.15   17.93  −3.22
     130     22.45   18.08  −4.37    23.65   18.08  −5.57

肩幅をバストに連動させても、前が一貫して+1.0cm(左右で2cm)広かった。
新文化式の製図では前袖ぐりは胸幅線に、後ろ袖ぐりは背幅線に**接する**ように
引く(出典: MAISON DE AS「レディース原型作り(新文化式)」)。つまり袖ぐりの
いちばん内側の点は胸幅/背幅そのものであるべきで、そこを合わせに行く。
"""

import pytest

from engine.bodice_fit import (
    ARMHOLE_SCOOP_MAX_FACTOR, ARMHOLE_SCOOP_MIN_FACTOR,
    back_width_cm, bodice_side_width_cm, chest_width_cm, fit_armhole_width,
)
from engine.compatibility import (
    SLEEVE_CAP_EASE_MAX_CM, SLEEVE_CAP_EASE_MIN_CM, SLEEVE_CAP_EASE_RATIO,
    armhole_length, sleeve_cap_ease_cm, sleeve_cap_length,
)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.scaling import scale_template
from engine.svgpath import bounding_box, segments_to_polyline
from engine.templates_db import TemplateDB

BUSTS = (60, 70, 83, 95, 110, 120, 130)


def _graded_shoulder(bust: float) -> float:
    """バストに釣り合う肩幅(cm)。標準M(バスト83/肩幅37)から4cmに1cmの割合。"""
    return 37.0 + (bust - 83) / 4.0


def _measurements(bust: float, shoulder: float | None = None) -> Measurements:
    return Measurements(bust=bust, waist=bust - 17, hip=bust + 8,
                        height=158, sleeve_length=52,
                        shoulder_width=_graded_shoulder(bust) if shoulder is None else shoulder)


def _scaled(part_type: str, m: Measurements, db: TemplateDB):
    return scale_template(part_type, "round_neck", db.get(part_type, "round_neck"), m,
                          fit_anchors=db.get_fit_anchors(part_type, "round_neck"),
                          fit_anchors_y=db.get_fit_anchors_y(part_type, "round_neck"))


def _armhole_point_from_cf(segments) -> float:
    """袖ぐり曲線がいちばん中心寄りへ出る点の、中心からの距離(cm)。

    エンジンの内部関数ではなく、**出来上がった輪郭を数値的に測る**
    (エンジンと同じ式で測っては、式どおりであることしか確かめられない)。
    輪郭は中心について左右対称なので、左半分だけ見る。
    """
    min_x, _min_y, max_x, _max_y = bounding_box(segments)
    cf = (min_x + max_x) / 2.0
    points = segments_to_polyline(segments, curve_steps=400)
    # 身頃の輪郭は必ず左肩先から始まり、左袖ぐり→脇線と続く
    # (scripts/generate_templates.pyの`_bodice_path`が保つ規則で、
    #  engine/compatibility.pyの`armhole_length`も同じ前提で測っている)。
    # 袖ぐりは肩先から中心側へふくらんでから脇の下へ降りるので、
    # 「xが肩先より外へ出る」までの区間がふくらみのすべてになる。
    # そこで止めれば、脇線・胸ぐせダーツ(中心側へ深く切れ込む)を
    # 取り違えることがない。
    shoulder_x = points[0][0]
    bulge = []
    for x, y in points:
        if x < shoulder_x - 1e-9 and bulge:
            break
        bulge.append((x, y))
    return cf - max(x for x, _y in bulge)


# --- 袖ぐりの点が式どおりの位置に来ること ---------------------------------

@pytest.mark.parametrize("bust", BUSTS)
@pytest.mark.parametrize("part_type,formula",
                          [("front_bodice", chest_width_cm),
                           ("back_bodice", back_width_cm)])
def test_the_armhole_point_lands_on_the_bunka_width(bust, part_type, formula):
    """釣り合いの取れた体型では、胸幅/背幅が式ぴったりになること。"""
    db = TemplateDB()
    scaled = _scaled(part_type, _measurements(bust), db)
    assert _armhole_point_from_cf(scaled.segments) == pytest.approx(formula(bust), abs=0.05)


@pytest.mark.parametrize("bust", BUSTS)
def test_the_back_is_wider_than_the_front_at_the_armhole(bust):
    """背幅が胸幅より広いこと(新文化式では常に1.2cm差)。

    round30まで前後は同じテンプレートから同じ形で作られていたので、
    胸幅と背幅がまったく同じだった。腕は前へ出す方が多いので、背中側を
    広く取るのが原型の定石。
    """
    db = TemplateDB()
    front = _armhole_point_from_cf(_scaled("front_bodice", _measurements(bust), db).segments)
    back = _armhole_point_from_cf(_scaled("back_bodice", _measurements(bust), db).segments)
    assert back - front == pytest.approx(back_width_cm(bust) - chest_width_cm(bust), abs=0.1)


def test_the_standard_size_moved_by_the_measured_amount():
    """標準Mサイズで、round30から実際にどれだけ動いたかの記録。

    数字を凍らせるためではなく、「直したつもりで何も動いていない」
    という後退を検出するために置いてある。
    """
    db = TemplateDB()
    front = _armhole_point_from_cf(_scaled("front_bodice", _measurements(83), db).segments)
    # round30の実測は17.61cm(式は16.57cm)。1.04cm内側へ寄った。
    assert front == pytest.approx(16.57, abs=0.05)
    assert abs(front - 17.61) > 0.5


# --- 幾何的に不可能な場合は、届かないことを開示する -------------------------

@pytest.mark.parametrize("bust", (95, 110, 120, 130))
def test_a_narrow_shoulder_is_disclosed_not_silently_squeezed(tmp_path, bust):
    """バストに対して肩幅が狭いと、届かないことを注記で開示すること。

    袖ぐりの点は肩先より外へは出られない。狭い型紙を黙って出さない。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, _measurements(bust, shoulder=37.0))
    assert any("袖ぐりまで" in w for w in result.measurement_warnings), bust
    assert any(getattr(p, "chest_width_limited", False) for p in result.scaled_parts)


@pytest.mark.parametrize("bust", BUSTS)
def test_a_balanced_body_is_not_disclosed(tmp_path, bust):
    """釣り合いの取れた体型では、届かなかったという注記が出ないこと。

    (この注記が常に出るようになったら、開示が無意味になる。)
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, _measurements(bust))
    assert not any("袖ぐりまで" in w for w in result.measurement_warnings), bust


def test_the_solver_is_measured_not_assumed_linear():
    """倍率を「出っ張りに比例」で決めると外れることを、実際に確かめる。

    round31で最初にそう実装して、前身頃の胸幅が最大1.59cmずれた。
    弦(肩先から脇の下へ降りる直線)の寄与は倍率に比例しないためで、
    二分法で解く現在の実装ならずれない。
    """
    db = TemplateDB()
    m = _measurements(130)
    scaled = _scaled("front_bodice", m, db)
    got = _armhole_point_from_cf(scaled.segments)
    assert got == pytest.approx(chest_width_cm(130), abs=0.05)
    # 比例で決めていた頃の値(20.86cm)には**なっていない**こと。
    assert abs(got - 20.86) > 1.0


def test_the_scoop_factor_stays_inside_its_limits():
    """えぐれ量の倍率が定めた範囲に収まっていること(定数の存在確認)。"""
    assert 0 < ARMHOLE_SCOOP_MIN_FACTOR < 1 < ARMHOLE_SCOOP_MAX_FACTOR


def test_untouched_when_there_is_no_armhole():
    """袖ぐりらしい曲線が無ければ、何も変えずに返すこと。"""
    segments = [("M", [0.0, 0.0]), ("L", [10.0, 0.0]), ("L", [10.0, 10.0]), ("Z", [])]
    out, achieved, clamped = fit_armhole_width(segments, underarm_y=10.0, cf_x=5.0,
                                                target_from_cf_cm=3.0)
    assert out == segments and clamped is False and achieved == 3.0


def test_the_side_width_formula_differs_by_part():
    assert bodice_side_width_cm("front_bodice", 83) == pytest.approx(chest_width_cm(83))
    assert bodice_side_width_cm("back_bodice", 83) == pytest.approx(back_width_cm(83))
    # 前開きの半身も前身頃と同じ胸幅を使う。
    assert bodice_side_width_cm("front_bodice_zip_panel", 83) == pytest.approx(chest_width_cm(83))


# --- 輪郭が壊れていないこと -------------------------------------------------

@pytest.mark.parametrize("bust", BUSTS)
@pytest.mark.parametrize("neckline", ("round_neck", "v_neck", "boat_neck", "square_neck"))
def test_the_outline_stays_valid(bust, neckline):
    """えぐれ量を動かしても、輪郭が自己交差しないこと。

    袖ぐりを深くえぐると、首ぐりや肩線と交わりうる。全ネックライン×
    全サイズで実際に多角形にして確かめる。
    """
    shapely = pytest.importorskip("shapely.geometry")
    db = TemplateDB()
    m = _measurements(bust)
    for part_type in ("front_bodice", "back_bodice"):
        segments = db.get(part_type, neckline)
        if segments is None:
            continue
        scaled = scale_template(
            part_type, neckline, segments, m,
            fit_anchors=db.get_fit_anchors(part_type, neckline),
            fit_anchors_y=db.get_fit_anchors_y(part_type, neckline))
        polygon = shapely.Polygon(segments_to_polyline(scaled.segments, curve_steps=200))
        assert polygon.is_valid, (part_type, neckline, bust)
        assert polygon.area > 0


# --- いせ込みを袖ぐりに比例させる -------------------------------------------

def test_the_ease_is_five_percent_of_the_armhole():
    """いせ込みが袖ぐりの5%であること(新文化式 AH×0.05)。"""
    assert sleeve_cap_ease_cm(40.0) == pytest.approx(2.0)
    assert sleeve_cap_ease_cm(50.0) == pytest.approx(50.0 * SLEEVE_CAP_EASE_RATIO)


def test_the_ease_is_bounded_at_both_ends():
    """家庭用ミシンで縫える範囲に収めること。"""
    assert sleeve_cap_ease_cm(10.0) == pytest.approx(SLEEVE_CAP_EASE_MIN_CM)
    assert sleeve_cap_ease_cm(200.0) == pytest.approx(SLEEVE_CAP_EASE_MAX_CM)
    assert sleeve_cap_ease_cm(None) > 0 and sleeve_cap_ease_cm(0) > 0


@pytest.mark.parametrize("bust", BUSTS)
def test_the_generated_sleeve_carries_that_much_ease(tmp_path, bust):
    """実際に生成された袖山が、袖ぐり+その割合ぶんの長さになっていること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, _measurements(bust))
    parts = {p.part_type: p for p in result.finalized_parts}
    per_arm = (armhole_length(parts["front_bodice"])
               + armhole_length(parts["back_bodice"])) / 2.0
    cap = sleeve_cap_length(parts["sleeve"])
    assert cap - per_arm == pytest.approx(sleeve_cap_ease_cm(per_arm), abs=0.1), bust
    # 固定値2.0cmのままなら、大きい体で足りない/小さい体で多すぎる。
    if bust >= 120:
        assert cap - per_arm > 2.2
    if bust <= 60:
        assert cap - per_arm < 1.9


@pytest.mark.parametrize("bust", BUSTS)
def test_no_compatibility_warning_is_produced(tmp_path, bust):
    """袖ぐりを動かした結果、袖が付かなくなっていないこと。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    result = pipeline.generate_from_selection(spec, _measurements(bust))
    assert [w.kind for w in result.compatibility_warnings()] == [], bust
