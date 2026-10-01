import io

from PIL import Image, ImageDraw


def _image():
    image = Image.new("RGB", (500, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(170, 90), (330, 90), (370, 250), (340, 430),
                  (420, 670), (80, 670), (160, 430), (130, 250)],
                 fill=(70, 90, 150))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def _base(stage="production"):
    return {
        "mode": "illustration", "illustration_stage": stage,
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "illustration": (_image(), "front.png"),
    }


def _confirmed():
    return {
        "illustration_neckline": "round_neck",
        "illustration_back_neckline": "round_neck",
        "illustration_sleeve_style": "straight",
        "illustration_skirt_style": "flare",
        "illustration_pants_style": "none",
        "illustration_collar_style": "none",
        "illustration_cuffs_style": "none",
        "illustration_waistband_style": "none",
        "illustration_hood": "no",
        "illustration_closure": "none",
        "illustration_symmetry": "symmetric",
        "illustration_internal_support": "none",
        "illustration_movement": "standard",
    }


def test_production_output_requires_every_critical_confirmation(client):
    response = client.post("/api/generate", data=_base(),
                           content_type="multipart/form-data")
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "製作用データ" in error
    assert "開閉方法" in error
    assert "内部構造" in error


def test_draft_only_returns_watermarked_preview_and_specification(client):
    response = client.post("/api/generate", data=_base("draft"),
                           content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    assert data["production_status"]["draft"] is True
    assert data["production_status"]["ready"] is False
    assert "preview_svg" in data
    assert set(data["download"]) == {"spec_pdf"}
    preview = client.get(data["preview_svg"])
    assert preview.status_code == 200
    assert b"DRAFT / NOT FOR CUTTING" in preview.data
    assert client.get(data["download"]["spec_pdf"]).status_code == 200
    assert client.get(f"/download/{data['job_id']}/pdf").status_code == 404


def test_confirmed_production_returns_manufacturing_formats(client):
    form = _base("production")
    form.update(_confirmed())
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    assert data["production_status"]["draft"] is False
    # 採寸・補正警告が別途あればreadyはFalseになる。ここでは未確認の選択欄が
    # 残っていないことと、製作用形式が作られたことを検査する。
    assert not any("確認してください" in item
                   for item in data["production_status"]["pending"])
    assert {"svg", "pdf", "dxf", "projector", "spec_pdf"} <= set(data["download"])


def test_back_zip_requires_opening_length_before_production(client):
    form = _base("production")
    form.update(_confirmed())
    form["illustration_closure"] = "back_zip"
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert "開き長" in response.get_json()["error"]


def test_back_zip_splits_the_back_and_preserves_the_length(client):
    form = _base("production")
    form.update(_confirmed())
    form.update({"illustration_closure": "back_zip",
                 "illustration_closure_length_cm": "35"})
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    backs = [part for part in data["parts"] if part["part_type"] == "back_bodice"]
    assert len(backs) == 2
    assert data["production_status"]["draft"] is False
    assert not any("開き長" in item for item in data["production_status"]["pending"])


def test_hooks_and_snaps_cannot_claim_to_be_production_ready(client):
    for closure in ("hooks", "snaps"):
        form = _base("production")
        form.update(_confirmed())
        form["illustration_closure"] = closure
        response = client.post("/api/generate", data=form,
                               content_type="multipart/form-data")
        assert response.status_code == 400
        assert "個数" in response.get_json()["error"]


def test_confirmed_hooks_and_snaps_create_production_patterns(client):
    cases = [
        ("hooks", {}),
        ("snaps", {"illustration_closure_overlap_cm": "2"}),
    ]
    for closure, extra in cases:
        form = _base("production")
        form.update(_confirmed())
        form.update({
            "illustration_closure": closure,
            "illustration_closure_count": "6",
            "illustration_closure_spacing_cm": "4",
            **extra,
        })
        response = client.post("/api/generate", data=form,
                               content_type="multipart/form-data")
        assert response.status_code == 200, response.get_json().get("error")
        data = response.get_json()
        assert data["production_status"]["draft"] is False
        assert not any("個数" in item or "間隔" in item or "重なり量" in item
                       for item in data["production_status"]["pending"])
        backs = [part for part in data["parts"]
                 if part["part_type"] == "back_bodice"]
        assert len(backs) == 2


def test_asymmetric_production_requires_separate_left_and_right_outlines(client):
    form = _base("production")
    form.update(_confirmed())
    form["illustration_symmetry"] = "asymmetric"
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "左側・右側" in error
    assert "2件以上" in error


def test_pleat_count_requires_a_real_fold_depth(client):
    form = _base("production")
    form.update(_confirmed())
    form["illustration_pleat_count"] = "8"
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert "ひだ深さ" in response.get_json()["error"]


def test_confirmed_soft_petticoat_adds_manufacturing_parts(client):
    form = _base("production")
    form.update(_confirmed())
    form.update({
        "illustration_internal_support": "petticoat",
        "illustration_petticoat_style": "soft",
        "illustration_petticoat_tier_count": "3",
        "illustration_petticoat_length_cm": "60",
        "illustration_petticoat_fullness_ratio": "1.6",
    })
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    part_types = {part["part_type"] for part in response.get_json()["parts"]}
    assert "petticoat_tier" in part_types
    assert "petticoat_waistband" in part_types
