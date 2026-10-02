"""round78: 画像資料の確認と、ラフから製作用へ進む導線の回帰テスト。"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent


def test_reference_board_is_rendered_with_accessible_status(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="reference-board"' in html
    assert 'aria-labelledby="reference-board-title"' in html
    assert 'id="reference-board-summary"' in html
    assert 'aria-live="polite"' in html
    match = re.search(r'data-max-images="(\d+)"', html)
    assert match and int(match.group(1)) > 0
    for kind in ("front", "back", "side", "detail"):
        assert f'data-reference-kind="{kind}"' in html


def test_reference_board_supports_preview_removal_and_limit_validation():
    js = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function renderReferenceBoard()" in js
    assert "function removeReferenceFile(" in js
    assert "function validateReferencesBeforeSubmit()" in js
    assert "new DataTransfer()" in js
    assert "reader.readAsDataURL(file)" in js
    assert "files.length > maxReferenceImages" in js
    assert 'file.type.startsWith("image/")' in js


def test_draft_result_has_a_clear_route_to_production(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="continue-to-production"' in html
    assert "未確認項目を補正して製作用データへ" in html

    js = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'input[name="illustration_stage"][value="production"]' in js
    assert 'advanced.open = true' in js
    assert 'continueToProduction.classList.toggle("hidden", !production || production.ready)' in js


def test_workflow_progress_has_visible_active_and_complete_states():
    css = (ROOT / "web" / "static" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert ".workflow-overview > div.is-active" in css
    assert ".workflow-overview > div.is-complete" in css
    assert 'step.classList.remove("is-active", "is-complete")' in js
    assert "function syncWorkflowProgress()" in js


def test_reference_previews_remain_usable_on_narrow_screens():
    css = (ROOT / "web" / "static" / "style.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(auto-fill, minmax(130px, 1fr))" in css
    assert ".reference-preview" in css and "min-width: 0" in css
    assert ".reference-preview-body span" in css and "text-overflow: ellipsis" in css
