from scripts.audit_endministrator_nearby_sizes import nearby_cases
from scripts.audit_endministrator_size_grid import STRESS_CASES
from scripts.audit_endministrator_3d_exports import max_triangle_edge_cm


def test_nearby_stress_grid_is_reproducible_and_keeps_each_anchor():
    first = nearby_cases()
    assert first == nearby_cases()
    assert len(first) == len(STRESS_CASES) * 5
    assert first[::5] == list(STRESS_CASES)
    assert first != nearby_cases(20261008)


def test_nearby_stress_grid_only_perturbs_declared_dimensions():
    cases = nearby_cases()
    for index, baseline in enumerate(STRESS_CASES):
        for variant in cases[index * 5 + 1:index * 5 + 5]:
            assert 1 <= abs(variant[0] - baseline[0]) <= 2
            assert 1 <= abs(variant[1] - baseline[1]) <= 2
            assert 1 <= abs(variant[2] - baseline[2]) <= 2
            assert variant[3] == baseline[3]
            assert abs(variant[4] - baseline[4]) <= 1
            assert abs(variant[5] - baseline[5]) <= 1


def test_3d_export_audit_reports_actual_face_edge_length():
    assert max_triangle_edge_cm({
        "vertices_cm": [(0, 0), (3, 0), (3, 4)],
        "faces": [(0, 1, 2)],
    }) == 5.0
