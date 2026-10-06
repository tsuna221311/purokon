import pytest
from collections import Counter
import math

from engine.pattern_panel_bridge import (aligned_trapezoid_distance,
                                         cloth_mesh_boundary_coverage,
                                         horizontal_span, interpolate_pattern_surface,
                                         interpolate_pattern_surface_with_normal,
                                         outward_wound_faces,
                                         relax_connected_shell_to_paper_edges,
                                         relax_overlay_to_paper_edges,
                                         place_three_panel_tops, pair_seam_vertices, sample_panel,
                                         require_initial_sewing_clearance,
                                         validate_cloth_panel_mesh,
                                         weld_seam_vertices,
                                         xy_scale_for_polyline_length)


def test_polygon_sampling_preserves_top_stitch_width_and_taper():
    outline = [(0, 0), (30.75, 0), (33.4, 27.3),
               (12.7, 37.92), (0, 15.16), (0, 0)]
    sampled = sample_panel(outline)
    assert sampled["top_width_cm"] == pytest.approx(30.75)
    assert sampled["height_cm"] == pytest.approx(37.92)
    assert len(sampled["vertices_cm"]) > 100
    assert len(sampled["faces"]) > 100
    assert sampled["vertices_cm"][sampled["top_indices"][0]] == (0, 0)
    assert sampled["boundary_paths"][0] == sampled["top_indices"]
    assert len(sampled["boundary_paths"]) == 5
    assert horizontal_span(outline, 27.3) == pytest.approx((6.77, 33.4), abs=.02)


def test_flared_panel_has_no_zero_area_faces_or_internal_stitch_edges():
    mesh = sample_panel([(0, 0), (30.75, 0), (39.85, 37.92),
                         (-9.1, 37.92)])
    vertices = mesh["vertices_cm"]
    counts = Counter(tuple(sorted((face[index], face[(index + 1) % 3])))
                     for face in mesh["faces"] for index in range(3))
    for path in mesh["boundary_paths"]:
        assert all(counts[tuple(sorted((a, b)))] == 1
                   for a, b in zip(path, path[1:]))
    assert all(abs((vertices[b][0] - vertices[a][0])
                   * (vertices[c][1] - vertices[a][1])
                   - (vertices[b][1] - vertices[a][1])
                   * (vertices[c][0] - vertices[a][0])) > 2e-8
               for a, b, c in mesh["faces"])


def test_nonquadrilateral_overlay_has_no_orphan_boundary_particles():
    mesh = sample_panel([(0, 0), (30.75, 0), (26.445, 18.2016),
                         (17.22, 37.92), (2.46, 27.6816), (0, 0)],
                        strict_boundary=True)
    used = {index for face in mesh["faces"] for index in face}
    edge_faces = Counter(tuple(sorted((face[index], face[(index + 1) % 3])))
                         for face in mesh["faces"] for index in range(3))
    assert used == set(range(len(mesh["vertices_cm"])))
    assert all(edge_faces[tuple(sorted((a, b)))] == 1
               for path in mesh["boundary_paths"]
               for a, b in zip(path, path[1:]))
    assert validate_cloth_panel_mesh(mesh)["vertices"] == len(mesh["vertices_cm"])
    broken = {**mesh, "faces": [face for face in mesh["faces"] if 0 not in face]}
    with pytest.raises(ValueError, match="disconnected|non-boundary"):
        validate_cloth_panel_mesh(broken)


def test_cloth_panel_validation_rejects_broken_face_topology():
    mesh = sample_panel([(0, 0), (8, 0), (8, 6), (0, 6), (0, 0)],
                        strict_boundary=True)
    duplicate = {**mesh, "faces": mesh["faces"] + [mesh["faces"][0]]}
    with pytest.raises(ValueError, match="duplicate triangles"):
        validate_cloth_panel_mesh(duplicate)
    collapsed = {**mesh, "vertices_cm": list(mesh["vertices_cm"])}
    a, b, _c = mesh["faces"][0]
    collapsed["vertices_cm"][b] = collapsed["vertices_cm"][a]
    with pytest.raises(ValueError, match="degenerate triangles"):
        validate_cloth_panel_mesh(collapsed)
    invalid = {**mesh, "vertices_cm": list(mesh["vertices_cm"])}
    invalid["vertices_cm"][0] = (float("nan"), 0)
    with pytest.raises(ValueError, match="invalid vertex coordinates"):
        validate_cloth_panel_mesh(invalid)
    area_mismatch = {**mesh, "stitch_area_cm2": mesh["stitch_area_cm2"] * 2}
    with pytest.raises(ValueError, match="area does not match"):
        validate_cloth_panel_mesh(area_mismatch)
    flipped = {**mesh, "faces": list(mesh["faces"])}
    a, b, c = flipped["faces"][0]
    flipped["faces"][0] = (a, c, b)
    with pytest.raises(ValueError, match="inconsistent triangle winding"):
        validate_cloth_panel_mesh(flipped)
    islands = {
        "vertices_cm": [(0, 0), (1, 0), (0, 1), (3, 0), (4, 0), (3, 1)],
        "faces": [(0, 1, 2), (3, 4, 5)],
        "boundary_paths": [[0, 1], [3, 4]],
    }
    with pytest.raises(ValueError, match="disconnected mesh islands"):
        validate_cloth_panel_mesh(islands)
    non_manifold = {
        "vertices_cm": [(0, 0), (1, 0), (0, 1), (0, 2), (1, 1)],
        "faces": [(0, 1, 2), (0, 1, 3), (0, 1, 4)],
        "boundary_paths": [[1, 2]],
    }
    with pytest.raises(ValueError, match="non-manifold"):
        validate_cloth_panel_mesh(non_manifold)


