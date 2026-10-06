"""Paper-only Endministrator side-seam truing is project-scoped by default."""

from pathlib import Path

from scripts.audit_endministrator_size_grid import run_case


OUTPUT = Path(__file__).resolve().parents[1] / "output"


def test_b108_paper_trial_closes_the_actual_side_seam_without_other_blockers():
    dimensions = (108, 90, 112, 165, 54, 43)
    original = run_case(dimensions, OUTPUT, disable_truing=True)
    trial = run_case(dimensions, OUTPUT)
    assert not original["digital_ready"]
    assert any("脇縫い線" in issue for issue in original["blockers"])
    assert trial["digital_ready"]
    assert not trial["blockers"]
    assert all(item["status"] == "paper_trial" and
               not item["physical_fit_verified"] and
               abs(item["adjusted_front_cm"] - item["back_half_cm"]) < .05
               for item in trial["side_seam_truing_applied"])


def test_b116_keeps_the_remaining_bust_and_shoulder_fit_blockers():
    trial = run_case((116, 84, 112, 165, 54, 42), OUTPUT)
    assert not trial["digital_ready"]
    assert any("胸ぐせダーツ" in issue for issue in trial["blockers"])
    assert any("肩幅" in issue for issue in trial["blockers"])


def test_normal_size_is_not_redrafted_unnecessarily():
    dimensions = (83, 66, 91, 158, 51, 37)
    original = run_case(dimensions, OUTPUT, disable_truing=True)
    trial = run_case(dimensions, OUTPUT)
    assert original["digital_ready"] == trial["digital_ready"]
    assert original["side_seam_stitch_lengths"] == trial["side_seam_stitch_lengths"]
    assert all(item["status"] == "already_matched"
               for item in trial["side_seam_truing_applied"])
