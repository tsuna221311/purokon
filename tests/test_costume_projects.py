"""衣装プロジェクトは非対称パネルを黙ってミラーしない。"""

from dataclasses import replace
from io import BytesIO
from math import dist

import pytest
from pypdf import PdfReader

from engine.compatibility import (
    armhole_length, check_seam_compatibility, neckline_length,
    shoulder_seam_length,
)
from engine.costume_projects import costume_project_choices, get_costume_project
from engine.measurements import Measurements
from engine.hem_extensions import hem_extension_warnings, hem_extension_rows
from engine.pipeline import (
    PatternForgePipeline, build_custom_panel_requests, build_garment_spec,
    merge_custom_panel_requests,
)
from engine.production_quality import production_quality_report


BODY = Measurements(83, 66, 91, 158, 52, 37)


def test_endministrator_project_contains_a_complete_project_plan():
    project = get_costume_project("endministrator_female", BODY)
    assert project is not None
    assert project.lining is True
    assert project.shoulder_drop_cm == 5.0
    assert project.worn_over_bust_cm == 93.0
    assert project.patternable_components
    assert project.separate_components
    assert project.material_plan
    assert project.construction_plan
    assert project.limitations


def test_endministrator_project_keeps_each_asymmetric_tail_as_its_own_panel():
    project = get_costume_project("endministrator_female", BODY)
    assert project is not None
    panels = project.custom_panel_specs
    assert len(panels) == 6
    assert all(panel.mirror is False for panel in panels)
    assert panels[3].points_cm != panels[4].points_cm
    assert all("下身頃" in panel.label for panel in panels[:3])
    assert all("オーバーレイ" in panel.label for panel in panels[3:])
    assert len(project.overlay_pairs) == 3
    # The panels are attached *below* a hip-length bodice; they are not
    # themselves a full shoulder-to-hem coat length.
    assert max(y for panel in panels for _x, y in panel.points_cm) < BODY.height * 0.30


def test_endministrator_lower_shell_and_overlays_use_different_fabrics_and_lining():
    project = get_costume_project("endministrator_female", BODY)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    requests = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, requests, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        spec, BODY, lining=True, worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm,
        fabric_group_assignments={"custom_panel": "外装パネル用生地"},
        skip_export=True)
    groups = {group.name: group.parts for group in result.fabric_groups}
    base_labels = {panel.label for panel in project.custom_panel_specs[:3]}
    overlay_labels = {panel.label for panel in project.custom_panel_specs[3:]}
    assert {part.variation for part in groups["表地"] if part.variation} >= base_labels
    assert {part.variation for part in groups["外装パネル用生地"]} == overlay_labels
    assert {part.variation for part in result.lining_parts
            if part.part_type == "custom_panel"} == base_labels
    assert hem_extension_warnings(result.finalized_parts, project.as_dict()) == []
    steps = result.assembly_steps()
    titles = [step.title for step in steps]
    assert titles.index("コート下身頃の脇を縫う") < titles.index(
        "非対称の裾飾りを下身頃へ重ねる") < titles.index(
        "裾パネルを本体へ縫い合わせる")
    joined = next(step for step in steps if step.title == "裾パネルを本体へ縫い合わせる")
    assert "三枚重ね" in joined.detail
    base = next(part for part in result.finalized_parts
                if part.variation == project.custom_panel_specs[0].label)
    damaged = replace(base, notches=[])
    warnings = hem_extension_warnings(
        [damaged if part is base else part for part in result.finalized_parts],
        project.as_dict())
    assert any("重ねA: 下身頃の対応合印" in warning for warning in warnings)
    overlay = next(part for part in result.finalized_parts
                   if part.variation == project.custom_panel_specs[3].label)
    wrong_allowance = replace(overlay, seam_allowance_cm=overlay.seam_allowance_cm + .3)
    warnings = hem_extension_warnings(
        [wrong_allowance if part is overlay else part
         for part in result.finalized_parts], project.as_dict())
    assert any("重ねA: 下身頃と飾りの縫い代幅" in warning for warning in warnings)


