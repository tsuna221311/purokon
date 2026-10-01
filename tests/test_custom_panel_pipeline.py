"""engine/pipeline.py への custom_panel(自由形状パーツ、round9で追加)の
組み込みを検証する統合テスト。engine/custom_panel.py自体の校正ロジックは
tests/test_custom_panel.pyで、輪郭追跡はtests/test_contour_tracing.py・
tests/test_auto_trace_outline.pyでそれぞれ検証済み。ここでは実際に
PatternForgePipeline.generate_from_selection()まで通してSVG/PDF等が
生成できることを確認する。
"""

import pytest
from PIL import Image, ImageDraw

from engine.custom_panel import calibrate_points_to_cm
from engine.measurements import Measurements
from engine.pipeline import (
    GarmentSpec,
    PatternForgePipeline,
    build_custom_panel_requests,
    build_garment_spec,
    merge_custom_panel_requests,
)

STANDARD = Measurements(bust=84, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)


def _cape_points_cm():
    # 参照線100px=40cmで校正した、幅40cm x 高さ60cmのマント状の輪郭。
    raw = [(0, 0), (100, 0), (120, 150), (-20, 150)]
    return calibrate_points_to_cm(raw, (0, 0), (100, 0), reference_cm=40.0)


def test_build_custom_panel_requests_without_mirror():
    points = _cape_points_cm()
    requests = build_custom_panel_requests("マント", points, quantity=1, mirror=False)
    assert len(requests) == 1
    assert requests[0].part_type == "custom_panel"
    assert requests[0].variation == "マント"
    assert requests[0].custom_segments is not None


def test_build_custom_panel_requests_with_mirror_produces_two_distinct_labels():
    points = _cape_points_cm()
    requests = build_custom_panel_requests("肩当て", points, quantity=1, mirror=True)
    assert len(requests) == 2
    labels = {r.variation for r in requests}
    assert labels == {"肩当て", "肩当て(反転)"}


def test_generate_from_selection_with_only_a_custom_panel(tmp_path):
    points = _cape_points_cm()
    requests = build_custom_panel_requests("マント", points, quantity=1)
    spec = GarmentSpec(parts=requests)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    assert len(result.finalized_parts) == 1
    part = result.finalized_parts[0]
    assert part.part_type == "custom_panel"
    assert part.dart_count == 0
    # 校正した通りおおよそ幅40cm(かつ台形の裾張り出し分)であることを確認
    # (校正時のreference_cm=40が正しく反映され、体型スケーリングで
    # 別の値に変わっていないことの確認)。width_cmはcut_line(縫い代オフセット
    # 後の外形線)基準のため、生の校正値56.0cmに左右合計で縫い代分
    # (デフォルト1.0cm x 2 = 2.0cm)が上乗せされ、約58.0cmになる。
    # 120-(-20)=140px -> *0.4 = 56.0cm(stitch_line) -> +2.0cm(縫い代) = 58.0cm
    assert part.width_cm == pytest.approx(58.0, abs=0.5)


def test_custom_panel_is_not_rescaled_by_measurements(tmp_path):
    # 採寸値をどう変えても、custom_panelの寸法は校正時のcmのまま変わらない
    # はず(PART_SCALE_RULES["custom_panel"]がNone/Noneのため)。
    points = _cape_points_cm()
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))

    small = Measurements(bust=60, waist=50, hip=70, height=140, sleeve_length=45, shoulder_width=30)
    large = Measurements(bust=130, waist=110, hip=130, height=185, sleeve_length=65, shoulder_width=45)

    for m in (small, large):
        requests = build_custom_panel_requests("マント", points, quantity=1)
        spec = GarmentSpec(parts=requests)
        result = pipeline.generate_from_selection(spec, m)
        part = result.finalized_parts[0]
        # cut_line基準のためstitch_lineの56.0cmに縫い代2.0cm分が上乗せされ約58.0cm
        # (詳細はtest_generate_from_selection_with_only_a_custom_panelのコメント参照)。
        assert part.width_cm == pytest.approx(58.0, abs=0.5)


def test_custom_panel_quantity_gets_numbered_labels(tmp_path):
    points = _cape_points_cm()
    requests = build_custom_panel_requests("肩装甲", points, quantity=3)
    spec = GarmentSpec(parts=requests)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(spec, STANDARD)
    suffixes = sorted(p.label_suffix for p in result.finalized_parts)
    assert suffixes == ["①", "②", "③"]


def test_custom_panel_combines_with_standard_template_parts(tmp_path):
    # round9のAskUserQuestionで「両方お願い」(体にフィットする本体も
    # カスタムパーツも両方対応)と回答されたため、標準テンプレートの
    # パーツとカスタムパーツを同じGarmentSpecに混在させられることを確認する。
    spec = build_garment_spec(sleeve_style="straight", skirt_style=None)
    spec.parts.extend(build_custom_panel_requests("装甲プレート", _cape_points_cm(), quantity=1))
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    part_types = {p.part_type for p in result.finalized_parts}
    assert "front_bodice" in part_types
    assert "custom_panel" in part_types


