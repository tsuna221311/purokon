"""Export the three disclosed, fixed-input presentation cases.

Usage: python scripts/build_presentation_demo.py ABSOLUTE_OUTPUT_DIRECTORY
The destination must not already exist, so an older backup is never replaced.
No network call or image-understanding API is used.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.costume_projects import get_costume_project
from engine.demo_cases import DEMO_CASES, DEMO_MEASUREMENTS
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.production_quality import production_quality_report


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/build_presentation_demo.py ABSOLUTE_OUTPUT_DIRECTORY")
    destination = Path(sys.argv[1])
    if not destination.is_absolute() or destination.exists():
        raise SystemExit("Use an absolute, not-yet-existing output directory.")
    body = Measurements(**DEMO_MEASUREMENTS)
    destination.mkdir(parents=True)
    manifest = {"measurements_cm": DEMO_MEASUREMENTS, "cases": []}
    for case in DEMO_CASES:
        project = get_costume_project(case["project_key"], body)
        spec = build_garment_spec(**project.garment_spec_kwargs)
        extras = [request for panel in project.custom_panel_specs
                  for request in build_custom_panel_requests(
                      panel.label, panel.points_cm, quantity=panel.quantity,
                      mirror=panel.mirror, allow_split=panel.allow_split)]
        if extras:
            spec.parts = merge_custom_panel_requests(
                spec.parts, extras, princess_line=spec.princess_line)
        spec.construction["costume_project_brief"] = project.as_dict()
        case_dir = destination / case["id"]
        case_dir.mkdir()
        result = PatternForgePipeline(output_dir=str(case_dir)).generate_from_selection(
            spec, body, lining=project.lining,
            worn_over_bust_cm=project.worn_over_bust_cm,
            shoulder_drop_cm=project.shoulder_drop_cm)
        report = production_quality_report(result)
        warnings = result.compatibility_warnings()
        if not report["digital_ready"] or warnings:
            raise RuntimeError(f"{case['id']} failed digital check: {report['blockers']} {warnings}")
        files = {key: str(Path(path).relative_to(destination))
                 for key, path in result.output_files.items()
                 if Path(path).is_file()}
        if not {"pdf", "svg", "spec_pdf"} <= files.keys():
            raise RuntimeError(f"{case['id']} did not export every required demo file")
        if case["sketch"]:
            sketch_source = ROOT / "web" / "static" / case["sketch"]
            sketch_target = case_dir / sketch_source.name
            shutil.copy2(sketch_source, sketch_target)
            files["three_view_sketch"] = str(sketch_target.relative_to(destination))
        manifest["cases"].append({
            "id": case["id"], "title": case["title"],
            "project_key": project.key, "parts": len(result.finalized_parts),
            "digital_ready": True, "files": files,
            "limitations": list(project.limitations),
        })
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
