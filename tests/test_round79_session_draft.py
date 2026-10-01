"""round79: タブ内の入力復元と生成前サマリーの回帰テスト。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _js() -> str:
    return (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_page_discloses_tab_only_autosave_and_offers_reset(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="session-draft-status"' in html
    assert "このタブ内だけに自動保存" in html
    assert "（画像を除く）" in html
    assert 'id="session-draft-clear"' in html
    assert "最初から入力" in html


def test_autosave_uses_session_storage_and_excludes_sensitive_or_binary_fields():
    js = _js()
    assert 'const SESSION_DRAFT_KEY = "patternforge:form-draft:v1"' in js
    assert "sessionStorage.setItem" in js
    assert "sessionStorage.getItem" in js
    assert "localStorage" not in js
    assert '["file", "hidden", "submit", "button", "password"]' in js
    assert "SESSION_DRAFT_MAX_AGE_MS = 12 * 60 * 60 * 1000" in js


def test_restored_controls_emit_change_so_dependent_ui_is_resynchronised():
    js = _js()
    assert "function restoreSessionDraft()" in js
    assert 'dispatchEvent(new Event("change", { bubbles: true }))' in js
    assert "if (selected) changed.push(control)" in js
    assert "未選択ラジオにもchangeを送ると" in js
    assert "if (restoredMode) setMode(restoredMode.value)" in js
    assert "if (measurementChanged) refreshMeasurementHints()" in js
    assert "採寸チェックは最後に1回だけ" in js
    assert "前回の入力をこのタブから復元しました" in js
    assert "画像は再選択してください" in js


def test_clear_action_requires_confirmation_before_resetting_the_page():
    js = _js()
    confirmation = js.index("window.confirm(")
    removal = js.index("sessionStorage.removeItem(SESSION_DRAFT_KEY)", confirmation)
    reload = js.index("window.location.reload()", removal)
    assert confirmation < removal < reload


def test_generation_summary_contains_mode_reference_count_and_key_measurements(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="generation-summary"' in html
    assert 'id="generation-summary-text"' in html

    js = _js()
    assert "function syncGenerationSummary()" in js
    assert 'form.elements.namedItem("bust")' in js
    assert 'form.elements.namedItem("waist")' in js
    assert 'form.elements.namedItem("hip")' in js
    assert 'form.elements.namedItem("height")' in js
    assert "referenceFiles().length" in js
    assert 'input[name="sizes"]:checked' in js