def test_mesh_boundary_coverage_detects_unlisted_open_edges():
    mesh = sample_panel([(0, 0), (8, 0), (8, 6), (0, 6), (0, 0)],
                        strict_boundary=True)
    assert cloth_mesh_boundary_coverage(mesh)["complete"]
    incomplete = {**mesh, "boundary_paths": mesh["boundary_paths"][:-1]}
    report = cloth_mesh_boundary_coverage(incomplete)
    assert not report["complete"]
    assert report["undeclared_mesh_boundary_edges"] > 0


def test_bad_scanline_is_rejected():
    with pytest.raises(ValueError, match="crossings"):
        horizontal_span([(0, 0), (1, 0), (1, 1), (0, 1)], 2)


def test_panel_tops_fit_real_bodice_hem_without_stretching():
    widths = {"A": 30.75, "B": 30.75, "C": 52.5}
    starts = place_three_panel_tops(127.5, widths)
    assert starts["B"] == 0
    assert starts["C"] == pytest.approx(37.5)
    assert starts["A"] + widths["A"] == pytest.approx(127.5)
    with pytest.raises(ValueError, match="shorter"):
        place_three_panel_tops(100, widths)


def test_guide_hem_scaling_accounts_for_vertical_fold_length():
    guide = [(0, 0, 0), (1, 0, .2), (2, 0, 0)]
    scale = xy_scale_for_polyline_length(guide, 2.0)
    assert scale < 1
    assert 2 * (scale * scale + .2 * .2) ** .5 == pytest.approx(2.0)


def test_sewing_spring_pairing_covers_both_unequal_seam_grids():
    pairs = pair_seam_vertices([10, 15, 20], [0, 4, 8, 10])
    assert {a for a, _b in pairs} == {0, 1, 2}
    assert {b for _a, b in pairs} == {0, 1, 2, 3}
    with pytest.raises(ValueError, match="do not match"):
        pair_seam_vertices([0, 10], [0, 20])
    with pytest.raises(ValueError, match="do not match"):
        pair_seam_vertices([0, 10], [0, 10.32])
    assert pair_seam_vertices([0, 5, 10], [0, 5.16, 10.32],
                              max_length_mismatch_cm=.5)


def test_overlay_point_maps_to_draped_triangle_but_not_outside_cut_shape():
    paper = [(0, 0), (2, 0), (0, 2)]
    draped = [(0, 0, 1), (2, 0, 2), (0, 2, 3)]
    assert interpolate_pattern_surface(
        (.5, .5), paper, [(0, 1, 2)], draped) == pytest.approx((.5, .5, 1.75))
    assert interpolate_pattern_surface((2, 2), paper, [(0, 1, 2)], draped) is None
    with pytest.raises(ValueError, match="vertex counts"):
        interpolate_pattern_surface((0, 0), paper, [(0, 1, 2)], draped[:2])


def test_overlay_mapping_supplies_the_draped_surface_normal():
    paper = [(0, 0), (2, 0), (0, 2)]
    surface = [(0, 0, 0), (2, 0, 0), (0, 2, 0)]
    mapped = interpolate_pattern_surface_with_normal(
        (.5, .5), paper, [(0, 1, 2)], surface)
    assert mapped is not None
    point, normal = mapped
    assert point == pytest.approx((.5, .5, 0))
    assert normal == pytest.approx((0, 0, 1))
    assert interpolate_pattern_surface_with_normal(
        (2, 2), paper, [(0, 1, 2)], surface) is None


