"""Add a small textile roughness map to the two cloth atlas materials in a GLB.

Blender's glTF exporter can fail while baking an ORM temporary image in some
restricted Windows environments. This post-export step changes only the
standard glTF material, image, texture and buffer records; geometry is intact.
"""

import argparse
import io
import json
import math
import struct
from pathlib import Path

from PIL import Image


JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def roughness_png():
    image = Image.new("RGBA", (512, 512))
    pixels = image.load()
    for y in range(512):
        for x in range(512):
            # glTF uses G for roughness and B for metallic. Low-amplitude
            # woven grain keeps highlights irregular without painted noise.
            grain = .025 * math.sin(x * .49) + .018 * math.sin(y * .73)
            grain += .012 * math.sin(x * .19 + y * .37)
            roughness = max(.65, min(.97, .86 + grain))
            pixels[x, y] = (0, round(255 * roughness), 0, 255)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def add_roughness(source, destination):
    data = Path(source).read_bytes()
    if data[:4] != b"glTF" or struct.unpack_from("<I", data, 8)[0] != len(data):
        raise ValueError("Invalid source GLB")
    json_size, json_type = struct.unpack_from("<II", data, 12)
    if json_type != JSON_CHUNK:
        raise ValueError("Missing GLB JSON chunk")
    model = json.loads(data[20:20 + json_size])
    offset = 20 + json_size
    binary_size, binary_type = struct.unpack_from("<II", data, offset)
    if binary_type != BIN_CHUNK or len(model.get("buffers", [])) != 1:
        raise ValueError("Expected one GLB binary buffer")
    binary = bytearray(data[offset + 8:offset + 8 + binary_size])
    if len(binary) != binary_size:
        raise ValueError("Truncated GLB binary chunk")

    png = roughness_png()
    while len(binary) % 4:
        binary.append(0)
    image_offset = len(binary)
    binary.extend(png)
    while len(binary) % 4:
        binary.append(0)
    views = model.setdefault("bufferViews", [])
    image_view = len(views)
    views.append({"buffer": 0, "byteOffset": image_offset, "byteLength": len(png)})
    images = model.setdefault("images", [])
    image_index = len(images)
    images.append({"bufferView": image_view, "mimeType": "image/png", "name": "woven fabric roughness"})
    textures = model.setdefault("textures", [])
    texture_index = len(textures)
    textures.append({"source": image_index, "name": "woven fabric roughness"})
    model["buffers"][0]["byteLength"] = len(binary)

    factors = {"00 combined cloth atlas": .98,
               "01 technical nylon and shoe leather atlas": .65}
    changed = set()
    for material in model.get("materials", []):
        name = material.get("name")
        if name not in factors:
            continue
        pbr = material.setdefault("pbrMetallicRoughness", {})
        if "metallicRoughnessTexture" in pbr:
            raise ValueError(f"Material already has a roughness texture: {name}")
        pbr["metallicRoughnessTexture"] = {"index": texture_index}
        pbr["roughnessFactor"] = factors[name]
        pbr["metallicFactor"] = 0.0
        changed.add(name)
    if changed != set(factors):
        raise ValueError(f"Missing expected fabric materials: {set(factors) - changed}")

    json_bytes = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    result = (struct.pack("<4sII", b"glTF", 2, total)
              + struct.pack("<II", len(json_bytes), JSON_CHUNK) + json_bytes
              + struct.pack("<II", len(binary), BIN_CHUNK) + binary)
    Path(destination).write_bytes(result)
    return {"materials_updated": sorted(changed), "roughness_png_bytes": len(png),
            "output_bytes": total}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(add_roughness(args.source, args.destination), ensure_ascii=False))