def test_endministrator_sewing_pattern_is_measurable_and_digitally_ready(tmp_path):
    project = get_costume_project("endministrator_female", BODY)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    overlays = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, overlays, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, BODY, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)

    assert production_quality_report(result)["digital_ready"] is True
    assert hem_extension_warnings(result.finalized_parts, project.as_dict()) == []
    rows = hem_extension_rows(result.finalized_parts, project.as_dict())
    assert [row[0] for row in rows] == ["A", "B", "C"]
    assert all(row[3].split(" / ")[0] == row[3].split(" / ")[1].split(" cm")[0]
               for row in rows)
    steps = result.assembly_steps()
    assert any(step.title == "裾パネルを本体へ縫い合わせる" for step in steps)
    assert any(step.title == "コート下身頃の脇を縫う" for step in steps)
    assert any(step.title == "非対称の裾飾りを下身頃へ重ねる" for step in steps)
    assert not any(step.title == "カスタムパーツを取り付ける" for step in steps)
    fronts = [part for part in result.finalized_parts
              if part.part_type == "front_bodice_zip_panel"]
    hoods = [part for part in result.finalized_parts
             if part.part_type == "hood"]
    hood_linings = [part for part in result.lining_parts
                    if part.part_type == "hood"]
    assert len(fronts) == len(hoods) == len(hood_linings) == 2
    assert all(armhole_length(part) for part in fronts)
    assert all(shoulder_seam_length(part) for part in fronts)
    assert all(neckline_length(part) for part in fronts)
    assert all(any(label == "CF" for label, _ in part.reference_lines)
               for part in fronts)

    # A broken sleeve/hood/shoulder must be caught after finalization, not
    # hidden by the original split-front measurement shortcut.
    damaged = replace(fronts[0], compatibility_measurements={
        **fronts[0].compatibility_measurements,
        "armhole_length": armhole_length(fronts[0]) + 8.0,
        "shoulder_seam_length": shoulder_seam_length(fronts[0]) + 8.0,
        "neckline_length": neckline_length(fronts[0]) + 8.0,
    })
    parts = [damaged if part is fronts[0] else part
             for part in result.finalized_parts]
    kinds = {warning.kind for warning in check_seam_compatibility(parts)}
    assert {"armhole_sleeve_cap", "shoulder_seam", "neckline_collar"} <= kinds


@pytest.mark.parametrize("dimensions", [
    (76, 60, 82, 150, 49, 34),
    (83, 66, 91, 158, 52, 37),
    (92, 76, 101, 168, 57, 41),
    (104, 88, 112, 175, 61, 44),
])
def test_endministrator_body_range_avoids_crossed_outlines(tmp_path, dimensions):
    body = Measurements(*dimensions)
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    overlays = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, overlays, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    report = production_quality_report(result)
    assert report["digital_ready"] is True
    assert hem_extension_warnings(result.finalized_parts, project.as_dict()) == []
    bases = [next(part for part in result.finalized_parts
                  if part.variation == panel.label)
             for panel in project.custom_panel_specs[:3]]
    side_lengths = [dist(part.stitch_line[0], part.stitch_line[-1])
                    for part in bases]
    assert max(side_lengths) - min(side_lengths) < .03
    assert all(dist(part.stitch_line[1], part.stitch_line[2]) ==
               pytest.approx(side_lengths[0], abs=.03) for part in bases)
    if body.bust == 76:
        assert any("胸ダーツと袖ぐりが交差しない" in note
                   for note in result.design_notes)


