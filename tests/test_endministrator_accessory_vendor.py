"""The character-specific vendor trial remains a labelled estimate, not an order."""

import json
from zipfile import ZipFile

from scripts.validate_endministrator_shoulder_vendor import generate


def test_endministrator_shoulder_trial_is_digitally_valid_but_order_held(tmp_path):
    audit = generate(tmp_path)
    assert audit["piece_count"] == 1
    assert audit["stl_watertight"] is True
    assert audit["pdf_pages"] == 1
    assert audit["design_values_are_estimates"] is True
    assert audit["visual_match_checked_against_source_pixels"] is False
    assert audit["fabrication_order_approved"] is False
    assert audit["mesh_dimensions_mm"]["x"] > 100
    assert audit["through_holes"]["diameter_mm"] == 3.2
    with ZipFile(audit["files"]["vendor_zip"]) as archive:
        names = archive.namelist()
        assert "TRIAL_ORDER_REVIEW_JA.txt" in names
        assert "DIMENSIONED_DRAWINGS.pdf" in names
        review = archive.read("TRIAL_ORDER_REVIEW_JA.txt").decode("utf-8-sig")
        assert "量産／完成衣装用の確定発注ではありません" in review
        assert "発注を止める未確定事項" in review
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["piece_count"] == 1
