"""round82: 完成コーデとして服・全小物の表示と取付位置を確認する。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _js() -> str:
    return (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_complete_outfit_preview_has_visibility_and_reset_controls(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="outfit-show-garment"' in html
    assert 'id="outfit-show-accessories"' in html
    assert 'id="outfit-show-mannequin"' in html
    assert 'id="outfit-reset-view"' in html
    assert 'id="outfit-accessory-list"' in html
    assert "完成コーデ確認" in html


def test_all_custom_accessories_can_be_repositioned_on_the_outfit():
    js = _js()
    assert "function renderOutfitAccessoryList(accessories)" in js
    assert "accessories.forEach((part, index)" in js
    assert "outfitState.accessoryAnchors[key] = select.value" in js
    assert 'left_shoulder: [-.69, -.72, -.14]' in js
    assert 'right_hip: [.50, .45, -.34]' in js
    assert 'face.kind === "accessory"' in js


def test_named_views_are_exact_and_preview_supports_zoom_and_tilt():
    js = _js()
    assert 'view === "left") setOutfitAngle(-Math.PI / 2)' in js
    assert 'view === "right") setOutfitAngle(Math.PI / 2)' in js
    assert 'addEventListener("wheel"' in js
    assert '"ArrowUp", "ArrowDown"' in js
    assert "outfitState.zoom" in js
    assert "outfitState.tilt" in js


def test_preview_layers_can_be_compared_independently():
    js = _js()
    assert 'face.kind === "mannequin"' in js
    assert 'face.kind === "accessory"' in js
    assert "outfitState.showGarment" in js
    assert "outfitState.showAccessories" in js
    assert "outfitState.showMannequin" in js
