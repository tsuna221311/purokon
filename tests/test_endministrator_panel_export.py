import pytest
from math import dist
from shapely.geometry import LineString, Polygon

from scripts.export_endministrator_panels import export_panels
from engine.endministrator_armhole import path_length_cm
from engine.measurements import Measurements
from engine.pattern_panel_bridge import (interpolate_pattern_surface,
                                         validate_cloth_panel_mesh)


@pytest.mark.parametrize("body", [
    (68, 54, 76, 148, 46, 33),
    (72, 70, 90, 150, 48, 35),
    (76, 60, 84, 154, 49, 35),
    (83, 66, 91, 158, 52, 37),
    (92, 74, 100, 164, 55, 39),
    (96, 74, 118, 165, 56, 42),
    (104, 88, 112, 170, 59, 43),
])
def test_export_contains_matching_bodice_and_lower_panel_seam_lines(body):
    data = export_panels(Measurements(*body))
    assert [item["code"] for item in data["panels"]] == ["A", "B", "C"]
    assert [item["code"] for item in data["bodice_hosts"]] == ["A", "B", "C"]
    assert [item["code"] for item in data["overlays"]] == ["A", "B", "C"]
    assert [item["host_code"] for item in data["front_details"]] == ["A", "B"]
    assert [item["host_code"] for item in data["lapels"]] == ["A", "B"]
    assert len(data["sleeves"]) == 2
    assert {item["side"] for item in data["sleeves"]} == {"左", "右"}
    for sleeve in data["sleeves"]:
        assert sleeve["prototype_3d_join_verified"] is False
        assert sleeve["sleeve_cap_stitch_length_cm"] == pytest.approx(
            path_length_cm(sleeve["cap_stitch_path_cm"]), abs=.001)
        assert len(sleeve["pattern_mesh"]["faces"]) > 100
        cap_mesh = sleeve["pattern_mesh"]["vertices_cm"]
        assert path_length_cm([cap_mesh[index] for index in
                               sleeve["cap_mesh_indices"]]) == pytest.approx(
            sleeve["sleeve_cap_stitch_length_cm"], abs=.01)
        assert len(sleeve["tube_side_mesh_paths"]) == 2
        for contour, path in zip(sleeve["tube_side_stitch_paths_cm"],
                                 sleeve["tube_side_mesh_paths"]):
            assert path_length_cm([cap_mesh[index] for index in path]) == pytest.approx(
                path_length_cm(contour), abs=.01)
        assert path_length_cm(sleeve["tube_side_stitch_paths_cm"][0]) == pytest.approx(
            path_length_cm(sleeve["tube_side_stitch_paths_cm"][1]), abs=.1)
    seam_audit = data["sleeve_join_audit"]
    assert seam_audit["3d_armhole_join_verified"] is False
    assert seam_audit["notch_pairing_verified_on_2d_stitch_lines"] is True
    body_marks = seam_audit["bodice_notch_distances_from_underarm_cm_by_host"]
    assert len(body_marks["A"][0]) == len(body_marks["B"][0]) == 1
    assert len(body_marks["C"]) == 2
    assert all(len(path) == 2 for path in body_marks["C"])
    assert body_marks["A"][0][0] == pytest.approx(body_marks["B"][0][0], abs=.05)
    for cap_marks in seam_audit["sleeve_notch_distances_from_underarm_cm_by_side"].values():
        assert cap_marks[0] == pytest.approx(body_marks["A"][0][0], abs=.1)
        assert sorted(cap_marks[1:]) == pytest.approx(body_marks["C"][1], abs=.1)
    assert seam_audit["direct_contour_armhole_per_arm_cm"] == pytest.approx(
        sum(host["armhole_contour_length_cm"]
            for host in data["bodice_hosts"]) / 2)
    assert seam_audit["bodice_armhole_per_arm_cm"] == pytest.approx(
        seam_audit["direct_contour_armhole_per_arm_cm"], abs=.01)
    for ease in seam_audit["cap_minus_direct_contour_cm_by_side"].values():
        assert ease == pytest.approx(1.5, abs=.1)
    for host in data["bodice_hosts"]:
        assert host["armhole_contour_length_cm"] == pytest.approx(
            sum(path_length_cm(path)
                for path in host["armhole_stitch_paths_cm"]))
        assert len(host["armhole_stitch_paths_cm"]) == (
            2 if host["code"] == "C" else 1)
        assert len(host["armhole_mesh_paths"]) == len(
            host["armhole_stitch_paths_cm"])
        mesh_vertices = host["pattern_mesh"]["vertices_cm"]
        for contour, mesh_path in zip(host["armhole_stitch_paths_cm"],
                                      host["armhole_mesh_paths"]):
            assert path_length_cm([mesh_vertices[index] for index in
                                   mesh_path]) == pytest.approx(
                path_length_cm(contour), abs=.01)
        assert len(host["side_seam_segments_cm"]) == (
            2 if host["code"] == "C" else len(host["side_bust_darts"]) + 1)
        for contour, mesh_path in zip(host["side_seam_segments_cm"],
                                      host["side_mesh_paths"]):
            assert path_length_cm([mesh_vertices[index] for index in
                                   mesh_path]) == pytest.approx(
                path_length_cm(contour), abs=.01)
        if host["code"] != "C":
            underarm_index = host["stitch_outline_cm"].index(
                host["armhole_stitch_paths_cm"][0][0])
            assert sum(path_length_cm(path) for path in
                       host["side_seam_segments_cm"]) < path_length_cm(
                           host["stitch_outline_cm"][:underarm_index + 1]) / 2
        darts = host["side_bust_darts"]
        if host["code"] == "C":
            assert not darts
        else:
            assert len(darts) in (1, 2)
        for dart in darts:
            assert dart["mouth_gap_cm"] > 0
            assert path_length_cm(dart["leg_a_cm"]) == pytest.approx(
                path_length_cm(dart["leg_b_cm"]), abs=.1)
            for side in ("a", "b"):
                mesh_path = dart[f"leg_{side}_mesh_indices"]
                assert path_length_cm([mesh_vertices[index] for index in
                                       mesh_path]) == pytest.approx(
                    dart["leg_length_cm"], abs=.1)
    effective_sides = {
        host["code"]: [path_length_cm(path) for path in
                       host["side_seam_segments_cm"]]
        for host in data["bodice_hosts"]}
    assert abs(sum(effective_sides["A"]) - effective_sides["C"][1]) < .5
    assert abs(sum(effective_sides["B"]) - effective_sides["C"][0]) < .5
    width_audit = data["open_bodice_width_audit"]
    assert width_audit["open_coat_width_is_not_finished_circumference"] is True
    assert width_audit["not_wearer_fit_validation"] is True
    assert [row["station"] for row in width_audit["sections"]] == [
        "bust_proxy", "waist_proxy", "high_hip_proxy"]
    for row in width_audit["sections"]:
        widths = row["paper_widths"]
        assert list(widths) == ["A", "B", "C"]
        assert widths["A"]["material_width_cm"] == pytest.approx(
            widths["B"]["material_width_cm"], abs=.002)
        assert row["open_paper_material_sum_cm"] == pytest.approx(
            sum(part["material_width_cm"] for part in widths.values()), abs=.002)
        assert row["body_proxy_reference_cm"] > 0
    for detail in data["front_details"]:
        host = next(item for item in data["bodice_hosts"]
                    if item["code"] == detail["host_code"])
        attachment = LineString(detail["host_attachment_line_cm"])
        assert attachment.length > 30
        assert attachment.distance(Polygon(host["stitch_outline_cm"]).boundary) < .001
        assert attachment.distance(Polygon(detail["stitch_outline_cm"]).boundary) < .001
        assert len(detail["pattern_mesh"]["faces"]) > 100
        assert detail["prototype_only"] is True
        assert detail["attachment_construction_verified"] is False
    for lapel in data["lapels"]:
        host = next(item for item in data["bodice_hosts"]
                    if item["code"] == lapel["host_code"])
        attachment = LineString(lapel["host_attachment_line_cm"])
        assert attachment.length > 8
        assert attachment.distance(Polygon(host["stitch_outline_cm"]).boundary) < .001
        assert attachment.distance(Polygon(lapel["stitch_outline_cm"]).boundary) < .001
        assert len(lapel["pattern_mesh"]["faces"]) > 50
        assert lapel["fold_line_verified"] is False
    assert all(abs(base["top_width_cm"] - overlay["top_width_cm"]) < .1
               for base, overlay in zip(data["panels"], data["overlays"]))
    assert all(host["hem_seam_allowance_cm"] == lower["seam_allowance_cm"]
               == overlay["seam_allowance_cm"] > 0
               for host, lower, overlay in zip(
                   data["bodice_hosts"], data["panels"], data["overlays"]))
    side_lengths = [dist(panel["stitch_outline_cm"][a],
                         panel["stitch_outline_cm"][b])
                    for panel in data["panels"] for a, b in ((0, 3), (1, 2))]
    assert max(side_lengths) - min(side_lengths) < 1e-5
    for host, lower in zip(data["bodice_hosts"], data["panels"]):
        assert abs(host["hem_stitch_width_cm"] - lower["top_width_cm"]) < .1
        assert len(host["stitch_outline_cm"]) > 10
        assert len(host["cut_outline_cm"]) > 10
        assert len(host["hem_notch_x_cm"]) >= 2
        assert len(host["pattern_mesh"]["vertices_cm"]) > 100
        assert len(host["pattern_mesh"]["faces"]) > 100
        assert abs(host["pattern_mesh"]["hem_width_cm"]
                   - lower["top_width_cm"]) < .1
        upper_grid = [host["pattern_mesh"]["vertices_cm"][index][0]
                      - host["hem_stitch_left_cm"]
                      for index in host["pattern_mesh"]["hem_indices"]]
        lower_grid = [lower["vertices_cm"][index][0]
                      - lower["vertices_cm"][lower["top_indices"][0]][0]
                      for index in lower["top_indices"]]
        assert len(upper_grid) == len(lower_grid)
        assert max(abs(a - b) for a, b in zip(upper_grid, lower_grid)) < 1e-5


