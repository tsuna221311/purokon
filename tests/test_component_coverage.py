import pytest

from engine.component_coverage import audit_component_nodes


def test_missing_commercial_piece_remains_visible_in_report():
    model = {"nodes": [
        {"name": "separate shorts leg-1", "mesh": 0},
        {"name": "separate shorts leg1", "mesh": 1},
        {"name": "hair ornament", "children": []},  # no exported mesh
    ]}
    result = audit_component_nodes(model, [
        {"component": "shorts", "name_contains": "shorts leg", "required_count": 2},
        {"component": "hair accessory", "name_contains": "hair ornament"},
    ])
    assert result["present_groups"] == 1
    assert result["expected_groups"] == 2
    assert result["components"][0]["found_count"] == 2
    assert result["components"][1]["present"] is False


def test_invalid_manifest_does_not_turn_empty_name_into_a_match():
    with pytest.raises(ValueError):
        audit_component_nodes({"nodes": [{"name": "coat", "mesh": 0}]},
                              [{"component": "coat", "name_contains": ""}])


def test_geometry_check_rejects_wrong_location_despite_matching_name():
    model = {
        "nodes": [{"name": "cuff removable wrap band-1", "mesh": 0,
                   "translation": [0, 0, 0]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"min": [-.1, -.1, -.1], "max": [.1, .1, .1]}],
    }
    result = audit_component_nodes(model, [{
        "component": "cuff", "name_contains": "cuff removable wrap band",
        "center_region": {"x_abs": [1.4, 1.9]}, "min_extent": {"z": .25},
    }])
    assert result["present_groups"] == 1
    assert result["geometry_pass_groups"] == 0
    assert result["components"][0]["geometry_ok"] is False


def test_geometry_check_applies_node_translation_and_bilateral_rule():
    model = {
        "nodes": [
            {"name": "arm wrap left", "mesh": 0, "translation": [-1.6, .45, 0]},
            {"name": "arm wrap right", "mesh": 0, "translation": [1.6, .45, 0]},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"min": [-.1, -.1, -.18], "max": [.1, .1, .18]}],
    }
    rule = {"component": "cuffs", "name_contains": "arm wrap", "required_count": 2,
            "center_region": {"x_abs": [1.4, 1.9]}, "min_extent": {"z": .25},
            "bilateral": True}
    result = audit_component_nodes(model, [rule])
    assert result["geometry_pass_groups"] == 1
    model["nodes"][1]["translation"][0] = -1.8
    assert audit_component_nodes(model, [rule])["geometry_pass_groups"] == 0


def test_possible_overlap_with_other_component_is_not_silently_passed():
    model = {
        "nodes": [
            {"name": "shoulder shell", "mesh": 0, "translation": [1, .9, 0]},
            {"name": "upper arm band", "mesh": 0, "translation": [1.08, .9, 0]},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"min": [-.1, -.1, -.1], "max": [.1, .1, .1]}],
    }
    rules = [
        {"component": "shoulder", "name_contains": "shoulder shell"},
        {"component": "arm", "name_contains": "upper arm band",
         "avoid_overlap_with": ["shoulder"]},
    ]
    report = audit_component_nodes(model, rules)
    assert report["components"][1]["possible_overlap_with"] == ["shoulder"]
    assert report["components"][1]["geometry_ok"] is False
