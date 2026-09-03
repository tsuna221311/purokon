import pytest

from engine.darts import (
    apply_bust_dart,
    apply_pants_waist_dart,
    apply_skirt_waist_dart,
    apply_waist_dart,
    compute_bust_dart_intake_cm,
    compute_dart_plan,
    compute_pants_dart_plan,
    compute_skirt_dart_plan,
)
from engine.measurements import Measurements, STANDARD_M, _VALID_RANGES
from engine.scaling import scale_template
from engine.seam import finalize_part
from engine.svgpath import segments_to_polyline
from engine.templates_db import TemplateDB


def test_standard_m_gets_no_dart():
    # 標準Mサイズ(バスト-ウエスト比が標準どおり)では、ダーツで摘む理由が無い。
    plan = compute_dart_plan("front_bodice", scaled_half_width_cm=15.0, measurements=STANDARD_M)
    assert plan.is_empty()


def test_moderate_hourglass_gets_one_dart_per_half():
    # 設計時の手計算: bust=100/waist=66 -> 半身あたり約2.07cmの摘み量(1本)。
    m = Measurements(bust=100, waist=66, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_dart_plan("front_bodice", scaled_half_width_cm=15.0 * (100 / 83.0), measurements=m)
    assert plan.darts_per_half == 1
    assert plan.intake_per_dart_cm == pytest.approx(2.07, abs=0.05)


def test_extreme_hourglass_gets_two_darts_per_half():
    # bust=110/waist=60 -> 手計算では半身あたり約5.24cmだが、暴走防止の
    # MAX_DART_INTAKE_PER_HALF_CM(5.0cm)でクランプされ、1本(上限2.5cm)を
    # 超えるため2本に分割される。
    m = Measurements(bust=110, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_dart_plan("front_bodice", scaled_half_width_cm=15.0 * (110 / 83.0), measurements=m)
    assert plan.darts_per_half == 2
    assert plan.intake_per_dart_cm * 2 == pytest.approx(5.0, abs=0.05)


def test_waist_wider_than_bust_ratio_gets_no_dart():
    # ウエストの方が(比率換算で)太い場合はそもそも摘む必要が無い。
    m = Measurements(bust=50, waist=150, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_dart_plan("front_bodice", scaled_half_width_cm=10.0, measurements=m)
    assert plan.is_empty()


def test_non_bodice_part_types_never_get_a_dart():
    for part_type in ("sleeve", "skirt", "front_pants", "back_pants", "collar", "cuffs", "waistband"):
        m = Measurements(bust=140, waist=45, hip=92, height=160, sleeve_length=54, shoulder_width=37)
        plan = compute_dart_plan(part_type, scaled_half_width_cm=15.0, measurements=m)
        assert plan.is_empty()


def test_apply_waist_dart_produces_valid_non_self_intersecting_polygon():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    m = Measurements(bust=110, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors
    rx, ry = compute_scale_factors(m, "front_bodice")
    scaled = scale_segments(segments, rx, ry)

    new_segments, dart_count = apply_waist_dart("front_bodice", scaled, m)
    assert dart_count > 0

    poly_points = segments_to_polyline(new_segments)
    closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
    assert Polygon(closed).is_valid


def test_apply_waist_dart_works_regardless_of_hem_segment_drawing_direction():
    """round33で発見・修正した実バグの回帰テスト。

    `apply_waist_dart`の安全確認(クリアランスチェック)は、以前は裾の
    Lセグメントが「開始点のx座標 < 終了点のx座標」(=左から右へ描かれて
    いる)ことを暗黙に仮定していた。同梱の全テンプレート
    (pattern_templates/*bodice*.svg)は実際にすべて左→右方向で裾を描いて
    いるため現状は問題にならないが、幾何的には全く同じ形状で裾だけを
    右→左に描いた合成テンプレートで試したところ、本来追加されるべき
    ウエストダーツが無条件に無効化される(線形スケーリングのみへ静かに
    フォールバックしてしまう)ことを確認した。min/maxで裾の左端・右端を
    明示的に求めるよう修正し、向きに関わらず同じダーツ本数・同じ配置
    (裾ラインのx座標の集合)になることを確認した。
    """
    segments_ltr = [
        ("M", [8, 0.0]), ("L", [3, 8.0]), ("L", [0, 14.0]), ("L", [0, 60.0]),
        ("L", [30, 60.0]), ("L", [30, 14.0]), ("L", [27, 8.0]), ("L", [8, 0.0]),
    ]
    # 上と幾何的には同じ形状だが、裾(y=60)だけを右(x=30)→左(x=0)に描く。
    segments_rtl = [
        ("M", [22, 0.0]), ("L", [27, 8.0]), ("L", [30, 14.0]), ("L", [30, 60.0]),
        ("L", [0, 60.0]), ("L", [0, 14.0]), ("L", [3, 8.0]), ("L", [22, 0.0]),
    ]
    m = Measurements(bust=100.0, waist=64.0, hip=92.0, height=160.0,
                      sleeve_length=54.0, shoulder_width=37.0)

    new_ltr, count_ltr = apply_waist_dart("front_bodice", segments_ltr, m)
    new_rtl, count_rtl = apply_waist_dart("front_bodice", segments_rtl, m)

    assert count_ltr > 0  # このテスト自体がダーツを発火させていなければ意味が無い
    assert count_ltr == count_rtl

    def _hem_x_coords(segs):
        return sorted(round(x, 3) for cmd, (x, y) in segs if cmd == "L" and abs(y - 60.0) < 1e-6)

    assert _hem_x_coords(new_ltr) == _hem_x_coords(new_rtl)


def test_apply_waist_dart_is_valid_across_full_measurement_range():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    bust_lo, bust_hi = _VALID_RANGES["bust"]
    waist_lo, waist_hi = _VALID_RANGES["waist"]

    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    checked_with_dart = 0
    bust = bust_lo
    while bust <= bust_hi:
        waist = waist_lo
        while waist <= waist_hi:
            m = Measurements(bust=bust, waist=waist, hip=92, height=160,
                              sleeve_length=54, shoulder_width=37)
            rx, ry = compute_scale_factors(m, "front_bodice")
            scaled = scale_segments(segments, rx, ry)
            new_segments, dart_count = apply_waist_dart("front_bodice", scaled, m)
            if dart_count:
                checked_with_dart += 1
                poly_points = segments_to_polyline(new_segments)
                closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
                assert Polygon(closed).is_valid, f"invalid polygon at bust={bust}, waist={waist}"
            waist += 10
        bust += 10
    assert checked_with_dart > 0  # このテスト自体がダーツを1回も発火させていなければ意味が無い


def test_finalize_part_reports_dart_count_in_display_name():
    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    m = Measurements(bust=110, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    scaled = scale_template("front_bodice", "round_neck", segments, m)
    finalized = finalize_part("front_bodice", "round_neck", scaled.segments,
                               dart_count=scaled.dart_count)
    assert finalized.dart_count > 0
    assert "ダーツ" in finalized.display_name


def test_pipeline_reports_darts_applied_for_hourglass_measurements(tmp_path):
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    hourglass = Measurements(bust=110, waist=60, hip=92, height=160,
                              sleeve_length=54, shoulder_width=37)
    result = pipeline.generate_from_selection(spec, hourglass)
    summary = result.summary()
    assert summary["darts_applied"] > 0
    assert result.nesting.unplaced == []


# --- 脇ダーツ(apply_bust_dart) ------------------------------------------


def test_standard_m_gets_no_bust_dart():
    assert compute_bust_dart_intake_cm(STANDARD_M) == 0.0


def test_larger_than_standard_bust_gets_a_bust_dart():
    m = Measurements(bust=110, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    intake = compute_bust_dart_intake_cm(m)
    assert intake > 0
    # (110-83)*0.10 = 2.7cm、上限3.0cm未満なのでクランプされない想定。
    assert intake == pytest.approx(2.7, abs=0.05)


def test_bust_dart_is_clamped_for_extreme_bust():
    m = Measurements(bust=150, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    intake = compute_bust_dart_intake_cm(m)
    assert intake == pytest.approx(3.0, abs=1e-6)


def test_bust_dart_does_not_apply_to_unrelated_part_types():
    # round6でfront_bodice_zip_panelも対象に加わったため、その他のpart_type
    # では引き続きダーツが追加されないことを確認する。
    m = Measurements(bust=110, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    db = TemplateDB()
    for part_type in ("back_bodice", "sleeve", "skirt", "front_pants", "back_pants", "collar", "cuffs", "waistband"):
        segments = db.get(part_type, "round_neck" if part_type == "back_bodice" else "")
        if segments is None:
            continue
        _, count = apply_bust_dart(part_type, segments, m)
        assert count == 0


def test_apply_bust_dart_produces_valid_non_self_intersecting_polygon():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    m = Measurements(bust=115, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors
    rx, ry = compute_scale_factors(m, "front_bodice")
    scaled = scale_segments(segments, rx, ry)

    new_segments, dart_count = apply_bust_dart("front_bodice", scaled, m)
    assert dart_count == 2  # 左右の脇線それぞれ1本ずつ

    poly_points = segments_to_polyline(new_segments)
    closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
    assert Polygon(closed).is_valid


def test_apply_bust_dart_works_regardless_of_side_seam_drawing_direction():
    """apply_waist_dartの裾方向バグと同種の問題が脇線側で起きないことの回帰テスト。

    脇線は前身頃の実テンプレートでは片方が上→下、もう片方が下→上に
    描かれている（_bodice_pathの実装参照）。ここでは意図的に両方の脇線を
    それぞれ逆方向に描いた合成テンプレートでも、同じダーツ本数・同じ位置
    (脇線のx座標に現れるtipのx座標の集合)になることを確認する。
    """
    # 幅30, 中心x=15。左脇線 x=0、右脇線 x=30。y=10(袖付け)〜y=50(裾)。
    segments_a = [
        ("M", [8, 0.0]),
        ("L", [0, 10.0]),   # 左肩付け根 -> 左脇線開始点
        ("L", [0, 50.0]),   # 左脇線: 上->下
        ("L", [30, 50.0]),  # 裾
        ("L", [30, 10.0]),  # 右脇線: 下->上
        ("L", [22, 0.0]),
        ("L", [8, 0.0]),
    ]
    segments_b = [
        ("M", [8, 0.0]),
        ("L", [0, 50.0]),   # 左脇線: いきなり裾側から始まる合成パス
        ("L", [0, 10.0]),   # 左脇線: 下->上 (aとは逆向き)
        ("L", [30, 10.0]),
        ("L", [30, 50.0]),  # 右脇線: 上->下 (aとは逆向き)
        ("L", [22, 0.0]),
        ("L", [8, 0.0]),
    ]
    m = Measurements(bust=115.0, waist=68.0, hip=92.0, height=160.0,
                      sleeve_length=54.0, shoulder_width=37.0)

    new_a, count_a = apply_bust_dart("front_bodice", segments_a, m)
    new_b, count_b = apply_bust_dart("front_bodice", segments_b, m)

    assert count_a == 2  # このテスト自体がダーツを発火させていなければ意味が無い
    assert count_a == count_b

    def _tip_xs(segs):
        return sorted(round(x, 3) for cmd, (x, y) in segs
                      if cmd == "L" and 0.0 < x < 30.0)

    assert _tip_xs(new_a) == _tip_xs(new_b)


def test_apply_bust_dart_tip_moves_toward_estimated_bust_apex_as_intake_grows():
    """round5改良の回帰テスト: ダーツ先端が単純な水平移動ではなく、推定BP
    (バスト頂点)へ向かう方向に、摘み量が大きいほど近づくことを確認する。

    合成テンプレート: 幅30, 中心x=15。左脇線 x=0(y=10〜50)、右脇線 x=30。
    BUST_APEX_OFFSET_RATIO=0.45なので、右脇線側のBP推定x座標は
    15 + 15*0.45 = 21.75、左脇線側は 15 - 15*0.45 = 8.25。
    """
    from engine.darts import BUST_APEX_OFFSET_RATIO

    segments = [
        ("M", [8, 0.0]),
        ("L", [0, 10.0]),
        ("L", [0, 50.0]),
        ("L", [30, 50.0]),
        ("L", [30, 10.0]),
        ("L", [22, 0.0]),
        ("L", [8, 0.0]),
    ]
    expected_bp_x_right = 15 + 15 * BUST_APEX_OFFSET_RATIO
    expected_bp_x_left = 15 - 15 * BUST_APEX_OFFSET_RATIO

    def _tip_xs_near_seam(new_segments):
        # x=0/x=30(脇線そのもの)を除き、かつy=0(肩・襟ぐり側の点)も除いた、
        # ダーツ先端(脇線のy範囲10〜50の内側)のx座標だけを抜き出す。
        return sorted(x for cmd, (x, y) in new_segments
                      if cmd == "L" and 0.0 < x < 30.0 and 10.0 < y < 50.0)

    # バストがわずかに標準を超える(摘み量が小さい)場合。
    m_small = Measurements(bust=90.0, waist=68.0, hip=92.0, height=160.0,
                            sleeve_length=54.0, shoulder_width=37.0)
    new_small, count_small = apply_bust_dart("front_bodice", segments, m_small)
    assert count_small == 2
    tips_small = _tip_xs_near_seam(new_small)

    # バストが大きく標準を超える(摘み量がクランプ上限に近い)場合。
    m_large = Measurements(bust=150.0, waist=68.0, hip=92.0, height=160.0,
                            sleeve_length=54.0, shoulder_width=37.0)
    new_large, count_large = apply_bust_dart("front_bodice", segments, m_large)
    assert count_large == 2
    tips_large = _tip_xs_near_seam(new_large)

    # 左脇線側(x0=0)のtipはBP(8.25)方向、右脇線側(x0=30)のtipはBP(21.75)
    # 方向へ向かう。摘み量が大きいほどBPに近づく、すなわち左側のtipは
    # より大きく(0に近づく)、右側のtipはより小さく(30に近づく)動く…では
    # なく、両者ともBPの方向(内側)へ深く入り込むはず。左側は0→8.25方向
    # (x増加)、右側は30→21.75方向(x減少)なので、それぞれの深さが
    # 摘み量とともに増えることを確認する。
    left_small, right_small = tips_small[0], tips_small[1]
    left_large, right_large = tips_large[0], tips_large[1]

    assert left_large > left_small, "摘み量が増えても左側のtipがBP方向へ深く入っていない"
    assert right_large < right_small, "摘み量が増えても右側のtipがBP方向へ深く入っていない"

    # どちらのtipも、推定BPのx座標を超えて(通り越して)いないこと
    # (BPそのものには到達させない設計であることの確認)。
    assert left_small < expected_bp_x_left
    assert left_large < expected_bp_x_left
    assert right_small > expected_bp_x_right
    assert right_large > expected_bp_x_right


def test_apply_bust_dart_is_valid_across_full_measurement_range():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    bust_lo, bust_hi = _VALID_RANGES["bust"]
    waist_lo, waist_hi = _VALID_RANGES["waist"]

    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    checked_with_dart = 0
    bust = bust_lo
    while bust <= bust_hi:
        waist = waist_lo
        while waist <= waist_hi:
            m = Measurements(bust=bust, waist=waist, hip=92, height=160,
                              sleeve_length=54, shoulder_width=37)
            rx, ry = compute_scale_factors(m, "front_bodice")
            scaled = scale_segments(segments, rx, ry)
            new_segments, dart_count = apply_bust_dart("front_bodice", scaled, m)
            if dart_count:
                checked_with_dart += 1
                poly_points = segments_to_polyline(new_segments)
                closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
                assert Polygon(closed).is_valid, f"invalid polygon at bust={bust}, waist={waist}"
            waist += 10
        bust += 10
    assert checked_with_dart > 0


def test_scale_template_sums_waist_and_bust_dart_counts():
    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    m = Measurements(bust=110, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    scaled = scale_template("front_bodice", "round_neck", segments, m)
    assert scaled.dart_count > 0


# --- round6: front_bodice_zip_panelへのバストダーツ対応 -------------------

def test_apply_bust_dart_does_not_swallow_the_remaining_side_seam_run():
    """round6で修正した不具合の回帰テスト: ダーツ挿入後も、脇線の
    「ダーツの口から元の終点まで」の区間が消失せず残っていること。

    ダーツ挿入前は脇線が1本のLセグメントだったのに対し、挿入後は
    (口A, 先端, 口B, 元の終点)の4点になる。この最後の点が元の終点と
    一致していないと、後続のセグメント(袖ぐりカーブ等)が誤った位置から
    描画されてしまう。
    """
    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    m = Measurements(bust=130, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    from engine.darts import _find_side_seam_segment_indices
    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    rx, ry = compute_scale_factors(m, "front_bodice")
    scaled = scale_segments(segments, rx, ry)
    side_indices = _find_side_seam_segment_indices(scaled)
    original_ends = {i: (scaled[i][1][0], scaled[i][1][1]) for i in side_indices}

    new_segments, count = apply_bust_dart("front_bodice", scaled, m)
    assert count == 2

    # 差し替えで挿入された各4点ブロックの最後の点が、元のセグメントの
    # 終点と一致していることを確認する(挿入によりインデックスがずれるため、
    # 元の終点の座標そのもので探す)。
    # round14で、ダーツの口より下は摘み量ぶん下がるようになった。元の終点が
    # 「消えていない」ことを確認する目的は変わらないので、下がった位置を
    # 含めて探す(消失していれば、どちらの位置にも見つからない)。
    mouth = abs(new_segments[side_indices[0] + 2][1][1]
                - new_segments[side_indices[0]][1][1])
    new_coords = {(round(nums[0], 3), round(nums[1], 3)) for cmd, nums in new_segments if cmd == "L"}
    for x, y in original_ends.values():
        assert ((round(x, 3), round(y, 3)) in new_coords
                or (round(x, 3), round(y + mouth, 3)) in new_coords), (x, y)


def test_apply_bust_dart_keeps_the_sewn_side_seam_length_unchanged():
    """ダーツを縫い閉じた後の脇線長が、ダーツを入れる前と**同じ**になること
    (round14で意味が変わったテスト)。

    round13までは「元の脇線長 - 口の幅(4.0cm固定)」に一致することを確認して
    いた。しかしそれは、後ろ身頃(ダーツ無し)の脇線と4.0cm合わないという
    ことでもあり、そのままでは脇を縫い合わせられない型紙だった。
    round14で、ダーツの口より下を摘み量ぶん下げて丈を足すようにしたので
    (engine/darts.pyの`_shift_below`)、縫い閉じた後の脇線長は元に戻る。
    """
    import math

    from engine.darts import _bust_dart_zip_panel_side_index, _segment_start_positions

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    m = Measurements(bust=130, waist=70, hip=95, height=160,
                      sleeve_length=STANDARD_M.sleeve_length, shoulder_width=STANDARD_M.shoulder_width)

    positions = _segment_start_positions(segments)
    side_idx = _bust_dart_zip_panel_side_index(segments)
    start = positions[side_idx]
    end = (segments[side_idx][1][0], segments[side_idx][1][1])
    original_len = abs(end[1] - start[1])

    new_segments, count = apply_bust_dart("front_bodice_zip_panel", segments, m)
    assert count == 1

    # 脇線の始点は「その1つ前のセグメントの終点」なので、ダーツ挿入後の
    # 輪郭から取り直す(この脇線は裾から袖ぐりへ向かう向きで、始点側が
    # ダーツより下にあるため、摘み量ぶん下がっている)。
    new_positions = _segment_start_positions(new_segments)
    new_start = new_positions[side_idx]
    replacement = new_segments[side_idx:side_idx + 4]
    pts = [new_start] + [(nums[0], nums[1]) for cmd, nums in replacement]
    mouth_first, tip, mouth_second, restored_end = pts[1], pts[2], pts[3], pts[4]
    mouth_width = abs(mouth_second[1] - mouth_first[1])
    # ダーツより上にある終点(袖ぐり側)は動かない。
    assert restored_end == pytest.approx(end)
    # 始点(裾側)は摘み量ぶん下がっている＝前身頃の丈がその分伸びている。
    assert new_start[1] == pytest.approx(start[1] + mouth_width)

    sewn_len = math.dist(new_start, mouth_first) + math.dist(mouth_second, restored_end)
    assert sewn_len == pytest.approx(original_len, abs=1e-6)


def test_bust_dart_applies_once_per_zip_panel_when_bust_is_excessive():
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    m = Measurements(bust=130, waist=70, hip=95, height=160,
                      sleeve_length=STANDARD_M.sleeve_length, shoulder_width=STANDARD_M.shoulder_width)
    _, count = apply_bust_dart("front_bodice_zip_panel", segments, m)
    assert count == 1  # 片側パネルなので外側の脇線1本にのみ追加される


def test_bust_dart_zip_panel_no_dart_below_threshold():
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    _, count = apply_bust_dart("front_bodice_zip_panel", segments, STANDARD_M)
    assert count == 0


def test_bust_dart_never_touches_the_center_front_zip_edge():
    """ダーツは外側の脇線にのみ追加され、中心前(見返し/裁ち割り線)の縁は
    一切変更されないことを確認する。
    """
    from engine.darts import _bust_dart_zip_panel_side_index

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    side_idx = _bust_dart_zip_panel_side_index(segments)

    m = Measurements(bust=130, waist=70, hip=95, height=160,
                      sleeve_length=STANDARD_M.sleeve_length, shoulder_width=STANDARD_M.shoulder_width)
    new_segments, count = apply_bust_dart("front_bodice_zip_panel", segments, m)
    assert count == 1

    # ダーツの差し替えはside_idxの1箇所だけに閉じていること。
    # round14で「ダーツの口より下は摘み量ぶん下がる」ようになったため、
    # 座標そのものの一致ではなく「セグメントの構造(コマンド列とx座標)が
    # 変わらず、yの変化が下方向への平行移動だけ」であることを確認する。
    threshold = max(new_segments[side_idx][1][1], new_segments[side_idx + 2][1][1])
    mouth = abs(new_segments[side_idx + 2][1][1] - new_segments[side_idx][1][1])

    def _expected(seg):
        cmd, nums = seg
        if cmd in ("Z", "H"):
            return seg
        vals = list(nums)
        for k in range(1, len(vals), 2):
            if vals[k] > threshold:
                vals[k] += mouth
        return (cmd, vals)

    for got, original in zip(new_segments[:side_idx], segments[:side_idx]):
        assert got[0] == original[0]
        assert got[1] == pytest.approx(_expected(original)[1])
    for got, original in zip(new_segments[side_idx + 4:], segments[side_idx + 1:]):
        assert got[0] == original[0]
        assert got[1] == pytest.approx(_expected(original)[1])
    # 中心前の縁は縦線のまま、x座標も長さも変わらないこと。
    cf_x = min(nums[0] for cmd, nums in segments if cmd in ("M", "L"))
    assert min(nums[0] for cmd, nums in new_segments if cmd in ("M", "L")) == pytest.approx(cf_x)


def test_bust_dart_zip_panel_produces_valid_non_self_intersecting_polygon():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    m = Measurements(bust=130, waist=70, hip=95, height=160,
                      sleeve_length=STANDARD_M.sleeve_length, shoulder_width=STANDARD_M.shoulder_width)
    new_segments, count = apply_bust_dart("front_bodice_zip_panel", segments, m)
    assert count == 1

    poly_points = segments_to_polyline(new_segments)
    closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
    assert Polygon(closed).is_valid


def test_bust_dart_zip_panel_is_valid_across_full_measurement_range():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    bust_lo, bust_hi = _VALID_RANGES["bust"]

    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    checked_with_dart = 0
    bust = bust_lo
    while bust <= bust_hi:
        m = Measurements(bust=bust, waist=70, hip=95, height=160,
                          sleeve_length=STANDARD_M.sleeve_length, shoulder_width=STANDARD_M.shoulder_width)
        rx, ry = compute_scale_factors(m, "front_bodice_zip_panel")
        scaled = scale_segments(segments, rx, ry)
        new_segments, dart_count = apply_bust_dart("front_bodice_zip_panel", scaled, m)
        if dart_count:
            checked_with_dart += 1
            poly_points = segments_to_polyline(new_segments)
            closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
            assert Polygon(closed).is_valid, f"invalid polygon at bust={bust}"
        bust += 10
    assert checked_with_dart > 0


def test_scale_template_applies_bust_dart_to_zip_panel():
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    # round11でzip_panelにもウエストダーツが入るようになったため、ウエストを
    # バスト比に合わせて比例させ(バスト/ウエスト比を標準のまま保ち)、
    # バストダーツだけが発火する条件でこのテストの意図を維持する。
    m = Measurements(bust=130, waist=130 / STANDARD_M.bust * STANDARD_M.waist, hip=95, height=160,
                      sleeve_length=STANDARD_M.sleeve_length, shoulder_width=STANDARD_M.shoulder_width)
    scaled = scale_template("front_bodice_zip_panel", "round_neck", segments, m)
    assert scaled.dart_count == 1


# --- スカートのウエストダーツ(apply_skirt_waist_dart) --------------------


def test_standard_m_gets_no_skirt_waist_dart():
    plan = compute_skirt_dart_plan("tight", scaled_half_width_cm=10.0, measurements=STANDARD_M)
    assert plan.is_empty()


def test_pear_shape_gets_a_skirt_waist_dart_on_tight_skirt():
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_skirt_dart_plan("tight", scaled_half_width_cm=10.0 * (105 / 92.0), measurements=m)
    assert plan.darts_per_half >= 1


def test_flare_skirt_never_gets_a_waist_dart():
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_skirt_dart_plan("flare", scaled_half_width_cm=20.0, measurements=m)
    assert plan.is_empty()


def test_waist_wider_than_hip_ratio_gets_no_skirt_dart():
    m = Measurements(bust=84, waist=150, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_skirt_dart_plan("tight", scaled_half_width_cm=10.0, measurements=m)
    assert plan.is_empty()


def test_apply_skirt_waist_dart_produces_valid_non_self_intersecting_polygon():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("skirt", "tight")
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors
    rx, ry = compute_scale_factors(m, "skirt")
    scaled = scale_segments(segments, rx, ry)

    new_segments, dart_count = apply_skirt_waist_dart("skirt", "tight", scaled, m)
    assert dart_count > 0

    poly_points = segments_to_polyline(new_segments)
    closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
    assert Polygon(closed).is_valid


def test_apply_skirt_waist_dart_works_regardless_of_top_edge_drawing_direction():
    """身頃の裾ダーツで見つかった方向依存バグと同種の問題が、スカートの
    ウエストライン(上端)側で起きないことの回帰テスト。上端を左→右/右→左の
    両方向で描いた合成テンプレートで、同じダーツ本数・同じ位置になることを
    確認する。
    """
    segments_ltr = [
        ("M", [2, 0.0]), ("L", [22, 0.0]), ("L", [20, 60.0]), ("L", [4, 60.0]), ("L", [2, 0.0]),
    ]
    # 上端(y=0)だけを右→左に描いた、幾何的には同じ形状の合成テンプレート。
    segments_rtl = [
        ("M", [22, 0.0]), ("L", [2, 0.0]), ("L", [4, 60.0]), ("L", [20, 60.0]), ("L", [22, 0.0]),
    ]
    m = Measurements(bust=84.0, waist=60.0, hip=105.0, height=160.0,
                      sleeve_length=54.0, shoulder_width=37.0)

    new_ltr, count_ltr = apply_skirt_waist_dart("skirt", "tight", segments_ltr, m)
    new_rtl, count_rtl = apply_skirt_waist_dart("skirt", "tight", segments_rtl, m)

    assert count_ltr > 0
    assert count_ltr == count_rtl

    def _top_x_coords(segs):
        return sorted(round(x, 3) for cmd, (x, y) in segs if cmd == "L" and abs(y - 0.0) < 1e-6)

    assert _top_x_coords(new_ltr) == _top_x_coords(new_rtl)


def test_apply_skirt_waist_dart_is_valid_across_full_measurement_range():
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get("skirt", "tight")
    waist_lo, waist_hi = _VALID_RANGES["waist"]
    hip_lo, hip_hi = _VALID_RANGES["hip"]

    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    checked_with_dart = 0
    waist = waist_lo
    while waist <= waist_hi:
        hip = hip_lo
        while hip <= hip_hi:
            m = Measurements(bust=84, waist=waist, hip=hip, height=160,
                              sleeve_length=54, shoulder_width=37)
            rx, ry = compute_scale_factors(m, "skirt")
            scaled = scale_segments(segments, rx, ry)
            new_segments, dart_count = apply_skirt_waist_dart("skirt", "tight", scaled, m)
            if dart_count:
                checked_with_dart += 1
                poly_points = segments_to_polyline(new_segments)
                closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
                assert Polygon(closed).is_valid, f"invalid polygon at waist={waist}, hip={hip}"
            hip += 10
        waist += 10
    assert checked_with_dart > 0


def test_scale_template_applies_skirt_waist_dart_for_tight_only():
    db = TemplateDB()
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)

    tight_segments = db.get("skirt", "tight")
    scaled_tight = scale_template("skirt", "tight", tight_segments, m)
    assert scaled_tight.dart_count > 0

    flare_segments = db.get("skirt", "flare")
    scaled_flare = scale_template("skirt", "flare", flare_segments, m)
    assert scaled_flare.dart_count == 0


# --- パンツのウエストダーツ(apply_pants_waist_dart) --------------------


def test_standard_m_gets_no_pants_waist_dart():
    plan = compute_pants_dart_plan("", scaled_half_width_cm=10.0, measurements=STANDARD_M)
    assert plan.is_empty()


def test_pear_shape_gets_a_pants_waist_dart():
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_pants_dart_plan("", scaled_half_width_cm=10.0 * (105 / 92.0), measurements=m)
    assert plan.darts_per_half >= 1


def test_waist_wider_than_hip_ratio_gets_no_pants_dart():
    m = Measurements(bust=84, waist=150, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_pants_dart_plan("", scaled_half_width_cm=10.0, measurements=m)
    assert plan.is_empty()


def test_unknown_pants_variation_gets_no_dart():
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    plan = compute_pants_dart_plan("not-a-real-style", scaled_half_width_cm=10.0, measurements=m)
    assert plan.is_empty()


@pytest.mark.parametrize("part_type", ["front_pants", "back_pants"])
@pytest.mark.parametrize("variation", ["", "wide", "tapered", "shorts", "flare"])
def test_apply_pants_waist_dart_produces_valid_non_self_intersecting_polygon(part_type, variation):
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get(part_type, variation)
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors
    rx, ry = compute_scale_factors(m, part_type)
    scaled = scale_segments(segments, rx, ry)

    new_segments, dart_count = apply_pants_waist_dart(part_type, variation, scaled, m)
    assert dart_count > 0

    poly_points = segments_to_polyline(new_segments)
    closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
    assert Polygon(closed).is_valid


@pytest.mark.parametrize("part_type", ["front_pants", "back_pants"])
def test_apply_pants_waist_dart_works_regardless_of_top_edge_drawing_direction(part_type):
    segments_ltr = [
        ("M", [2, 0.0]), ("L", [22, 0.0]), ("L", [20, 14.0]), ("L", [18, 100.0]),
        ("L", [6, 100.0]), ("L", [2, 14.0]), ("L", [2, 0.0]),
    ]
    segments_rtl = [
        ("M", [22, 0.0]), ("L", [2, 0.0]), ("L", [2, 14.0]), ("L", [6, 100.0]),
        ("L", [18, 100.0]), ("L", [20, 14.0]), ("L", [22, 0.0]),
    ]
    m = Measurements(bust=84.0, waist=60.0, hip=105.0, height=160.0,
                      sleeve_length=54.0, shoulder_width=37.0)

    new_ltr, count_ltr = apply_pants_waist_dart(part_type, "", segments_ltr, m)
    new_rtl, count_rtl = apply_pants_waist_dart(part_type, "", segments_rtl, m)

    assert count_ltr > 0
    assert count_ltr == count_rtl

    def _top_x_coords(segs):
        return sorted(round(x, 3) for cmd, (x, y) in segs if cmd == "L" and abs(y - 0.0) < 1e-6)

    assert _top_x_coords(new_ltr) == _top_x_coords(new_rtl)


@pytest.mark.parametrize("part_type", ["front_pants", "back_pants"])
@pytest.mark.parametrize("variation", ["", "wide", "tapered", "shorts", "flare"])
def test_apply_pants_waist_dart_is_valid_across_full_measurement_range(part_type, variation):
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    db = TemplateDB()
    segments = db.get(part_type, variation)
    waist_lo, waist_hi = _VALID_RANGES["waist"]
    hip_lo, hip_hi = _VALID_RANGES["hip"]

    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    checked_with_dart = 0
    waist = waist_lo
    while waist <= waist_hi:
        hip = hip_lo
        while hip <= hip_hi:
            m = Measurements(bust=84, waist=waist, hip=hip, height=160,
                              sleeve_length=54, shoulder_width=37)
            rx, ry = compute_scale_factors(m, part_type)
            scaled = scale_segments(segments, rx, ry)
            new_segments, dart_count = apply_pants_waist_dart(part_type, variation, scaled, m)
            if dart_count:
                checked_with_dart += 1
                poly_points = segments_to_polyline(new_segments)
                closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
                assert Polygon(closed).is_valid, f"invalid polygon at waist={waist}, hip={hip}"
            hip += 10
        waist += 10
    assert checked_with_dart > 0


def test_scale_template_applies_pants_waist_dart_for_every_pants_variation():
    db = TemplateDB()
    m = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    for part_type in ("front_pants", "back_pants"):
        for variation in ("", "wide", "tapered", "shorts", "flare"):
            segments = db.get(part_type, variation)
            scaled = scale_template(part_type, variation, segments, m)
            assert scaled.dart_count > 0, f"{part_type}({variation})にダーツが入っていない"


# --- round7: 肩ダーツ・プリンセスラインの再調査(実装は見送り) ---------------
#
# darts.pyモジュールdocstringの「round7: 『本当のバストダーツ・プリンセス
# ライン』の再調査」に記載した通り、前身頃には独立した「肩線」の直線区間が
# 無く、既存の脇ダーツ/ウエストダーツと同じ「直線(L)セグメントを検出して
# V字に置き換える」設計を肩ダーツに転用できない、という調査結論に至った。
# このテストは、その調査結論の根拠(=front_bodiceの輪郭にL(直線)セグメントが
# ちょうど2本(左右の脇線)しか無く、肩線に相当するL区間が存在しない)が
# 実際のテンプレートに対して成り立っていることを固定化する。将来
# テンプレートの輪郭設計が変わってこの前提が崩れた場合、このテストが
# 失敗することで気づけるようにする(=肩ダーツ実装の再検討が必要になる合図)。
def test_front_bodice_has_no_straight_shoulder_segment_for_every_neckline():
    """round7投資調査の根拠(engine/darts.pyモジュールdocstring参照)を固定化する。

    調査で分かった内容: round_neck/v_neck/sweetheart/boat_neckは、肩先同士を
    ネックライン自体のベジエ曲線または斜め線で直接橋渡ししており、独立した
    「肩線」の水平な直線(L)区間が無い。一方square_neck/turtle_neckは、
    ネックライン開口部の縁自体が水平な直線(角ネック・タートルネックの
    台襟の付け根)になっているため、この輪郭上端の水平線は例外的に存在する。
    ただし、これは「肩線」ではなく「ネックライン開口部の縁」そのものであり、
    ここにV字ノッチを入れると縫い目ではなくネックラインの見た目自体が
    変形してしまう。かつ過半数のネックライン(round/v/sweetheart/boat)には
    そもそも適用できないため、この例外があっても「肩ダーツを既存の脇線
    ダーツと同じ仕組みで一般的に追加することはできない」という調査結論は
    変わらない。
    """
    from engine.darts import _find_side_seam_segment_indices, _segment_start_positions

    # ネックライン開口部の縁自体が水平な直線になっている、確認済みの例外。
    _FLAT_NECKLINE_EDGE_EXCEPTIONS = {"square_neck", "turtle_neck"}

    db = TemplateDB()
    for neckline in ("round_neck", "v_neck", "square_neck", "boat_neck",
                      "turtle_neck", "sweetheart"):
        segments = db.get("front_bodice", neckline)
        assert segments is not None, f"template not found: front_bodice/{neckline}"

        # 既存の脇ダーツ実装が前提とする「脇線がちょうど2本」であることを確認
        # (肩ダーツをこの脇線検出の仕組みにそのまま転用できない、という
        # 調査結論の前提の一部)。
        side_indices = _find_side_seam_segment_indices(segments)
        assert len(side_indices) == 2, (
            f"front_bodice/{neckline}の脇線本数が想定と異なる"
            f"({len(side_indices)}本)。engine/darts.pyのround7投資調査コメントを見直すこと。"
        )

        if neckline in _FLAT_NECKLINE_EDGE_EXCEPTIONS:
            continue  # 上記の通り、既知の例外(ネックライン開口部の縁)。

        # 「肩線」に相当する、ほぼ水平で肩幅程度の長さを持つ直線(L)セグメントが
        # 輪郭の上端(=ネックライン・肩先の高さ)付近に存在しないことを確認する。
        # 裾(y最大の水平線)は対象外にする(裾は既存のウエストダーツが使う、
        # 意図的に存在する水平線のため)。
        positions = _segment_start_positions(segments)
        poly_points = segments_to_polyline(segments)
        top_y = min(p[1] for p in poly_points)
        for i, (cmd, nums) in enumerate(segments):
            if cmd != "L":
                continue
            start = positions[i]
            end = (nums[0], nums[1])
            dx, dy = abs(start[0] - end[0]), abs(start[1] - end[1])
            # 「ほぼ水平」は緩やかな斜め線(V字ネックラインの縁等)まで誤検出
            # しないよう、dyが小さい(ほぼ真横に進む)場合のみに絞る。
            is_roughly_horizontal_and_wide = dy < 2.0 and dx > 3.0
            is_near_top = min(start[1], end[1]) - top_y < 5.0
            assert not (is_roughly_horizontal_and_wide and is_near_top), (
                f"front_bodice/{neckline}に肩線らしき水平なL区間が輪郭上端付近で"
                f"見つかった({start} -> {end})。テンプレートの輪郭設計が変わった"
                "可能性があるため、engine/darts.pyのround7投資調査コメント"
                "(肩ダーツが実装可能かどうかの前提)を見直すこと。"
            )


# --- round11: front_bodice_zip_panelへのウエストダーツ対応 -----------------

def test_standard_m_zip_panel_gets_no_waist_dart():
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    _, count = apply_waist_dart("front_bodice_zip_panel", segments, STANDARD_M)
    assert count == 0


@pytest.mark.parametrize("variation",
                          ["round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart"])
def test_hourglass_zip_panel_gets_a_waist_dart_for_every_variation(variation):
    m = Measurements(bust=100, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", variation)
    _, count = apply_waist_dart("front_bodice_zip_panel", segments, m)
    assert count > 0


def test_waist_wider_than_bust_ratio_gets_no_zip_panel_waist_dart():
    m = Measurements(bust=50, waist=140, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    _, count = apply_waist_dart("front_bodice_zip_panel", segments, m)
    assert count == 0


def test_zip_panel_waist_dart_uses_the_full_hem_not_the_short_facing_bridge():
    """round11の実装中に実測で見つかった罠の回帰テスト。

    zip_panelの裾は「見返し用の短い橋渡し辺(4cm)」と「本来の裾」に
    分かれており、しかも後者はZによる暗黙のクローズ辺として表現されている。
    `_find_hem_segment_index`(cmd=="L"のみを見る)は前者を裾と誤判定するため、
    そのまま使うと半幅を4cmと見積もってダーツが一切入らなくなる。
    ここでは、ダーツの位置が「見返し側の4cm区間」ではなく、脇線側まで含めた
    本来の裾の幅に基づいて決まっていることを確認する。
    """
    from engine.darts import (
        _bust_dart_zip_panel_side_index, _find_side_seam_segment_indices,
        _segment_start_positions, DART_OFFSET_RATIO,
    )

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    positions = _segment_start_positions(segments)
    candidates = _find_side_seam_segment_indices(segments)
    side_idx = _bust_dart_zip_panel_side_index(segments)
    other_idx = candidates[0] if candidates[1] == side_idx else candidates[1]
    side_x = segments[side_idx][1][0]
    cf_x = segments[other_idx][1][0]
    half_width = abs(side_x - cf_x)
    assert half_width > 10.0  # 見返しの橋渡し辺(4cm)ではなく本来の半幅

    m = Measurements(bust=100, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    new_segments, count = apply_waist_dart("front_bodice_zip_panel", segments, m)
    assert count > 0

    # ダーツの先端は裾からDEFAULT_APEX_LEN_CM上がった高さにある。その高さの
    # 点だけを取り出して、脇線側の想定位置に置かれていることを確認する。
    from engine.darts import DEFAULT_APEX_LEN_CM

    hem_y = max(nums[1] for cmd, nums in new_segments if cmd in ("L", "M"))
    apex_y = hem_y - DEFAULT_APEX_LEN_CM
    tip_xs = [nums[0] for cmd, nums in new_segments
              if cmd == "L" and abs(nums[1] - apex_y) < 1e-6]
    assert tip_xs, "ダーツの先端が見つからない"
    expected_anchor = cf_x + (side_x - cf_x) * DART_OFFSET_RATIO
    assert min(tip_xs) == pytest.approx(expected_anchor, abs=3.0)
    # 見返し側の4cm区間(cf_x〜cf_x+4)にダーツが置かれていないことも確認する。
    assert min(tip_xs) > min(cf_x, side_x) + 6.0


def test_zip_panel_waist_dart_keeps_the_center_front_hem_corner():
    """ダーツは脇線側にのみ入り、中心前(見返し)側の裾の角は残ること。"""
    from engine.darts import (
        _bust_dart_zip_panel_side_index, _find_side_seam_segment_indices,
        _segment_start_positions,
    )

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    positions = _segment_start_positions(segments)
    candidates = _find_side_seam_segment_indices(segments)
    side_idx = _bust_dart_zip_panel_side_index(segments)
    other_idx = candidates[0] if candidates[1] == side_idx else candidates[1]
    a, b = positions[other_idx], (segments[other_idx][1][0], segments[other_idx][1][1])
    cf_hem_point = a if a[1] > b[1] else b

    m = Measurements(bust=100, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    new_segments, count = apply_waist_dart("front_bodice_zip_panel", segments, m)
    assert count > 0
    coords = {(round(nums[0], 3), round(nums[1], 3)) for cmd, nums in new_segments if cmd == "L"}
    assert (round(cf_hem_point[0], 3), round(cf_hem_point[1], 3)) in coords


def test_zip_panel_waist_dart_produces_valid_non_self_intersecting_polygon():
    shapely = pytest.importorskip("shapely.geometry")
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    m = Measurements(bust=100, waist=60, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    new_segments, count = apply_waist_dart("front_bodice_zip_panel", segments, m)
    assert count > 0
    pts = segments_to_polyline(new_segments)
    closed = pts[:-1] if pts[0] == pts[-1] else pts
    assert shapely.Polygon(closed).is_valid


def test_zip_panel_waist_dart_is_valid_across_full_measurement_range():
    shapely = pytest.importorskip("shapely.geometry")
    from engine.svgpath import scale_segments
    from engine.scaling import compute_scale_factors

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    bust_lo, bust_hi = _VALID_RANGES["bust"]
    waist_lo, waist_hi = _VALID_RANGES["waist"]

    checked = 0
    bust = bust_lo
    while bust <= bust_hi:
        waist = waist_lo
        while waist <= waist_hi:
            m = Measurements(bust=bust, waist=waist, hip=92, height=160,
                              sleeve_length=54, shoulder_width=37)
            rx, ry = compute_scale_factors(m, "front_bodice_zip_panel")
            scaled = scale_segments(segments, rx, ry)
            new_segments, count = apply_waist_dart("front_bodice_zip_panel", scaled, m)
            if count:
                checked += 1
                pts = segments_to_polyline(new_segments)
                closed = pts[:-1] if pts[0] == pts[-1] else pts
                assert shapely.Polygon(closed).is_valid, f"bust={bust} waist={waist}"
            waist += 15
        bust += 15
    assert checked > 0


def test_scale_template_applies_waist_dart_to_zip_panel():
    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", "round_neck")
    # バストダーツ(bust絶対超過で発火)を誘発せず、ウエストダーツ(bust/waist比で
    # 発火)だけを単独で確認できる採寸を選ぶ。
    m = Measurements(bust=84, waist=58, hip=92, height=160, sleeve_length=54, shoulder_width=37)
    assert compute_bust_dart_intake_cm(m) == 0.0
    scaled = scale_template("front_bodice_zip_panel", "round_neck", segments, m)
    assert scaled.dart_count > 0
