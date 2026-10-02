from math import hypot

from engine.assembly import assembly_steps
from engine.construction_features import apply_construction_features
from engine.cutting import part_needs_interfacing
from engine.fabric import interfacing_length_cm
from engine.lining import build_lining_parts, lining_part
from engine.seam import FinalizedPart


def _part(part_type, label="", width=40.0, height=70.0):
    stitch = [(0.0, 0.0), (width, 0.0), (width, height),
              (0.0, height), (0.0, 0.0)]
    return FinalizedPart(
        part_type=part_type, variation="flare" if part_type == "skirt" else "round_neck",
        stitch_line=stitch, cut_line=stitch, notches=[],
        grainline={"x": width / 2, "y1": 5.0, "y2": height - 5.0},
        seam_allowance_cm=1.0, label_suffix=label,
    )


def test_confirmed_features_become_shared_export_reference_lines():
    parts = [
        _part("front_bodice"), _part("back_bodice"),
        _part("skirt", "前・第1層"), _part("skirt", "後・第1層"),
        _part("skirt", "前・第2層"), _part("skirt", "後・第2層"),
    ]
    result = apply_construction_features(parts, {
        "closure": "back_zip", "closure_length_cm": 45,
        "internal_support": "boning",
        "pleat_count": 8, "pleat_depth_cm": 2,
        "slit_position": "back", "slit_length_cm": 25,
        "motif_position": "chest_front", "motif_width_cm": 12,
        "motif_height_cm": 8,
    })
    labels = [label for part in result for label, _ in part.reference_lines]
    assert any("後中心ファスナー" in label for label in labels)
    assert any("ボーン位置" in label for label in labels)
    assert sum("プリーツ" in label for label in labels) == 16
    assert sum("スリット" in label for label in labels) == 2
    assert sum("配置線 12×8cm" in label for label in labels) == 1
    back_zip_parts = [part for part in result
                      if part.part_type == "back_bodice"]
    assert len(back_zip_parts) == 2
    assert {"左", "右"} == {
        "左" if "左" in part.label_suffix else "右" for part in back_zip_parts}
    # 元の中心後x=20に、左右それぞれの縫い線が接する。裁断線はその外側へ
    # 縫い代1cmを持つため、後中心を突き合わせて裁つ形にはならない。
    assert all(any(abs(x - 20) < 1e-6 for x, _y in part.stitch_line)
               for part in back_zip_parts)
    assert all(part.width_cm > 20 for part in back_zip_parts)
    second_layer = [part for part in result if "第2層" in part.label_suffix]
    assert not any("プリーツ" in label or "スリット" in label
                   for part in second_layer for label, _ in part.reference_lines)


def test_slit_longer_than_the_pattern_is_rejected():
    try:
        apply_construction_features([_part("skirt", "前", height=30)], {
            "slit_position": "front", "slit_length_cm": 30,
        })
    except ValueError as exc:
        assert "対象パーツ丈" in str(exc)
    else:
        raise AssertionError("丈以上のスリットが受理されました")


def test_uploaded_motif_outline_is_scaled_and_written_as_the_real_shape():
    outline = [(0.0, 0.0), (1.0, 0.0), (0.75, 0.45),
               (1.0, 1.0), (0.0, 1.0), (0.25, 0.45)]
    result = apply_construction_features([_part("front_bodice")], {
        "motif_position": "chest_front", "motif_width_cm": 12,
        "motif_height_cm": 8, "motif_outline_normalized": outline,
    })
    label, points = next(
        entry for entry in result[0].reference_lines if "画像外形" in entry[0])
    assert label == "画像外形 12×8cm"
    assert abs(max(x for x, _y in points) - min(x for x, _y in points) - 12) < 1e-6
    assert abs(max(y for _x, y in points) - min(y for _x, y in points) - 8) < 1e-6
    assert len(points) == len(outline) + 1


def test_partial_lining_can_select_front_only_and_sleeveless():
    parts = [_part("front_bodice"), _part("back_bodice"), _part("sleeve")]
    front_only = build_lining_parts(parts, scope=["front_bodice"])
    assert [part.part_type for part in front_only] == ["front_bodice"]
    sleeveless = build_lining_parts(
        parts, scope=["front_bodice", "back_bodice"])
    assert {part.part_type for part in sleeveless} == {
        "front_bodice", "back_bodice"}


