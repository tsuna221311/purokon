"""A digital pass must never be reported as commercial/physical parity."""

from pathlib import Path
from unittest.mock import patch

from scripts import audit_endministrator_simulation as audit


def test_size_audit_keeps_the_large_unready_coat_visible():
    rows = audit.audit_pattern_sizes()
    wide = next(row for row in rows
                if row["measurements_cm"]["bust"] == 116)
    assert wide["digital_ready"] is False
    assert any("胸ぐせダーツ" in blocker for blocker in wide["blockers"])


def test_complete_available_audit_keeps_physical_gap_visible():
    sizes = [{"digital_ready": True, "hem_join_warnings": []} for _ in range(4)]
    drapes = [{"self_collision": True, "inputs_are_measured": False}
              for _ in range(3)]
    components = {"expected_groups": 13,
                  "missing_groups": ["water-drop decoration", "hair accessory"]}
    with (patch.object(audit, "audit_pattern_sizes", return_value=sizes),
          patch.object(audit, "audit_drape", return_value=drapes),
          patch.object(audit, "audit_components", return_value=components)):
        report = audit.build_report(Path("unused"), Path("unused"), Path("unused"))
    assert report["scope"] == {
        "pattern_sizes": 4, "cloth_material_profiles": 3,
        "static_render_views": 9, "physical_wear_tests": 0,
    }
    assert all(item["digital_ready"] and not item["hem_join_warnings"]
               for item in report["pattern_size_cases"])
    assert all(item["self_collision"] and not item["inputs_are_measured"]
               for item in report["cloth_material_sensitivity_cases"])
    assert report["commercial_component_inventory"]["expected_groups"] == 13
    assert report["commercial_equivalence_verified"] is False
    assert any("2D型紙" in reason for reason in report["blockers"])


def test_pattern_derived_trial_is_reported_separately_from_physical_signoff():
    pattern = {
        "sleeves_topologically_welded_to_bodice": False,
        "fabric_inputs_measured": False,
        "commercial_quality_approved": False,
        "notch_pairing_verified_on_2d_stitch_lines": True,
    }
    with (patch.object(audit, "audit_pattern_sizes", return_value=[]),
          patch.object(audit, "audit_drape", return_value=[]),
          patch.object(audit, "audit_components", return_value={
              "missing_groups": []}),
          patch.object(audit, "audit_pattern_derived_drape", return_value=pattern)):
        report = audit.build_report(Path("unused"), Path("unused"),
                                    Path("unused"), Path("trial.json"))
    assert report["pattern_derived_drape_trial"] == pattern
    assert report["commercial_equivalence_verified"] is False
    assert any("共有頂点" in reason for reason in report["blockers"])
    assert any("生地物性" in reason for reason in report["blockers"])


def test_pattern_derived_geometry_failures_are_explicit_blockers():
    pattern = {
        "sleeves_topologically_welded_to_bodice": False,
        "fabric_inputs_measured": False,
        "upper_bodice_p95_paper_edge_strain_percent": {"C": 11.47},
        "sleeve_p95_paper_edge_strain_percent": {"左": 26.76},
        "shoulder_final_gap_p95_cm": {"A": 5.984},
    }
    with (patch.object(audit, "audit_pattern_sizes", return_value=[]),
          patch.object(audit, "audit_drape", return_value=[]),
          patch.object(audit, "audit_components", return_value={
              "missing_groups": []}),
          patch.object(audit, "audit_pattern_derived_drape", return_value=pattern)):
        report = audit.build_report(Path("unused"), Path("unused"),
                                    Path("unused"), Path("trial.json"))
    assert any("上身頃" in item and "8%" in item for item in report["blockers"])
    assert any("袖" in item and "10%" in item for item in report["blockers"])
    assert any("肩" in item and "0.5cm" in item for item in report["blockers"])


def test_front_zip_trial_gap_is_an_explicit_blocker():
    pattern = {
        "sleeves_topologically_welded_to_bodice": True,
        "fabric_inputs_measured": False,
        "front_zip_trial": {
            "mode": "sewn-front-zip-trial",
            "initial_gap_p95_cm": 36.531,
            "final_gap_p95_cm": 22.475,
            "provisional_gap_pass": False,
        },
    }
    with (patch.object(audit, "audit_pattern_sizes", return_value=[]),
          patch.object(audit, "audit_drape", return_value=[]),
          patch.object(audit, "audit_components", return_value={
              "missing_groups": []}),
          patch.object(audit, "audit_pattern_derived_drape", return_value=pattern)):
        report = audit.build_report(Path("unused"), Path("unused"),
                                    Path("unused"), Path("trial.json"))
    assert any("前ファスナー" in item and "0.5cm" in item
               for item in report["blockers"])
    assert report["commercial_equivalence_verified"] is False


def test_unclosed_waist_dart_trial_is_an_explicit_blocker():
    pattern = {
        "sleeves_topologically_welded_to_bodice": False,
        "fabric_inputs_measured": False,
        "waist_dart_trial": {
            "present": True,
            "closure_pass": False,
            "topologically_welded_to_lower_shell": False,
        },
    }
    with (patch.object(audit, "audit_pattern_sizes", return_value=[]),
          patch.object(audit, "audit_drape", return_value=[]),
          patch.object(audit, "audit_components", return_value={
              "missing_groups": []}),
          patch.object(audit, "audit_pattern_derived_drape", return_value=pattern)):
        report = audit.build_report(Path("unused"), Path("unused"),
                                    Path("unused"), Path("trial.json"))
    assert any("裾ダーツ" in reason and "閉じていない" in reason
               for reason in report["blockers"])
    assert any("裾ダーツ" in reason and "一体メッシュ" in reason
               for reason in report["blockers"])


def test_pattern_only_audit_does_not_require_legacy_assets():
    pattern = {
        "sleeves_topologically_welded_to_bodice": False,
        "fabric_inputs_measured": False,
        "sleeve_p95_paper_edge_strain_percent": {"left": 19.66},
    }
    with patch.object(audit, "audit_pattern_derived_drape",
                      return_value=pattern):
        report = audit.build_pattern_only_report(Path("trial.json"))
    assert report["pattern_derived_drape_trial"] == pattern
    assert report["scope"] == {"static_render_views": 3,
                               "physical_wear_tests": 0}
    assert report["commercial_equivalence_verified"] is False
    assert any("10%" in reason for reason in report["blockers"])
    assert any("実布" in reason for reason in report["blockers"])


def test_lower_panel_strain_and_geometry_screen_are_not_hidden():
    pattern = {
        "sleeves_topologically_welded_to_bodice": True,
        "fabric_inputs_measured": False,
        "lower_panel_p95_paper_edge_strain_percent": {"A": 23.44},
        "provisional_geometry_screen_pass": False,
    }
    blockers = audit.pattern_trial_blockers(pattern)
    assert any("下身頃" in reason and "5%" in reason for reason in blockers)
    assert any("暫定形状判定" in reason for reason in blockers)
