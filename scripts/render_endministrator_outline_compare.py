"""Overlay two exported front-bodice stitch outlines for paper-trial QA."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def front_outlines(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {host["code"]: host["stitch_outline_cm"]
            for host in data["bodice_hosts"] if host["code"] in ("A", "B")}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("before", type=Path)
parser.add_argument("after", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
before, after = front_outlines(args.before), front_outlines(args.after)
if before.keys() != after.keys():
    raise ValueError("Front panel sets differ")

scale = 12
margin = 36
panels = {}
for code in sorted(before):
    xs = [point[0] for line in (before[code], after[code]) for point in line]
    ys = [point[1] for line in (before[code], after[code]) for point in line]
    left, top = min(xs), min(ys)
    width = int((max(xs) - left) * scale) + margin * 2
    height = int((max(ys) - top) * scale) + margin * 2
    canvas = Image.new("RGB", (width, height), (249, 248, 244))
    draw = ImageDraw.Draw(canvas)
    for outline, color in ((before[code], (215, 60, 52)),
                           (after[code], (22, 122, 170))):
        points = [((x - left) * scale + margin,
                   (y - top) * scale + margin) for x, y in outline]
        draw.line(points + [points[0]], fill=color, width=3, joint="curve")
    draw.text((margin, 8), f"{code}: red before / blue paper trial",
              fill=(25, 30, 35))
    panels[code] = canvas

combined = Image.new("RGB", (sum(im.width for im in panels.values()),
                             max(im.height for im in panels.values())),
                     (249, 248, 244))
offset = 0
for code in sorted(panels):
    combined.paste(panels[code], (offset, 0))
    offset += panels[code].width
args.output.parent.mkdir(parents=True, exist_ok=True)
combined.save(args.output)
print(args.output)
