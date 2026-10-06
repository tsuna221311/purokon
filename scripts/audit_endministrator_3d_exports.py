"""Stress the 2D-to-3D panel export without claiming cloth/fit validity."""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_endministrator_size_grid import STRESS_CASES
from scripts.audit_endministrator_nearby_sizes import nearby_cases
from scripts.export_endministrator_panels import export_panels
from engine.measurements import Measurements


def max_triangle_edge_cm(mesh: dict) -> float:
    vertices = mesh["vertices_cm"]
    return round(max(math.dist(vertices[a], vertices[b])
                     for face in mesh["faces"]
                     for a, b in ((face[0], face[1]),
                                  (face[1], face[2]),
                                  (face[2], face[0]))), 3)


def audit(cases=STRESS_CASES) -> dict:
    rows = []
    for dimensions in cases:
        row = {"measurements_cm": dimensions}
        try:
            data = export_panels(Measurements(*dimensions))
            row.update({
                "exported": True,
                "simulation_input_ready": data["simulation_input_ready"],
                "darted_hem_hosts_pending_3d_sewing": data[
                    "darted_hem_hosts_pending_3d_sewing"],
                "bodice_boundary_incomplete": data[
                    "bodice_boundary_incomplete"],
                "do_not_cut_or_publish_as_ready": data[
                    "do_not_cut_or_publish_as_ready"],
                "host_mesh_faces": {host["code"]: len(host["pattern_mesh"]["faces"])
                                    for host in data["bodice_hosts"]},
                "host_boundary_gap_patch_faces": {
                    host["code"]: host["pattern_mesh"].get(
                        "boundary_gap_patch_faces", 0)
                    for host in data["bodice_hosts"]},
                "host_max_triangle_edge_cm": {
                    host["code"]: max_triangle_edge_cm(host["pattern_mesh"])
                    for host in data["bodice_hosts"]},
                "front_detail_mesh_strategy": {
                    detail["host_code"]: detail["mesh_strategy"]
                    for detail in data["front_details"]},
                "front_detail_max_triangle_edge_cm": {
                    detail["host_code"]: max_triangle_edge_cm(
                        detail["pattern_mesh"])
                    for detail in data["front_details"]},
            })
        except Exception as exc:
            row.update({"exported": False,
                        "exception": f"{type(exc).__name__}: {exc}"})
        rows.append(row)
    return {
        "purpose": "panel topology stress, not a 3D garment or physical fit audit",
        "case_count": len(rows),
        "exported_count": sum(row["exported"] for row in rows),
        "simulation_input_ready_count": sum(row.get("simulation_input_ready", False)
                                             for row in rows),
        "dart_pending_count": sum(bool(row.get(
            "darted_hem_hosts_pending_3d_sewing")) for row in rows),
        "incomplete_bodice_boundary_count": sum(bool(row.get(
            "bodice_boundary_incomplete")) for row in rows),
        "front_detail_boundary_fallback_count": sum(
            strategy == "boundary_constrained_fallback"
            for row in rows for strategy in
            row.get("front_detail_mesh_strategy", {}).values()),
        "bodice_boundary_gap_patch_faces": sum(
            count for row in rows for count in
            row.get("host_boundary_gap_patch_faces", {}).values()),
        "cases": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nearby", action="store_true",
                        help="Probe the fixed 100-case nearby-size grid")
    args = parser.parse_args()
    report = audit(nearby_cases() if args.nearby else STRESS_CASES)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "case_count", "exported_count", "simulation_input_ready_count",
        "dart_pending_count", "incomplete_bodice_boundary_count",
        "front_detail_boundary_fallback_count",
        "bodice_boundary_gap_patch_faces")}))
