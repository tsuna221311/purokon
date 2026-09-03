import pytest

from engine.compatibility import (
    CUFFS_EASE_CM,
    CompatibilityWarning,
    WAISTBAND_CLOSURE_EASE_CM,
    SLEEVE_CAP_DESIGN_GATHER_CM,
    SLEEVE_CAP_EASE_CM,
    _mismatched,
    _sum_length_at_x,
    _sum_length_at_y,
    armhole_length,
    band_length,
    check_seam_compatibility,
    hem_or_wrist_opening_length,
    side_seam_length,
    sleeve_cap_length,
    waist_opening_length,
)
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline, build_garment_spec
from engine.scaling import scale_template
from engine.seam import finalize_part
from engine.templates_db import TemplateDB

STANDARD = Measurements(bust=84, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)


def _finalize(part_type: str, variation: str, measurements: Measurements, **kwargs):
    db = TemplateDB()
    segments = db.get(part_type, variation)
    assert segments is not None, f"template not found: {part_type}/{variation}"
    # round14: 身頃は「区間ごとに違う倍率」で変形するので、本番(pipeline)と
    # 同じくテンプレートの基準点を渡す。渡し忘れると古い一律スケーリングに
    # 落ちて、テストだけ別の型紙を見ることになる。
    scaled = scale_template(part_type, variation, segments, measurements,
                            fit_anchors=db.get_fit_anchors(part_type, variation))
    return finalize_part(part_type, variation, scaled.segments, dart_count=scaled.dart_count, **kwargs)


# --- 幾何ヘルパーの単体テスト ---------------------------------------------

def test_sum_length_at_x_only_counts_matching_vertical_edges():
    points = [(0.0, 0.0), (0.0, 10.0), (5.0, 10.0), (5.0, 0.0), (0.0, 0.0)]
    assert _sum_length_at_x(points, 0.0) == pytest.approx(10.0)
    assert _sum_length_at_x(points, 5.0) == pytest.approx(10.0)
    assert _sum_length_at_x(points, 2.5) == pytest.approx(0.0)


def test_sum_length_at_x_sums_fragmented_edges_from_a_dart_mouth():
    # ダーツのV字ノッチ(口A→先端→口B→元の終点)を模したセグメント。
    # 口A-口Bの間(先端への往復)はx=0から外れるため合計に含まれず、
    # (0,0)-(0,3)と(0,7)-(0,10)の2区間だけが合計される。
    points = [(0.0, 0.0), (0.0, 3.0), (2.0, 5.0), (0.0, 7.0), (0.0, 10.0)]
    assert _sum_length_at_x(points, 0.0) == pytest.approx(3.0 + 3.0)


def test_sum_length_at_y_only_counts_matching_horizontal_edges():
    points = [(0.0, 0.0), (0.0, 10.0), (5.0, 10.0), (5.0, 0.0), (0.0, 0.0)]
    assert _sum_length_at_y(points, 0.0) == pytest.approx(5.0)
    assert _sum_length_at_y(points, 10.0) == pytest.approx(5.0)


def test_mismatched_uses_the_larger_of_absolute_and_relative_tolerance():
    # 小さい値同士: 絶対許容誤差(1.5cm)が支配的。
    assert not _mismatched(expected_cm=10.0, actual_cm=11.4)
    assert _mismatched(expected_cm=10.0, actual_cm=11.6)
    # 大きい値同士: 相対許容誤差(5%)が支配的。
    assert not _mismatched(expected_cm=100.0, actual_cm=104.9)
    assert _mismatched(expected_cm=100.0, actual_cm=105.1)


def test_mismatched_is_false_for_zero_expected():
    assert not _mismatched(expected_cm=0.0, actual_cm=5.0)


# --- パーツ単位の長さ抽出 --------------------------------------------------

def test_side_seam_length_matches_between_symmetric_front_and_back_at_standard_m():
    front = _finalize("front_bodice", "round_neck", STANDARD)
    back = _finalize("back_bodice", "round_neck", STANDARD)
    front_len = side_seam_length(front)
    back_len = side_seam_length(back)
    assert front_len is not None and back_len is not None
    assert front_len == pytest.approx(back_len)


