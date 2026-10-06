"""Experimental exterior front-panel pattern derived from a finished bodice.

This is not the internal zip facing.  It is the visible contrasting panel in
the Endministrator reference.  A host edge is shared in 2D, but its attachment
method, roll, fabric and wear behaviour still need a toile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon, box
from shapely.ops import linemerge

from .seam import FinalizedPart, finalize_from_stitch_line


@dataclass(frozen=True)
class DraftedFrontDetail:
    part: FinalizedPart
    host_attachment_line_cm: tuple[tuple[float, float], ...]
    host_identifier: str


def draft_exterior_front_panel(host: FinalizedPart, *, width_cm: float = 8.5
                               ) -> DraftedFrontDetail:
    """Cut a 2D contrast strip along the host's actual centre-front outline.

    The curved attachment edge is taken from the finalized host stitch line,
    not a separately guessed curve.  The opposite edge/extent is a provisional
    design hypothesis, not an extracted garment pattern.
    """
    if host.part_type != "front_bodice_zip_panel" or width_cm <= 2:
        raise ValueError("A zipped front bodice and positive panel width are required")
    host_shape = Polygon(host.stitch_line)
    if not host_shape.is_valid or host_shape.area <= 0:
        raise ValueError("The host stitch outline is invalid")
    left, bottom, right, top = host_shape.bounds
    height = top - bottom
    if height < 30 or right - left < width_cm + 2:
        raise ValueError("The host is too small for a front detail panel")
    first_y = bottom + height * .12
    last_y = bottom + height * .90
    outer, inner = [], []
    for index in range(33):
        progress = index / 32
        y = first_y + (last_y - first_y) * progress
        section = host_shape.intersection(LineString([
            (left - 2, y), (right + 2, y)]))
        if section.is_empty:
            raise ValueError("Cannot find a continuous front-body cross section")
        section_left, _y0, section_right, _y1 = section.bounds
        taper = .72 + .28 * math.sin(math.pi * progress)
        inside_x = min(section_left + width_cm * taper, section_right - 1)
        if inside_x - section_left < 2:
            raise ValueError("The contrast panel pinches below 2 cm")
        # Keep this edge safely outside the host; clipping then copies the
        # actual centre-front stitch path instead of a faceted approximation.
        outer.append((left - 2, y))
        inner.append((inside_x, y))
    band = Polygon(outer + list(reversed(inner)))
    clipped = host_shape.intersection(band)
    if clipped.geom_type != "Polygon" or not clipped.is_valid or clipped.area < 50:
        raise ValueError("Contrast panel is fragmented or too small")
    # Overlaying two independently noded polygon boundaries can lose exact
    # collinearity along host segments at floating-point precision.  Select
    # the centre-front host edge from the original stitch geometry instead,
    # then verify it lies on the clipped panel edge.
    # The centre-front edge slopes inward toward the neckline.  A 3 cm
    # search strip truncated a valid 54.8 cm attachment to 31.8 cm on a
    # broad-hip block.  Search within the inner two thirds of this panel,
    # still short of its dart-side free edge.
    shared = host_shape.boundary.intersection(box(
        left - .1, first_y, left + min(width_cm * .65, 5.5), last_y))
    raw_lines = ([shared] if shared.geom_type == "LineString" else
                 [geometry for geometry in getattr(shared, "geoms", ())
                  if geometry.geom_type == "LineString"])
    merged = linemerge(raw_lines) if len(raw_lines) > 1 else (
        raw_lines[0] if raw_lines else None)
    lines = ([merged] if merged is not None and
             merged.geom_type == "LineString" else
             list(merged.geoms) if merged is not None and
             merged.geom_type == "MultiLineString" else [])
    if not lines:
        raise ValueError(f"Contrast panel has no shared bodice stitch edge ({shared.geom_type})")
    attachment = max(lines, key=lambda line: line.length)
    # The real centre-front can curve into the neckline before the nominal
    # 90%-height target, especially on broad-hip blocks.  The separate lapel
    # covers that upper region.  Require one substantial continuous sewn edge
    # and independently verify below that it lies on the clipped panel.
    if len(lines) != 1 or attachment.length < 30.0:
        raise ValueError(f"Contrast panel attachment is not continuous: "
                         f"{attachment.length:.2f}cm vs {last_y-first_y:.2f}cm, "
                         f"pieces={[round(line.length, 2) for line in lines]}")
    if attachment.difference(clipped.boundary.buffer(1e-5)).length > 1e-4:
        raise ValueError("The selected bodice edge is not on the contrast panel")
    attachment_points = list(attachment.coords)
    if attachment_points[0][1] > attachment_points[-1][1]:
        attachment_points.reverse()
    label = f"管理人コート・前面明灰色パネル{host.label_suffix or ''}"
    part = finalize_from_stitch_line(
        "custom_panel", label, list(clipped.exterior.coords)[:-1],
        seam_allowance_cm=host.seam_allowance_cm,
        notch_points=[tuple(attachment.interpolate(fraction, normalized=True).coords[0])
                      for fraction in (.25, .5, .75)],
        reference_lines=[("本体前端へ仮止め（試作）", attachment_points)])
    return DraftedFrontDetail(part=part,
                              host_attachment_line_cm=tuple(attachment_points),
                              host_identifier=f"{host.part_type}:{host.label_suffix}")


def draft_neck_lapel(host: FinalizedPart) -> DraftedFrontDetail:
    """Provisional neckline flap with an exact host attachment curve.

    The outline is an inferred costume design, not the source garment's
    confirmed lapel construction.  Its long curved edge follows the actual
    neckline of a generated front bodice; the free angular edge is a design
    hypothesis for a separate fabric piece.
    """
    if host is None or host.part_type != "front_bodice_zip_panel":
        raise ValueError("A zipped front bodice is required")
    host_shape = Polygon(host.stitch_line)
    if not host_shape.is_valid or host_shape.area <= 0:
        raise ValueError("The host stitch outline is invalid")
    left, bottom, _right, top = host_shape.bounds
    height = top - bottom
    if height < 30:
        raise ValueError("The front bodice is too short for a lapel")
    outline = list(host.stitch_line)
    neck_index = min(range(len(outline)), key=lambda index: outline[index][1])
    neck = outline[neck_index]
    next_point = outline[(neck_index + 1) % len(outline)]
    previous_point = outline[(neck_index - 1) % len(outline)]
    direction = 1 if next_point[0] < neck[0] else -1
    adjacent = next_point if direction == 1 else previous_point
    if not adjacent[0] < neck[0] or not adjacent[1] > neck[1]:
        raise ValueError("Cannot identify the centre-front neckline")
    attachment = [neck]
    for step in range(1, len(outline)):
        point = outline[(neck_index + direction * step) % len(outline)]
        prior = attachment[-1]
        if (point[0] >= prior[0] - .001 or
                point[1] <= prior[1] + .001 or
                point[1] >= bottom + height * .16):
            break
        attachment.append(point)
    if len(attachment) < 5 or LineString(attachment).length < 8:
        raise ValueError("The extracted neckline is too short")
    # Extend the free edge to chest level instead of reducing the lapel to a
    # narrow shoulder tab.  These proportions remain illustrative until a
    # side view or physical reference fixes the fold and roll line.
    front_tip = (left + 2.5, bottom + height * .40)
    outer_tip = (neck[0] + 7, bottom + height * .34)
    shape = Polygon(attachment + [front_tip, outer_tip])
    if not shape.is_valid or shape.area < 70:
        raise ValueError("Inferred lapel leaves the front bodice or degenerates")
    # The provisional straight free edge can cross a curved host outline by
    # fractions of a square centimetre at different measurements.  Trim only
    # this small overshoot; a genuinely out-of-body design must still fail.
    outside_area = shape.difference(host_shape).area
    if outside_area > min(.5, shape.area * .005):
        raise ValueError("Inferred lapel leaves the front bodice or degenerates")
    if outside_area > 1e-6:
        shape = shape.intersection(host_shape)
        if shape.geom_type != "Polygon" or not shape.is_valid or shape.area < 70:
            raise ValueError("Inferred lapel clipping is not a sewable panel")
    seam = LineString(attachment)
    if seam.difference(shape.boundary.buffer(1e-5)).length > 1e-4:
        raise ValueError("Inferred lapel lost its neckline attachment")
    label = f"管理人コート・首ぐりラペル試作{host.label_suffix or ''}"
    part = finalize_from_stitch_line(
        "custom_panel", label, list(shape.exterior.coords)[:-1],
        seam_allowance_cm=host.seam_allowance_cm,
        notch_points=[tuple(seam.interpolate(fraction, normalized=True).coords[0])
                      for fraction in (.25, .5, .75)],
        reference_lines=[("首ぐりへの取付線（試作）", attachment),
                         ("折り位置は仮縫いで確定", [attachment[-1], outer_tip])])
    return DraftedFrontDetail(
        part=part, host_attachment_line_cm=tuple(attachment),
        host_identifier=f"{host.part_type}:{host.label_suffix}")
