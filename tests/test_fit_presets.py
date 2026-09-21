"""round24: ゆとり(着方)を利用者が選べるようにする。

round23でゆとりを「体の大きさによらず一定」にしたが、その一定値は
テンプレートの設計値(身頃8cm / ウエスト2cm / ヒップ4cm)に固定で、
利用者は選べなかった。ゆとりは体型ではなく**着方の好み**で決まる量で、
衣装制作では特に効く(下に重ね着する、動きの大きい演目、逆に体の線を
出したい等)。
"""

import pytest

from tests.conftest import bodice_width_at_bust_cm

from engine.part_specs import (
    DEFAULT_FIT, FIT_PRESETS, LOWER_BASE_HIP_CM, LOWER_BASE_WAIST_CM,
    fit_ease, lower_garment_x_scale,
)
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import bounding_box

M = Measurements(83, 66, 91, 158, 52, 37)


def _bodice_girth_cm(pipeline, fit=None, measurements=M):
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1)])
    result = pipeline.generate_from_selection(spec, measurements, fit=fit)
    # round26: 外接矩形の幅は裾(ヒップ)の幅になったので、バストのゆとりは
    # バストの高さで測る(tests/conftest.py の bodice_width_at_bust_cm)。
    return sum(bodice_width_at_bust_cm(p) for p in result.scaled_parts), result


# --- プリセットの定義 -------------------------------------------------------

def test_the_default_preset_matches_the_template_design_values():
    """既定("standard")が、テンプレートの設計値そのままであること。

    ここがずれると、ゆとりを指定していない既存の利用者の型紙が黙って
    変わってしまう。
    """
    from engine.bodice_fit import BODICE_EASE_CM

    ease = fit_ease(DEFAULT_FIT)
    assert ease.bodice_cm == BODICE_EASE_CM
    assert ease.waist_cm == 2.0
    assert ease.hip_cm == 4.0


def test_the_presets_are_ordered_from_fitted_to_relaxed():
    """3つのプリセットが、どの項目でも一貫して大小関係を保つこと。"""
    fitted, standard, relaxed = (FIT_PRESETS["fitted"], FIT_PRESETS["standard"],
                                  FIT_PRESETS["relaxed"])
    for field in ("bodice_cm", "waist_cm", "hip_cm"):
        assert getattr(fitted, field) < getattr(standard, field) < getattr(relaxed, field), field


def test_an_unknown_fit_is_rejected_rather_than_silently_ignored():
    """未知の名前を黙って標準へ落とさないこと。

    落とすと、指定したつもりのゆとりが効いていないことに利用者は
    出来上がりを見るまで気付けない。
    """
    with pytest.raises(ValueError, match="fit は"):
        fit_ease("loose")
    assert fit_ease(None) is FIT_PRESETS[DEFAULT_FIT]


# --- 実際に生成される型紙 ---------------------------------------------------

@pytest.mark.parametrize("fit", sorted(FIT_PRESETS))
def test_the_finished_girth_is_bust_plus_the_chosen_ease(tmp_path, fit):
    """出来上がりの胴回りが「バスト + 選んだゆとり」になること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    girth, _result = _bodice_girth_cm(pipeline, fit)
    assert girth == pytest.approx(M.bust + fit_ease(fit).bodice_cm, abs=0.15)


def test_omitting_the_fit_is_identical_to_the_default(tmp_path):
    """指定しない場合が、既定を明示した場合とまったく同じであること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    without, _r1 = _bodice_girth_cm(pipeline, None)
    with_default, _r2 = _bodice_girth_cm(pipeline, DEFAULT_FIT)
    assert without == pytest.approx(with_default)


@pytest.mark.parametrize("fit", sorted(FIT_PRESETS))
def test_the_lower_garment_ease_follows_too(fit):
    """スカート・パンツのゆとりも連動すること。"""
    ease = fit_ease(fit)
    scale = lower_garment_x_scale(M.waist, M.hip, fit)
    assert (LOWER_BASE_WAIST_CM * scale >= M.waist + ease.waist_cm - 1e-6
            or LOWER_BASE_HIP_CM * scale >= M.hip + ease.hip_cm - 1e-6)
    # ゆとりが大きいほど幅も広い。
    assert scale >= lower_garment_x_scale(M.waist, M.hip, "fitted") - 1e-9


