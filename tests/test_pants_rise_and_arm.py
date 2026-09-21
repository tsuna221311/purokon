"""round25: 股上をヒップで決め、二の腕まわりを採寸できるようにし、
ゆとりを数値で指定できるようにする。

3つとも「round24までの正直な限界」として書いていたものへの対応で、
いずれも**出来上がる型紙そのもの**の質に効く。
"""

import pytest

from tests.conftest import bodice_width_at_bust_cm

from engine.bodice_fit import (
    PANTS_FIT_Y_ROLES, PANTS_RISE_PER_HIP_CM, build_pants_y_map, pants_rise_cm,
)
from engine.measurements import Measurements, STANDARD_M, graded_measurements
from engine.part_specs import (
    CUSTOM_EASE_RANGES, DEFAULT_FIT, FIT_PRESETS, custom_fit_ease, fit_ease,
)
from engine.compatibility import armhole_length, sleeve_cap_ease_cm, sleeve_cap_length
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.scaling import SLEEVE_FIT_TOLERANCE_CM
from engine.svgpath import bounding_box, segments_to_polyline
from engine.templates_db import TemplateDB

PANTS_VARIATIONS = ("", "wide", "tapered", "flare", "shorts", "cropped")
HIPS = (80, 91, 105, 120)


def _pants(pipeline, hip_cm, height_cm=158.0, variation=""):
    spec = GarmentSpec(parts=[PartRequest("front_pants", variation, 2),
                               PartRequest("back_pants", variation, 2)])
    # ウエストにも独自の有効範囲(engine/measurements.pyの_VALID_RANGES)が
    # あるので、比例値をその範囲へ収めてから渡す。
    waist = min(150.0, max(40.0, hip_cm * 0.72))
    result = pipeline.generate_from_selection(
        spec, Measurements(83, waist, hip_cm, height_cm, 52, 37))
    return result, {p.part_type: p for p in result.scaled_parts}


def _measured_rise_cm(scaled) -> float:
    """ウエスト(上端)から股ぐりの先端までの距離。

    股ぐりの先端は「中心線側(xが最小)の輪郭で、いちばん下にある点」。
    """
    points = segments_to_polyline(scaled.segments, curve_steps=300)
    _min_x, min_y, _max_x, _max_y = bounding_box(scaled.segments)
    left = min(x for x, _y in points)
    return max(y for x, y in points if abs(x - left) < 0.6) - min_y


# --- 股上(パンツ) -----------------------------------------------------------

@pytest.mark.parametrize("variation", PANTS_VARIATIONS)
def test_every_pants_template_declares_its_fit_lines(variation):
    """全てのパンツテンプレートが`data-fit-y`を持つこと。

    持たないテンプレートは静かに従来どおり(股上が身長比)へ戻るので、
    「新しく足した丈だけ股上が浅い」という後退を防ぐ。
    """
    db = TemplateDB()
    for part_type in ("front_pants", "back_pants"):
        anchors = db.get_fit_anchors_y(part_type, variation)
        roles = {role for role, _y in anchors}
        assert roles == set(PANTS_FIT_Y_ROLES), (part_type, variation, anchors)


def test_the_standard_size_keeps_the_template_rise():
    """標準M(ヒップ91)では増分0で、テンプレートの股上そのままになること。"""
    assert pants_rise_cm(25.0, STANDARD_M.hip, 1.0) == pytest.approx(25.0)


def test_the_rise_follows_the_drafting_guideline():
    """ヒップ1cmあたりの深さの増え方が、目安(ヒップ/4)と一致すること。"""
    assert PANTS_RISE_PER_HIP_CM == pytest.approx(0.25)
    base = pants_rise_cm(25.0, 91, 1.0)
    assert pants_rise_cm(25.0, 120, 1.0) - base == pytest.approx(29 / 4.0)
    assert pants_rise_cm(25.0, 80, 1.0) - base == pytest.approx(-11 / 4.0)


def test_the_height_scale_still_applies_to_the_rise():
    assert pants_rise_cm(25.0, 91, 1.2) == pytest.approx(30.0)


