"""Audit open-coat paper strip widths at the preview torso height stations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pattern_width_audit import audit_open_bodice_widths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = json.loads(args.panels.read_text(encoding="utf-8"))
    report = audit_open_bodice_widths(source["bodice_hosts"], source["body_cm"])
    report["source_pattern_json"] = str(args.panels.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for row in report["sections"]:
        widths = row["paper_widths"]
        print(f"{row['station']}: A={widths['A']['material_width_cm']:.2f}, "
              f"B={widths['B']['material_width_cm']:.2f}, "
              f"C={widths['C']['material_width_cm']:.2f}; "
              f"open paper sum={row['open_paper_material_sum_cm']:.2f} cm; "
              f"body proxy reference={row['body_proxy_reference_cm']:.2f} cm")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