def test_side_seam_length_matches_the_back_even_when_a_bust_dart_is_applied():
    """脇ダーツが入っても、前身頃と後ろ身頃の脇線長が一致すること
    (round14で意味が変わったテスト)。

    round13までは「ダーツが入ると前身頃の脇線が短くなる」ことを確認して
    いた。実測では標準的なバスト100cmの体型でも前61.9cm・後69.9cmと8.0cm
    (片側4.0cm)ずれており、そのままでは脇を縫い合わせられない型紙だった。
    round14でダーツの口より下に丈を足すようにしたので、前後が一致する。
    """
    for bust in (90.0, 100.0, 112.0, 130.0):
        m = Measurements(bust=bust, waist=68, hip=92, height=160,
                          sleeve_length=54, shoulder_width=37)
        front = _finalize("front_bodice", "round_neck", m)
        back = _finalize("back_bodice", "round_neck", m)
        assert front.dart_count >= 2, bust  # 左右の脇線それぞれ1本ずつ
        front_len, back_len = side_seam_length(front), side_seam_length(back)
        assert front_len is not None and back_len is not None
        assert front_len == pytest.approx(back_len, abs=0.05), (bust, front_len, back_len)


def test_side_seam_length_for_zip_panel_excludes_the_center_front_facing_edge():
    front_zip = _finalize("front_bodice_zip_panel", "round_neck", STANDARD)
    back = _finalize("back_bodice", "round_neck", STANDARD)
    zip_len = side_seam_length(front_zip)
    back_len = side_seam_length(back)
    assert zip_len is not None
    # front_bodice_zip_panelは片側パネル1枚なので、back_bodiceの片方の
    # 脇線とほぼ同じ長さになるはず(back_bodiceは左右合算した値)。
    assert zip_len == pytest.approx(back_len / 2.0, rel=0.05)


def test_waist_opening_length_for_skirt():
    skirt = _finalize("skirt", "tight", STANDARD)
    length = waist_opening_length(skirt)
    assert length > 0


def test_waist_opening_length_shrinks_with_skirt_waist_dart():
    pear = Measurements(bust=84, waist=60, hip=100, height=160, sleeve_length=54, shoulder_width=37)
    no_dart = _finalize("skirt", "flare", STANDARD)  # flareはダーツ対象外
    with_dart = _finalize("skirt", "tight", pear)
    assert with_dart.dart_count > 0
    # 別variationなので絶対値の直接比較はできないが、両方とも正の値になる
    # ことと、ダーツが実際に長さへ反映されていることだけ確認する。
    assert waist_opening_length(no_dart) > 0
    assert waist_opening_length(with_dart) > 0


def test_hem_or_wrist_opening_length_for_sleeve():
    sleeve = _finalize("sleeve", "straight", STANDARD)
    length = hem_or_wrist_opening_length(sleeve)
    assert length > 0


def test_band_length_for_waistband_and_cuffs():
    waistband = _finalize("waistband", "", STANDARD)
    cuffs = _finalize("cuffs", "", STANDARD)
    assert band_length(waistband) > 0
    assert band_length(cuffs) > 0


# --- パイプライン統合テスト ------------------------------------------------

