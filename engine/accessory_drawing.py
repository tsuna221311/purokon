"""Dimensioned A4 drawings for the accessory vendor package.

The flat outline is the calibrated, pre-bend contour.  Front/side silhouettes
and their bounding dimensions come from the exact triangles sent as STL.
Dimensions, not the page scale, are authoritative for manufacturing.
"""

from __future__ import annotations

from io import BytesIO
from typing import Sequence

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .pdf_export import _LABEL_FONT, _require_jp_label_font, unprintable_characters


PAGE_W, PAGE_H = landscape(A4)


def _number(value: float) -> str:
    # Match the 0.001 mm bounding dimensions written to manifest.json.
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _dim_horizontal(c: canvas.Canvas, left: float, right: float,
                    base_y: float, line_y: float, label: str) -> None:
    c.setStrokeColorRGB(.13, .29, .43)
    c.setFillColorRGB(.13, .29, .43)
    c.setLineWidth(.65)
    for x in (left, right):
        c.line(x, base_y + 3, x, line_y + (3 if line_y > base_y else -3))
    c.line(left, line_y, right, line_y)
    for x, direction in ((left, 1), (right, -1)):
        p = c.beginPath()
        p.moveTo(x, line_y)
        p.lineTo(x + direction * 5, line_y + 2)
        p.lineTo(x + direction * 5, line_y - 2)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
    c.setFillColorRGB(.13, .29, .43)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString((left + right) / 2, line_y + 5, label)


def _dim_vertical(c: canvas.Canvas, bottom: float, top: float,
                  base_x: float, line_x: float, label: str) -> None:
    c.setStrokeColorRGB(.13, .29, .43)
    c.setFillColorRGB(.13, .29, .43)
    c.setLineWidth(.65)
    for y in (bottom, top):
        c.line(base_x - 3, y, line_x - 3, y)
    c.line(line_x, bottom, line_x, top)
    for y, direction in ((bottom, 1), (top, -1)):
        p = c.beginPath()
        p.moveTo(line_x, y)
        p.lineTo(line_x - 2, y + direction * 5)
        p.lineTo(line_x + 2, y + direction * 5)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
    c.saveState()
    c.translate(line_x - 8, (bottom + top) / 2)
    c.rotate(90)
    c.setFillColorRGB(.13, .29, .43)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(0, 0, label)
    c.restoreState()


def _draw_ring(c: canvas.Canvas, path, coords, x: float, y: float,
               scale: float, min_x: float, min_y: float) -> None:
    points = list(coords)
    if not points:
        return
    path.moveTo(x + (points[0][0] - min_x) * scale,
                y + (points[0][1] - min_y) * scale)
    for px, py in points[1:]:
        path.lineTo(x + (px - min_x) * scale, y + (py - min_y) * scale)
    path.close()


def _draw_polygon(c: canvas.Canvas, polygon: Polygon, x: float, y: float,
                  scale: float, min_x: float, min_y: float,
                  *, show_interiors: bool = True) -> None:
    path = c.beginPath()
    _draw_ring(c, path, polygon.exterior.coords, x, y, scale, min_x, min_y)
    if show_interiors:
        for ring in polygon.interiors:
            _draw_ring(c, path, ring.coords, x, y, scale, min_x, min_y)
    c.setFillColorRGB(.88, .94, .93)
    c.setStrokeColorRGB(.08, .27, .29)
    c.setLineWidth(.95)
    c.drawPath(path, fill=1, stroke=1, fillMode=0)


def _draw_shape(c: canvas.Canvas, shape, x: float, y: float,
                scale: float, min_x: float, min_y: float,
                *, show_interiors: bool = True) -> None:
    if shape.is_empty:
        return
    if shape.geom_type == "Polygon":
        _draw_polygon(c, shape, x, y, scale, min_x, min_y,
                      show_interiors=show_interiors)
    elif hasattr(shape, "geoms"):
        for child in shape.geoms:
            _draw_shape(c, child, x, y, scale, min_x, min_y,
                        show_interiors=show_interiors)


