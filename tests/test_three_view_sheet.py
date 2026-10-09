"""A single front/side/back sheet must keep each view separate."""

import pytest
from PIL import Image

from app import _split_three_view_sheet


def test_three_view_sheet_is_split_into_labeled_views():
    sheet = Image.new("RGB", (900, 500), "white")
    for start, color in ((0, "red"), (300, "green"), (600, "blue")):
        sheet.paste(color, (start, 0, start + 300, 500))

    front, back, side = _split_three_view_sheet(sheet)

    assert [view.size for view in (front, back, side)] == [(300, 500)] * 3
    assert front.getpixel((150, 250)) == (255, 0, 0)
    assert side.getpixel((150, 250)) == (0, 128, 0)
    assert back.getpixel((150, 250)) == (0, 0, 255)


def test_three_view_sheet_rejects_portrait_images():
    with pytest.raises(ValueError, match="横長"):
        _split_three_view_sheet(Image.new("RGB", (600, 800)))
