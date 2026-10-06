"""Read-only structural audit for an exported VRChat-style outfit GLB.

Visual fidelity, skin clipping and Unity/VRChat behavior cannot be certified
from a GLB. This module deliberately reports those as manual checks.
"""

import json
import struct
from pathlib import Path


def read_glb_json(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("Not a GLB file")
    total_length = struct.unpack_from("<I", data, 8)[0]
    json_length, chunk_type = struct.unpack_from("<II", data, 12)
    if total_length != len(data) or chunk_type != 0x4E4F534A or 20 + json_length > len(data):
        raise ValueError("Invalid GLB header or JSON chunk")
    return json.loads(data[20:20 + json_length])


def audit_gltf(model):
    accessors = model.get("accessors", [])
    meshes = model.get("meshes", [])
    materials = model.get("materials", [])
    primitives = [primitive for mesh in meshes for primitive in mesh.get("primitives", [])]
    triangles = 0
    missing = {name: 0 for name in ("NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0")}
    for primitive in primitives:
        mode = primitive.get("mode", 4)
        indices = primitive.get("indices")
        if indices is not None and 0 <= indices < len(accessors):
            count = accessors[indices]["count"]
        else:
            position = primitive.get("attributes", {}).get("POSITION")
            count = accessors[position]["count"] if position is not None else 0
        if mode == 4:
            triangles += count // 3
        elif mode in (5, 6):
            triangles += max(0, count - 2)
        attributes = primitive.get("attributes", {})
        for name in missing:
            missing[name] += int(name not in attributes)

    normal_maps = sum("normalTexture" in material for material in materials)
    roughness_maps = sum("metallicRoughnessTexture" in material.get("pbrMetallicRoughness", {})
                         for material in materials)
    base_maps = sum("baseColorTexture" in material.get("pbrMetallicRoughness", {})
                    for material in materials)
    issues = []
    if not model.get("skins"):
        issues.append("スキンがなく、アバターに追従する衣装としては未完成")
    if missing["NORMAL"]:
        issues.append(f"法線がないプリミティブ: {missing['NORMAL']}")
    if missing["TEXCOORD_0"]:
        issues.append(f"UVがないプリミティブ: {missing['TEXCOORD_0']}")
    if model.get("skins") and (missing["JOINTS_0"] or missing["WEIGHTS_0"]):
        issues.append("スキンがあってもウェイトがないプリミティブがある")
    if not normal_maps:
        issues.append("ノーマルマップ未収録。布・金具の近接表現を目視確認")
    if triangles > 70_000:
        issues.append("衣装単体で7万三角形超。素体込みのPC性能目標を圧迫")
    improvements = []
    if not roughness_maps:
        improvements.append("ラフネスマップ未収録。布・合皮・金具の粗さ差をマップで表現")
    if triangles > 35_000:
        improvements.append("衣装だけでPCアバター7万三角形目安の半分超。素体込みで再計測")
    return {
        "triangles": triangles,
        "mesh_count": len(meshes),
        "primitive_count": len(primitives),
        "material_count": len(materials),
        "skin_count": len(model.get("skins", [])),
        "texture_count": len(model.get("textures", [])),
        "base_color_map_count": base_maps,
        "normal_map_count": normal_maps,
        "roughness_map_count": roughness_maps,
        "missing_attribute_primitives": missing,
        "issues": issues,
        "improvement_opportunities": improvements,
        "manual_review_required": [
            "正面・側面・背面のシルエットを資料と比較",
            "肩・脇・肘・股・裾の貫通を複数ポーズで確認",
            "布と金具の質感を近接表示で確認",
            "Unity/VRChat SDKでアバター全体の性能・表示を確認",
            "参照・利用素材の権利を確認",
        ],
        "vrchat_certified": False,
    }
