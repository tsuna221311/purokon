"""Printed shopping notes must not disappear after the first page fills."""

from engine.fabric import FabricSuggestion, ShoppingList, WidthOption
from engine.pdf_export import (_draw_shopping_page, _wrap_pdf_line_to_width,
                               _LABEL_FONT, unprintable_characters)
from reportlab.pdfbase import pdfmetrics


class RecordingCanvas:
    def __init__(self):
        self.pages = [[]]

    def setFillColorRGB(self, *_args):
        pass

    def setFont(self, *_args):
        pass

    def drawString(self, _x, _y, value):
        self.pages[-1].append(value)

    def showPage(self):
        self.pages.append([])


def test_all_notes_and_suggestions_survive_page_breaks():
    memo = ShoppingList(
        widths=[WidthOption(150, 200, 210, .1, True)],
        recommended_width_cm=150,
        notes=[f"備考{i:02d} " + "裁断前に確認する。" * 5
               for i in range(55)],
        suggestions=[FabricSuggestion(
            part_label=f"生地候補{i:02d}", text="張りと厚みを確認する。",
            source_name="資料", source_url=f"https://example.com/material/{i:02d}")
            for i in range(15)],
    )
    canvas = RecordingCanvas()
    _draw_shopping_page(canvas, memo)
    text = "\n".join(line for page in canvas.pages for line in page)
    assert len(canvas.pages) > 2
    for index in range(55):
        assert f"備考{index:02d}" in text
    for index in range(15):
        assert f"生地候補{index:02d}" in text
        assert f"https://example.com/material/{index:02d}" in text
    assert sum("買い物メモ（続き）" in page for page in canvas.pages) >= 1


def test_long_source_url_wraps_without_losing_characters():
    url = "https://example.com/material/" + "verylongpath" * 40
    lines = _wrap_pdf_line_to_width(url, 120, 7)
    assert len(lines) > 1
    assert "".join(lines) == url
    assert all(pdfmetrics.stringWidth(line, _LABEL_FONT, 7) <= 120
               for line in lines)


def test_builtin_costume_shopping_components_are_printable():
    from scripts.build_pattern_label_font import _costume_separate_component_chars

    printed_text = ("型紙外の同梱物: この型紙と生地量には含まれず、"
                    "別途制作・調達が必要です。")
    printed_text += "".join(_costume_separate_component_chars())
    assert not unprintable_characters(printed_text)
