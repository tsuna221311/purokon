"""Build the four frozen booth examples from reviewed, fixed plans.

Usage: python scripts/build_booth_demo.py ABSOLUTE_NEW_DIRECTORY
Never replaces an existing bundle. Source images are identified by SHA-256 in
engine.booth_demo; this script does not call a vision API.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.booth_demo import CASES
from engine.demo_cases import DEMO_MEASUREMENTS
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.production_quality import production_quality_report


def build_case(case, destination: Path) -> dict[str, object]:
    destination.mkdir()
    body = Measurements(**DEMO_MEASUREMENTS)
    spec = build_garment_spec(**case.spec)
    spec.construction["booth_demo"] = {
        "source_sha256": case.sha256,
        "included": list(case.included),
        "not_included": list(case.not_included),
        "disclosure": "画像自動解析ではなく、事前に構成を指定した展示用の型紙初稿。実布の仮縫いは未実施。",
    }
    result = PatternForgePipeline(output_dir=str(destination)).generate_from_selection(
        spec, body)
    report = production_quality_report(result)
    warnings = result.compatibility_warnings()
    if not report["digital_ready"] or warnings:
        raise RuntimeError(f"{case.key}: {report['blockers']} {warnings}")
    files = {}
    for kind, source in result.output_files.items():
        source = Path(source)
        if not source.is_file():
            continue
        suffix = source.suffix.lower()
        if kind not in {"pdf", "svg", "dxf", "spec_pdf"}:
            continue
        name = "pattern" + suffix if kind in {"pdf", "svg", "dxf"} else "specification.pdf"
        target = destination / name
        shutil.move(str(source), target)
        files[kind] = name
    if set(files) != {"pdf", "svg", "dxf", "spec_pdf"}:
        raise RuntimeError(f"{case.key}: expected PDF/SVG/DXF/specification, got {files}")
    payload = result.summary()
    payload.update({
        "ok": True,
        "mode": "illustration",
        "source_sha256": case.sha256,
        "digital_ready": True,
        "prepared_example": {
            "title": case.title,
            "included": list(case.included),
            "not_included": list(case.not_included),
            "message": "この画像と固定採寸に一致したため、事前に構成・縫い線を検査した展示用の型紙初稿を表示しています。画像理解APIのリアルタイム生成ではありません。実布の仮縫いは未実施です。",
        },
        "production_status": {
            "ready": True, "draft": False,
            "pending": ["実布の仮縫い", "開き・装飾・取付方法の確認"],
        },
        "quality_report": report,
        "files": files,
        "project_name": case.title + "（展示用・固定構成）",
    })
    payload.pop("output_files", None)  # temporary build-machine paths must not leak
    payload["job_id"] = "booth-" + case.key
    (destination / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"case": case.key, "parts": len(result.finalized_parts),
            "files": files, "digital_ready": report["digital_ready"]}


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    destination = Path(sys.argv[1])
    if not destination.is_absolute() or destination.exists():
        raise SystemExit("Use a new absolute destination; existing data is never replaced.")
    destination.mkdir(parents=True)
    manifest = []
    for case in CASES:
        manifest.append(build_case(case, destination / case.key))
    (destination / "manifest.json").write_text(
        json.dumps({"measurements_cm": DEMO_MEASUREMENTS, "cases": manifest},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
