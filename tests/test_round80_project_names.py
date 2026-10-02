"""round80: プロジェクト名を生成・履歴・再生成で一貫して扱う。"""

from pathlib import Path

import app as app_module


ROOT = Path(__file__).resolve().parent.parent


def _valid_form(**updates):
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
    }
    form.update(updates)
    return form


def test_project_name_field_is_optional_bounded_and_in_generation_summary(client):
    html = client.get("/").get_data(as_text=True)
    assert 'name="project_name"' in html
    assert 'id="project-name"' in html
    assert 'maxlength="80"' in html
    assert 'id="result-project-name"' in html

    js = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'namedItem("project_name")' in js
    assert "プロジェクト：${name}" in js


def test_generate_returns_normalised_project_name_and_records_it(client):
    response = client.post(
        "/api/generate", data=_valid_form(project_name="  文化祭用・黒コート  "))
    assert response.status_code == 200
    data = response.get_json()
    assert data["project_name"] == "文化祭用・黒コート"

    owner_key = app_module.db.get_job_owner(data["job_id"])
    jobs = app_module.db.list_jobs_for_owner(owner_key)
    assert jobs[0]["job_id"] == data["job_id"]
    assert jobs[0]["project_name"] == "文化祭用・黒コート"


def test_project_name_rejects_over_80_characters_without_consuming_generation(client):
    response = client.post(
        "/api/generate", data=_valid_form(project_name="衣" * 81))
    assert response.status_code == 400
    assert "80文字以内" in response.get_json()["error"]


def test_account_escapes_project_name_and_regeneration_preserves_it(client):
    client.post("/signup", data={
        "email": "project@example.com", "password": "password123"},
        follow_redirects=True)
    response = client.post(
        "/api/generate", data=_valid_form(project_name="舞台衣装<script>"))
    assert response.status_code == 200
    original_job_id = response.get_json()["job_id"]

    account = client.get("/account").get_data(as_text=True)
    assert "舞台衣装&lt;script&gt;" in account
    assert "舞台衣装<script>" not in account
    assert "プロジェクト" in account

    regenerated = client.post(
        f"/account/jobs/{original_job_id}/regenerate", follow_redirects=True)
    assert regenerated.status_code == 200
    owner_key = app_module.db.get_job_owner(original_job_id)
    jobs = app_module.db.list_jobs_for_owner(owner_key)
    assert len(jobs) >= 2
    assert jobs[0]["project_name"] == "舞台衣装<script>"
