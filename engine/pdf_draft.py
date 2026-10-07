"""Mark digitally blocked pattern PDFs as inspection copies, not cutting masters."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path

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

    Stage every replacement before changing any original.  SVG and DXF remain
    diagnostic exports and must be treated as blocked by their callers too.
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
