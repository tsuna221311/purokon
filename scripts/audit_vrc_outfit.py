"""Print a structural quality report for a GLB outfit export."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.vrc_outfit_audit import audit_gltf, read_glb_json
from engine.component_coverage import audit_component_nodes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("glb", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--component-manifest", type=Path,
                        help="Optional reviewer-supplied commercial component checklist JSON")
    args = parser.parse_args()
    gltf = read_glb_json(args.glb)
    report = audit_gltf(gltf)
    if args.component_manifest:
        manifest = json.loads(args.component_manifest.read_text(encoding="utf-8"))
        report["component_coverage"] = audit_component_nodes(gltf, manifest["components"])
        report["component_coverage"]["benchmark_source"] = manifest.get("source", "")
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