def test_an_incomplete_declaration_produces_no_pants_map():
    """役割が足りない宣言では写像を作らず、一律倍率へ落ちること。"""
    assert build_pants_y_map([("waist", 0.0), ("hem", 96.0)], 91.0, 1.0) == []
    assert build_pants_y_map([], 91.0, 1.0) == []


@pytest.mark.parametrize("variation", PANTS_VARIATIONS)
def test_the_map_keeps_its_order_across_the_whole_valid_range(variation):
    """有効な採寸の全域で、節点の順序(ウエスト<股ぐり<裾)が崩れないこと。

    崩れると写像を作らずに一律倍率へ落ちる=股上の補正が静かに効かなく
    なるので、「どこでも効いている」ことを端から端まで確かめる。
    いちばん際どいのは、股上25cmを確保した最短丈のショーツである。
    """
    db = TemplateDB()
    anchors = db.get_fit_anchors_y("front_pants", variation)
    for hip in (50, 91, 170):
        for height_scale in (120 / 158, 1.0, 210 / 158):
            knots = build_pants_y_map(anchors, hip, height_scale)
            assert knots, (variation, hip, height_scale)
            ys = [dst for _src, dst in knots]
            assert ys == sorted(ys) and len(set(ys)) == 3, (variation, hip, height_scale)


@pytest.mark.parametrize("hip", HIPS)
def test_the_generated_rise_tracks_the_guideline(tmp_path, hip):
    """生成されたパンツの股上が、目安(ヒップ/4+2)どおりに深くなること。

    round24までは身長比だけで決まっていて、ヒップ120cmで目安より7cm浅かった
    (座れないどころか立っていても股が食い込む)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _pants(pipeline, hip)
    # テンプレートの股上25cmは目安(91/4+2=24.75)より0.25cm深い。その差を保つ。
    expected = hip / 4 + 2 + 0.25
    assert _measured_rise_cm(parts["front_pants"]) == pytest.approx(expected, abs=0.3), hip


@pytest.mark.parametrize("hip", HIPS)
def test_the_inseam_stays_driven_by_height(tmp_path, hip):
    """股下(股ぐり〜裾)は身長だけで決まり、ヒップでは変わらないこと。

    股下は脚の長さ、股上は体の厚み——別々の量なので、総丈は両者の和として
    変わる(身頃の着丈を固定したのとは事情が違う)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _pants(pipeline, hip)
    scaled = parts["front_pants"]
    _min_x, _min_y, _max_x, max_y = bounding_box(scaled.segments)
    _min_x2, min_y, _max_x2, _max_y2 = bounding_box(scaled.segments)
    inseam = (max_y - min_y) - _measured_rise_cm(scaled)
    assert inseam == pytest.approx(71.0, abs=0.3), hip


def test_the_standard_size_pants_are_unchanged(tmp_path):
    """標準Mのパンツは、round24までとまったく同じ寸法であること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _result, parts = _pants(pipeline, STANDARD_M.hip)
    scaled = parts["front_pants"]
    _min_x, min_y, _max_x, max_y = bounding_box(scaled.segments)
    assert _measured_rise_cm(scaled) == pytest.approx(25.0, abs=0.05)
    assert (max_y - min_y) == pytest.approx(96.0, abs=0.05)


@pytest.mark.parametrize("variation", PANTS_VARIATIONS)
def test_the_pants_outline_stays_valid_across_the_range(tmp_path, variation):
    """全丈×ヒップの両端で、輪郭が自己交差しないこと。

    ショーツは股上25cmを確保した最短丈(38cm)なので、股上を深くすると
    股ぐりが裾に迫る。そこが破綻しないことを実際に確かめる。
    """
    shapely = pytest.importorskip("shapely.geometry")

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for hip in (50, 91, 170):
        for height in (120, 158, 210):
            _result, parts = _pants(pipeline, hip, height, variation)
            for scaled in parts.values():
                polygon = shapely.Polygon(
                    segments_to_polyline(scaled.segments, curve_steps=120))
                assert polygon.is_valid, (variation, hip, height, scaled.part_type)
                assert polygon.area > 0


@pytest.mark.parametrize("hip", HIPS)
def test_the_waistband_still_fits_the_deeper_pants(tmp_path, hip):
    """股上を深くしても、ウエストバンドが合うこと。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("front_pants", "", 2),
                               PartRequest("back_pants", "", 2),
                               PartRequest("waistband", "", 1)])
    result = pipeline.generate_from_selection(
        spec, Measurements(83, hip * 0.72, hip, 158, 52, 37))
    assert [w.kind for w in result.compatibility_warnings()] == [], hip


