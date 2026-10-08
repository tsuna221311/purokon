"""Keep digitally blocked exports usable for inspection, not cutting."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from .pdf_export import _LABEL_FONT, _require_jp_label_font


def _warning_overlay(width: float, height: float) -> BytesIO:
    stream = BytesIO()
    page = canvas.Canvas(stream, pagesize=(width, height))
    page.saveState()
    page.setFillColorRGB(0.72, 0.04, 0.08)
    page.setFillAlpha(0.17)
    page.translate(width / 2, height / 2)
    page.rotate(32)
    page.setFont("Helvetica-Bold", min(40, max(20, width / 11)))
    page.drawCentredString(0, 0, "DRAFT - NOT FOR CUTTING")
    page.restoreState()
    page.saveState()
    page.setFillColorRGB(0.72, 0.04, 0.08)
    page.setFont(_LABEL_FONT, 11)
    page.drawCentredString(width / 2, height - 17, "検査不合格・裁断禁止")
    page.restoreState()
    page.save()
    stream.seek(0)
    return stream


def mark_blocked_pdfs(output_files: dict[str, str]) -> None:
    """Atomically replace each generated PDF with a visibly blocked copy.

    Stage every replacement before changing any original. SVG and DXF are
    handled separately by :func:`block_cutting_exports`.
    """
    paths = list(dict.fromkeys(
        Path(path) for path in output_files.values()
        if str(path).lower().endswith(".pdf")
    ))
    if not paths:
        return
    _require_jp_label_font()
    staged: list[tuple[Path, Path]] = []
    try:
        for path in paths:
            reader = PdfReader(str(path))
            writer = PdfWriter()
            for source_page in reader.pages:
                width = float(source_page.mediabox.width)
                height = float(source_page.mediabox.height)
                overlay = _warning_overlay(width, height)
                source_page.merge_page(PdfReader(overlay).pages[0])
                writer.add_page(source_page)
            temp = path.with_name(path.name + ".quality.tmp")
            staged.append((path, temp))
            with temp.open("wb") as handle:
                writer.write(handle)
        for path, temp in staged:
            os.replace(temp, path)
    finally:
        for _path, temp in staged:
            if temp.exists():
                temp.unlink()


def _blocked_svg_markup(source: str) -> str:
    """Add a prominent, scale-aware inspection watermark to a generated SVG."""
    if 'id="patternforge-draft-watermark"' in source:
        return source
    closing = source.rfind("</svg>")
    view_box = re.search(r'viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"',
                         source[:1000])
    if closing < 0 or view_box is None:
        raise ValueError("Generated SVG has no closing tag or viewBox")
    x, y, width, height = (float(value) for value in view_box.groups())
    if width <= 0 or height <= 0:
        raise ValueError("Generated SVG has an invalid viewBox")
    middle_x, middle_y = x + width / 2, y + height / 2
    font = min(4.0, width / 24)
    english_font = font * 0.75
    band_height = font * 5
    banner = f'''<g id="patternforge-draft-watermark" pointer-events="none">
  <rect x="{x}" y="{y}" width="{width}" height="{height}"
        fill="#fff" fill-opacity="0.18" />
  <rect x="{x}" y="{middle_y - band_height / 2}"
        width="{width}" height="{band_height}" fill="#fff" fill-opacity="0.88" />
  <text x="{middle_x}" y="{middle_y - font * 0.1}" text-anchor="middle"
        font-family="PatternForgeJP,sans-serif" font-weight="700" font-size="{font}"
        fill="#b00020">検査不合格・裁断禁止</text>
  <text x="{middle_x}" y="{middle_y + font * 1.15}" text-anchor="middle"
        font-family="sans-serif" font-weight="700" font-size="{english_font}"
        fill="#b00020">DRAFT - NOT FOR CUTTING</text>
  <rect x="{x}" y="{y}" width="{width}" height="{font * 3.0}"
        fill="#fff" fill-opacity="0.94" />
  <text x="{middle_x}" y="{y + font * 1.25}" text-anchor="middle"
        font-family="PatternForgeJP,sans-serif" font-weight="700" font-size="{font}"
        fill="#b00020">検査不合格・裁断禁止</text>
  <text x="{middle_x}" y="{y + font * 2.35}" text-anchor="middle"
        font-family="sans-serif" font-weight="700" font-size="{english_font}"
        fill="#b00020">DRAFT - NOT FOR CUTTING</text>
</g>'''
    return source[:closing] + banner + source[closing:]


def block_cutting_exports(output_files: dict[str, str], output_dir: str) -> None:
    """Watermark generated SVGs and withhold generated DXFs after a failed gate.

    DXF geometry has no dependable human-visible warning in CAD/cutting tools.
    Only files directly inside this pipeline's output directory are touched.
    """
    root = Path(output_dir).resolve()
    svg_paths = list(dict.fromkeys(Path(path) for key, path in output_files.items()
                                   if key.endswith("svg")))
    dxf_items = [(key, Path(path)) for key, path in output_files.items()
                 if key.endswith("dxf")]
    for path in svg_paths + [path for _key, path in dxf_items]:
        resolved = path.resolve()
        if resolved.parent != root or resolved.suffix.lower() not in {".svg", ".dxf"}:
            raise ValueError(f"Unsafe generated export path: {path}")
    staged: list[tuple[Path, Path]] = []
    try:
        for path in svg_paths:
            marked = _blocked_svg_markup(path.read_text(encoding="utf-8"))
            temp = path.with_name(path.name + ".quality.tmp")
            staged.append((path, temp))
            temp.write_text(marked, encoding="utf-8")
        for path, temp in staged:
            os.replace(temp, path)
    finally:
        for _path, temp in staged:
            if temp.exists():
                temp.unlink()
    for key, path in dxf_items:
        path.unlink(missing_ok=True)
        output_files.pop(key, None)
