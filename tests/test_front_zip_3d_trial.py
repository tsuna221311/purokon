"""The Blender closure trial must use the actual drafted centre-front seam."""

from math import dist

import pytest

from engine.measurements import Measurements
from engine.zip_front_geometry import front_zip_center_path
from scripts.export_endministrator_panels import export_panels


def test_endministrator_front_openings_pair_on_the_paper_stitch_line():
    exported = export_panels(Measurements(87, 75, 98, 155, 49, 41))
    fronts = [host for host in exported["bodice_hosts"]
              if host["code"] in {"A", "B"}]
    assert len(fronts) == 2
    for host in fronts:
        path = host["front_opening_stitch_path_cm"]
        indices = host["front_opening_mesh_path"]
        paper = host["pattern_mesh"]["vertices_cm"]
        assert path == front_zip_center_path(
            host["stitch_outline_cm"], host["hem_stitch_y_cm"])
        assert len(indices) > 10 and len(set(indices)) == len(indices)
        assert dist(paper[indices[0]], path[0]) < .03
        assert dist(paper[indices[-1]], path[-1]) < .03
    left, right = fronts
    assert left["front_opening_stitch_path_cm"] == right[
        "front_opening_stitch_path_cm"]


def test_front_opening_rejects_an_unrelated_contour():
    with pytest.raises(ValueError, match="opening"):
        front_zip_center_path([(0, 0), (1, 0), (1, 1)], 1)