# --- 二の腕まわり(任意採寸) -------------------------------------------------

def test_the_upper_arm_is_optional_and_omitted_from_the_dict():
    """未指定でも作れて、辞書には現れないこと。

    JSONや保存済みプロフィールにNoneが混ざると、受け手が「0cm」と誤って
    扱いうるため、項目ごと落とす。
    """
    without = Measurements(83, 66, 91, 158, 52, 37)
    assert without.upper_arm is None
    assert "upper_arm" not in without.as_dict()

    with_arm = Measurements(83, 66, 91, 158, 52, 37, upper_arm=27)
    assert with_arm.as_dict()["upper_arm"] == 27


def test_an_out_of_range_upper_arm_is_rejected():
    with pytest.raises(ValueError, match="upper_arm"):
        Measurements(83, 66, 91, 158, 52, 37, upper_arm=5)


def test_grading_keeps_the_upper_arm_unset_when_it_was_unset():
    """サイズ展開で、未指定の任意項目が0cmにならないこと。"""
    without = graded_measurements(Measurements(83, 66, 91, 158, 52, 37), "L")
    assert without.upper_arm is None
    with_arm = graded_measurements(
        Measurements(83, 66, 91, 158, 52, 37, upper_arm=27), "L")
    assert with_arm.upper_arm == pytest.approx(28.0)


def _sleeve_width_cm(pipeline, upper_arm=None, fit=None, bust=83):
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1),
                               PartRequest("sleeve", "straight", 2)])
    result = pipeline.generate_from_selection(
        spec, Measurements(bust, bust * 0.79, bust * 1.10, 158, 52, 37,
                            upper_arm=upper_arm), fit=fit)
    sleeve = next(p for p in result.scaled_parts if p.part_type == "sleeve")
    min_x, _min_y, max_x, _max_y = bounding_box(sleeve.segments)
    return max_x - min_x, result


