"""The public demo may generate patterns but must not expose account features."""

import app as app_module


def test_demo_allows_pattern_workflow_and_explains_limits(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    home = client.get("/")
    assert home.status_code == 200
    body = home.get_data(as_text=True)
    assert "公開デモ（試作版）" in body
    assert "サーバー上の生成ファイルは消える" in body
    assert 'id="project-save-local"' in body
    assert 'id="project-load-local"' in body
    assert 'id="project-export-file"' in body
    assert 'id="project-import-file"' in body
    assert "生成済みのPDF／SVG／DXFは別途ダウンロード" in body
    assert 'href="/signup"' not in body
    assert 'href="/pricing"' not in body
    assert client.get("/guide").status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert home.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert "Disallow: /" in client.get("/robots.txt").get_data(as_text=True)
    assert "/signup" not in client.get("/sitemap.xml").get_data(as_text=True)


def test_demo_blocks_accounts_billing_and_private_api(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    for path in ("/signup", "/login", "/account", "/pricing", "/terms", "/privacy", "/legal"):
        assert client.get(path).status_code == 404, path
    assert client.post("/signup", data={"email": "x@example.com", "password": "secret"}).status_code == 404
    assert client.post("/billing/webhook", data=b"{}").status_code == 404
    assert client.post("/api/v1/generate", data={}).status_code == 404


def test_demo_opt_in_does_not_change_normal_site(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", False)
    assert client.get("/signup").status_code == 200
    assert client.get("/pricing").status_code == 200
    assert 'id="project-save-local"' not in client.get("/").get_data(as_text=True)


def test_demo_generates_and_downloads_pattern(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare", "illustration_stage": "draft",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    for fmt in ("pdf", "svg"):
        download = client.get(body["download"][fmt])
        assert download.status_code == 200
        assert download.data
