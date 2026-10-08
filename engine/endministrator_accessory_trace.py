"""Female Endministrator's yellow shoulder silhouette traced from a known front image.

The saved points describe image pixels, not millimetres.  The character art has
no calibration object, so a physical width must be supplied separately and
must never be inferred from the image.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from shapely.geometry import Polygon


SOURCE_SHA256 = "af06655393d0b769bdb578ba032175ab6968cd6ada7e256cd8c598fcdf82a694"
SOURCE_SIZE_PX = (1200, 2391)
ROI_PX = (760, 700, 1030, 900)  # left, top, right, bottom

# Frozen output of trace_yellow_silhouette() for the source above.  These
# points let the trial remain reproducible when the copyrighted art is absent.
TRACE_POINTS_PX = (
    (901, 735), (881, 746), (885, 750), (863, 771), (864, 783),
    (860, 790), (802, 840), (801, 845), (826, 873), (835, 871),
    (862, 848), (978, 847), (988, 838), (988, 828), (942, 776),
    (949, 768), (947, 761), (915, 737),
)


def trace_yellow_silhouette(image_path: str | Path) -> tuple[tuple[int, int], ...]:
    """Reproduce the front-image trace; reject a different source image."""
    path = Path(image_path)
    if sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("管理人の検証済み正面画像ではありません。別画像のROIを流用しません。")
    image = Image.open(path).convert("RGB")
    if image.size != SOURCE_SIZE_PX:
        raise ValueError("管理人の正面画像の画素寸法が一致しません。")
    left, top, right, bottom = ROI_PX
    rgb = np.asarray(image)[top:bottom, left:right].astype(np.int16)
    yellow = ((rgb[:, :, 0] > 145) & (rgb[:, :, 1] > 135)
              & (rgb[:, :, 0] - rgb[:, :, 2] > 60)
              & (rgb[:, :, 1] - rgb[:, :, 2] > 40))
    connected = ndimage.binary_closing(yellow, iterations=5)
    labels, count = ndimage.label(connected)
    if not count:
        raise ValueError("肩の黄色い領域を検出できません。")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    mask = ndimage.binary_fill_holes(labels == sizes.argmax())
    rows = []
    for row in range(mask.shape[0]):
        xs = np.flatnonzero(mask[row])
        if xs.size:
            rows.append((row + top, int(xs.min()) + left, int(xs.max()) + left))
    polygon = Polygon([(x_min, y) for y, x_min, _ in rows]
                      + [(x_max, y) for y, _, x_max in reversed(rows)])
    polygon = polygon.simplify(2.5, preserve_topology=True)
    if not polygon.is_valid or polygon.area < 1000:
        raise ValueError("輪郭の抽出結果が成立しません。")
    return tuple((round(x), round(y)) for x, y in polygon.exterior.coords[:-1])


def silhouette_for_provisional_width_cm(width_cm: float) -> list[tuple[float, float]]:
    """Scale the traced *ratio* for a labelled quotation trial, not final CAD."""
    if not 3.0 <= width_cm <= 25.0:
        raise ValueError("試作幅は3～25 cmで指定してください。実寸を別途測定する必要があります。")
    xs, ys = zip(*TRACE_POINTS_PX)
    x0, y_max = min(xs), max(ys)
    image_width = max(xs) - x0
    return [((x - x0) / image_width * width_cm,
             (y_max - y) / image_width * width_cm)
            for x, y in TRACE_POINTS_PX]
