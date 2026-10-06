"""Render an inspection map of the actual 2D darted bodice stitch outlines.

This visualizes stitch runs and dart legs only. It is not a cutting layout,
sewn 3D preview, or proof of physical fit.
"""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render(panel_file: Path, output: Path) -> None:
    data = json.loads(panel_file.read_text(encoding="utf-8"))
    hosts = data["bodice_hosts"]
    if [item["code"] for item in hosts] != ["A", "B", "C"]:
        raise ValueError("Expected A/B/C bodice hosts")
    image = Image.new("RGB", (1660, 690), "#f5f3ed")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for column, host in enumerate(hosts):
        outline = host["stitch_outline_cm"]
        xs = [point[0] for point in outline]
        ys = [point[1] for point in outline]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        scale = min(450 / (max_x - min_x), 480 / (max_y - min_y))
        origin_x = 50 + column * 550 + (450 - (max_x - min_x) * scale) / 2
        origin_y = 95 + (480 - (max_y - min_y) * scale) / 2

        def point(xy):
            return (origin_x + (xy[0] - min_x) * scale,
                    origin_y + (xy[1] - min_y) * scale)

        draw.rectangle((column * 550 + 12, 12, column * 550 + 538, 678),
                       outline="#d9dce0", width=2)
        draw.text((column * 550 + 34, 28),
                  f"Bodice {host['code']} / sewn hem {host['hem_stitch_width_cm']:.2f} cm",
                  fill="#15213a", font=font)
        draw.line([point(xy) for xy in outline], fill="#333d4d", width=3,
                  joint="curve")
        for left, right in host["hem_sewn_runs_cm"]:
            draw.line((point((left, host["hem_stitch_y_cm"])),
                       point((right, host["hem_stitch_y_cm"]))),
                      fill="#0d9876", width=7)
        for dart in host["hem_waist_darts"]:
            for name in ("leg_a_cm", "leg_b_cm"):
                draw.line([point(xy) for xy in dart[name]],
                          fill="#d44b50", width=5)
        draw.text((column * 550 + 34, 619),
                  f"green: sewn runs ({len(host['hem_sewn_runs_cm'])})   "
                  f"red: dart legs ({len(host['hem_waist_darts'])})",
                  fill="#15213a", font=font)
        draw.text((column * 550 + 34, 640),
                  "paper topology only / 3D sewing pending",
                  fill="#8a3440", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.panels, args.output)
    print(args.output)