@pytest.mark.parametrize("arm", [21, 27, 32, 41])
def test_the_sleeve_width_is_the_measured_arm_plus_ease(tmp_path, arm):
    """二の腕まわりを入れると、袖幅がその実測+ゆとりちょうどになること。

    round24までは袖ぐりから相似で決まっていて、腕の太さが体型比から
    外れている人には合わなかった。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    width, _result = _sleeve_width_cm(pipeline, upper_arm=arm)
    assert width == pytest.approx(arm + fit_ease(None).sleeve_cm, abs=0.1)


@pytest.mark.parametrize("fit", sorted(FIT_PRESETS))
def test_the_sleeve_ease_follows_the_fit(tmp_path, fit):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    width, _result = _sleeve_width_cm(pipeline, upper_arm=27, fit=fit)
    assert width == pytest.approx(27 + fit_ease(fit).sleeve_cm, abs=0.1)


def test_omitting_the_upper_arm_lets_the_armhole_decide_the_sleeve(tmp_path):
    """二の腕まわり未指定なら、袖幅は袖ぐりから決まること(round24の経路)。

    【round31で期待値を書き換えた理由】round30までこのテストは袖幅が
    31.70cmちょうどであることを確かめていた。round31で袖ぐりの点を
    新文化式の胸幅・背幅の位置へ合わせた結果、標準Mサイズの袖ぐりが
    片腕39.72cm→40.59cmになり、それに合わせて袖幅も32.82cmになった。
    **数字を合わせに行ったのではなく、袖ぐりが変わったぶんだけ袖が
    変わった**ことを確かめる形に直してある。凍らせた定数ではなく、
    「袖山カーブが実際の袖ぐり+いせに合っていること」という、この経路の
    本来の不変条件を測る(定数を書き換えるだけでは、袖が袖ぐりに合わなく
    なった場合にこのテストが何も守らなくなる)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    width, result = _sleeve_width_cm(pipeline)
    parts = {p.part_type: p for p in result.finalized_parts}
    per_arm = (armhole_length(parts["front_bodice"])
               + armhole_length(parts["back_bodice"])) / 2.0
    cap = sleeve_cap_length(parts["sleeve"])
    assert cap == pytest.approx(per_arm + sleeve_cap_ease_cm(per_arm),
                                abs=SLEEVE_FIT_TOLERANCE_CM * 2)
    # 実測の記録(この数字が動いたら、袖ぐりが動いたということ)。
    # round43で32.82→34.32へ更新。肩傾斜を製図の角度(前22°/後ろ18°)で
    # 引き直した結果、肩先が上がって袖ぐりが片腕1.16cm長くなった。
    # 袖は袖ぐりに合わせて作られるので、袖も1.5cm広くなる——
    # **袖ぐりが動いたから袖が動いた**のであって、数字を合わせに行ったのではない。
    assert width == pytest.approx(34.32, abs=0.1)


@pytest.mark.parametrize("bust,arm", [(60, 21), (83, 27), (83, 32), (110, 34), (130, 41)])
def test_the_arm_driven_sleeve_still_fits_the_armhole(tmp_path, bust, arm):
    """袖幅を腕で固定しても、袖山カーブが袖ぐりに合っていること。

    幅を腕で固定したぶん、袖ぐりに合わせるのは袖山の**高さ**になる
    (実際のパタンナーの手順もこの順序)。合わなければチェック5が警告する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _width, result = _sleeve_width_cm(pipeline, upper_arm=arm, bust=bust)
    kinds = [w.kind for w in result.compatibility_warnings()]
    assert "armhole_sleeve_cap" not in kinds, (bust, arm, kinds)


# --- ゆとりの数値指定 -------------------------------------------------------

def test_an_arm_too_thick_for_the_armhole_is_disclosed(tmp_path):
    """袖ぐりに対して腕が太すぎる場合、黙って縫えない袖を出さないこと。

    袖幅を腕で固定すると、袖ぐりに合わせられるのは袖山の高さだけになる。
    腕がバストに対して極端に太いと、袖山をいちばん低くしても袖山カーブが
    袖ぐりより長くなる。

    【round43で境目が動いた】肩傾斜を製図の角度で引き直して袖ぐりが
    片腕1.16cm長くなったぶん、**より太い腕が入るようになった**。実測
    (バスト83):

        二の腕36cm → 袖幅41.0cm  縫える
        二の腕40cm → 袖幅45.0cm  縫える  ← round42までは縫えなかった
        二の腕42cm → 袖幅47.0cm  袖山カーブが袖ぐりより長い

    見張りたいのは「入らないときに黙らないこと」なので、境目を追いかける。

    チェック5の文面はround14当時の理由(身頃と袖で採寸が別)のままなので、
    二の腕を入力したせいだと分かる注記を別に出す。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _width, ok_result = _sleeve_width_cm(pipeline, upper_arm=40)
    assert not [n for n in ok_result.measurement_warnings if "二の腕" in n]

    _width, bad_result = _sleeve_width_cm(pipeline, upper_arm=42)
    notes = [n for n in bad_result.measurement_warnings if "二の腕" in n]
    assert notes, bad_result.measurement_warnings
    assert "42" in notes[0] and "縫い付けられません" in notes[0]