def test_large_coat_side_seam_is_trued_before_panel_export():
    data = export_panels(Measurements(116, 100, 128, 180, 64, 45))
    assert not data["side_seam_unresolved_diagnostic_only"]
    assert data["do_not_cut_or_publish_as_ready"]
    assert not data["physical_fit_and_materials_verified"]
    assert data["simulation_input_ready"]
    assert not data["bodice_boundary_incomplete"]
    with pytest.raises(ValueError, match="Invalid coat side seams"):
        export_panels(Measurements(116, 100, 128, 180, 64, 45),
                      disable_side_seam_truing=True)


def test_rounded_back_armhole_notch_is_measured_to_the_real_underarm():
    # Formerly stopped one curve edge early and failed the notch gate.
    # The default paper truing now closes the side-seam gap, while the
    # uncorrected control remains independently rejected.
    data = export_panels(Measurements(84, 65, 95, 148, 47, 36))
    assert data["sleeve_join_audit"]["notch_pairing_verified_on_2d_stitch_lines"]
    with pytest.raises(ValueError, match="Invalid coat side seams"):
        export_panels(Measurements(84, 65, 95, 148, 47, 36),
                      disable_side_seam_truing=True)


def test_b112_waist_dart_hems_export_as_disjoint_sewn_runs_not_false_bridges():
    data = export_panels(Measurements(112, 82, 116, 170, 57, 43))
    assert data["do_not_cut_or_publish_as_ready"]
    assert not data["physical_fit_and_materials_verified"]
    assert not data["simulation_input_ready"]
    assert data["darted_hem_hosts_pending_3d_sewing"] == ["A", "B", "C"]
    for host, lower in zip(data["bodice_hosts"], data["panels"]):
        runs = host["hem_sewn_runs_cm"]
        mesh = host["pattern_mesh"]
        assert len(runs) == (3 if host["code"] == "C" else 2)
        assert len(host["hem_waist_darts"]) == len(runs) - 1
        assert len(mesh["hem_paths"]) == len(runs)
        assert mesh["constrained_boundary_only"]
        assert validate_cloth_panel_mesh(mesh)["faces"] == len(mesh["faces"])
        assert sum(right - left for left, right in runs) == pytest.approx(
            host["hem_stitch_width_cm"], abs=.001)
        assert host["hem_stitch_width_cm"] == pytest.approx(
            lower["top_width_cm"], abs=.001)
        for dart in host["hem_waist_darts"]:
            assert dart["mouth_gap_cm"] > .2
            assert not dart["sewn_to_lower_panel"]
            assert not dart["3d_sewing_verified"]
            assert path_length_cm(dart["leg_a_cm"]) == pytest.approx(
                path_length_cm(dart["leg_b_cm"]), abs=.1)


