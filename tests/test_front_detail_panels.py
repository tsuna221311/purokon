"""The provisional visible front pieces must follow the generated bodice."""

import pytest
from shapely.geometry import LineString, Polygon

from engine.costume_projects import get_costume_project
from engine.front_detail_panels import (draft_exterior_front_panel,
                                        draft_neck_lapel)
from engine.measurements import Measurements
from engine.pattern_panel_bridge import sample_panel, validate_cloth_panel_mesh
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                             build_garment_spec, merge_custom_panel_requests)


@pytest.mark.parametrize("body", [
    (76, 60, 84, 154, 49, 35),
    (83, 66, 91, 158, 52, 37),
    (92, 74, 100, 164, 55, 39),
    (104, 88, 112, 170, 59, 43),
])
def test_visible_front_detail_has_real_host_attachment(body):
    measurements = Measurements(*body)
    project = get_costume_project("endministrator_female", measurements)
    spec = build_garment_spec(**project.garment_spec_kwargs)
    requests = [request for panel in project.custom_panel_specs
                for request in build_custom_panel_requests(
                    panel.label, panel.points_cm, quantity=panel.quantity,
                    mirror=panel.mirror, allow_split=panel.allow_split)]
    spec.parts = merge_custom_panel_requests(
        spec.parts, requests, princess_line=spec.princess_line)
    spec.construction["costume_project_brief"] = project.as_dict()
    result = PatternForgePipeline(output_dir="output").generate_from_selection(
        spec, measurements, lining=project.lining,
        worn_over_bust_cm=project.worn_over_bust_cm,
        shoulder_drop_cm=project.shoulder_drop_cm, skip_export=True)
    hosts = [part for part in result.finalized_parts
             if part.part_type == "front_bodice_zip_panel"]
    assert len(hosts) == 2
    for host in hosts:
        drafted = draft_exterior_front_panel(host)
        piece = drafted.part
        assert piece.part_type == "custom_panel"
        assert piece.seam_allowance_cm == host.seam_allowance_cm
        assert Polygon(piece.stitch_line).is_valid
        assert Polygon(piece.cut_line).is_valid
        assert len(piece.notches) >= 3
        edge = LineString(drafted.host_attachment_line_cm)
        assert edge.length > 30
        assert edge.distance(Polygon(host.stitch_line).boundary) < .01
        assert edge.distance(Polygon(piece.stitch_line).boundary) < .01
        lapel = draft_neck_lapel(host)
        assert Polygon(lapel.part.stitch_line).is_valid
        assert Polygon(lapel.part.cut_line).is_valid
        assert len(lapel.part.notches) >= 3
        neckline = LineString(lapel.host_attachment_line_cm)
        assert neckline.length > 8
        assert neckline.distance(Polygon(host.stitch_line).boundary) < .001
        assert neckline.distance(Polygon(lapel.part.stitch_line).boundary) < .001
        mesh = sample_panel(lapel.part.stitch_line, strict_boundary=True,
                            require_horizontal_top=False)
        assert validate_cloth_panel_mesh(mesh)["faces"] > 50


def test_visible_front_detail_rejects_non_front_host():
    with pytest.raises((AttributeError, ValueError)):
        draft_exterior_front_panel(None)
    with pytest.raises((AttributeError, ValueError)):
        draft_neck_lapel(None)