def _projection(triangles, a: int, b: int):
    faces = []
    for triangle in triangles:
        face = Polygon([(vertex[a], vertex[b]) for vertex in triangle])
        if face.area > 1e-8:
            faces.append(face)
    return unary_union(faces) if faces else Polygon()


def _view(c: canvas.Canvas, shape, *, box: tuple[float, float, float, float],
          title: str, x_label: str, y_label: str,
          show_interiors: bool = True) -> tuple[float, float, float]:
    bx, by, bw, bh = box
    c.setStrokeColorRGB(.79, .84, .84)
    c.setLineWidth(.7)
    c.roundRect(bx, by, bw, bh, 5, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(.08, .21, .23)
    c.drawString(bx + 12, by + bh - 17, title)
    min_x, min_y, max_x, max_y = shape.bounds
    span_x, span_y = max_x - min_x, max_y - min_y
    usable_w, usable_h = bw - 86, bh - 76
    scale = min(usable_w / max(span_x, .1), usable_h / max(span_y, .1), 4.0)
    origin_x = bx + (bw - span_x * scale) / 2 + 8
    origin_y = by + (bh - span_y * scale) / 2 + 3
    _draw_shape(c, shape, origin_x, origin_y, scale, min_x, min_y,
                show_interiors=show_interiors)
    _dim_horizontal(c, origin_x, origin_x + span_x * scale,
                    origin_y + span_y * scale, by + bh - 32,
                    f"{x_label} {_number(span_x)} mm")
    _dim_vertical(c, origin_y, origin_y + span_y * scale,
                  origin_x, bx + 24, f"{y_label} {_number(span_y)} mm")
    return origin_x, origin_y, scale


def build_dimensioned_drawings(rows: Sequence[dict], *,
                               thickness_mm: float,
                               curvature_radius_mm: float | None,
                               curvature_height_radius_mm: float | None,
                               curve_axis: str,
                               magnet_depth_mm: float | None,
                               material_profile: str = "consult") -> bytes:
    """Return a one-page-per-piece vector PDF for review with a print vendor."""
    _require_jp_label_font()
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    c.setTitle("PatternForge accessory dimensioned drawings")
    for page, row in enumerate(rows, 1):
        polygon = row["polygon"]
        triangles = row["triangles"]
        label = row["label"]
        pockets = row["pockets"]
        dims = row["dimensions_mm"]
        c.setFillColorRGB(.07, .22, .24)
        c.rect(0, PAGE_H - 53, PAGE_W, 53, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(28, PAGE_H - 32, "PatternForge | ACCESSORY DIMENSION DRAWING")
        c.setFont("Helvetica", 9)
        c.drawRightString(PAGE_W - 28, PAGE_H - 30, f"PART {page:03d} / {len(rows):03d}")
        c.setFillColorRGB(.08, .21, .23)
        if not unprintable_characters(label):
            c.setFont(_LABEL_FONT, 11)
            c.drawString(32, PAGE_H - 72, label[:40])
        else:
            c.setFont("Helvetica", 9)
            c.drawString(32, PAGE_H - 70, "Part name: see manifest.json (unsupported PDF glyphs)")
        c.setFont("Helvetica", 8)
        c.drawRightString(PAGE_W - 30, PAGE_H - 70,
                          "UNITS: mm | Dimensions govern; drawing not to scale")
        c.setFont("Helvetica-Bold", 8)
        c.drawString(530, PAGE_H - 85, f"DWG {row['drawing_id']} | REV: AUTO DRAFT")

        top_x, top_y, top_scale = _view(
            c, polygon, box=(30, 221, 475, 286),
            title="FLAT OUTLINE (before bending)", x_label="X", y_label="Y")
        for index, ring in enumerate(polygon.interiors, 1):
            hole = Polygon(ring)
            center = hole.centroid
            x, y = top_x + center.x * top_scale, top_y + center.y * top_scale
            c.setFont("Helvetica-Bold", 7)
            c.setFillColorRGB(.60, .12, .16)
            c.drawString(x + 5, y + 5, f"C{index}")
        for index, pocket in enumerate(pockets, 1):
            c.setStrokeColorRGB(.60, .12, .16)
            c.setDash(3, 2)
            coords = list(pocket.exterior.coords)
            path = c.beginPath()
            _draw_ring(c, path, coords, top_x, top_y, top_scale, 0, 0)
            c.drawPath(path, fill=0, stroke=1)
            c.setDash()
            center = pocket.centroid
            c.setFont("Helvetica-Bold", 7)
            c.drawString(top_x + center.x * top_scale + 5,
                         top_y + center.y * top_scale + 5, f"P{index}")

        front = _projection(triangles, 0, 2)
        side = _projection(triangles, 1, 2)
        _view(c, front, box=(30, 65, 475, 145),
              title="FRONT / final mesh", x_label="X", y_label="Z",
              show_interiors=False)
        _view(c, side, box=(516, 65, 296, 145),
              title="SIDE / final mesh", x_label="Y", y_label="Z",
              show_interiors=False)

        c.setStrokeColorRGB(.79, .84, .84)
        c.roundRect(516, 221, 296, 286, 5, stroke=1, fill=0)
        c.setFillColorRGB(.08, .21, .23)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(530, 486, "DIMENSIONS / FEATURES")
        c.setFont("Helvetica", 8)
        lines = [
            f"Final mesh X x Y x Z: {_number(dims['x'])} x {_number(dims['y'])} x {_number(dims['z'])} mm",
            f"Nominal wall thickness: {_number(thickness_mm)} mm",
            "Datum: flat outline lower-left (X=0, Y=0)",
            "Process request: " + {
                "pa12": "PA12 nylon / SLS candidate",
                "tough_resin": "tough resin / SLA candidate",
                "prototype": "PLA or PETG / FDM prototype",
                "consult": "vendor to propose",
            }[material_profile],
        ]
        if curvature_radius_mm is not None:
            lines.append(f"Bend axis: {curve_axis}; inner R={_number(curvature_radius_mm)} mm")
            if curvature_height_radius_mm is not None:
                lines.append(f"Second inner R={_number(curvature_height_radius_mm)} mm")
        else:
            lines.append("Bend: none (flat)")
        for index, ring in enumerate(polygon.interiors, 1):
            hole = Polygon(ring)
            cx, cy = hole.centroid.x, hole.centroid.y
            left, bottom, right, top = hole.bounds
            wx, hy = right - left, top - bottom
            kind = (f"dia {_number(wx)}" if abs(wx - hy) < .2
                    else f"slot {_number(wx)} x {_number(hy)}")
            lines.append(f"C{index} THROUGH {kind}; center X={_number(cx)}, Y={_number(cy)}")
        for index, pocket in enumerate(pockets, 1):
            cx, cy = pocket.centroid.x, pocket.centroid.y
            diameter = pocket.bounds[2] - pocket.bounds[0]
            lines.append(f"P{index} POCKET dia {_number(diameter)} depth {_number(magnet_depth_mm or 0)}")
            lines.append(f"     center X={_number(cx)}, Y={_number(cy)} (not through)")
        y = 466
        for line in lines:
            if y < 260:
                raise ValueError("Accessory drawing feature list exceeds page")
            c.drawString(530, y, line)
            y -= 15
        c.setStrokeColorRGB(.78, .83, .83)
        c.line(530, 273, 798, 273)
        c.setFont("Helvetica", 7.5)
        c.drawString(530, 259, "Fit, tolerances, orientation and supports: vendor approval required.")
        c.drawString(530, 247, "Color, finish and hardware: see ORDER_NOTES_JA.txt.")
        c.drawString(530, 235, "Do not print this PDF as a 1:1 cutting template.")
        c.setStrokeColorRGB(.78, .83, .83)
        c.line(28, 48, PAGE_W - 28, 48)
        c.setFont("Helvetica", 7)
        c.drawString(30, 35, "FOR QUOTATION / SAMPLE ONLY. Match STL / 3MF; verify physical sample before final order.")
        c.drawRightString(PAGE_W - 30, 35, f"PAGE {page} / {len(rows)}")
        c.showPage()
    c.save()
    return output.getvalue()
