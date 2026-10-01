"""round83: 完成コーデを調整・拡大・保存できる確認ワークスペース。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _js() -> str:
    return (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_preview_can_expand_and_save_a_png(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="outfit-expand-preview"' in html
    assert 'id="outfit-save-image"' in html
    assert 'id="outfit-save-status"' in html
    js = _js()
    assert 'outfitCanvas.toBlob(saveBlob, "image/png")' in js
    assert '完成イメージ.png' in js
    assert 'classList.toggle("is-expanded")' in js
    css = (ROOT / "web" / "static" / "style.css").read_text(encoding="utf-8")
    assert "body.has-outfit-preview-expanded .action-bar { visibility: hidden; }" in css
    assert 'document.body.appendChild(outfitPreviewBox)' in js
    assert 'outfitPreviewPlaceholder.parentNode.insertBefore' in js
    assert "0 0 0 100vmax" in css
    assert "z-index: 1000" in css


def test_each_accessory_has_scale_and_position_adjustments():
    js = _js()
    assert "accessoryTransforms: {}" in js
    assert '["scale", "大きさ", 60, 160' in js
    assert '["x", "左右", -50, 50' in js
    assert '["y", "上下", -50, 50' in js
    assert "transform.scale" in js
    assert "anchor[0] + transform.x" in js
    assert "anchor[1] + transform.y" in js


def test_reset_returns_accessories_and_view_to_the_generated_defaults():
    js = _js()
    assert "outfitState.accessoryAnchors = {};" in js
    assert "outfitState.accessoryTransforms = {};" in js
    assert "renderOutfitAccessoryList(outfitState.parts.filter" in js


def test_downloaded_image_contains_its_own_background():
    js = _js()
    assert "context.createRadialGradient" in js
    assert 'background.addColorStop(1, "#11121d")' in js
