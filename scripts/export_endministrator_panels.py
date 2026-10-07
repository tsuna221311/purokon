"""Export the real generated stitch outlines for a Blender drape study."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.costume_projects import get_costume_project
from engine.compatibility import armhole_length, sleeve_cap_length, underarm_y_of
from engine.endministrator_armhole import (arc_of_point_cm, back_armhole_paths,
                                           back_side_paths,
                                           choose_sleeve_shoulder_station,
                                           front_zip_armhole_path,
                                           front_effective_side_segments,
                                           endministrator_notch_pairing_warnings,
                                           endministrator_side_seam_warnings,
                                           mesh_indices_for_contour_path,
                                           path_length_cm, shoulder_stitch_paths,
                                           sleeve_cap_path,
                                           sleeve_underarm_side_paths)
from engine.endministrator_darts import (front_bust_dart_legs,
                                         hem_waist_dart_legs)
from engine.front_detail_panels import (draft_exterior_front_panel,
                                        draft_neck_lapel)
from engine.hem_extensions import (_sewn_bottom_edge, _straight_edge,
                                   hem_extension_warnings)
from engine.measurements import Measurements
from engine.pattern_width_audit import audit_open_bodice_widths
from engine.pattern_panel_bridge import (sample_bodice_from_stitch_line,
                                         cloth_mesh_boundary_coverage,
                                         sample_constrained_stitch_outline,
                                         sample_panel, validate_cloth_panel_mesh)
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.zip_front_geometry import front_zip_center_path


def export_panels(body: Measurements, *,
                  disable_side_seam_truing: bool = False,
                  allow_side_mismatch_diagnostic: bool = False) -> dict:
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    requests = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, requests, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    if disable_side_seam_truing:
        spec.construction["disable_endministrator_side_seam_truing"] = True
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    notch_warnings = endministrator_notch_pairing_warnings(result.finalized_parts)
    if notch_warnings:
        raise ValueError("Invalid coat sewing notches: " + "; ".join(notch_warnings))
    side_warnings = endministrator_side_seam_warnings(result.finalized_parts)
    if side_warnings and not allow_side_mismatch_diagnostic:
        raise ValueError("Invalid coat side seams: " + "; ".join(side_warnings))
    warnings = hem_extension_warnings(result.finalized_parts, project.as_dict())
    if warnings:
        raise ValueError("Invalid hem joins: " + "; ".join(warnings))
    sleeve_parts = [part for part in result.finalized_parts
                    if part.part_type == "sleeve"]
    if len(sleeve_parts) != 2:
        raise ValueError("Endministrator coat needs a left and right sleeve")
    sleeves = []
    for sleeve in sleeve_parts:
        cap_length = sleeve_cap_length(sleeve)
        if cap_length is None:
            raise ValueError("Generated sleeve has no identifiable cap seam")
        sleeve_mesh = sample_panel(sleeve.stitch_line, spacing_cm=2.0,
                                   strict_boundary=True,
                                   require_horizontal_top=False)
        validate_cloth_panel_mesh(sleeve_mesh)
        cap_path = sleeve_cap_path(sleeve.stitch_line)
        tube_paths = sleeve_underarm_side_paths(sleeve.stitch_line)
        if abs(path_length_cm(cap_path) - cap_length) > .001:
            raise ValueError("Sleeve cap path and length calculation disagree")
        sleeves.append({
            "side": sleeve.label_suffix,
            "stitch_outline_cm": sleeve.stitch_line,
            "cut_outline_cm": sleeve.cut_line,
            "notches_cm": [point for point, _end in sleeve.notches],
            "sleeve_cap_stitch_length_cm": cap_length,
            "cap_stitch_path_cm": cap_path,
            "cap_mesh_indices": mesh_indices_for_contour_path(
                sleeve_mesh, sleeve.stitch_line, cap_path),
            "tube_side_stitch_paths_cm": tube_paths,
            "tube_side_mesh_paths": [mesh_indices_for_contour_path(
                sleeve_mesh, sleeve.stitch_line, path) for path in tube_paths],
            "seam_allowance_cm": sleeve.seam_allowance_cm,
            "pattern_mesh": sleeve_mesh,
            "prototype_3d_join_verified": False,
        })
    panels = []
    bodice_hosts = []
    for code, label, host_type, side in project.hem_extension_pairs:
        matches = [part for part in result.finalized_parts
                   if part.part_type == "custom_panel" and part.variation == label]
        if len(matches) != 1:
            raise ValueError(f"Panel {code} is missing or ambiguous")
        host_matches = [part for part in result.finalized_parts
                        if part.part_type == host_type and part.label_suffix == side]
        if len(host_matches) != 1:
            raise ValueError(f"Bodice host {code} is missing or ambiguous")
        host = host_matches[0]
        underarm_y = underarm_y_of(host)
        if underarm_y is None:
            raise ValueError(f"Bodice host {code} has no underarm reference")
        armhole_paths = ([front_zip_armhole_path(host.stitch_line, underarm_y)]
                         if host_type == "front_bodice_zip_panel" else
                         list(back_armhole_paths(host.stitch_line, underarm_y)))
        shoulder_paths = shoulder_stitch_paths(host.stitch_line, armhole_paths)
        hem_runs, hem_y = _sewn_bottom_edge(
            host, allow_darts=project.hem_extension_allow_sewn_darts)
        left, right = hem_runs[0][0], hem_runs[-1][1]
        sewn_hem_width = sum(end - start for start, end in hem_runs)
        bodice_mesh = sample_bodice_from_stitch_line(
            host.stitch_line, hem_y, sewn_hem_runs=hem_runs)
        boundary_coverage = cloth_mesh_boundary_coverage(bodice_mesh)
        darts = (front_bust_dart_legs(host.stitch_line, bodice_mesh)
                 if host_type == "front_bodice_zip_panel" else [])
        waist_darts = (hem_waist_dart_legs(
            host.stitch_line, bodice_mesh, hem_runs, hem_y)
            if len(hem_runs) > 1 else [])
        side_paths = (front_effective_side_segments(
            host.stitch_line, underarm_y, right, hem_y, darts)
            if darts else back_side_paths(
                host.stitch_line, underarm_y, left, right, hem_y))
        front_opening = (front_zip_center_path(host.stitch_line, hem_y)
                         if host_type == "front_bodice_zip_panel" else None)
        outline = matches[0].stitch_line
        mesh = sample_panel(outline)
        if abs(sewn_hem_width - mesh["top_width_cm"]) > 0.1:
            raise ValueError(f"Host and panel {code} have different stitch lengths")
        panels.append({"code": code, "label": label,
                       "seam_allowance_cm": matches[0].seam_allowance_cm,
                       "stitch_outline_cm": outline, **mesh})
        bodice_hosts.append({
            "code": code, "part_type": host_type, "side": side,
            "stitch_outline_cm": host.stitch_line,
            "cut_outline_cm": host.cut_line,
            "pattern_mesh": bodice_mesh,
            "mesh_boundary_coverage": boundary_coverage,
            "hem_stitch_left_cm": left, "hem_stitch_right_cm": right,
            "hem_stitch_y_cm": hem_y,
            "hem_stitch_width_cm": sewn_hem_width,
            "hem_sewn_runs_cm": hem_runs,
            "hem_waist_darts": waist_darts,
            "hem_seam_allowance_cm": host.hem_seam_allowance_cm,
            "underarm_y_cm": underarm_y,
            "armhole_stitch_length_cm": armhole_length(host),
            "armhole_stitch_paths_cm": armhole_paths,
            "armhole_mesh_paths": [mesh_indices_for_contour_path(
                bodice_mesh, host.stitch_line, path) for path in armhole_paths],
            "shoulder_stitch_paths_cm": shoulder_paths,
            "shoulder_mesh_paths": [mesh_indices_for_contour_path(
                bodice_mesh, host.stitch_line, path) for path in shoulder_paths],
            "side_seam_segments_cm": side_paths,
            "side_mesh_paths": [mesh_indices_for_contour_path(
                bodice_mesh, host.stitch_line, path) for path in side_paths],
            "front_opening_stitch_path_cm": front_opening,
            "front_opening_mesh_path": (
                mesh_indices_for_contour_path(
                    bodice_mesh, host.stitch_line, front_opening)
                if front_opening else None),
            "armhole_contour_length_cm": sum(
                path_length_cm(path) for path in armhole_paths),
            "side_bust_darts": darts,
            "hem_notch_x_cm": [point[0] for point, _end in host.notches
                               if abs(point[1] - hem_y) < .03],
        })
    overlays = []
    for code, overlay_label, base_label in project.overlay_pairs:
        overlay = next(part for part in result.finalized_parts
                       if part.part_type == "custom_panel"
                       and part.variation == overlay_label)
        base = next(part for part in result.finalized_parts
                    if part.part_type == "custom_panel"
                    and part.variation == base_label)
        overlay_mesh = sample_panel(overlay.stitch_line, strict_boundary=True)
        base_mesh = next(panel for panel in panels if panel["code"] == code)
        if abs(overlay_mesh["top_width_cm"] - base_mesh["top_width_cm"]) > .1:
            raise ValueError(f"Overlay {code} does not match its lower shell")
        overlays.append({"code": code, "label": overlay_label,
                         "base_label": base.variation,
                         "seam_allowance_cm": overlay.seam_allowance_cm,
                         "stitch_outline_cm": overlay.stitch_line,
                         **overlay_mesh})
    front_details = []
    lapels = []
    for host in bodice_hosts:
        if host["part_type"] != "front_bodice_zip_panel":
            continue
        source = next(part for part in result.finalized_parts
                      if part.part_type == host["part_type"]
                      and part.label_suffix == host["side"])
        drafted = draft_exterior_front_panel(source)
        try:
            mesh = sample_panel(drafted.part.stitch_line, strict_boundary=True)
            mesh_strategy = "sampled_delaunay"
        except ValueError as exc:
            if "Stitch boundary endpoint was omitted by triangulation" not in str(exc):
                raise
            # This narrow fallback preserves every contrast-panel sewing
            # endpoint.  Do not quietly accept a partial attachment boundary.
            mesh = sample_constrained_stitch_outline(drafted.part.stitch_line)
            mesh_strategy = "boundary_constrained_fallback"
        validate_cloth_panel_mesh(mesh)
        front_details.append({
            "host_code": host["code"],
            "host_side": host["side"],
            "label": drafted.part.variation,
            "stitch_outline_cm": drafted.part.stitch_line,
            "cut_outline_cm": drafted.part.cut_line,
            "host_attachment_line_cm": drafted.host_attachment_line_cm,
            "notches_cm": [point for point, _end in drafted.part.notches],
            "seam_allowance_cm": drafted.part.seam_allowance_cm,
            "pattern_mesh": mesh,
            "mesh_strategy": mesh_strategy,
            "prototype_only": True,
            "attachment_construction_verified": False,
            "fabric_measured": False,
        })
        lapel = draft_neck_lapel(source)
        lapel_mesh = sample_panel(lapel.part.stitch_line,
                                  strict_boundary=True,
                                  require_horizontal_top=False)
        validate_cloth_panel_mesh(lapel_mesh)
        lapels.append({
            "host_code": host["code"], "host_side": host["side"],
            "label": lapel.part.variation,
            "stitch_outline_cm": lapel.part.stitch_line,
            "cut_outline_cm": lapel.part.cut_line,
            "host_attachment_line_cm": lapel.host_attachment_line_cm,
            "notches_cm": [point for point, _end in lapel.part.notches],
            "seam_allowance_cm": lapel.part.seam_allowance_cm,
            "pattern_mesh": lapel_mesh,
            "prototype_only": True,
            "fold_line_verified": False,
            "attachment_construction_verified": False,
            "fabric_measured": False,
        })
    armhole_parts = [part for part in result.finalized_parts
                     if part.part_type in {"front_bodice_zip_panel", "back_bodice"}]
    armhole_lengths = [armhole_length(part) for part in armhole_parts]
    if len(armhole_lengths) != 3 or any(length is None for length in armhole_lengths):
        raise ValueError("Generated bodices have no complete armhole measurements")
    per_arm_armhole_cm = sum(armhole_lengths) / 2
    bodice_notch_arcs = {}
    for host in bodice_hosts:
        part = next(part for part in result.finalized_parts
                    if part.part_type == host["part_type"]
                    and part.label_suffix == host["side"])
        per_path = []
        for index, path in enumerate(host["armhole_stitch_paths_cm"]):
            arcs = [arc_of_point_cm(path, point) for point, _ in part.notches]
            # The left back path runs shoulder -> underarm.  All other paths
            # run underarm -> shoulder, as does the sleeve cap from its ends.
            distances = sorted(
                path_length_cm(path) - arc if host["code"] == "C" and index == 0
                else arc for arc in arcs if arc is not None)
            expected = 2 if host["code"] == "C" else 1
            if len(distances) != expected:
                raise ValueError(f"{host['code']} has missing armhole sewing notches")
            per_path.append(distances)
        bodice_notch_arcs[host["code"]] = per_path
    sleeve_notch_arcs = {}
    printed_shoulder_arcs = {}
    front_notch_distance = bodice_notch_arcs["A"][0][0]
    back_notch_distances = bodice_notch_arcs["C"][1]
    if abs(front_notch_distance - bodice_notch_arcs["B"][0][0]) > .05:
        raise ValueError("The front panel armhole sewing notches disagree")
    for sleeve in sleeves:
        cap = sleeve["cap_stitch_path_cm"]
        cap_length = sleeve["sleeve_cap_stitch_length_cm"]
        arcs = [arc_of_point_cm(cap, point)
                for point in sleeve["notches_cm"]]
        if len(arcs) not in (3, 4) or any(arc is None for arc in arcs):
            raise ValueError("The sleeve cap needs three pairing notches and an optional shoulder mark")
        matched = [arcs[0], cap_length - arcs[1], cap_length - arcs[2]]
        if (abs(matched[0] - front_notch_distance) > .1 or
                max(abs(actual - expected) for actual, expected in zip(
                    sorted(matched[1:]), back_notch_distances)) > .1):
            raise ValueError(
                "The sleeve cap notches do not match the bodice: "
                f"cap={matched}, front={front_notch_distance}, "
                f"back={back_notch_distances}")
        sleeve_notch_arcs[sleeve["side"]] = matched
        printed_shoulder_arcs[sleeve["side"]] = arcs[3] if len(arcs) == 4 else None
    shoulder_stations = {}
    for sleeve in sleeves:
        cap_points = [sleeve["pattern_mesh"]["vertices_cm"][index]
                      for index in sleeve["cap_mesh_indices"]]
        front_code = "A" if sleeve["side"] == "左" else "B"
        front_host = next(host for host in bodice_hosts
                          if host["code"] == front_code)
        back_host = next(host for host in bodice_hosts
                         if host["code"] == "C")
        front_length = path_length_cm(front_host[
            "armhole_stitch_paths_cm"][0])
        back_length = path_length_cm(back_host[
            "armhole_stitch_paths_cm"][1 if front_code == "A" else 0])
        try:
            index = choose_sleeve_shoulder_station(
                cap_points, front_length, back_length,
                front_notch_cm=front_notch_distance,
                back_notch_cm=max(back_notch_distances))
        except ValueError as exc:
            shoulder_stations[sleeve["side"]] = {
                "3d_trial_station_available": False,
                "reason": str(exc),
            }
            continue
        geometric_apex = min(range(len(cap_points)),
                             key=lambda candidate: cap_points[candidate][1])
        front_cap = path_length_cm(cap_points[:index + 1])
        back_cap = path_length_cm(cap_points[index:])
        shoulder_stations[sleeve["side"]] = {
            "3d_trial_station_available": True,
            "sampled_cap_index": index,
            "offset_from_geometric_apex_cm": round(
                path_length_cm(cap_points[:index + 1]) -
                path_length_cm(cap_points[:geometric_apex + 1]), 3),
            "front_cap_ease_cm": round(front_cap - front_length, 3),
            "back_cap_ease_cm": round(back_cap - back_length, 3),
            "not_marked_on_printed_pattern": True,
        }
        printed_arc = printed_shoulder_arcs[sleeve["side"]]
        shoulder_stations[sleeve["side"]][
            "printed_shoulder_mark_matches_3d_station"] = (
                printed_arc is not None and
                abs(printed_arc - front_cap) <= .1)
        shoulder_stations[sleeve["side"]][
            "not_marked_on_printed_pattern"] = printed_arc is None
    sleeve_join_audit = {
        "bodice_armhole_per_arm_cm": per_arm_armhole_cm,
        "direct_contour_armhole_per_arm_cm": (
            sum(host["armhole_contour_length_cm"] for host in bodice_hosts) / 2),
        "armhole_stitch_length_cm_by_host": {
            host["code"]: host["armhole_stitch_length_cm"]
            for host in bodice_hosts},
        "sleeve_cap_cm_by_side": {
            sleeve["side"]: sleeve["sleeve_cap_stitch_length_cm"]
            for sleeve in sleeves},
        "cap_minus_armhole_cm_by_side": {
            sleeve["side"]: sleeve["sleeve_cap_stitch_length_cm"]
            - per_arm_armhole_cm for sleeve in sleeves},
        "cap_minus_direct_contour_cm_by_side": {
            sleeve["side"]: sleeve["sleeve_cap_stitch_length_cm"]
            - sum(host["armhole_contour_length_cm"]
                  for host in bodice_hosts) / 2 for sleeve in sleeves},
        "bodice_notch_distances_from_underarm_cm_by_host": bodice_notch_arcs,
        "sleeve_notch_distances_from_underarm_cm_by_side": sleeve_notch_arcs,
        "sleeve_shoulder_stations_for_3d_trial": shoulder_stations,
        "notch_pairing_verified_on_2d_stitch_lines": True,
        "3d_armhole_join_verified": False,
        "ease_requires_distribution_at_notches": True,
    }
    darted_hem_hosts = [host["code"] for host in bodice_hosts
                        if host["hem_waist_darts"]]
    incomplete_bodice_boundaries = [
        host["code"] for host in bodice_hosts
        if not host["mesh_boundary_coverage"]["complete"]]
    return {"reference": "front-only Endministrator illustration",
            "body_cm": body.as_dict(), "panel_units": "cm",
            "side_seam_unresolved_diagnostic_only": side_warnings,
            # Clearing a paper seam mismatch is not a wearer fit or a
            # production sign-off.  These meshes are simulation inputs only.
            "do_not_cut_or_publish_as_ready": True,
            "physical_fit_and_materials_verified": False,
            "darted_hem_hosts_pending_3d_sewing": darted_hem_hosts,
            "bodice_boundary_incomplete": incomplete_bodice_boundaries,
            "simulation_input_ready": not (darted_hem_hosts or
                                           incomplete_bodice_boundaries or
                                           any(not station[
                                               "3d_trial_station_available"] or
                                               not station.get(
                                                   "printed_shoulder_mark_matches_3d_station",
                                                   False)
                                               for station in
                                               shoulder_stations.values())),
            "cut_lines_used_for_simulation": False,
            "physical_materials_measured": False,
            "panels": panels, "bodice_hosts": bodice_hosts,
            "open_bodice_width_audit": audit_open_bodice_widths(
                bodice_hosts, body.as_dict()),
            "overlays": overlays, "front_details": front_details,
            "sleeves": sleeves, "sleeve_join_audit": sleeve_join_audit,
            "lapels": lapels}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/endministrator_pattern_drape/panels.json")
    parser.add_argument("--measurements", nargs=6, type=float,
                        metavar=("BUST", "WAIST", "HIP", "HEIGHT", "SLEEVE", "SHOULDER"),
                        help="Six body measurements in centimetres")
    parser.add_argument("--disable-side-seam-truing", action="store_true",
                        help="Export the uncorrected control for comparison")
    parser.add_argument("--allow-side-mismatch-diagnostic", action="store_true",
                        help="Export a blocked pattern for controlled comparison only")
    args = parser.parse_args()
    data = export_panels(
        Measurements(*(args.measurements or (83, 66, 91, 158, 52, 37))),
        disable_side_seam_truing=args.disable_side_seam_truing,
        allow_side_mismatch_diagnostic=args.allow_side_mismatch_diagnostic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
