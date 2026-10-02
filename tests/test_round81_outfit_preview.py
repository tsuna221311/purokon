"""round81: 服と小物をまとめて確認する360度完成イメージ。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _js() -> str:
    return (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_result_has_accessible_360_degree_outfit_preview(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="outfit-preview-3d"' in html
    assert 'id="outfit-preview-canvas"' in html
    assert 'tabindex="0"' in html
    assert "服と小物を合わせた360°イメージ" in html
    assert 'data-outfit-view="front"' in html
    assert 'data-outfit-view="back"' in html
    assert 'id="outfit-auto-rotate"' in html


def test_preview_is_explicitly_separate_from_manufacturing_dimensions(client):
    html = client.get("/").get_data(as_text=True)
    assert "物理シミュレーションではありません" in html
    assert "裁断寸法はPDF・DXF" in html
    assert "3Dプリント寸法はSTL・3MF" in html


def test_preview_builds_clothing_and_accessories_from_generated_parts():
    js = _js()
    assert "function renderOutfitPreview(data)" in js
    assert 'part.part_type === "custom_panel"' in js
    assert 'types.has("front_bodice")' in js
    assert 'types.has("sleeve")' in js
    assert 'types.has("skirt")' in js
    assert 'types.has("front_pants")' in js
    assert 'types.has("hood")' in js
    assert "renderOutfitPreview(data);" in js
    assert "function _previewAccessoryAnchor(part, index)" in js
    assert "ブローチ" in js
    assert "バックル" in js
    assert "翼" in js


def test_preview_supports_drag_keyboard_named_views_and_optional_auto_rotation():
    js = _js()
    assert 'addEventListener("pointermove"' in js
    assert '["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]' in js
    assert 'view === "front"' in js
    assert 'view === "back"' in js
    assert "window.requestAnimationFrame(animateOutfitPreview)" in js
    assert 'setAttribute("aria-pressed", String(outfitState.auto))' in js