@pytest.mark.parametrize("measurements", [
    (87, 75, 98, 155, 49, 41),
    (100, 90, 109, 160, 52, 44),
])
def test_front_contrast_boundary_fallback_preserves_attachment(measurements):
    data = export_panels(Measurements(*measurements))
    assert data["simulation_input_ready"]
    assert not data["bodice_boundary_incomplete"]
    assert all(host["mesh_boundary_coverage"]["complete"]
               for host in data["bodice_hosts"])
    if measurements[0] == 87:
        assert sum(host["pattern_mesh"]["boundary_gap_patch_faces"]
                   for host in data["bodice_hosts"]) >= 4
    assert [part["mesh_strategy"] for part in data["front_details"]] == [
        "boundary_constrained_fallback", "boundary_constrained_fallback"]
    for detail in data["front_details"]:
        mesh = detail["pattern_mesh"]
        host = next(host for host in data["bodice_hosts"]
                    if host["code"] == detail["host_code"])
        host_mesh = host["pattern_mesh"]
        host_surface = [(x, y, 0) for x, y in host_mesh["vertices_cm"]]
        assert validate_cloth_panel_mesh(mesh)["faces"] == len(mesh["faces"])
        assert all(interpolate_pattern_surface(
            point, host_mesh["vertices_cm"], host_mesh["faces"],
            host_surface) is not None for point in mesh["vertices_cm"])


def test_sloped_front_opening_keeps_the_full_contrast_panel_attachment():
    data = export_panels(Measurements(96, 74, 118, 165, 56, 42))
    assert all(LineString(detail["host_attachment_line_cm"]).length > 50
               for detail in data["front_details"])
