"""round81: 服と小物をまとめて確認する360度完成イメージ。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _js() -> str:
    return (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_procon_result_hides_unverified_360_degree_outfit_preview(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="outfit-preview-3d" class="outfit-preview-3d hidden" hidden' in html
    assert 'id="outfit-preview-canvas"' in html
    assert "outfit3d.js" not in html
    assert 'id="download-stl" href="#" class="btn-solid hidden" hidden' in html


def test_procon_result_promotes_2d_manufacturing_files(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="download-pdf"' in html
    assert 'id="download-spec-pdf"' in html
    assert 'id="download-dxf"' in html
    assert 'id="download-projector"' in html
    assert 'id="download-stl" href="#" class="btn-solid hidden" hidden' in html


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