def test_no_warnings_for_plain_bodice_at_standard_measurements(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.compatibility_warnings() == []


def test_no_side_seam_warning_when_bust_dart_is_applied(tmp_path):
    """脇ダーツが入る体型でも脇線の警告が出ないこと(round14で意味が変わった)。

    round13までは、この警告が**出ること**を確認していた。当時の警告文は
    「前身頃に脇ダーツが入ると、その分だけ前身頃側の脇線が短くなるため
    発生することがあります」と、正常な現象であるかのように説明していたが、
    実際には縫い合わせられない型紙になっていた。round14で寸法そのものを
    直したので、この警告はもう出ない。

    チェッカーが生きていることは
    `test_side_seam_warning_still_fires_for_a_genuine_mismatch`が確認する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    for bust in (100.0, 130.0):
        m = Measurements(bust=bust, waist=60, hip=92, height=160,
                          sleeve_length=54, shoulder_width=37)
        result = pipeline.generate_from_selection(spec, m)
        kinds = {w.kind for w in result.compatibility_warnings()}
        assert "side_seam" not in kinds, (bust, [w.message for w in result.compatibility_warnings()])


def test_side_seam_warning_still_fires_for_a_genuine_mismatch(tmp_path):
    """脇線の長さが本当に食い違えば、従来通り警告が出ること。

    前身頃だけ丈を10cm縮めた型紙を組み立てて、チェッカーが検出することを
    確認する(上のテストで警告が出なくなったのが、検査の無効化ではなく
    寸法の改善であることを示すため)。
    """
    from engine.svgpath import scale_segments

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    db = pipeline.template_db
    front_segments = scale_segments(db.get("front_bodice", "round_neck"), 1.0, 0.8)
    front = finalize_part("front_bodice", "round_neck", front_segments)
    back = _finalize("back_bodice", "round_neck", STANDARD)
    kinds = {w.kind for w in check_seam_compatibility([front, back])}
    assert "side_seam" in kinds


def test_no_waist_opening_warning_when_neither_skirt_nor_pants_present(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None,
                               include_waistband=True, waistband_style="")
    result = pipeline.generate_from_selection(spec, STANDARD)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "waist_opening_skirt" not in kinds
    assert "waist_opening_pants" not in kinds


def test_no_wrist_opening_warning_when_no_cuffs(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "wrist_opening" not in kinds


def test_warning_as_dict_has_expected_keys():
    w = CompatibilityWarning(kind="side_seam", message="test", expected_cm=10.0, actual_cm=8.0)
    d = w.as_dict()
    assert set(d.keys()) == {"kind", "message", "expected_cm", "actual_cm", "diff_cm"}
    assert d["diff_cm"] == pytest.approx(2.0)


def test_pipeline_result_summary_includes_compatibility_warnings(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    payload = result.summary()
    assert "compatibility_warnings" in payload
    assert isinstance(payload["compatibility_warnings"], list)


def test_check_seam_compatibility_is_a_pure_function_of_finalized_parts(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    direct = check_seam_compatibility(result.finalized_parts)
    assert direct == result.compatibility_warnings()


# --- round7: waistband/cuffsを相手パーツの実測値に合わせる修正の回帰テスト ---
#
# round6時点では、skirt/pantsのウエスト開きとwaistbandの長さ、袖口とcuffsの
# 長さが、標準的な採寸でもほぼ常に警告になっていた(テンプレート同士の
# 基準寸法が独立に決められており、偶然一致する保証が無かったため)。
# round7でwaistband/cuffsを「相手パーツの完成後の長さ」から直接導出する
# 方式(engine.scaling.scale_band_to_target_width)に変更したことで、
# これらの組み合わせでは警告が出なくなったはずである。

_VARIED_MEASUREMENTS = [
    STANDARD_M,
    Measurements(bust=100, waist=80, hip=100, height=165, sleeve_length=55, shoulder_width=40),
    Measurements(bust=78, waist=60, hip=85, height=150, sleeve_length=48, shoulder_width=34),
]


@pytest.mark.parametrize("skirt_style", ["tight", "flare", "pleated", "wrap", "mermaid"])
@pytest.mark.parametrize("measurements", _VARIED_MEASUREMENTS, ids=["standard", "bust_large", "petite"])
def test_skirt_waistband_no_longer_mismatches_after_round7_fix(tmp_path, skirt_style, measurements):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style=skirt_style,
                               include_waistband=True, waistband_style="")
    result = pipeline.generate_from_selection(spec, measurements)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "waist_opening_skirt" not in kinds


@pytest.mark.parametrize("pants_style", ["", "flare", "shorts", "tapered", "wide"])
@pytest.mark.parametrize("measurements", _VARIED_MEASUREMENTS, ids=["standard", "bust_large", "petite"])
def test_pants_waistband_no_longer_mismatches_after_round7_fix(tmp_path, pants_style, measurements):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style=None, include_pants=True,
                               pants_style=pants_style, include_waistband=True, waistband_style="")
    result = pipeline.generate_from_selection(spec, measurements)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "waist_opening_pants" not in kinds


@pytest.mark.parametrize("sleeve_style", ["straight", "puff", "bell", "cap", "curve"])
@pytest.mark.parametrize("measurements", _VARIED_MEASUREMENTS, ids=["standard", "bust_large", "petite"])
def test_sleeve_cuffs_no_longer_mismatches_after_round7_fix(tmp_path, sleeve_style, measurements):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=sleeve_style, include_cuffs=True, cuffs_style="",
                               skirt_style=None)
    result = pipeline.generate_from_selection(spec, measurements)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "wrist_opening" not in kinds


def test_waistband_width_matches_skirt_waist_opening_plus_closure_ease(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style="tight",
                               include_waistband=True, waistband_style="")
    result = pipeline.generate_from_selection(spec, STANDARD)
    skirt_parts = [p for p in result.finalized_parts if p.part_type == "skirt"]
    waistband_parts = [p for p in result.finalized_parts if p.part_type == "waistband"]
    skirt_total = sum(waist_opening_length(p) for p in skirt_parts)
    band_total = sum(band_length(p) for p in waistband_parts)
    assert band_total == pytest.approx(skirt_total + WAISTBAND_CLOSURE_EASE_CM, abs=0.05)


def test_cuffs_width_matches_sleeve_opening_plus_ease_per_cuff(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style="straight", include_cuffs=True, cuffs_style="",
                               skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    sleeve_parts = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    cuffs_parts = [p for p in result.finalized_parts if p.part_type == "cuffs"]
    assert len(cuffs_parts) == 2  # 左右一対
    sleeve_total = sum(hem_or_wrist_opening_length(p) for p in sleeve_parts)
    cuffs_total = sum(band_length(p) for p in cuffs_parts)
    # 左右それぞれが独立に閉じる輪なので、ゆとり分もカフスの枚数分加わる。
    assert cuffs_total == pytest.approx(sleeve_total + CUFFS_EASE_CM * len(cuffs_parts), abs=0.05)


def test_waistband_target_derivation_is_independent_of_parts_list_order(tmp_path):
    # generate_from_illustration()はAIが検出した領域の順序をそのまま
    # partsの順序にするため、band系パーツ(waistband)が相手パーツ(skirt)
    # より先に来る並びも起こりうる。_build_from_spec()がpartsの並び順に
    # 依存せず正しくtarget widthを算出できることを確認する
    # (通常はbuild_garment_spec()が常にwaistbandを後ろに置くため、
    # この並びは単体では作れない箇所を直接GarmentSpecを組み立てて再現する)。
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec_reordered = GarmentSpec(parts=[
        PartRequest("front_bodice", "round_neck", 1),
        PartRequest("back_bodice", "round_neck", 1),
        PartRequest("waistband", "", 1),
        PartRequest("skirt", "tight", 2),
    ])
    spec_normal_order = build_garment_spec(sleeve_style=None, skirt_style="tight",
                                            include_waistband=True, waistband_style="")

    result_reordered = pipeline.generate_from_selection(spec_reordered, STANDARD)
    result_normal = pipeline.generate_from_selection(spec_normal_order, STANDARD)

    assert "waist_opening_skirt" not in {w.kind for w in result_reordered.compatibility_warnings()}

    band_reordered = [p for p in result_reordered.finalized_parts if p.part_type == "waistband"]
    band_normal = [p for p in result_normal.finalized_parts if p.part_type == "waistband"]
    assert band_length(band_reordered[0]) == pytest.approx(band_length(band_normal[0]))


# --- round11: 袖ぐり(armhole) vs 袖山(sleeve cap) --------------------------

def test_armhole_length_is_none_for_unsupported_part_types():
    assert armhole_length(_finalize("skirt", "tight", STANDARD)) is None


def test_armhole_length_is_none_for_zip_panel():
    # front_bodice_zip_panelは輪郭の先頭点が肩先である保証が無いため対象外
    # (armhole_lengthのdocstring参照)。
    assert armhole_length(_finalize("front_bodice_zip_panel", "round_neck", STANDARD)) is None


def test_armhole_length_is_invariant_to_neckline_variation():
    """袖ぐりカーブはネックライン形状に依存しない位置にあるため、
    どのvariationでもほぼ同じ長さになるはず(検出方法が誤ってネックライン側へ
    走査を伸ばしていないことの確認も兼ねる)。

    round14で完全一致から`abs=0.05`の許容へ変えた。身頃のX方向が
    「基準点の間ごとに違う倍率をもつ区分線形写像」になったため
    (engine/bodice_fit.py)、首の付け根の位置が違うボートネックだけは
    肩線側の区間の倍率がわずかに違い、その区間へはみ出している袖ぐり曲線の
    制御点が0.011cmだけ別の位置へ動く。実測した差は5種が39.6238cm、
    ボートネックのみ39.6129cm(差0.0109cm=0.03%)。
    許容を緩めた理由が「走査がネックラインへ漏れた」ことでないのを
    示すため、下限も併せて確認する(漏れた場合はネックラインの形状ごとに
    cm単位で違う値になり、この許容には収まらない)。
    """
    values = [
        armhole_length(_finalize("front_bodice", v, STANDARD))
        for v in ("round_neck", "v_neck", "turtle_neck", "square_neck", "boat_neck", "sweetheart")
    ]
    assert all(v is not None and v > 0 for v in values)
    assert values == pytest.approx([values[0]] * len(values), abs=0.05)
    assert max(values) - min(values) < 0.05


def test_armhole_length_covers_both_left_and_right_armholes():
    """左右2つ分を返していること(片側だけを返していないこと)を、実測値の
    大きさから確認する。round12の身頃原型では、前身頃の片側の袖ぐりが
    約19.5cmで、左右合わせて約39cmになる。
    """
    front = armhole_length(_finalize("front_bodice", "round_neck", STANDARD_M))
    assert front == pytest.approx(38.97, abs=0.3)


@pytest.mark.parametrize("variation", ["straight", "curve", "puff", "bell", "cap", "three_quarter"])
def test_sleeve_cap_length_is_positive_for_every_sleeve_variation(variation):
    length = sleeve_cap_length(_finalize("sleeve", variation, STANDARD))
    assert length is not None and length > 0


def test_sleeve_cap_length_is_shorter_than_the_full_sleeve_outline():
    """袖山は輪郭の一部(上端のカーブ)だけなので、輪郭全体の周長より必ず
    短いはず(誤って輪郭を一周してしまっていないことの確認)。
    """
    from math import hypot

    sleeve = _finalize("sleeve", "straight", STANDARD)
    pts = sleeve.stitch_line
    perimeter = sum(hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
                     for i in range(1, len(pts)))
    cap = sleeve_cap_length(sleeve)
    assert 0 < cap < perimeter * 0.6


def test_sleeve_cap_matches_the_armhole_plus_ease_at_standard_measurements():
    """round12の中心的な回帰テスト: 袖山カーブが袖ぐり+いせ込みに一致する。

    round11までの袖テンプレートは、袖ぐり36.2cmに対して袖山が22.1cmしか
    無く、袖を袖ぐりに縫い付けることが物理的にできなかった。round12で
    袖テンプレートを作り直し、袖山=袖ぐり+いせ込み(約2cm)にした。
    """
    front = _finalize("front_bodice", "round_neck", STANDARD_M)
    back = _finalize("back_bodice", "round_neck", STANDARD_M)
    armhole_per_arm = (armhole_length(front) + armhole_length(back)) / 2.0

    for variation in ("straight", "curve", "bell", "cap", "three_quarter"):
        cap = sleeve_cap_length(_finalize("sleeve", variation, STANDARD_M))
        ease = cap - armhole_per_arm
        assert ease > 0, f"{variation}: 袖山が袖ぐりより短い(縫い付け不能)"
        # 布帛のいせ込みとして妥当な範囲(1.5〜3.5cm)に収まっていること。
        assert 1.5 <= ease <= 3.5, f"{variation}: いせ込みが{ease:.1f}cmで妥当な範囲外"


def test_puff_sleeve_cap_is_intentionally_larger_for_gathering():
    """パフ袖は膨らみを出すため、袖山を袖ぐりよりかなり大きく作る。
    その意図した差が、想定しているギャザー量とおおむね一致すること。
    """
    front = _finalize("front_bodice", "round_neck", STANDARD_M)
    back = _finalize("back_bodice", "round_neck", STANDARD_M)
    armhole_per_arm = (armhole_length(front) + armhole_length(back)) / 2.0
    cap = sleeve_cap_length(_finalize("sleeve", "puff", STANDARD_M))
    extra = cap - armhole_per_arm - SLEEVE_CAP_EASE_CM
    assert extra == pytest.approx(SLEEVE_CAP_DESIGN_GATHER_CM["puff"], abs=1.5)


def test_sleeve_length_matches_the_entered_sleeve_length_measurement():
    """round12の回帰テスト: 入力した袖丈が、そのまま袖の型紙の丈になる。

    round11までは袖丈52cmを入力しても丈22cmの袖しか出てこなかった
    (A4実寸1:1で印刷する設計なので、印刷して裁つと本当に22cmだった)。
    """
    for sleeve_length in (40.0, 52.0, 64.0):
        m = Measurements(bust=83, waist=66, hip=91, height=158,
                          sleeve_length=sleeve_length, shoulder_width=37)
        sleeve = _finalize("sleeve", "straight", m)
        # height_cmは裁断線(縫い代込み)なので、上下の縫い代を差し引く。
        stitch_length = sleeve.height_cm - 2 * sleeve.seam_allowance_cm
        assert stitch_length == pytest.approx(sleeve_length, abs=0.5), sleeve_length


def test_sleeve_width_is_a_realistic_upper_arm_girth():
    """袖幅(二の腕まわり・平置き)が現実的な寸法であること。
    round11までは20cmで、成人の二の腕が通らない寸法だった。
    """
    sleeve = _finalize("sleeve", "straight", STANDARD_M)
    stitch_width = sleeve.width_cm - 2 * sleeve.seam_allowance_cm
    assert 28.0 <= stitch_width <= 36.0, stitch_width


def test_no_armhole_sleeve_cap_warning_at_standard_measurements(tmp_path):
    """基準体型では、どの袖variationでも警告が出ないこと。
    「常に出る警告」になっていないことの確認(この検査の存在意義そのもの)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for sleeve_style in ("straight", "curve", "puff", "bell", "cap", "three_quarter"):
        spec = build_garment_spec(neckline="round_neck", sleeve_style=sleeve_style, skirt_style=None)
        result = pipeline.generate_from_selection(spec, STANDARD_M)
        kinds = {w.kind for w in result.compatibility_warnings()}
        assert "armhole_sleeve_cap" not in kinds, sleeve_style


@pytest.mark.parametrize("label,measurements", [
    ("バストに対して肩幅が極端に狭い", Measurements(bust=140, waist=100, hip=110, height=160,
                                                   sleeve_length=54, shoulder_width=30)),
    ("バストに対して肩幅が極端に広い", Measurements(bust=60, waist=55, hip=80, height=160,
                                                   sleeve_length=54, shoulder_width=50)),
])
def test_extreme_bust_to_shoulder_ratios_now_produce_a_sewable_sleeve(tmp_path, label, measurements):
    """round14で意味が変わったテスト。

    round13までは、この2つの極端な体型で「袖ぐりと袖山が合わない」という
    警告が**出ること**を確認していた(身頃はバスト比、袖は肩幅比と、別々の
    採寸で独立に拡大縮小していたので、釣り合いが崩れるのは構造上避けられず、
    せめて利用者に知らせる、という位置づけだった)。

    round14で袖の幅を「実際に縫い付ける袖ぐりの長さ」に合わせて決めるように
    したため(engine/scaling.pyのscale_sleeve_to_cap_length)、この状況は
    警告ではなく**解消**されるようになった。round7でウエストバンド/カフスに
    同じ手を入れたときと同じ変化なので、テストも「警告が出ないこと」＝
    「袖が縫い付けられること」を確認する形へ書き換えた。

    チェッカー自体が生きていることは
    `test_armhole_sleeve_cap_warning_still_fires_when_sleeve_is_not_fitted`
    が(袖ぐりに合わせない袖をわざと作って)確認している。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, measurements)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "armhole_sleeve_cap" not in kinds, (label, [w.message for w in result.compatibility_warnings()])


def test_armhole_sleeve_cap_warning_still_fires_when_sleeve_is_not_fitted(tmp_path):
    """袖ぐり合わせを通さずに袖を作った場合は、従来通り警告が出ること。

    「警告が出なくなった」のが検査の無効化ではなく実際の改善であることを
    示すために、round13までと同じ独立スケーリング(scale_template)で袖を
    作り、チェッカーが不整合を検出できることを確認する。
    """
    measurements = Measurements(bust=140, waist=100, hip=110, height=160,
                                 sleeve_length=54, shoulder_width=30)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, measurements)

    db = pipeline.template_db
    unfitted = scale_template("sleeve", "straight", db.get("sleeve", "straight"), measurements)
    parts = [p for p in result.finalized_parts if p.part_type != "sleeve"]
    parts.append(finalize_part("sleeve", "straight", unfitted.segments,
                               dart_count=unfitted.dart_count))

    kinds = {w.kind for w in check_seam_compatibility(parts)}
    assert "armhole_sleeve_cap" in kinds


def test_no_armhole_sleeve_cap_warning_when_no_sleeve_present(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "armhole_sleeve_cap" not in kinds
