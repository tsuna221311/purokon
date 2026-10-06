"""Probe reproducible nearby measurements, not a population or fit sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_endministrator_size_grid import STRESS_CASES, run_case


def nearby_cases(seed: int = 20261007) -> list[tuple[int, ...]]:
    rng = random.Random(seed)
    rows = []
    for baseline in STRESS_CASES:
        rows.append(baseline)
        for _ in range(4):
            bust, waist, hip, height, sleeve, shoulder = baseline
            rows.append((bust + rng.choice((-2, -1, 1, 2)),
                         waist + rng.choice((-2, -1, 1, 2)),
                         hip + rng.choice((-2, -1, 1, 2)),
                         height, sleeve + rng.choice((-1, 0, 1)),
                         shoulder + rng.choice((-1, 0, 1))))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20261007)
    parser.add_argument("--disable-truing", action="store_true")
    args = parser.parse_args()
    results = []
    for dimensions in nearby_cases(args.seed):
        try:
            case = run_case(dimensions, args.output.parent,
                            disable_truing=args.disable_truing)
            results.append({"measurements_cm": case["measurements_cm"],
                            "digital_ready": case["digital_ready"],
                            "blockers": case["blockers"],
                            "side_seam_stitch_lengths":
                                case["side_seam_stitch_lengths"]})
        except Exception as exc:
            results.append({"measurements_cm": dimensions,
                            "digital_ready": False,
                            "exception": f"{type(exc).__name__}: {exc}"})
    report = {"purpose": "deterministic nearby-size digital stress, not real fit",
              "seed": args.seed,
              "side_seam_truing_enabled": not args.disable_truing,
              "case_count": len(results),
              "digital_ready_count": sum(row["digital_ready"] for row in results),
              "exception_count": sum("exception" in row for row in results),
              "cases": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "case_count", "digital_ready_count", "exception_count")}))


if __name__ == "__main__":
    main()