def test_custom_panel_mirrored_pair_generates_both_shapes(tmp_path):
    requests = build_custom_panel_requests("肩当て", _cape_points_cm(), quantity=1, mirror=True)
    spec = GarmentSpec(parts=requests)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    assert len(result.finalized_parts) == 2
    variations = {p.variation for p in result.finalized_parts}
    assert variations == {"肩当て", "肩当て(反転)"}


def test_confirmed_flat_pattern_replaces_standard_part_at_exact_real_size(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    original_spec = build_garment_spec(sleeve_style=None, skirt_style=None)
    original = pipeline.generate_from_selection(
        original_spec, STANDARD, skip_export=True)
    original_front = next(
        p for p in original.finalized_parts if p.part_type == "front_bodice")
    points = list(original_front.stitch_line)
    if points[0] == points[-1]:
        points.pop()

    base = build_garment_spec(sleeve_style=None, skirt_style=None)
    replacement = build_custom_panel_requests(
        "実寸前身頃", points, replacement_part_type="front_bodice",
        seam_fit_confirmed=True)
    base.parts = merge_custom_panel_requests(base.parts, replacement)
    assert sum(r.part_type == "front_bodice" for r in base.parts) == 1
    assert next(r for r in base.parts if r.part_type == "front_bodice").custom_segments

    result = pipeline.generate_from_selection(base, STANDARD, skip_export=True)
    front = next(p for p in result.finalized_parts if p.part_type == "front_bodice")
    assert front.variation == "実寸前身頃"
    # 実寸輪郭へ採寸倍率を二重に掛けず、元の縫い線寸法を維持する。
    assert front.width_cm == pytest.approx(original_front.width_cm, abs=0.05)
    assert result.compatibility_warnings() == []


def test_replacement_with_mismatched_seams_stops_before_export(tmp_path):
    base = build_garment_spec(sleeve_style="straight", skirt_style=None)
    bad = build_custom_panel_requests(
        "合わない袖", _cape_points_cm(), mirror=True,
        replacement_part_type="sleeve", seam_fit_confirmed=True)
    base.parts = merge_custom_panel_requests(base.parts, bad)
    with pytest.raises(ValueError, match="裁断用PDF・SVG・DXFは出力していません"):
        PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
            base, STANDARD)
    assert list(tmp_path.iterdir()) == []


def test_replacement_requires_confirmation_and_exact_piece_count():
    with pytest.raises(ValueError, match="縫い線の長さを確認"):
        build_custom_panel_requests(
            "袖", _cape_points_cm(), replacement_part_type="sleeve")

    base = build_garment_spec(sleeve_style="straight", skirt_style=None)
    one_sleeve = build_custom_panel_requests(
        "左袖", _cape_points_cm(), replacement_part_type="sleeve",
        seam_fit_confirmed=True)
    with pytest.raises(ValueError, match="2枚必要"):
        merge_custom_panel_requests(base.parts, one_sleeve)


def test_mirrored_replacement_supplies_both_sleeves_without_standard_sleeves():
    base = build_garment_spec(sleeve_style="straight", skirt_style=None)
    sleeves = build_custom_panel_requests(
        "確認済み袖", _cape_points_cm(), mirror=True,
        replacement_part_type="sleeve", seam_fit_confirmed=True)
    base.parts = merge_custom_panel_requests(base.parts, sleeves)
    sleeve_requests = [r for r in base.parts if r.part_type == "sleeve"]
    assert len(sleeve_requests) == 2
    assert all(r.custom_segments is not None for r in sleeve_requests)


def test_illustration_route_replaces_detected_sleeves_too(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    standard = pipeline.generate_from_selection(
        build_garment_spec(sleeve_style="straight", skirt_style="flare"),
        STANDARD, skip_export=True)
    sleeve = next(p for p in standard.finalized_parts if p.part_type == "sleeve")
    points = list(sleeve.stitch_line)
    if points[0] == points[-1]:
        points.pop()
    requests = build_custom_panel_requests(
        "画像確認済み袖", points, mirror=True,
        replacement_part_type="sleeve", seam_fit_confirmed=True)
    corrections = {
        "neckline": "round_neck", "back_neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
        "pants_style": None, "collar_style": None, "cuffs_style": None,
        "waistband_style": None, "hood": False, "closure": "none",
        "symmetry": "symmetric", "internal_support": "none",
        "movement": "standard",
    }
    image = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(140, 60), (260, 60), (300, 180), (270, 350),
         (330, 560), (70, 560), (130, 350), (100, 180)],
        fill=(60, 80, 130))
    result = pipeline.generate_from_illustration(
        image, STANDARD,
        corrections=corrections, extra_part_requests=requests,
        include_empty_tiles=False)
    sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert len(sleeves) == 2
    assert {p.variation for p in sleeves} == {
        "画像確認済み袖", "画像確認済み袖(反転)"}
    assert result.compatibility_warnings() == []
