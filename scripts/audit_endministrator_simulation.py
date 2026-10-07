"""Audit every currently computable Endministrator garment check.

This is a *gap audit*, not a certificate of parity with a purchased costume.
The older material-sensitivity drape uses authored 3D geometry.  An optional
newer pattern-derived trial is reported separately and is not a finished
sewn reconstruction.  Missing measurements and physical tests stay explicit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.component_coverage import audit_component_nodes
from engine.costume_projects import get_costume_project
from engine.hem_extensions import hem_extension_rows, hem_extension_warnings
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.production_quality import production_quality_report
from engine.vrc_outfit_audit import audit_gltf, read_glb_json


SIZES = (
    (76, 60, 82, 150, 49, 34),
    (83, 66, 91, 158, 52, 37),
    (92, 76, 101, 168, 57, 41),
    (104, 88, 112, 175, 61, 44),
    # The wide coat remains a real cutting blocker (bust-dart capacity after
    # the project-specific paper side-seam truing).  Keep it in the published
    # audit rather than sampling only passing sizes.
    (116, 100, 128, 180, 64, 45),
)
PROFILES = ("soft", "baseline", "stiff")
VIEWS = ("front", "side", "back")


def audit_pattern_sizes() -> list[dict]:
    results = []
    pipeline = PatternForgePipeline(output_dir=str(ROOT / "output"))
    for dimensions in SIZES:
        body = Measurements(*dimensions)
        project = get_costume_project("endministrator_female", body)
        spec = build_garment_spec(**project.garment_spec_kwargs)
        panels = [request for panel in project.custom_panel_specs
                  for request in build_custom_panel_requests(
                      panel.label, panel.points_cm, quantity=panel.quantity,
                      mirror=panel.mirror, allow_split=panel.allow_split)]
        spec.parts = merge_custom_panel_requests(
            spec.parts, panels, princess_line=spec.princess_line)
        spec.construction["costume_project_brief"] = project.as_dict()
        result = pipeline.generate_from_selection(
            spec, body, lining=project.lining,
            worn_over_bust_cm=project.worn_over_bust_cm,
            shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
        quality = production_quality_report(result)
        results.append({
            "measurements_cm": body.as_dict(),
            "digital_ready": quality["digital_ready"],
            "blockers": quality["blockers"],
            "hem_join_warnings": hem_extension_warnings(
                result.finalized_parts, project.as_dict()),
            "hem_join_stitch_lengths": [
                {"code": code, "host": host, "panel": panel,
                 "host_panel_cm": lengths}
                for code, host, panel, lengths in hem_extension_rows(
                    result.finalized_parts, project.as_dict())
            ],
            "physical_signoff_required": True,
        })
    return results


def audit_drape(directory: Path) -> list[dict]:
    results = []
    for profile in PROFILES:
        report_path = directory / profile / "simulation_report.json"
        if not report_path.is_file():
            raise FileNotFoundError(f"Missing cloth simulation: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("profile") != profile or not report.get("cloth_self_collision"):
            raise ValueError(f"Self-collision result is missing for {profile}")
        views = [directory / profile / f"{profile}_{view}.png" for view in VIEWS]
        if not all(path.is_file() for path in views):
            raise FileNotFoundError(f"A rendered view is missing for {profile}")
        results.append({
            "profile": profile,
            "inputs_are_measured": False,
            "self_collision": True,
            "hem_spread_ratio": report["hem_spread_ratio"],
            "p95_edge_strain_percent": report["p95_absolute_edge_strain_percent"],
            "mean_displacement_cm": report["mean_displacement_cm"],
            "source_blend": report.get("source_blend", ""),
            "visual_surface_follow_point_count": sum(
                report.get("visual_surface_follow_points", {}).values()),
            "visual_attachment_is_structural_sewing": report.get(
                "visual_surface_follow_is_structural_sewing", False),
            "renders": {view: str(path.resolve())
                        for view, path in zip(VIEWS, views)},
            "not_simulated": report["not_simulated"],
        })
    return results


def audit_components(glb_path: Path, manifest_path: Path) -> dict:
    gltf = read_glb_json(glb_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    coverage = audit_component_nodes(gltf, manifest["components"])
    mesh = audit_gltf(gltf)
    return {
        "merchant_reference": manifest["source"],
        "expected_groups": coverage["expected_groups"],
        "present_groups": coverage["present_groups"],
        "geometry_pass_groups": coverage["geometry_pass_groups"],
        "missing_groups": [item["component"] for item in coverage["components"]
                           if not item["present"]],
        "mesh_triangles": mesh["triangles"],
        "mesh_skin_count": mesh["skin_count"],
        "structural_issues": mesh["issues"],
        "photos_and_materials_automatically_verified": False,
    }


def audit_pattern_derived_drape(report_path: Path) -> dict:
    """Inspect the newer sewn-pattern trial without certifying its appearance."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report.get("pattern_sleeves_rendered") or not report.get(
            "support_bodice_is_pattern_derived"):
        raise ValueError("This is not a pattern-derived bodice/sleeve trial")
    image_dir = report_path.parent
    views = {
        view: str((image_dir / f"pattern_shell_smoothed_{view}.png").resolve())
        for view in VIEWS
    }
    if not all(Path(path).is_file() for path in views.values()):
        raise FileNotFoundError("Pattern-derived drape lacks three diagnostic views")
    sleeves = report.get("sleeve_drape_report") or {}
    if len(sleeves) != 2:
        raise ValueError("Pattern-derived drape lacks both sleeves")
    upper = {item["code"]: item["upper_final_p95_absolute_paper_edge_strain_percent"]
             for item in report.get("panels", [])
             if "code" in item and
             "upper_final_p95_absolute_paper_edge_strain_percent" in item}
    shoulders = {side: item["final_gap_p95_cm"]
                 for side, item in (report.get("shoulder_seam_report") or {}).items()
                 if "final_gap_p95_cm" in item}
    front_zip_mode = report.get("front_zip_seam_mode", "open-front-zip")
    front_zip = report.get("front_zip_seam_report") or {}
    if front_zip_mode == "sewn-front-zip-trial" and "final_gap_p95_cm" not in front_zip:
        raise ValueError("Front-zip trial lacks measured closure gaps")
    return {
        "source_pattern_json": report.get("source_pattern_json"),
        "sleeve_cap_ease_distribution": report.get("sleeve_cap_ease_distribution"),
        "sleeve_axis_mode": report.get("sleeve_axis_mode", "horizontal-sleeve"),
        "nominal_arm_fixture_pose_degrees": report.get(
            "nominal_arm_fixture_pose_degrees"),
        "waist_dart_trial": {
            "present": report.get("waist_dart_3d_trial", False),
            "closure_pass": report.get("waist_dart_trial_closure_pass"),
            "topologically_welded_to_lower_shell": report.get(
                "bodice_to_panel_seam_topologically_welded", False),
        },
        "sleeve_p95_paper_edge_strain_percent": {
            side: result["p95_absolute_paper_edge_strain_percent"]
            for side, result in sleeves.items()},
        "upper_bodice_p95_paper_edge_strain_percent": upper,
        "shoulder_final_gap_p95_cm": shoulders,
        "front_zip_trial": {
            "mode": front_zip_mode,
            "initial_gap_p95_cm": front_zip.get("initial_gap_p95_cm"),
            "final_gap_p95_cm": front_zip.get("final_gap_p95_cm"),
            "provisional_gap_pass": (
                front_zip_mode == "sewn-front-zip-trial"
                and front_zip.get("final_gap_p95_cm", float("inf")) <= .5),
            "real_zipper_fit_validated": False,
        },
        "sleeves_topologically_welded_to_bodice": all(
            item.get("topologically_welded_to_bodice", False)
            for item in sleeves.values()),
        "notch_pairing_verified_on_2d_stitch_lines": report.get(
            "sleeve_join_audit", {}).get(
                "notch_pairing_verified_on_2d_stitch_lines", False),
        "fabric_inputs_measured": report.get("fabric_inputs_measured", False),
        "commercial_quality_approved": report.get("commercial_quality_approved", False),
        "diagnostic_views": views,
    }


