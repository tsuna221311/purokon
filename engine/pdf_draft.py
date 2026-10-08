"""Keep digitally blocked exports usable for inspection, not cutting."""

from __future__ import annotations

from io import BytesIO
from functools import lru_cache
import os
from pathlib import Path
import re

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont as OutlineFont
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from .pdf_export import _JP_FONT_PATH, _LABEL_FONT, _require_jp_label_font


_STOP_WARNING_JA = "検査不合格・裁断禁止"
_UNCONFIRMED_WARNING_JA = "未確認・裁断禁止"


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


def _blocked_svg_markup(source: str,
                        warning_ja: str = _STOP_WARNING_JA) -> str:
    """Add a prominent, scale-aware inspection watermark to a generated SVG."""
    if warning_ja not in {_STOP_WARNING_JA, _UNCONFIRMED_WARNING_JA}:
        raise ValueError("Unknown SVG inspection warning")
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
    warning_middle = _outlined_warning(
        warning_ja, middle_x, middle_y - font * 0.1, font)
    warning_top = _outlined_warning(
        warning_ja, middle_x, y + font * 1.25, font)
    banner = f'''<g id="patternforge-draft-watermark" pointer-events="none">
  <title>{warning_ja} / DRAFT - NOT FOR CUTTING</title>
  <rect x="{x}" y="{y}" width="{width}" height="{height}"
        fill="#fff" fill-opacity="0.18" />
  <rect x="{x}" y="{middle_y - band_height / 2}"
        width="{width}" height="{band_height}" fill="#fff" fill-opacity="0.88" />
  {warning_middle}
  <text x="{middle_x}" y="{middle_y + font * 1.15}" text-anchor="middle"
        font-family="sans-serif" font-weight="700" font-size="{english_font}"
        fill="#b00020">DRAFT - NOT FOR CUTTING</text>
  <rect x="{x}" y="{y}" width="{width}" height="{font * 3.0}"
        fill="#fff" fill-opacity="0.94" />
  {warning_top}
  <text x="{middle_x}" y="{y + font * 2.35}" text-anchor="middle"
        font-family="sans-serif" font-weight="700" font-size="{english_font}"
        fill="#b00020">DRAFT - NOT FOR CUTTING</text>
</g>'''
    return source[:closing] + banner + source[closing:]


@lru_cache(maxsize=2)
def _warning_outlines(warning_ja: str) -> tuple[int, int, str]:
    """Trace the bundled Japanese glyphs so SVG viewers need no CJK font."""
    font = OutlineFont(_JP_FONT_PATH)
    try:
        cmap = font.getBestCmap()
        glyph_set = font.getGlyphSet()
        advances = font["hmtx"].metrics
        units_per_em = font["head"].unitsPerEm
        offset = 0
        paths = []
        for character in warning_ja:
            glyph_name = cmap.get(ord(character))
            if glyph_name is None:
                raise RuntimeError(f"SVG警告用フォントに文字がありません: {character}")
            pen = SVGPathPen(glyph_set)
            glyph_set[glyph_name].draw(pen)
            paths.append(f'<path d="{pen.getCommands()}" '
                         f'transform="translate({offset},0)" />')
            offset += advances[glyph_name][0]
        return units_per_em, offset, "".join(paths)
    finally:
        font.close()


def _outlined_warning(warning_ja: str, center_x: float,
                      baseline_y: float, size: float) -> str:
    units_per_em, advance, paths = _warning_outlines(warning_ja)
    scale = size / units_per_em
    left_x = center_x - advance * scale / 2
    return (f'<g fill="#b00020" transform="translate({left_x},{baseline_y}) '
            f'scale({scale},-{scale})">{paths}</g>')


def mark_inspection_svg(path: str, warning_ja: str = _STOP_WARNING_JA) -> None:
    """Atomically mark one generated SVG before allowing it to be previewed."""
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    marked = _blocked_svg_markup(source, warning_ja)
    if marked == source:
        return
    temp = target.with_name(target.name + ".draft.tmp")
    try:
        temp.write_text(marked, encoding="utf-8")
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()


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
