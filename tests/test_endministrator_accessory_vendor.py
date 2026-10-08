"""The character-specific vendor trial remains a labelled estimate, not an order."""

import json
from zipfile import ZipFile

from scripts.validate_endministrator_shoulder_vendor import generate


def test_endministrator_shoulder_trial_is_digitally_valid_but_order_held(tmp_path):
    audit = generate(tmp_path)
    assert audit["piece_count"] == 2
    assert audit["stl_watertight"] is True
    assert audit["pdf_pages"] == 2
    assert audit["design_values_are_estimates"] is True
    assert audit["visual_match_checked_against_source_pixels"] is False
    assert audit["fabrication_order_approved"] is False
    assert 40 < audit["mesh_dimensions_mm"]["x"] < 46
    assert audit["through_holes"]["through_hole"] is False
    assert audit["component_features_checked"] == 4
    assert audit["missing_source_dimensions"] > 0
    with ZipFile(audit["files"]["vendor_zip"]) as archive:
        names = archive.namelist()
        assert "TRIAL_ORDER_REVIEW_JA.txt" in names
        assert "DIMENSIONED_DRAWINGS.pdf" in names
        assert "COMPONENT_REVIEW.json" in names
        review = archive.read("TRIAL_ORDER_REVIEW_JA.txt").decode("utf-8-sig")
        assert "量産／完成衣装用の確定発注ではありません" in review
        assert "発注を止める未確定事項" in review
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["piece_count"] == 1
        assert manifest["mounting_holes"]["through_hole"] is False
        component_review = json.loads(archive.read("COMPONENT_REVIEW.json"))
        assert component_review["ready_for_fabrication_order"] is False
        assert len(component_review["observed"]) == 4
    with ZipFile(audit["files"]["charm_vendor_zip"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["piece_count"] == 1
        assert manifest["files"][0]["watertight"] is True
        assert manifest["files"][0]["dimensions_mm"]["y"] == 32
        assert manifest["mounting_holes"]["through_hole"] is False