def test_explicit_interfacing_targets_create_real_cut_lines_and_shopping_amount():
    result = apply_construction_features([
        _part("front_bodice"), _part("back_bodice"), _part("sleeve")], {
        "internal_support": "interfacing",
        "interfacing_targets": ["bodice"],
        "interfacing_inset_cm": 1.5,
    })
    bodices = [part for part in result if "bodice" in part.part_type]
    sleeve = next(part for part in result if part.part_type == "sleeve")
    assert all(part_needs_interfacing(part) for part in bodices)
    assert not part_needs_interfacing(sleeve)
    assert all("端から1.5cm内側" in part.cutting_note for part in bodices)
    assert all(any("接着芯裁断線" in label
                   for label, _points in part.reference_lines)
               for part in bodices)
    assert interfacing_length_cm(result) > 0
    full = apply_construction_features([
        _part("front_bodice"), _part("back_bodice")], {
        "internal_support": "interfacing",
        "interfacing_targets": ["bodice"], "interfacing_inset_cm": 0,
    })
    assert interfacing_length_cm(result) <= interfacing_length_cm(full)
    steps = assembly_steps(result)
    interfacing_step = next(step for step in steps if step.title == "接着芯を貼る")
    assert any("端から1.5cm内側" in name for name in interfacing_step.parts)


def test_motif_is_not_silently_shrunk_when_it_cannot_fit_inside_pattern():
    # 外接枠上は入るが、三角形の細い上側には指定寸法の矩形が入らない。
    triangular = _part("front_bodice")
    triangular.stitch_line = [(20, 0), (40, 70), (0, 70), (20, 0)]
    try:
        apply_construction_features([triangular], {
            "motif_position": "chest_front", "motif_width_cm": 35,
            "motif_height_cm": 55,
        })
    except ValueError as exc:
        assert "縫い線内に収まりません" in str(exc)
    else:
        raise AssertionError("型紙外の装飾が黙って縮小または受理されました")


def test_center_slit_splits_the_skirt_and_adds_center_seam_allowance():
    result = apply_construction_features([_part("skirt", "後")], {
        "slit_position": "back", "slit_length_cm": 25,
    })
    assert len(result) == 2
    assert all("後中心スリット" in part.label_suffix for part in result)
    assert all(part.width_cm > 20 for part in result)
    assert all(any("裾から25cm" in label for label, _points in part.reference_lines)
               for part in result)


def test_side_slit_follows_the_real_side_edge_for_the_exact_length():
    result = apply_construction_features([
        _part("skirt", "前"), _part("skirt", "後")], {
        "slit_position": "right", "slit_length_cm": 24,
    })
    for part in result:
        line = next(points for label, points in part.reference_lines
                    if "right脇スリット" in label)
        length = sum(hypot(b[0] - a[0], b[1] - a[1])
                     for a, b in zip(line, line[1:]))
        assert abs(length - 24) < 1e-6
        assert all(abs(x - 40) < 1e-6 for x, _y in line)


def test_pleats_without_a_skirt_are_rejected():
    try:
        apply_construction_features([_part("front_bodice")], {
            "pleat_count": 4, "pleat_depth_cm": 2})
    except ValueError as exc:
        assert "スカート型紙" in str(exc)
    else:
        raise AssertionError("スカート無しのプリーツ指定が受理されました")


def test_gather_ratio_changes_the_pattern_width_and_records_finished_length():
    original = _part("skirt", "前", width=40, height=70)
    gathered = apply_construction_features([original], {
        "gather_ratio": 1.8,
    })[0]
    assert abs(gathered.stitch_line[1][0] - gathered.stitch_line[0][0] - 72) < 1e-6
    assert gathered.compatibility_measurements["waist_opening_length"] == 40
    assert any("1.8倍" in label and "40.0cm" in label
               for label, _points in gathered.reference_lines)


def test_gather_and_pleats_can_be_combined_without_losing_either_allowance():
    original = _part("skirt", "前", width=40)
    combined = apply_construction_features([original], {
        "gather_ratio": 1.5, "pleat_count": 4, "pleat_depth_cm": 2,
    })[0]
    # ギャザーで40→60cm、プリーツ折り込み4本×深さ2cm×両側=16cm。
    assert combined.width_cm >= 76
    labels = [label for label, _points in combined.reference_lines]
    assert any("ギャザー" in label for label in labels)
    assert any("プリーツ" in label for label in labels)


def test_soft_petticoat_generates_real_tier_panels_and_waistband():
    result = apply_construction_features([_part("skirt", "前")], {
        "internal_support": "petticoat", "petticoat_style": "soft",
        "petticoat_tier_count": 3, "petticoat_length_cm": 60,
        "petticoat_waist_cm": 70, "petticoat_fullness_ratio": 1.6,
        "petticoat_seam_allowance_cm": 1,
    })
    tiers = [part for part in result if part.part_type == "petticoat_tier"]
    bands = [part for part in result if part.part_type == "petticoat_waistband"]
    assert tiers and len(bands) == 1
    assert {part.label_suffix.split("・")[0] for part in tiers} == {
        "第1段", "第2段", "第3段"}
    assert all(max(x for x, _y in part.stitch_line)
               - min(x for x, _y in part.stitch_line) <= 90.0 + 1e-6
               for part in tiers + bands)
    assert all(abs(part.height_cm - 22.0) < 0.1 for part in tiers)


