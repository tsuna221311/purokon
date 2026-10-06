"""Structural checks for the hand-authored fitting asset (not VRC certification)."""

import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / "web" / "static" / "models" / "endministrator_rigged_fitting.glb"


def _gltf_json():
    data = GLB.read_bytes()
    assert data[:4] == b"glTF"
    assert struct.unpack_from("<I", data, 8)[0] == len(data)
    json_length, chunk_type = struct.unpack_from("<II", data, 12)
    assert chunk_type == 0x4E4F534A
    return json.loads(data[20:20 + json_length])


def test_fitting_asset_has_one_skin_and_budgeted_materials():
    model = _gltf_json()
    assert len(model["meshes"]) == 1
    assert len(model["skins"]) == 1
    assert len(model["skins"][0]["joints"]) >= 10
    assert len(model["materials"]) <= 4
    assert len(model["meshes"][0]["primitives"]) <= 4
    triangles = sum(model["accessors"][part["indices"]]["count"] // 3
                    for part in model["meshes"][0]["primitives"])
    assert 10_000 < triangles <= 30_000


def test_each_material_primitive_keeps_uv_and_weights():
    model = _gltf_json()
    for primitive in model["meshes"][0]["primitives"]:
        attributes = primitive["attributes"]
        assert all(key in attributes for key in
                   ("POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"))


def test_cloth_and_technical_fabric_retain_distinct_pbr_finish():
    model = _gltf_json()
    materials = {material["name"]: material for material in model["materials"]}
    cloth = materials["00 combined cloth atlas"]["pbrMetallicRoughness"]
    technical = materials["01 technical nylon and shoe leather atlas"]["pbrMetallicRoughness"]
    assert "baseColorTexture" in cloth
    assert "baseColorTexture" in technical
    assert cloth["roughnessFactor"] >= .8
    assert technical["roughnessFactor"] <= .6
