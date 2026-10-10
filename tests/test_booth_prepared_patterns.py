"""The exact four booth sheets return only their audited frozen artifacts."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from werkzeug.datastructures import MultiDict

import app as app_module
from engine.booth_demo import (CASES, default_options_match, exact_match, match_sheet,
                               fixed_measurements_match, load_prepared)
from engine.demo_cases import DEMO_MEASUREMENTS
from engine.measurements import Measurements

SHEETS = Path(__file__).parent / "fixtures" / "booth_sheets"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.key)
def test_exact_sheet_returns_same_audited_files(client, monkeypatch, case):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    monkeypatch.setattr(
        app_module.pipeline, "generate_from_illustration",
        lambda *args, **kwargs: pytest.fail("exact booth sheet must not call image AI"))
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == case)
    form = {key: str(value) for key, value in DEMO_MEASUREMENTS.items()}
    form.update(mode="illustration", illustration_stage="draft",
                illustration_three_views="1", fit="standard", paper="a4")
    pdf_bytes = None
    for _ in range(2):
        data = dict(form)
        data["illustration"] = (io.BytesIO(source.read_bytes()), source.name)
        response = client.post("/api/generate", data=data,
                               content_type="multipart/form-data")
        assert response.status_code == 200, response.get_json()
        payload = response.get_json()
        assert payload["prepared_example"]["title"] == case.title
        assert payload["production_quality"]["digital_ready"] is True
        assert payload["ai_engine"] == "none"
        assert payload["part_count"] > 0
        assert len(payload["prepared_example"]["attachments"]) == len(case.panels)
        for panel in case.panels:
            assert sum(part["part_type"] == "custom_panel"
                       and (part["variation"] == panel.label or
                            part["variation"].startswith(panel.label + "-"))
                       for part in payload["parts"]) == panel.quantity
        for kind in ("pdf", "svg", "dxf", "spec_pdf"):
            downloaded = client.get(payload["download"][kind])
            assert downloaded.status_code == 200
            assert downloaded.data
            if kind == "pdf":
                assert downloaded.data.startswith(b"%PDF")
                if pdf_bytes is not None:
                    assert downloaded.data == pdf_bytes
                pdf_bytes = downloaded.data


def test_only_identical_bytes_and_default_settings_match():
    case = CASES[0]
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == case)
    original = source.read_bytes()
    stream = io.BytesIO(original)
    stream.seek(17)
    assert exact_match(SimpleNamespace(stream=stream)) == case
    assert stream.tell() == 17
    assert exact_match(SimpleNamespace(stream=io.BytesIO(original + b"changed"))) is None
    assert fixed_measurements_match(Measurements(**DEMO_MEASUREMENTS))
    changed = dict(DEMO_MEASUREMENTS, bust=84)
    assert not fixed_measurements_match(Measurements(**changed))
    changed = dict(DEMO_MEASUREMENTS, head_circumference=56)
    assert not fixed_measurements_match(Measurements(**changed))
    assert default_options_match(MultiDict({"fit": "standard", "paper": "a4",
                                            "illustration_layer_count": "1"}))
    assert not default_options_match(MultiDict({"fit": "custom"}))
    assert not default_options_match(MultiDict({"illustration_hood": "yes"}))
    assert not default_options_match(MultiDict({"seam_allowance_cm": "2"}))
    assert load_prepared(case)["source_sha256"] == case.sha256


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.key)
def test_confirmed_production_upload_returns_downloadable_pattern(client, monkeypatch, case):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    monkeypatch.setattr(app_module.pipeline, "generate_from_illustration",
                        lambda *args, **kwargs: pytest.fail("reviewed sheet should not call image AI"))
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == case)
    image = Image.open(source)
    encoded = io.BytesIO()
    image.save(encoded, format="JPEG", quality=72)
    matched = match_sheet(SimpleNamespace(stream=io.BytesIO(encoded.getvalue())))
    assert matched == (case, "near_identical")
    spec = case.spec
    fields = {
        "illustration_neckline": spec["neckline"],
        "illustration_back_neckline": spec["neckline"],
        "illustration_sleeve_style": spec["sleeve_style"] or "none",
        "illustration_skirt_style": spec["skirt_style"] or "none",
        "illustration_pants_style": (spec["pants_style"] or "default") if spec["include_pants"] else "none",
        "illustration_collar_style": (spec["collar_style"] or "default") if spec["include_collar"] else "none",
        "illustration_cuffs_style": (spec["cuffs_style"] or "default") if spec["include_cuffs"] else "none",
        "illustration_waistband_style": (spec.get("waistband_style") or "default") if spec["include_waistband"] else "none",
        "illustration_hood": "yes" if spec.get("include_hood") else "no",
        "illustration_closure": "front_zip" if spec["front_zip"] else "none",
        "illustration_symmetry": "symmetric",
        "illustration_internal_support": "none",
        "illustration_movement": "standard",
    }
    form = dict(bust="84", waist="68", hip="92", height="160",
                sleeve_length="54", shoulder_width="37", mode="illustration",
                illustration_stage="production", paper="a4", fit="standard",
                **fields)
    form["illustration"] = (io.BytesIO(encoded.getvalue()), "sheet.jpg")
    response = client.post("/api/generate", data=form, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["prepared_example"]["dynamic"] is True
    assert payload["production_quality"]["digital_ready"] is True
    assert payload["ai_engine"] == "none"
    for kind, header in (("pdf", b"%PDF"), ("dxf", b"  0")):
        downloaded = client.get(payload["download"][kind])
        assert downloaded.status_code == 200
        assert downloaded.data.startswith(header)


def test_production_checkbox_alone_uses_registered_sheet_plan(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == CASES[0])
    form = dict(bust="84", waist="68", hip="92", height="160",
                sleeve_length="54", shoulder_width="37", mode="illustration",
                illustration_stage="production", illustration_three_views="1",
                paper="a4", fit="standard", block="adult_female",
                custom_panels_json="[]", illustration_layer_count="1",
                illustration_slit_position="none",
                illustration_motif_position="none")
    form["illustration"] = (io.BytesIO(source.read_bytes()), source.name)
    response = client.post("/api/generate", data=form, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["production_status"]["ready"] is True
    assert client.get(payload["download"]["pdf"]).data.startswith(b"%PDF")


def test_duplicate_booth_sheet_in_front_and_back_still_downloads_pdf(client, monkeypatch):
    """The browser can receive the same three-view sheet in both upload slots."""
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    monkeypatch.setattr(app_module.pipeline, "generate_from_illustration",
                        lambda *args, **kwargs: pytest.fail("reviewed sheet must not call image AI"))
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == CASES[0])
    image_bytes = source.read_bytes()
    form = dict(bust="84", waist="68", hip="92", height="160",
                sleeve_length="54", shoulder_width="37", mode="illustration",
                illustration_stage="production", paper="a4", fit="standard",
                block="adult_female", custom_panels_json="[]",
                illustration_layer_count="1", illustration_slit_position="none",
                illustration_motif_position="none")
    form["illustration"] = (io.BytesIO(image_bytes), source.name)
    form["illustration_back"] = (io.BytesIO(image_bytes), source.name)
    response = client.post("/api/generate", data=form, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["prepared_example"]["dynamic"] is True
    pdf = client.get(payload["download"]["pdf"])
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")


def test_different_back_image_does_not_use_registered_plan(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_MODE", True)
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == CASES[0])
    other = next(path for path in SHEETS.glob("*.png")
                 if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == CASES[1])
    form = dict(bust="84", waist="68", hip="92", height="160",
                sleeve_length="54", shoulder_width="37", mode="illustration",
                illustration_stage="production", paper="a4", fit="standard",
                block="adult_female", custom_panels_json="[]")
    form["illustration"] = (io.BytesIO(source.read_bytes()), source.name)
    form["illustration_back"] = (io.BytesIO(other.read_bytes()), other.name)
    response = client.post("/api/generate", data=form, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "自動判定" in response.get_json()["error"]


def test_modified_or_unrelated_image_is_not_misidentified():
    source = next(path for path in SHEETS.glob("*.png")
                  if exact_match(SimpleNamespace(stream=io.BytesIO(path.read_bytes()))) == CASES[0])
    with Image.open(source) as image:
        flipped = io.BytesIO()
        image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(flipped, format="PNG")
    assert match_sheet(SimpleNamespace(stream=io.BytesIO(flipped.getvalue()))) is None
    unrelated = io.BytesIO()
    Image.new("RGB", (1536, 1024), "white").save(unrelated, format="PNG")
    assert match_sheet(SimpleNamespace(stream=io.BytesIO(unrelated.getvalue()))) is None