def test_hoop_petticoat_records_each_wire_diameter_and_assembly_steps():
    result = apply_construction_features([], {
        "internal_support": "petticoat", "petticoat_style": "hoop",
        "petticoat_tier_count": 3, "petticoat_length_cm": 60,
        "petticoat_waist_cm": 70,
        "petticoat_hoop_diameters_cm": [45, 65, 85],
        "petticoat_seam_allowance_cm": 1,
    })
    labels = [label for part in result for label, _points in part.reference_lines]
    for diameter in (45, 65, 85):
        assert any(f"輪直径{diameter}cm" in label for label in labels)
    titles = [step.title for step in assembly_steps(result)]
    assert "パニエの各段を輪にする" in titles
    assert "パニエへワイヤーを通す" in titles
    assert "パニエのウエストを作る" in titles


def test_back_and_side_zip_require_an_explicit_opening_length():
    for closure in ("back_zip", "side_zip"):
        try:
            apply_construction_features([_part("back_bodice")], {"closure": closure})
        except ValueError as exc:
            assert "開きの長さ" in str(exc)
        else:
            raise AssertionError(f"{closure} without length was accepted")


def test_side_zip_follows_the_actual_side_seam_for_the_exact_length():
    parts = [_part("front_bodice"), _part("back_bodice")]
    result = apply_construction_features(parts, {
        "closure": "side_zip", "closure_length_cm": 32,
    })
    for part in result:
        lines = [points for label, points in part.reference_lines
                 if "右脇ファスナー" in label]
        assert lines
        length = sum(hypot(b[0] - a[0], b[1] - a[1])
                     for points in lines for a, b in zip(points, points[1:]))
        assert abs(length - 32) < 1e-6
        # 幅40cmの長方形なので右脇縫い線はx=40。内側98%の近似線ではない。
        assert all(abs(x - 40) < 1e-6 for points in lines for x, _y in points)


def test_hooks_and_snaps_are_not_misrepresented_as_production_ready():
    for closure in ("hooks", "snaps"):
        try:
            apply_construction_features([_part("back_bodice")], {"closure": closure})
        except ValueError as exc:
            assert "個数" in str(exc)
        else:
            raise AssertionError(f"{closure} was accepted without overlap/count/spacing")


def test_hooks_split_the_back_and_add_measured_installation_marks():
    result = apply_construction_features([_part("back_bodice")], {
        "closure": "hooks", "closure_count": 6, "closure_spacing_cm": 4,
    })
    assert len(result) == 2
    assert all("後中心ホック" in part.label_suffix for part in result)
    for part in result:
        labels = [label for label, _points in part.reference_lines if "ホック" in label]
        assert len(labels) == 6
        assert labels[-1].startswith("ホック6/6")


def test_snaps_add_a_real_overlap_extension_and_marks():
    result = apply_construction_features([_part("back_bodice")], {
        "closure": "snaps", "closure_count": 5,
        "closure_spacing_cm": 4, "closure_overlap_cm": 2,
    })
    assert len(result) == 2
    left = next(part for part in result if "・左" in part.label_suffix)
    right = next(part for part in result if "・右" in part.label_suffix)
    # 右後ろだけが中心後を2cm越えて左側へ持ち出す。
    assert right.width_cm > left.width_cm + 1.5
    assert any("重なり2cm" in label for label, _points in right.reference_lines)
    assert sum("スナップ" in label and "/5" in label
               for label, _points in right.reference_lines) == 5


def test_center_back_closures_do_not_get_a_conflicting_lining_pleat():
    for closure, settings in (
        ("hooks", {"closure_count": 5, "closure_spacing_cm": 4}),
        ("snaps", {"closure_count": 5, "closure_spacing_cm": 4,
                   "closure_overlap_cm": 2}),
    ):
        parts = apply_construction_features([_part("back_bodice")], {
            "closure": closure, **settings,
        })
        linings = [lining_part(part) for part in parts]
        assert all(lining is not None for lining in linings)
        assert not any(label == "きせ" for lining in linings
                       for label, _points in lining.reference_lines)
        titles = [step.title for step in assembly_steps(
            parts, closure=closure, closure_count=5, closure_spacing_cm=4,
            closure_overlap_cm=(2 if closure == "snaps" else None),
            lining_parts=linings)]
        assert "裏地の背中心にきせをたたむ" not in titles


def test_unresolved_closure_can_remain_in_draft_without_changing_cut_lines():
    original = _part("back_bodice")
    for closure in ("back_zip", "side_zip", "hooks", "snaps"):
        result = apply_construction_features([original], {
            "closure": closure, "draft_mode": True})
        assert len(result) == 1
        assert result[0].stitch_line == original.stitch_line