def test_endministrator_joined_hem_replaces_wide_turnup_and_detects_damage(tmp_path):
    project = get_costume_project("endministrator_female", BODY)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    panels = [request for panel in project.custom_panel_specs
              for request in build_custom_panel_requests(panel.label, panel.points_cm)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, panels, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, BODY, hem_seam_allowance_cm=3.0,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    hosts = [part for part in result.finalized_parts
             if any(part.part_type == pair[2] and part.label_suffix == pair[3]
                    for pair in project.hem_extension_pairs)]
    assert len(hosts) == 3
    assert all(part.hem_edge_is_joined and part.hem_seam_allowance_cm == 1.0
               for part in hosts)
    assert hem_extension_warnings(result.finalized_parts, project.as_dict()) == []
    panel = next(part for part in result.finalized_parts
                 if part.variation == project.custom_panel_specs[0].label)
    damaged = replace(panel, notches=[])
    parts = [damaged if part is panel else part for part in result.finalized_parts]
    assert any("合印" in warning for warning in
               hem_extension_warnings(parts, project.as_dict()))


def test_endministrator_commercial_components_are_not_claimed_as_cloth_patterns():
    project = get_costume_project("endministrator_female", BODY)
    assert project is not None
    cloth = " ".join(project.patternable_components)
    separate = " ".join(project.separate_components)
    assert "ショートパンツ" in cloth
    for item in ("袖口装飾2個", "上腕装飾2個", "背面装飾2個", "髪飾り"):
        assert item in separate
        assert item not in cloth
    assert any("正面画像だけ" in note for note in project.commercial_benchmark)
    assert any("未採用" in note for note in project.material_plan)
    assert any("Cossky" in note and "CCosplay" in note
               for note in project.limitations)
    assert any("裾に開きダーツ" in note and "直線でまたがない" in note
               for note in project.construction_plan)


def test_endministrator_export_separates_overlay_fabric_and_preserves_handoff(client):
    response = client.post("/api/generate", data={
        "bust": "83", "waist": "66", "hip": "91", "height": "158",
        "sleeve_length": "52", "shoulder_width": "37", "mode": "manual",
        "costume_project": "endministrator_female",
    })
    assert response.status_code == 200, response.get_json().get("error")
    payload = response.get_json()
    groups = {group["name"]: group for group in payload["fabric_groups"]}
    assert "表地" in groups
    assert "外装パネル用生地" in groups
    assert groups["外装パネル用生地"]["part_count"] == 3
    assert groups["表地"]["part_count"] >= 3
    assert "all_fabrics_pdf" in payload["download"]
    checks = {item["code"] for item in
              payload["production_quality"]["fitting_checklist"]}
    assert {"overlay_alignment", "costume_attachment", "reference_match"} <= checks
    pdf = client.get(payload["download"]["spec_pdf"])
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in
                     PdfReader(BytesIO(pdf.data)).pages)
    for phrase in ("管理人（女性）", "衣装固有の製作計画", "袖口装飾2個",
                   "素材の使い分け", "背面資料"):
        assert phrase in text


def test_unknown_costume_project_is_rejected_and_empty_selection_is_allowed():
    assert get_costume_project("", BODY) is None
    assert any(key == "endministrator_female" for key, _label in costume_project_choices())
    try:
        get_costume_project("not-a-project", BODY)
    except ValueError as exc:
        assert "不正" in str(exc)
    else:
        raise AssertionError("unknown project must not be ignored")


def test_researched_projects_have_a_pattern_plan_and_commercial_gap_checklist():
    keys = ("endministrator_male", "perlica", "chen_qianyu",
            "hatsune_miku_classic", "yor_forger_thorn_princess")
    for key in keys:
        project = get_costume_project(key, BODY)
        assert project is not None
        assert project.custom_panel_specs
        assert project.patternable_components
        assert project.separate_components
        assert project.commercial_benchmark
        assert all(panel.mirror is False for panel in project.custom_panel_specs)


def test_all_selectable_project_keys_resolve():
    for key, _label in costume_project_choices():
        if key:
            assert get_costume_project(key, BODY) is not None


def test_catalog_has_fifty_total_character_presets_and_uses_known_silhouettes():
    projects = [get_costume_project(key, BODY)
                for key, _label in costume_project_choices() if key]
    assert len(projects) == 50
    assert all(project is not None for project in projects)
    assert all(project.garment_spec_kwargs for project in projects)
