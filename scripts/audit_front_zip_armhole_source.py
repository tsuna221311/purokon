"""Compare scaled and finalized front-zip armholes for the Endministrator.

Read-only diagnostic.  The direct contour is the actual cut-piece stitch path;
compatibility values may still refer to the unsplit measuring block.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.compatibility import armhole_length
from engine.costume_projects import get_costume_project
from engine.endministrator_armhole import front_zip_armhole_path, path_length_cm
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)
from engine.svgpath import segments_to_polyline


def audit(body: Measurements) -> dict:
    project = get_costume_project("endministrator_female", body)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    requests = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, requests, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir=str(ROOT / "output")).generate_from_selection(
        spec, body, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    scaled = [part for part in result.scaled_parts
              if part.part_type == "front_bodice_zip_panel"]
    finalized = [part for part in result.finalized_parts
                 if part.part_type == "front_bodice_zip_panel"]
    if len(scaled) != 2 or len(finalized) != 2:
        raise ValueError("Expected two scaled and two finalized zip fronts")
    return {
        "body_cm": {key: getattr(body, key) for key in
                    ("bust", "waist", "hip", "height", "sleeve_length",
                     "shoulder_width")},
        "scaled_direct_armhole_cm": [path_length_cm(front_zip_armhole_path(
            segments_to_polyline(part.segments), part.underarm_y_cm))
            for part in scaled],
        "final_direct_armhole_cm": [path_length_cm(front_zip_armhole_path(
            part.stitch_line, part.underarm_y_cm)) for part in finalized],
        "final_compatibility_armhole_cm": [armhole_length(part)
                                             for part in finalized],
    }


if __name__ == "__main__":
    samples = ((76, 60, 84, 154, 49, 35),
               (83, 66, 91, 158, 52, 37),
               (92, 74, 100, 164, 55, 39),
               (104, 88, 112, 170, 59, 43))
    print(json.dumps([audit(Measurements(*values)) for values in samples],
                     ensure_ascii=False, indent=2))
