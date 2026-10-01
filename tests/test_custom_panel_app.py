"""app.py に round10 で追加した custom_panel(自由形状パーツ)関連の
エンドポイント・機能のテスト。

engine.custom_panel自体の校正ロジック、engine.pipelineへの組み込みは
それぞれ tests/test_custom_panel.py・tests/test_custom_panel_pipeline.py で
検証済み。ここではHTTP層(/api/custom-panel/trace、/api/generateの
custom_panels_json処理、再生成)を検証する。
"""

import io
import json

import pytest
from PIL import Image, ImageDraw

import app as app_module


def _valid_form():
    return {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
        "illustration_stage": "draft",
    }


def _cape_png_bytes():
    image = Image.new("RGB", (300, 400), "white")
    ImageDraw.Draw(image).rectangle([50, 50, 250, 350], fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_motif_image_outline_is_normalized_for_safe_regeneration():
    upload = type("Upload", (), {"stream": _cape_png_bytes(), "filename": "logo.png"})()
    points = app_module._trace_normalized_motif_outline(upload)
    assert len(points) >= 4
    assert min(x for x, _y in points) == 0
    assert max(x for x, _y in points) == 1
    assert min(y for _x, y in points) == 0
    assert max(y for _x, y in points) == 1


def test_motif_image_extracts_major_colour_regions():
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([10, 10, 109, 69], fill=(220, 20, 40, 255))
    draw.ellipse([40, 20, 80, 60], fill=(20, 80, 220, 255))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    upload = type("Upload", (), {"stream": buf, "filename": "logo.png"})()
    outline, regions = app_module._trace_normalized_motif_data(upload)
    assert len(outline) >= 4
    assert len(regions) >= 2
    assert all(region["color"].startswith("#") for region in regions)


def _cape_panel_payload(label="マント", quantity=1, mirror=False, reference_cm=40.0,
                         measurement_field=None):
    panel = {
        "label": label,
        "points": [[0, 0], [100, 0], [120, 150], [-20, 150]],
        "ref_point_a": [0, 0],
        "ref_point_b": [100, 0],
        "quantity": quantity,
        "mirror": mirror,
    }
    if measurement_field:
        panel["measurement_field"] = measurement_field
    else:
        panel["reference_cm"] = reference_cm
    return panel


def _fitted_sleeve_replacement_payload():
    """標準袖そのものの実寸縫い線を、確認済み置換入力へ変換する。"""
    from engine.measurements import Measurements
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    measurements = Measurements(
        bust=84, waist=68, hip=92, height=160,
        sleeve_length=54, shoulder_width=37)
    result = PatternForgePipeline().generate_from_selection(
        build_garment_spec(sleeve_style="straight", skirt_style="flare"),
        measurements, skip_export=True)
    sleeve = next(part for part in result.finalized_parts
                  if part.part_type == "sleeve")
    points = [list(point) for point in sleeve.stitch_line]
    if points[0] == points[-1]:
        points.pop()
    return {
        "label": "確認済み袖", "points": points,
        # 入力座標をすでにcmとして扱うため100単位=100cm、倍率1.0。
        "ref_point_a": [0, 0], "ref_point_b": [100, 0],
        "reference_cm": 100, "quantity": 1, "mirror": True,
        "replacement_part_type": "sleeve", "seam_fit_confirmed": True,
    }


# ---------------------------------------------------------------------------
# /api/custom-panel/trace
# ---------------------------------------------------------------------------

def test_trace_endpoint_extracts_outline_from_uploaded_image(client):
    response = client.post(
        "/api/custom-panel/trace",
        data={"image": (_cape_png_bytes(), "cape.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["image_width"] == 300
    assert data["image_height"] == 400
    assert len(data["points"]) >= 3
    xs = [p[0] for p in data["points"]]
    ys = [p[1] for p in data["points"]]
    assert min(xs) == pytest.approx(50, abs=3)
    assert max(xs) == pytest.approx(250, abs=3)
    assert min(ys) == pytest.approx(50, abs=3)
    assert max(ys) == pytest.approx(350, abs=3)


def test_trace_endpoint_returns_422_when_no_silhouette_detected(client):
    blank = Image.new("RGB", (200, 200), "white")
    buf = io.BytesIO()
    blank.save(buf, format="PNG")
    buf.seek(0)
    response = client.post(
        "/api/custom-panel/trace",
        data={"image": (buf, "blank.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    data = response.get_json()
    assert data["ok"] is False


def test_trace_endpoint_requires_image_file(client):
    response = client.post("/api/custom-panel/trace", data={})
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_trace_endpoint_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(app_module._custom_panel_trace_rate_limiter, "max_requests", 1)
    first = client.post(
        "/api/custom-panel/trace",
        data={"image": (_cape_png_bytes(), "cape.png")},
        content_type="multipart/form-data",
    )
    assert first.status_code == 200
    second = client.post(
        "/api/custom-panel/trace",
        data={"image": (_cape_png_bytes(), "cape.png")},
        content_type="multipart/form-data",
    )
    assert second.status_code == 429


def test_trace_endpoint_requires_csrf_token(client):
    # clientフィクスチャはPOSTのdataにCSRFトークンを自動補完してしまうため、
    # ここでは補完前のtest_clientを直接使い、本当に検証されていることを確認する。
    with app_module.app.test_client() as raw_client:
        response = raw_client.post(
            "/api/custom-panel/trace",
            data={"image": (_cape_png_bytes(), "cape.png")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        assert response.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# /api/generate: custom_panels_json (manual mode)
# ---------------------------------------------------------------------------

def test_generate_manual_mode_combines_custom_panel_with_standard_parts(client):
    form = _valid_form()
    form["custom_panels_json"] = json.dumps([_cape_panel_payload()])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    display_names = {p["display_name"] for p in data["parts"]}
    assert any("マント" in name for name in display_names)
    # 標準パーツ(身頃等)も引き続き含まれている(round9のAskUserQuestion
    # 「両方お願い」の回答通り、併用できることの確認)。
    assert len(data["parts"]) > 1


def test_generate_manual_mode_custom_panel_only_without_body_garment(client):
    form = _valid_form()
    form["include_body_garment"] = "0"
    form["custom_panels_json"] = json.dumps([_cape_panel_payload(label="装甲プレート")])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["part_count"] == 1
    assert "装甲プレート" in data["parts"][0]["display_name"]


def test_generate_manual_mode_rejects_no_parts_at_all(client):
    form = _valid_form()
    form["include_body_garment"] = "0"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "生成するパーツがありません" in response.get_json()["error"]


def test_generate_manual_mode_custom_panel_with_measurement_field_calibration(client):
    form = _valid_form()
    form["custom_panels_json"] = json.dumps(
        [_cape_panel_payload(measurement_field="shoulder_width")]
    )
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_generate_manual_mode_custom_panel_mirror_produces_two_parts(client):
    form = _valid_form()
    form["include_body_garment"] = "0"
    form["custom_panels_json"] = json.dumps([_cape_panel_payload(label="肩当て", mirror=True)])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["part_count"] == 2


def test_standard_part_replacement_requires_flat_pattern_seam_confirmation(client):
    form = _valid_form()
    panel = _cape_panel_payload(label="左袖")
    panel["replacement_part_type"] = "sleeve"
    panel["seam_fit_confirmed"] = False
    form["custom_panels_json"] = json.dumps([panel])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "平面型紙" in response.get_json()["error"]


def test_standard_part_replacement_refuses_to_guess_missing_other_sleeve(client):
    form = _valid_form()
    panel = _cape_panel_payload(label="左袖")
    panel.update({"replacement_part_type": "sleeve", "seam_fit_confirmed": True})
    form["custom_panels_json"] = json.dumps([panel])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "2枚必要" in response.get_json()["error"]


def test_confirmed_mirrored_outline_replaces_both_standard_sleeves(client):
    form = _valid_form()
    form["custom_panels_json"] = json.dumps([_fitted_sleeve_replacement_payload()])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    sleeves = [part for part in response.get_json()["parts"]
               if part["part_type"] == "sleeve"]
    assert len(sleeves) == 2
    assert {part["variation"] for part in sleeves} == {
        "確認済み袖", "確認済み袖(反転)"}


def test_confirmed_but_mismatched_replacement_is_withheld(client):
    form = _valid_form()
    panel = _cape_panel_payload(label="合わない袖", mirror=True)
    panel.update({"replacement_part_type": "sleeve", "seam_fit_confirmed": True})
    form["custom_panels_json"] = json.dumps([panel])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "裁断用PDF・SVG・DXFは出力していません" in response.get_json()["error"]


def test_generate_manual_mode_custom_panel_invalid_json_returns_clear_error(client):
    form = _valid_form()
    form["custom_panels_json"] = "not valid json"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "JSON" in response.get_json()["error"]


def test_generate_manual_mode_custom_panel_bad_geometry_names_the_panel(client):
    form = _valid_form()
    panel = _cape_panel_payload(label="翼")
    panel["reference_cm"] = 40.0
    panel["ref_point_a"] = [0, 0]
    panel["ref_point_b"] = [0, 0]  # 参照線の2点が同一=距離0で校正不能
    form["custom_panels_json"] = json.dumps([panel])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "翼" in response.get_json()["error"]


def test_generate_manual_mode_custom_panel_over_limit_count_rejected(client):
    from engine.custom_panel import MAX_CUSTOM_PANELS_PER_REQUEST
    form = _valid_form()
    panels = [_cape_panel_payload(label=f"パーツ{i}") for i in range(MAX_CUSTOM_PANELS_PER_REQUEST + 1)]
    form["custom_panels_json"] = json.dumps(panels)
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400


def test_generate_illustration_mode_combines_detected_and_custom_panels(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    form = _valid_form()
    form["mode"] = "illustration"
    form["custom_panels_json"] = json.dumps([_cape_panel_payload()])
    response = client.post("/api/generate", data={
        **form,
        "illustration": (_cape_png_bytes(), "cape.png"),
    }, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    payload = response.get_json()
    assert any(part["part_type"] == "custom_panel" for part in payload["parts"])
    assert any(part["part_type"] == "front_bodice" for part in payload["parts"])


def test_generate_multi_size_mode_grades_custom_panels_json(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M", "L"]
    panel = _cape_panel_payload()
    panel["grade_width_cm"] = 2
    panel["grade_height_cm"] = 4
    form["custom_panels_json"] = json.dumps([panel])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    results = response.get_json()["results"]
    widths, heights = [], []
    for size in ("S", "M", "L"):
        part = next(item for item in results[size]["parts"]
                    if item["part_type"] == "custom_panel")
        widths.append(part["width_cm"])
        heights.append(part["height_cm"])
    assert widths[1] - widths[0] == pytest.approx(2, abs=0.05)
    assert widths[2] - widths[1] == pytest.approx(2, abs=0.05)
    assert heights[1] - heights[0] == pytest.approx(4, abs=0.05)
    assert heights[2] - heights[1] == pytest.approx(4, abs=0.05)


def test_generate_manual_mode_custom_panel_failure_does_not_consume_daily_usage(client):
    form = _valid_form()
    form["custom_panels_json"] = "not valid json"
    before_response = client.post("/api/generate", data=_valid_form())
    assert before_response.status_code == 200
    used_before = before_response.get_json()["usage"]["used_today"]

    response = client.post("/api/generate", data=form)
    assert response.status_code == 400

    after_response = client.post("/api/generate", data=_valid_form())
    used_after = after_response.get_json()["usage"]["used_today"]
    # 失敗した1回分(カスタムパーツJSON不正)は課金されず、成功2回分だけ加算される。
    assert used_after == used_before + 1


# ---------------------------------------------------------------------------
# 生成履歴からの再生成(round8機能)がcustom_panelにも対応していること
# ---------------------------------------------------------------------------

def _signup(client, email="user@example.com", password="password123"):
    return client.post("/signup", data={"email": email, "password": password}, follow_redirects=True)


def test_regenerate_job_recreates_custom_panel_from_stored_spec(client):
    _signup(client, email="custom_panel_regen@example.com")
    form = _valid_form()
    form["include_body_garment"] = "0"
    form["custom_panels_json"] = json.dumps([_cape_panel_payload(label="マント", mirror=True)])
    generate_response = client.post("/api/generate", data=form)
    assert generate_response.status_code == 200
    payload = generate_response.get_json()
    assert payload["part_count"] == 2
    job_id = payload["job_id"]

    regen_response = client.post(f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert regen_response.status_code == 200
    assert "再生成しました" in regen_response.get_data(as_text=True)


def test_regenerate_keeps_confirmed_standard_part_replacement(client):
    _signup(client, email="replacement_regen@example.com")
    form = _valid_form()
    form["custom_panels_json"] = json.dumps([_fitted_sleeve_replacement_payload()])
    generated = client.post("/api/generate", data=form)
    assert generated.status_code == 200, generated.get_json().get("error")
    job_id = generated.get_json()["job_id"]

    regenerated = client.post(
        f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert regenerated.status_code == 200
    assert "再生成しました" in regenerated.get_data(as_text=True)


# --- round11: トレース画面の寸法プレビュー・頂点の個別削除 -------------------

def _app_js() -> str:
    import pathlib
    import app as app_module
    return (pathlib.Path(app_module.BASE_DIR) / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_browser_sends_replacement_target_and_requires_seam_confirmation():
    js = _app_js()
    assert "replacement_part_type: panel.els.replacementSelect.value || null" in js
    assert "seam_fit_confirmed: panel.els.seamFitConfirmed.checked" in js
    assert "着用画像の外形ではなく、実寸の平面型紙輪郭" in js
    assert "標準パーツを置き換えるには" in js


def test_client_side_dimension_limits_match_the_server_side_constants():
    """画面側の寸法プレビューが使う上下限が、サーバー側の判定値と一致すること。

    round11で追加した「送信前に実寸(cm)を表示し、小さすぎ/大きすぎを予告する」
    機能は、engine/custom_panel.py の判定値を app.js 側にも書き写している。
    片方だけ変更すると「画面上は問題なしなのに送信するとエラー」(またはその逆)
    という分かりにくい食い違いになるため、値が揃っていることを固定する。
    """
    import re

    from engine.custom_panel import (
        MAX_CUSTOM_PANEL_DIMENSION_CM, MIN_CUSTOM_PANEL_DIMENSION_CM,
        MIN_REFERENCE_PIXEL_DISTANCE,
    )

    js = _app_js()

    def _js_number(name):
        m = re.search(rf"const {name} = ([0-9.]+);", js)
        assert m, f"{name} が app.js に見つかりません"
        return float(m.group(1))

    assert _js_number("CUSTOM_PANEL_MIN_DIMENSION_CM") == MIN_CUSTOM_PANEL_DIMENSION_CM
    assert _js_number("CUSTOM_PANEL_MAX_DIMENSION_CM") == MAX_CUSTOM_PANEL_DIMENSION_CM
    assert _js_number("CUSTOM_PANEL_MIN_REFERENCE_PIXEL_DISTANCE") == MIN_REFERENCE_PIXEL_DISTANCE


def test_client_side_size_preview_uses_the_same_calibration_formula():
    """寸法プレビューが、サーバー側の校正式(参照線の実寸÷ピクセル長を
    一様に掛ける)と同じ計算になっていることを、コード上の要点で確認する。
    """
    js = _app_js()
    assert "function computeCustomPanelSizeCm(panel)" in js
    # 参照線のピクセル長で割ってcm/pxのスケールを出している
    assert "referenceCm / refPx" in js
    # 縫い代を足した裁断寸法も併記している(結果表示と食い違わないように)
    assert "field-seam-allowance" in js


def test_vertex_can_be_deleted_individually_by_double_click():
    """頂点の個別削除(ダブルクリック)が実装されていること。

    round10までは「最後の頂点を削除」しか無く、途中の1点を直すのに
    それ以降を全部消して引き直す必要があった。
    """
    js = _app_js()
    assert 'canvas.addEventListener("dblclick"' in js
    # 3点未満にはできない(輪郭として成立しないため)
    assert "panel.points.length <= 3" in js


def test_reference_point_mode_takes_priority_over_dragging_an_existing_vertex():
    """「参照点Aを指定」を選んでいる間は、既存頂点のドラッグより参照点の
    配置を優先すること(round11で修正したUI上の不具合の回帰テスト)。

    修正前は、置きたい位置に頂点があると参照点が置かれずドラッグが始まり、
    ボタンを押したのに何も起きないように見えていた。自動抽出した輪郭は
    頂点が密なため、実際にかなりの確率で踏む。
    """
    js = _app_js()
    pointerdown = js[js.index('canvas.addEventListener("pointerdown"'):]
    pointerdown = pointerdown[:pointerdown.index("canvas.addEventListener(\"dblclick\"")]
    ref_branch = pointerdown.index('panel.mode === "refA"')
    handle_branch = pointerdown.index("findNearestHandle(panel, pt)")
    assert ref_branch < handle_branch, "参照点モードの分岐が当たり判定より後ろにある"
