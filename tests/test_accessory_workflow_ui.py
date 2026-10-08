"""小物の試作・見積導線が画面から使え、発注確定と混同しないこと。"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_accessory_export_is_reachable_and_describes_order_hold(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/#custom-panel-section"' in html
    assert re.search(r'<div class="field-box accessory-export-box" id="accessory-export-box">', html)
    assert html.count("data-accessory-check") == 4
    assert "画像だけで発注用の実寸を確定しません" in html
    assert "試作・見積相談用ZIP（寸法図PDF入り）" in html
    assert "確定発注には使えません" in html


def test_accessory_result_links_are_unhidden_when_generated():
    js = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'window.location.hash !== "#custom-panel-section"' in js
    assert 'manualMode.checked = true' in js
    assert "customPanelSection.open = true" in js
    assert "stlLink.hidden = !data.download.stl" in js
    assert "vendorLink.hidden = !data.download.vendor_zip" in js
    assert "accessoryBox.hidden = !accessory" in js
