import json
import struct
from pathlib import Path

from scripts.add_gltf_roughness import add_roughness


def test_roughness_patch_preserves_geometry_and_adds_two_maps(monkeypatch):
    model = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": 4}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 4}],
        "materials": [
            {"name": "00 combined cloth atlas", "pbrMetallicRoughness": {}},
            {"name": "01 technical nylon and shoe leather atlas", "pbrMetallicRoughness": {}},
        ],
        "accessors": [{"count": 3}],
        "meshes": [{"primitives": [{"indices": 0, "attributes": {"POSITION": 0}}]}],
    }
    payload = json.dumps(model).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    original = (struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(payload) + 8 + 4)
                + struct.pack("<II", len(payload), 0x4E4F534A) + payload
                + struct.pack("<II", 4, 0x004E4942) + b"DATA")
    written = {}
    monkeypatch.setattr(Path, "read_bytes", lambda self: original)
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: written.setdefault(str(self), data))
    result = add_roughness("in.glb", "out.glb")
    patched = written["out.glb"]
    json_size = struct.unpack_from("<I", patched, 12)[0]
    updated = json.loads(patched[20:20 + json_size])
    assert result["materials_updated"] == [
        "00 combined cloth atlas", "01 technical nylon and shoe leather atlas"]
    assert updated["meshes"] == model["meshes"]
    assert updated["accessors"] == model["accessors"]
    assert len(updated["textures"]) == 1
    assert all("metallicRoughnessTexture" in item["pbrMetallicRoughness"]
               for item in updated["materials"])
    assert struct.unpack_from("<I", patched, 8)[0] == len(patched)