def test_custom_ease_overrides_only_what_is_given():
    ease = custom_fit_ease(bodice_cm=11.5)
    standard = FIT_PRESETS[DEFAULT_FIT]
    assert ease.bodice_cm == 11.5
    assert ease.waist_cm == standard.waist_cm
    assert ease.hip_cm == standard.hip_cm
    assert ease.sleeve_cm == standard.sleeve_cm


def test_custom_ease_with_no_overrides_equals_the_default():
    ease = custom_fit_ease()
    standard = FIT_PRESETS[DEFAULT_FIT]
    for field in ("bodice_cm", "waist_cm", "hip_cm", "sleeve_cm"):
        assert getattr(ease, field) == getattr(standard, field), field


@pytest.mark.parametrize("field", sorted(CUSTOM_EASE_RANGES))
def test_out_of_range_custom_ease_is_rejected(field):
    lo, hi = CUSTOM_EASE_RANGES[field]
    with pytest.raises(ValueError, match="範囲"):
        custom_fit_ease(**{field: hi + 1})
    with pytest.raises(ValueError, match="範囲"):
        custom_fit_ease(**{field: lo - 1})


def test_an_unknown_ease_field_is_rejected():
    with pytest.raises(ValueError, match="ゆとりに指定できる項目"):
        custom_fit_ease(chest_cm=5)


def test_a_non_numeric_custom_ease_is_rejected():
    with pytest.raises(TypeError):
        custom_fit_ease(bodice_cm="ゆったり")


def test_a_custom_ease_object_can_be_passed_straight_through(tmp_path):
    """`FitEase`をそのまま`fit`に渡せて、実際に効くこと。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    ease = custom_fit_ease(bodice_cm=11.5)
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1)])
    result = pipeline.generate_from_selection(
        spec, Measurements(83, 66, 91, 158, 52, 37), fit=ease)
    girth = sum(bodice_width_at_bust_cm(p) for p in result.scaled_parts)
    assert girth == pytest.approx(83 + 11.5, abs=0.15)
    # round32: 「こう作りました」の説明は design_notes(青)へ分離した。
    assert any("11.5" in n for n in result.design_notes), result.design_notes


# --- Web側 -------------------------------------------------------------------

def test_the_form_offers_the_optional_upper_arm_and_custom_ease(client):
    page = client.get("/").get_data(as_text=True)
    assert 'name="upper_arm"' in page
    assert 'value="custom"' in page
    for field in ("ease_bodice", "ease_waist", "ease_hip", "ease_sleeve"):
        assert f'name="{field}"' in page, field


def _form(**extra):
    form = {
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "",
        "bust": "83", "waist": "66", "hip": "91",
        "height": "158", "sleeve_length": "52", "shoulder_width": "37",
    }
    form.update(extra)
    return form


def test_the_upper_arm_reaches_the_sleeve_through_the_web(client):
    def _sleeve_width(**extra):
        response = client.post("/api/generate", data=_form(**extra))
        assert response.status_code == 200, response.get_data(as_text=True)[:300]
        payload = response.get_json()
        assert payload["ok"], payload
        widths = [p["width_cm"] for p in payload["parts"]
                  if p["part_type"] == "sleeve"]
        assert widths
        return widths[0]

    assert _sleeve_width(upper_arm="40") > _sleeve_width() + 5.0


def test_a_custom_ease_through_the_web_widens_the_pattern(client):
    def _total(**extra):
        response = client.post("/api/generate", data=_form(**extra))
        assert response.status_code == 200, response.get_data(as_text=True)[:300]
        payload = response.get_json()
        assert payload["ok"], payload
        return sum(p["width_cm"] for p in payload["parts"]), payload

    standard, _p1 = _total()
    custom, payload = _total(fit="custom", ease_bodice="16")
    assert custom > standard + 4.0
    assert any("16" in w for w in payload["design_notes"])


def test_an_out_of_range_custom_ease_from_the_web_is_an_error(client):
    response = client.post("/api/generate",
                            data=_form(fit="custom", ease_bodice="99"))
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_a_bad_upper_arm_from_the_web_is_an_error(client):
    response = client.post("/api/generate", data=_form(upper_arm="3"))
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
