"""Measure the *stand-in* avatar at garment heights; not a wearer scan.

Run: blender -b -t 4 --python scripts/measure_avatar_cross_section.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.context.scene.objects)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "web/static/models/default-avatar.vrm"))
imported = set(bpy.context.scene.objects) - before
body = next(obj for obj in imported if obj.type == "MESH" and obj.name.startswith("Body"))
rig = next(obj for obj in imported if obj.type == "ARMATURE")
rig.scale = (2.07,) * 3
rig.location.z = -1.72
bpy.context.view_layer.update()
evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
mesh = evaluated.to_mesh()
world = [body.matrix_world @ vertex.co for vertex in mesh.vertices]


def hull(points):
    ordered = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(ordered) < 3:
        return []

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    lower = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


results = []
for height in (.35, .25, .15, .08, 0, -.08, -.15, -.20,
               -.25, -.30, -.35, -.40, -.43, -.60, -.85):
    intersections = []
    for polygon in mesh.polygons:
        indices = list(polygon.vertices)
        for a, b in zip(indices, indices[1:] + indices[:1]):
            first, second = world[a], world[b]
            if (first.z < height <= second.z) or (second.z < height <= first.z):
                fraction = (height - first.z) / (second.z - first.z)
                intersections.append((first.x + fraction * (second.x - first.x),
                                      first.y + fraction * (second.y - first.y)))
    outline = hull(intersections)
    circumference = sum(math.dist(a, b) for a, b in zip(
        outline, outline[1:] + outline[:1])) if outline else 0
    torso_only = [(x, y) for x, y in intersections if abs(x) < .75 and abs(y) < .75]
    torso_hull = hull(torso_only)
    torso_length = sum(math.dist(a, b) for a, b in zip(
        torso_hull, torso_hull[1:] + torso_hull[:1])) if torso_hull else 0
    results.append({"z_scene": height, "circumference_cm_at_2x_scale": round(
        circumference / .02, 2), "torso_limited_cm": round(torso_length / .02, 2),
        "x_range": [round(min(x for x, _y in intersections), 3),
                    round(max(x for x, _y in intersections), 3)],
        "y_range": [round(min(y for _x, y in intersections), 3),
                    round(max(y for _x, y in intersections), 3)],
        "sample_count": len(intersections)})
evaluated.to_mesh_clear()
print("AVATAR_CROSS_SECTIONS", json.dumps(results), flush=True)
