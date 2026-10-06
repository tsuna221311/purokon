import pytest
from pathlib import Path

from engine.vrc_outfit_audit import audit_gltf, read_glb_json


def test_skinned_textured_outfit_reports_structural_metrics():
    model = {
        "accessors": [{"count": 300}],
        "meshes": [{"primitives": [{
            "indices": 0,
            "attributes": {"POSITION": 0, "NORMAL": 0, "TEXCOORD_0": 0,
                           "JOINTS_0": 0, "WEIGHTS_0": 0},
        }]}],
        "skins": [{"joints": [1]}],
        "materials": [{"pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0},
            "metallicRoughnessTexture": {"index": 1},
        }, "normalTexture": {"index": 2}}],
        "textures": [{}, {}, {}],
    }
    report = audit_gltf(model)
    assert report["triangles"] == 100
    assert report["normal_map_count"] == 1
    assert report["roughness_map_count"] == 1
    assert report["issues"] == []
    assert report["improvement_opportunities"] == []
    assert report["vrchat_certified"] is False


def test_static_untextured_preview_does_not_claim_vrc_ready():
    model = {"accessors": [{"count": 6}],
             "meshes": [{"primitives": [{"indices": 0, "attributes": {"POSITION": 0}}]}]}
    report = audit_gltf(model)
    assert report["triangles"] == 2
    assert report["skin_count"] == 0
    assert len(report["issues"]) >= 3


def test_bad_glb_rejected(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"bad")
    with pytest.raises(ValueError, match="Not a GLB"):
        read_glb_json("bad.glb")
