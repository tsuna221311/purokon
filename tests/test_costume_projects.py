"""衣装プロジェクトは非対称パネルを黙ってミラーしない。"""

from engine.costume_projects import costume_project_choices, get_costume_project
from engine.measurements import Measurements


BODY = Measurements(83, 66, 91, 158, 52, 37)


def test_endministrator_project_contains_a_complete_project_plan():
    project = get_costume_project("endministrator_female", BODY)
    assert project is not None
    assert project.lining is True
    assert project.shoulder_drop_cm == 5.0
    assert project.worn_over_bust_cm == 93.0
    assert project.patternable_components
    assert project.separate_components
    assert project.material_plan
    assert project.construction_plan
    assert project.limitations


def test_endministrator_project_keeps_each_asymmetric_tail_as_its_own_panel():
    project = get_costume_project("endministrator_female", BODY)
    assert project is not None
    panels = project.custom_panel_specs
    assert len(panels) == 3
    assert all(panel.mirror is False for panel in panels)
    assert panels[0].points_cm != panels[1].points_cm


def test_unknown_costume_project_is_rejected_and_empty_selection_is_allowed():
    assert get_costume_project("", BODY) is None
    assert any(key == "endministrator_female" for key, _label in costume_project_choices())
    try:
        get_costume_project("not-a-project", BODY)
    except ValueError as exc:
        assert "不正" in str(exc)
    else:
        raise AssertionError("unknown project must not be ignored")


def test_researched_projects_have_a_pattern_plan_and_commercial_gap_checklist():
    keys = ("endministrator_male", "perlica", "chen_qianyu",
            "hatsune_miku_classic", "yor_forger_thorn_princess")
    for key in keys:
        project = get_costume_project(key, BODY)
        assert project is not None
        assert project.custom_panel_specs
        assert project.patternable_components
        assert project.separate_components
        assert project.commercial_benchmark
        assert all(panel.mirror is False for panel in project.custom_panel_specs)


def test_all_selectable_project_keys_resolve():
    for key, _label in costume_project_choices():
        if key:
            assert get_costume_project(key, BODY) is not None


def test_catalog_has_fifty_total_character_presets_and_uses_known_silhouettes():
    projects = [get_costume_project(key, BODY)
                for key, _label in costume_project_choices() if key]
    assert len(projects) == 50
    assert all(project is not None for project in projects)
    assert all(project.garment_spec_kwargs for project in projects)
