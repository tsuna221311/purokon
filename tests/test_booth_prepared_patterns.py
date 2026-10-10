"""The exact four booth sheets return only their audited frozen artifacts."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

import app as app_module
from engine.booth_demo import (CASES, default_options_match, exact_match,
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
