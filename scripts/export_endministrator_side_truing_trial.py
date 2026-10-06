"""Export a labelled, experimental Endministrator paper pattern for QA."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.costume_projects import get_costume_project
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.production_quality import production_quality_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", nargs=6, type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    body = Measurements(*args.measurements)
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    extras = [request for panel in project.custom_panel_specs
              for request in build_custom_panel_requests(
                  panel.label, panel.points_cm, quantity=panel.quantity,
                  mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, extras, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir=str(args.output_dir)).generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm)
    quality = production_quality_report(result)
    report = {
        "status": "experimental paper pattern, not a fitted commercial garment",
        "measurements_cm": body.as_dict(),
        "output_files": result.output_files,
        "side_seam_truing_report":
            spec.construction.get("side_seam_truing_report"),
        "digital_ready": quality["digital_ready"],
        "physical_signoff_required": quality["physical_signoff_required"],
        "blockers": quality["blockers"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "trial_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
