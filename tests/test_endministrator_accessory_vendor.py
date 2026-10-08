"""The character-specific vendor trial remains a labelled estimate, not an order."""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from engine.endministrator_accessory_trace import (
    TRACE_POINTS_PX, silhouette_for_provisional_width_cm,
    trace_yellow_silhouette,
)
from scripts.validate_endministrator_shoulder_vendor import generate


def test_endministrator_shoulder_trial_is_digitally_valid_but_order_held(tmp_path):
    audit = generate(tmp_path)
    assert audit["piece_count"] == 2
    assert audit["stl_watertight"] is True
    assert audit["pdf_pages"] == 2
    assert audit["design_values_are_estimates"] is True
    assert audit["visual_match_checked_against_source_pixels"] is False
    assert audit["fabrication_order_approved"] is False
    assert audit["measurement_gate_complete"] is False
    assert 105 < audit["mesh_dimensions_mm"]["x"] < 111
    assert 75 < audit["mesh_dimensions_mm"]["y"] < 85
    assert audit["front_color_region_traced_from_source_pixels"] is True
    assert audit["through_holes"]["through_hole"] is False
    assert audit["component_features_checked"] == 4
    assert audit["missing_source_dimensions"] > 0
    with ZipFile(audit["files"]["vendor_zip"]) as archive:
        names = archive.namelist()
        assert "TRIAL_ORDER_REVIEW_JA.txt" in names
        assert "DIMENSIONED_DRAWINGS.pdf" in names
        assert "COMPONENT_REVIEW.json" in names
        assert "MEASUREMENTS_REQUIRED.json" in names
        review = archive.read("TRIAL_ORDER_REVIEW_JA.txt").decode("utf-8-sig")
        assert "量産／完成衣装用の確定発注ではありません" in review
        assert "発注を止める未確定事項" in review
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["piece_count"] == 1
        assert manifest["mounting_holes"]["through_hole"] is False
        component_review = json.loads(archive.read("COMPONENT_REVIEW.json"))
        assert component_review["ready_for_fabrication_order"] is False
        assert len(component_review["observed"]) == 4
        assert len(component_review["front_trace_points_px"]) == len(TRACE_POINTS_PX)
        assert component_review["selected_hardware_for_fit_trial"][0]["post_length_mm"] == 5
        required = json.loads(archive.read("MEASUREMENTS_REQUIRED.json"))
        assert required["shoulder_yellow_visible_width"] is None
        assert required["wearer_front_and_side_fit_confirmed"] is False
    with ZipFile(audit["files"]["charm_vendor_zip"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["piece_count"] == 1
        assert manifest["files"][0]["watertight"] is True
        assert manifest["files"][0]["dimensions_mm"]["y"] == 32
        assert manifest["mounting_holes"]["through_hole"] is False


def test_front_trace_has_ratio_only_and_rejects_other_image(tmp_path):
    outline = silhouette_for_provisional_width_cm(11)
    assert max(x for x, _ in outline) - min(x for x, _ in outline) == pytest.approx(11)
    assert 7.5 < max(y for _, y in outline) < 8.5
    wrong = tmp_path / "other.png"
    Image.new("RGB", (1200, 2391), "yellow").save(wrong)
    with pytest.raises(ValueError, match="検証済み正面画像"):
        trace_yellow_silhouette(wrong)


def test_frozen_trace_reproduces_source_when_workspace_copy_exists():
    repository = Path(__file__).resolve().parents[1]
    source = repository.parent.parent / "output" / "validation_endministrator_3d" / "endministrator_reference.jpg"
    if not source.exists():
        pytest.skip("front artwork is not bundled with the repository")
    assert trace_yellow_silhouette(source) == TRACE_POINTS_PX