def pattern_trial_blockers(pattern_drape: dict) -> list[str]:
    """Keep an unfinished cloth trial from being mistaken for a fit approval."""
    blockers = []
    if not pattern_drape["sleeves_topologically_welded_to_bodice"]:
        blockers.append("型紙由来の袖は身頃と共有頂点で連続していない")
    if not pattern_drape["fabric_inputs_measured"]:
        blockers.append("型紙由来の布計算にも実測した生地物性がない")
    upper = pattern_drape.get("upper_bodice_p95_paper_edge_strain_percent") or {}
    if any(value > 8 for value in upper.values()):
        blockers.append("型紙由来の上身頃に試作内部目安8%を超す紙面辺長変形がある")
    sleeves = pattern_drape.get("sleeve_p95_paper_edge_strain_percent") or {}
    if any(value > 10 for value in sleeves.values()):
        blockers.append("型紙由来の袖に試作内部目安10%を超す紙面辺長変形がある")
    shoulders = pattern_drape.get("shoulder_final_gap_p95_cm") or {}
    if any(value > .5 for value in shoulders.values()):
        blockers.append("肩の縫い合わせに試作内部目安0.5cmを超す隙間が残る")
    waist_darts = pattern_drape.get("waist_dart_trial") or {}
    if waist_darts.get("present") and not waist_darts.get("closure_pass"):
        blockers.append("裾ダーツの3D仮縫合が閉じていない")
    if (waist_darts.get("present") and not waist_darts.get(
            "topologically_welded_to_lower_shell", False)):
        blockers.append("裾ダーツのある上身頃と下身頃は一体メッシュ接合されていない")
    front_zip = pattern_drape.get("front_zip_trial") or {}
    if (front_zip.get("mode") == "sewn-front-zip-trial"
            and not front_zip.get("provisional_gap_pass", False)):
        blockers.append("前ファスナー仮接合に試作内部目安0.5cmを超す隙間が残る")
    return blockers