def test_a_non_default_fit_is_disclosed(tmp_path):
    """既定以外を選んだ場合、実際に使ったゆとりを開示すること。

    どのゆとりで作られたかは出来上がりの型紙を見ても分かりにくい。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    _girth, relaxed = _bodice_girth_cm(pipeline, "relaxed")
    # round32: 「こう作りました」という説明は、赤い警告ではなく
    # design_notes(青い「この型紙の作り方」)へ分離した。
    notes = [n for n in relaxed.design_notes if "ゆとり" in n]
    assert notes, relaxed.design_notes
    assert "14" in notes[0]

    _girth, default = _bodice_girth_cm(pipeline, DEFAULT_FIT)
    assert not [n for n in default.design_notes + default.measurement_warnings
                if "ゆとり" in n]


@pytest.mark.parametrize("fit", sorted(FIT_PRESETS))
def test_the_pattern_stays_sewable_for_every_fit(tmp_path, fit):
    """どのゆとりでも、縫い合わせの整合が崩れないこと。

    身頃の幅が変わると袖ぐりの長さも変わる。袖・衿・ウエストバンドは
    相手の実測に合わせて作られるので追随するはずで、そこを確かめる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("front_bodice", "round_neck", 1),
                               PartRequest("back_bodice", "round_neck", 1),
                               PartRequest("sleeve", "straight", 2),
                               PartRequest("collar", "", 1),
                               PartRequest("skirt", "flare", 2),
                               PartRequest("waistband", "", 1)])
    for bust in (60, 83, 110):
        result = pipeline.generate_from_selection(
            spec, Measurements(bust, bust * 0.79, bust * 1.10, 158, 52, 37), fit=fit)
        kinds = [w.kind for w in result.compatibility_warnings()]
        assert kinds == [], (fit, bust, kinds)


def test_the_clamp_warning_follows_the_chosen_ease():
    """クランプ境界の注記が、選んだゆとりに合わせて動くこと。

    ゆとりを変えると、同じ倍率に対応するバストも動く。注記だけ既定の
    ゆとりのままだと、実際には正しく生成できている値に嘘の説明が付く
    (round23で同じ種類の食い違いを実際に出した)。
    """
    from engine.bodice_fit import bodice_bust_cm_for_scale
    from engine.part_specs import MAX_SCALE
    from engine.scaling import measurement_clamp_warnings

    for fit in sorted(FIT_PRESETS):
        ease = fit_ease(fit).bodice_cm
        boundary = bodice_bust_cm_for_scale(MAX_SCALE, ease)
        inside = Measurements(boundary - 0.5, 66, 91, 158, 52, 37)
        outside = Measurements(boundary + 0.5, 66, 91, 158, 52, 37)
        assert not [w for w in measurement_clamp_warnings(inside, fit) if "バスト" in w], fit
        flagged = [w for w in measurement_clamp_warnings(outside, fit) if "バスト" in w]
        assert flagged, fit
        assert f"{boundary:.1f}" in flagged[0], (fit, flagged[0])


# --- Web側 -------------------------------------------------------------------

def test_the_form_offers_the_fit_choices(client):
    page = client.get("/").get_data(as_text=True)
    assert 'name="fit"' in page
    for key, preset in FIT_PRESETS.items():
        assert f'value="{key}"' in page, key
        assert preset.label in page, key


def test_choosing_relaxed_through_the_web_widens_the_pattern(client):
    """Webから「ゆったり」を選ぶと、実際に型紙が広くなること。"""
    def _post(fit):
        form = {
            "mode": "manual", "neckline": "round_neck",
            "sleeve_style": "", "skirt_style": "",
            "bust": "83", "waist": "66", "hip": "91",
            "height": "158", "sleeve_length": "52", "shoulder_width": "37",
        }
        if fit:
            form["fit"] = fit
        response = client.post("/api/generate", data=form)
        assert response.status_code == 200, response.get_data(as_text=True)[:300]
        payload = response.get_json()
        assert payload["ok"], payload
        return payload

    standard = _post(None)
    relaxed = _post("relaxed")
    width = lambda p: sum(x["width_cm"] for x in p["parts"])  # noqa: E731
    # round26以降、身頃の外接矩形の幅は**裾(ヒップ)の幅**になる。したがって
    # ここでの差は「ヒップのゆとりの差」(8-4=4cm)が主で、バストのゆとりの差
    # (14-8=6cm)ではない。バストのゆとりそのものは
    # test_the_finished_girth_is_bust_plus_the_chosen_ease が測っている。
    assert width(relaxed) >= width(standard) + 3.5
    assert any("ゆとり" in w for w in relaxed["design_notes"])
    assert not any("ゆとり" in w
                   for w in standard["design_notes"] + standard["measurement_warnings"])


def test_an_unknown_fit_from_the_web_is_an_error_not_a_silent_default(client):
    form = {
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "", "skirt_style": "", "fit": "loose",
        "bust": "83", "waist": "66", "hip": "91",
        "height": "158", "sleeve_length": "52", "shoulder_width": "37",
    }
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
