"""Test a real Blender sewing-spring join on one Endministrator pattern seam.

This is a flat coupon, not a garment or a fit test.  The upper paper-pattern
mesh is pinned and the lower panel starts four centimetres away.  Only loose
edges join the two grids; Blender's Cloth modifier supplies sewing springs.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.pattern_panel_bridge import pair_seam_vertices  # noqa: E402


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def run() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) not in {2, 3, 4}:
        raise SystemExit("-- PANELS_JSON OUTPUT_JSON [A|B|C] [on|off]")
    source, output = Path(argv[0]), Path(argv[1])
    code = argv[2] if len(argv) > 2 else "B"
    sewing_option = argv[3] if len(argv) > 3 else "on"
    if sewing_option not in {"on", "off"}:
        raise ValueError("Sewing springs must be on or off")
    sewing = sewing_option == "on"
    if code not in {"A", "B", "C"}:
        raise ValueError("Unknown panel")
    data = json.loads(source.read_text(encoding="utf-8"))
    host = next(item for item in data["bodice_hosts"] if item["code"] == code)
    panel = next(item for item in data["panels"] if item["code"] == code)
    host_mesh = host["pattern_mesh"]
    host_x = [host_mesh["vertices_cm"][index][0]
              for index in host_mesh["hem_indices"]]
    panel_x = [panel["vertices_cm"][index][0]
               for index in panel["top_indices"]]
    seam_pairs = pair_seam_vertices(host_x, panel_x)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scale = .02  # metres in the virtual trial per centimetre on paper
    gap = .08  # scene units: 4 paper centimetres
    upper = [((x - host_x[0]) * scale, 0, (host["hem_stitch_y_cm"] - y) * scale)
             for x, y in host_mesh["vertices_cm"]]
    panel_top_y = panel["vertices_cm"][panel["top_indices"][0]][1]
    lower = [((x - panel_x[0]) * scale, 0, -(y - panel_top_y) * scale - gap)
             for x, y in panel["vertices_cm"]]
    offset = len(upper)
    faces = [tuple(face) for face in host_mesh["faces"]]
    faces += [tuple(index + offset for index in face) for face in panel["faces"]]
    springs = [(host_mesh["hem_indices"][a],
                panel["top_indices"][b] + offset) for a, b in seam_pairs]
    mesh = bpy.data.meshes.new(f"{code}_sewing_coupon")
    mesh.from_pydata(upper + lower, springs, faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{code}_pattern_seam_coupon", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    pin = obj.vertex_groups.new(name="pinned_upper_pattern")
    pin.add(list(range(offset)), 1.0, "REPLACE")
    cloth = obj.modifiers.new("sewing_spring_trial", "CLOTH")
    cloth.settings.vertex_group_mass = pin.name
    cloth.settings.pin_stiffness = 25
    cloth.settings.quality = 8
    cloth.settings.mass = .2
    cloth.settings.tension_stiffness = 18
    cloth.settings.compression_stiffness = 18
    cloth.settings.shear_stiffness = 10
    cloth.settings.bending_stiffness = .6
    cloth.settings.use_sewing_springs = sewing
    cloth.settings.sewing_force_max = 20
    cloth.collision_settings.use_collision = False
    cloth.collision_settings.use_self_collision = False
    scene = bpy.context.scene
    scene.frame_end = 72
    cloth.point_cache.frame_start = 1
    cloth.point_cache.frame_end = scene.frame_end
    distances_by_frame = {}
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        if frame in {1, 12, 24, 48, 72}:
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            evaluated_mesh = evaluated.to_mesh()
            try:
                locations = [vertex.co.copy() for vertex in evaluated_mesh.vertices]
                distances = [(locations[a] - locations[b]).length / scale
                             for a, b in springs]
                distances_by_frame[str(frame)] = {
                    "median_gap_cm": round(statistics.median(distances), 4),
                    "p95_gap_cm": round(percentile(distances, .95), 4),
                    "max_gap_cm": round(max(distances), 4),
                }
                if frame == scene.frame_end:
                    mesh_edges = {(min(face[i], face[(i + 1) % len(face)]),
                                   max(face[i], face[(i + 1) % len(face)]))
                                  for face in faces for i in range(len(face))}
                    strains = []
                    for a, b in mesh_edges:
                        initial = math.dist((upper + lower)[a], (upper + lower)[b])
                        if initial > 1e-8:
                            strains.append(abs((locations[a] - locations[b]).length
                                               / initial - 1))
                    p95_strain = round(percentile(strains, .95), 4)
            finally:
                evaluated.to_mesh_clear()
    report = {
        "scope": "flat seam coupon only; not wearer fit or commercial-grade garment",
        "panel": code,
        "sewing_springs_enabled": sewing,
        "upper_vertices": len(upper),
        "lower_vertices": len(lower),
        "sewing_spring_edges": len(springs),
        "gap_cm_by_frame": distances_by_frame,
        "p95_cloth_edge_strain_final": p95_strain,
        "seam_closed_within_0_05_cm_in_trial": (
            sewing and distances_by_frame[str(scene.frame_end)]["p95_gap_cm"] < .05),
        "physical_materials_measured": False,
        "thread_strength_tested": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if sewing and not report["seam_closed_within_0_05_cm_in_trial"]:
        raise RuntimeError("The virtual sewing spring trial did not close the seam")


if __name__ == "__main__":
    run()