def build_pattern_only_report(pattern_panel_report: Path) -> dict:
    """Audit a current pattern-derived Blender run without legacy GLB assets."""
    pattern_drape = audit_pattern_derived_drape(pattern_panel_report)
    return {
        "reference": "Arknights: Endfield female Endministrator",
        "commercial_equivalence_verified": False,
        "pattern_derived_drape_trial": pattern_drape,
        "scope": {"static_render_views": len(VIEWS), "physical_wear_tests": 0},
        "blockers": [
            "側面・背面と素材物性は実測値がなく、正面資料からの推定",
            "装飾の固定点・荷重・脱着疲労を布シミュレーションに含めていない",
            "歩行・着座・腕上げ時の布変形と身体への干渉を検査していない",
            "実布の仮縫い、耐久、質感の市販品との実物比較をしていない",
            *pattern_trial_blockers(pattern_drape),
        ],
    }


def build_report(simulation_dir: Path, glb_path: Path,
                 manifest_path: Path,
                 pattern_panel_report: Path | None = None) -> dict:
    sizes = audit_pattern_sizes()
    drapes = audit_drape(simulation_dir)
    components = audit_components(glb_path, manifest_path)
    pattern_drape = (audit_pattern_derived_drape(pattern_panel_report)
                     if pattern_panel_report is not None else None)
    blockers = []
    if not all(size["digital_ready"] and not size["hem_join_warnings"]
               for size in sizes):
        blockers.append("一部のサイズで型紙のデジタル検査または裾接合が不合格")
    if components["missing_groups"]:
        blockers.append("市販セットの部品が3D試作に不足: "
                        + "、".join(components["missing_groups"]))
    blockers.extend([
        "布モデルは2D型紙を縫製して復元した形状ではなく、接合部の張力を検査できない",
        "側面・背面と素材物性は実測値がなく、正面資料からの推定",
        "装飾の固定点・荷重・脱着疲労を布シミュレーションに含めていない",
        "歩行・着座・腕上げ時の布変形と身体への干渉を検査していない",
        "実布の仮縫い、耐久、質感の市販品との実物比較をしていない",
    ])
    if pattern_drape is not None:
        blockers.extend(pattern_trial_blockers(pattern_drape))
    return {
        "reference": "Arknights: Endfield female Endministrator",
        "commercial_equivalence_verified": False,
        "pattern_size_cases": sizes,
        "cloth_material_sensitivity_cases": drapes,
        "commercial_component_inventory": components,
        **({"pattern_derived_drape_trial": pattern_drape}
           if pattern_drape is not None else {}),
        "scope": {
            "pattern_sizes": len(sizes),
            "cloth_material_profiles": len(drapes),
            "static_render_views": len(drapes) * len(VIEWS),
            "physical_wear_tests": 0,
        },
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulations", type=Path,
                        default=ROOT / "output/endministrator_material_study_v3")
    parser.add_argument("--glb", type=Path,
                        default=ROOT / "output/endministrator_commercial_sewn_v4"
                                       "/endministrator_sewn_costume.glb")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "docs/endministrator_commercial_components.json")
    parser.add_argument("--pattern-panel-report", type=Path,
                        help="Optional newer sewn-pattern trial JSON and its three views")
    parser.add_argument("--pattern-only", action="store_true",
                        help="Audit only the current pattern-derived Blender trial")
    parser.add_argument("--fail-on-blockers", action="store_true",
                        help="Exit with status 2 when the audit has blockers")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/endministrator_material_study_v3"
                                       "/commercial_gap_audit.json")
    args = parser.parse_args()
    if args.pattern_only:
        if args.pattern_panel_report is None:
            parser.error("--pattern-only needs --pattern-panel-report")
        report = build_pattern_only_report(args.pattern_panel_report)
    else:
        report = build_report(args.simulations, args.glb, args.manifest,
                              args.pattern_panel_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"output": str(args.output), "scope": report["scope"],
                      "commercial_equivalence_verified": False,
                      "blockers": report["blockers"]}, ensure_ascii=False))
    if args.fail_on_blockers and report["blockers"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