def test_welded_side_seam_is_one_surface_without_losing_panel_faces():
    vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0),
                (1.1, 0, 0), (2, 0, 0), (1.1, 1, 0)]
    faces = [(0, 1, 2), (3, 4, 5)]
    result = weld_seam_vertices(vertices, faces, [(0, 2), (3, 5)], [(1, 3)])
    welded, triangles, springs, remap = result
    assert len(welded) == 5
    assert remap[1] == remap[3]
    assert welded[remap[1]] == pytest.approx((1.05, 0, 0))
    assert all(len(set(face)) == 3 for face in triangles)
    assert len(springs) == 2
    with pytest.raises(ValueError, match="collapsed"):
        weld_seam_vertices(vertices, faces, [], [(0, 1)])


def test_wrapped_panel_faces_point_outward_after_placement():
    vertices = [(1, -1, 0), (1, 1, 0), (1, 1, 1)]
    faces, flipped = outward_wound_faces(vertices, [(0, 1, 2)])
    assert faces == [(0, 1, 2)]
    assert not flipped
    faces, flipped = outward_wound_faces(vertices, [(2, 1, 0)])
    assert faces == [(0, 1, 2)]
    assert flipped
    with pytest.raises(ValueError, match="ambiguous"):
        outward_wound_faces([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])


def test_overlay_relaxation_reduces_initial_pattern_edge_error():
    paper = [(0, 0), (10, 0), (10, 10), (0, 10)]
    initial = [(0, 0, .02), (.2, 0, .02),
               (.16, .14, .02), (0, .14, .02)]
    support = [(x, y, 0) for x, y, _z in initial]
    faces = [(0, 1, 2), (0, 2, 3)]
    normals = [(0, 0, 1)] * 4
    relaxed = relax_overlay_to_paper_edges(
        initial, paper, faces, [0, 1], support, normals)
    edges = {(min(a, b), max(a, b))
             for face in faces for a, b in zip(face, face[1:] + face[:1])}

    def error(points):
        return sum(abs(math.dist(points[a], points[b])
                       / (math.dist(paper[a], paper[b]) * .02) - 1)
                   for a, b in edges)

    assert relaxed[:2] == initial[:2]
    assert error(relaxed) < error(initial) * .5
    assert all(point[2] >= .018 for point in relaxed)


def test_connected_shell_relaxation_keeps_welded_edge_and_pinned_bodice():
    # Two adjacent panels share vertices 1 and 4, like a welded side seam.
    paper = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]
    initial = [(0, 0, 0), (1, 0, 0), (2, 0, 0),
               (0, .7, 0), (1, .7, 0), (2, .7, 0)]
    triangles = [(0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4)]
    edges = {tuple(sorted((a, b))) for face in triangles
             for a, b in zip(face, face[1:] + face[:1])}
    targets = {edge: math.dist(paper[edge[0]], paper[edge[1]])
               for edge in edges}
    relaxed = relax_connected_shell_to_paper_edges(
        initial, targets, [0, 1, 2], max_guide_distance_m=.5)

    def error(points):
        return sum(abs(math.dist(points[a], points[b]) / target - 1)
                   for (a, b), target in targets.items())

    assert relaxed[:3] == initial[:3]
    assert error(relaxed) < error(initial) * .5
    assert relaxed[4][1] > initial[4][1]
    with pytest.raises(ValueError, match="paper edge"):
        relax_connected_shell_to_paper_edges(initial, {(1, 0): 0}, [0])



def test_flared_panel_side_edges_start_from_shared_seam_locations():
    front = [(0, 0), (30.75, 0), (33.7836, 37.92), (-3.0336, 37.92)]
    back = [(0, 0), (52.5, 0), (55.5336, 37.92), (-3.0336, 37.92)]
    assert aligned_trapezoid_distance((33.7836, 37.92), front, 0) == pytest.approx(30.75)
    assert aligned_trapezoid_distance((-3.0336, 37.92), back, 30.75) == pytest.approx(30.75)
    assert aligned_trapezoid_distance((0, 0), back, 30.75) == pytest.approx(30.75)
    assert aligned_trapezoid_distance((52.5, 0), back, 30.75) == pytest.approx(83.25)


def test_sewing_clearance_rejects_remote_neckline_even_if_shoulder_tip_is_near():
    vertices = [(0, 0, 0), (.12, 0, 0),
                (0, .66, 0), (.12, .14, 0)]
    # The first pair is 33 cm apart; the second is only 7 cm apart.
    with pytest.raises(ValueError, match="33.00 cm exceeds 10.00 cm"):
        require_initial_sewing_clearance(vertices, [(0, 2), (1, 3)])
    assert require_initial_sewing_clearance(
        vertices, [(1, 3)]) == {"spring_count": 1, "maximum_gap_cm": 7.0}
    with pytest.raises(ValueError, match="invalid spring indices"):
        require_initial_sewing_clearance(vertices, [(0, 4)])
