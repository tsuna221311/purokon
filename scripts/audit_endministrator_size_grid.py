"""Run a declared digital pattern stress grid, never a population fit study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.costume_projects import get_costume_project
from engine.compatibility import (side_seam_edges, side_seam_length,
                                  underarm_y_of, _closed_points)
from engine.endministrator_side_seam_truing import (
    _front_side_length, true_front_side_seam)
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.production_quality import production_quality_report


# B/W/H/height/sleeve/shoulder, centimetres. These deliberately probe
# broad and narrow proportions; they are not a body-size distribution.
STRESS_CASES = (
    (68, 47, 70, 148, 47, 36),
    (72, 56, 78, 150, 48, 35),
    (76, 54, 87, 160, 50, 38),
    (76, 60, 82, 150, 48, 36),
    (80, 60, 88, 155, 49, 37),
    (83, 66, 91, 158, 51, 37),
    (86, 62, 92, 160, 52, 38),
    (88, 74, 96, 155, 50, 40),
    (90, 66, 94, 162, 52, 39),
    (92, 72, 98, 165, 54, 40),
    (94, 78, 102, 160, 51, 40),
    (96, 67, 100, 160, 50, 38),
    (98, 82, 106, 168, 54, 42),
    (100, 76, 104, 165, 54, 41),
    (102, 88, 110, 160, 52, 43),
    (104, 78, 108, 170, 56, 42),
    (108, 90, 112, 165, 54, 43),
    (112, 82, 116, 170, 57, 43),
    (116, 84, 112, 165, 54, 42),
    (120, 102, 124, 170, 57, 45),
)


def side_seam_segments(part) -> list[dict]:
    """Record stitched straight runs only, excluding dart legs and armholes."""
    points = _closed_points(part.stitch_line)
    return [{"side": side, "from_cm": p1, "to_cm": p2,
             "length_cm": ((p1[0] - p2[0]) ** 2 +
                           (p1[1] - p2[1]) ** 2) ** .5}
            for _index, side, p1, p2 in
            side_seam_edges(points, .5, underarm_y_of(part))]


def run_case(dimensions: tuple[int, ...], output_dir: Path,
             *, disable_truing: bool = False) -> dict:
    body = Measurements(*dimensions)
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    requests = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, requests, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    if disable_truing:
        spec.construction["disable_endministrator_side_seam_truing"] = True
    result = PatternForgePipeline(output_dir=str(output_dir)).generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    audit = production_quality_report(result)
    fronts = [part for part in result.finalized_parts
              if part.part_type == "front_bodice_zip_panel"]
    backs = [part for part in result.finalized_parts
             if part.part_type == "back_bodice"]
    back_length = side_seam_length(backs[0]) if len(backs) == 1 else None
    seam_lengths = {
        "front_left_cm": side_seam_length(fronts[0]) if len(fronts) == 2 else None,
        "front_right_cm": side_seam_length(fronts[1]) if len(fronts) == 2 else None,
        "back_half_cm": back_length / 2 if back_length is not None else None,
    }
    seam_segments = {
        "front_left": side_seam_segments(fronts[0]) if len(fronts) == 2 else [],
        "front_right": side_seam_segments(fronts[1]) if len(fronts) == 2 else [],
        "back_both_sides": side_seam_segments(backs[0]) if len(backs) == 1 else [],
    }
    trial = []
    scaled_fronts = [part for part in result.scaled_parts
                     if part.part_type == "front_bodice_zip_panel"]
    scaled_backs = [part for part in result.scaled_parts
                    if part.part_type == "back_bodice"]
    if len(scaled_fronts) == 2 and len(scaled_backs) == 1:
        back_scaled_length = _front_side_length(
            scaled_backs[0], scaled_backs[0].segments)
        if back_scaled_length is not None:
            for part in scaled_fronts:
                _adjusted, record = true_front_side_seam(
                    part, back_scaled_length / 2)
                trial.append(record)
    return {"measurements_cm": body.as_dict(),
            "digital_ready": audit["digital_ready"],
            "blockers": audit["blockers"],
            "side_seam_stitch_lengths": seam_lengths,
            "side_seam_stitch_segments": seam_segments,
            "side_seam_truing_independent_diagnostic": trial,
            "side_seam_truing_applied":
                spec.construction.get("side_seam_truing_report")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disable-truing", action="store_true",
                        help="Reproduce the uncorrected control for comparison")
    args = parser.parse_args()
    rows = []
    for dimensions in STRESS_CASES:
        try:
            rows.append(run_case(dimensions, args.output.parent,
                                 disable_truing=args.disable_truing))
        except Exception as exc:
            rows.append({"measurements_cm": dimensions,
                         "digital_ready": False,
                         "exception": f"{type(exc).__name__}: {exc}"})
    report = {
        "purpose": "digital drafting stress grid, not fit or commercial quality",
        "side_seam_truing_enabled": not args.disable_truing,
        "case_count": len(rows),
        "digital_ready_count": sum(bool(row["digital_ready"]) for row in rows),
        "exception_count": sum("exception" in row for row in rows),
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "case_count", "digital_ready_count", "exception_count")}))


if __name__ == "__main__":
    main()
