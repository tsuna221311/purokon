"""round84: 完成イメージを配色し、共有用4面図として出力する。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_outfit_preview_exposes_colour_and_four_view_controls(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="outfit-garment-color"' in html
    assert 'id="outfit-accessory-color"' in html
    assert 'id="outfit-save-four-views"' in html
    assert "正面・背面・左右を1枚に保存" in html


def test_preview_colours_are_part_of_the_render_state():
    js = _read("web/static/app.js")
    assert 'garmentColor: "#4f46e5"' in js
    assert 'accessoryColor: "#16a34a"' in js
    assert "garment = outfitState.garmentColor" in js
    assert "accent = outfitState.accessoryColor" in js
    assert 'outfitGarmentColor?.addEventListener("input"' in js
    assert 'outfitAccessoryColor?.addEventListener("input"' in js


def test_four_view_sheet_uses_exact_named_angles_and_restores_the_view():
    js = _read("web/static/app.js")
    assert 'sheet.width = 1600' in js
    assert '["正面", 0], ["右側面", Math.PI / 2]' in js
    assert '["背面", Math.PI], ["左側面", -Math.PI / 2]' in js
    assert 'setOutfitAngle(previousAngle)' in js
    assert '"完成4面図"' in js


def test_expanded_preview_can_be_closed_with_escape():
    js = _read("web/static/app.js")
    assert 'event.key === "Escape"' in js
    assert 'outfitExpandPreview?.click()' in js
