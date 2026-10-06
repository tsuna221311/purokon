"""Run a three-case *sensitivity study* of the authored coat in Blender.

This is not a measured fabric model, a validated garment fit simulation, or a
durability test.  The side/back geometry is inferred from the supplied front
illustration.  Each case changes arbitrary solver parameters to reveal where
the design is sensitive to drape.  The separate hard accessories are rendered
for context, but their loads and attachment strength are not simulated.

Run from the repository root:
  blender -b -t 4 --python scripts/simulate_endministrator_fit.py -- OUT PROFILE [SOURCE_BLEND]
where PROFILE is soft, baseline, or stiff.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "assets/endministrator/endministrator_authored_costume.blend"
AVATAR = ROOT / "web/static/models/default-avatar.vrm"
PROFILES = {
    "soft": {"mass": 0.18, "bend": 1.0, "tension": 12.0, "shear": 8.0},
    "baseline": {"mass": 0.32, "bend": 5.0, "tension": 20.0, "shear": 12.0},
    "stiff": {"mass": 0.45, "bend": 12.0, "tension": 32.0, "shear": 20.0},
}
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) not in (2, 3) or args[1] not in PROFILES:
    raise SystemExit("Usage: -- OUTPUT_DIR soft|baseline|stiff [SOURCE_BLEND]")
out = Path(args[0]).resolve() / args[1]
out.mkdir(parents=True, exist_ok=True)
profile_name = args[1]
values = PROFILES[profile_name]
SOURCE = Path(args[2]).resolve() if len(args) == 3 else DEFAULT_SOURCE
if not SOURCE.is_file():
    raise FileNotFoundError(SOURCE)

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
scene.frame_set(1)
coat = bpy.data.objects["open long coat continuous outer shell"]
original = [vertex.co.copy() for vertex in coat.data.vertices]
edges = [(edge.vertices[0], edge.vertices[1]) for edge in coat.data.edges]
solidify = next(mod for mod in coat.modifiers if mod.type == "SOLIDIFY")
bevel = next(mod for mod in coat.modifiers if mod.type == "BEVEL")
thickness, offset = solidify.thickness, solidify.offset
bevel_width, bevel_segments = bevel.width, bevel.segments
coat.modifiers.clear()

anchors = coat.vertex_groups.new(name="simulation upper-body anchors")
for vertex in coat.data.vertices:
    z = vertex.co.z
    if z > 0.10:
        anchors.add([vertex.index], 1.0, "REPLACE")
    elif z > -0.18:
        anchors.add([vertex.index], max(0.0, (z + 0.18) / 0.28), "REPLACE")

existing = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=str(AVATAR))
imported = set(scene.objects) - existing
body = next(obj for obj in imported if obj.type == "MESH" and obj.name.startswith("Body"))
avatar_rig = next(obj for obj in imported if obj.type == "ARMATURE")
avatar_rig.scale = (2.07, 2.07, 2.07)
avatar_rig.location.z = -1.72
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.context.view_layer.objects.active = body
if not body.collision:
    bpy.ops.object.modifier_add(type="COLLISION")
body.collision.thickness_outer = 0.012
body.collision.cloth_friction = 6.0
for obj in imported:
    obj.hide_render = True

bpy.ops.object.select_all(action="DESELECT")
coat.select_set(True)
bpy.context.view_layer.objects.active = coat
cloth = coat.modifiers.new("material sensitivity drape", "CLOTH")
cloth.settings.quality = 6
cloth.settings.mass = values["mass"]
cloth.settings.tension_stiffness = values["tension"]
cloth.settings.compression_stiffness = values["tension"]
cloth.settings.shear_stiffness = values["shear"]
cloth.settings.bending_stiffness = values["bend"]
cloth.settings.vertex_group_mass = anchors.name
cloth.settings.pin_stiffness = 20
cloth.collision_settings.collision_quality = 4
cloth.collision_settings.distance_min = 0.012
cloth.collision_settings.use_self_collision = True
cloth.collision_settings.self_distance_min = 0.008
cloth.collision_settings.self_friction = 5.0

scene.frame_end = 36
for frame in range(1, 37):
    scene.frame_set(frame)
    if frame % 12 == 0:
        print(f"SIM_FRAME {profile_name} {frame}/36", flush=True)

depsgraph = bpy.context.evaluated_depsgraph_get()
evaluated = coat.evaluated_get(depsgraph)
draped = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
if len(draped.vertices) != len(original):
    raise RuntimeError("Simulation changed the mesh topology; metrics would be invalid")
positions = [vertex.co.copy() for vertex in draped.vertices]
displacements = [(a - b).length for a, b in zip(positions, original)]
strain = []
for a, b in edges:
    initial = (original[a] - original[b]).length
    if initial > 1e-5:
        strain.append(abs((positions[a] - positions[b]).length / initial - 1.0))

def percentile(samples, fraction):
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


# A nearest-surface distance is only a proximity proxy, not a signed
# penetration test.  The imported avatar is a fitting stand-in, not the
# wearer's scanned body.
body_tree = BVHTree.FromObject(body, depsgraph, deform=True)
body_inverse = body.matrix_world.inverted()
near_contact = 0
for point in positions:
    query = body_inverse @ (coat.matrix_world @ point)
    nearest = body_tree.find_nearest(query)
    if nearest and nearest[3] is not None and nearest[3] < 0.012:
        near_contact += 1

# These detail pieces are not sewn to the simulated coat mesh.  Compare
# their nearest coat-surface distance before/after drape to expose separation;
# the distance alone is NOT a fastening or collision-force test.
faces = [tuple(poly.vertices) for poly in coat.data.polygons]
rest_tree = BVHTree.FromPolygons(original, faces)
draped_tree = BVHTree.FromPolygons(positions, faces)
coat_inverse = coat.matrix_world.inverted()


def _surface_delta(point):
    """Advect trim from a nearby coat triangle, preserving its stand-off.

    This is kinematic *visual attachment*, not a stitched seam or a test of
    glue/fastener strength.  The closest rest triangle remains the anchor.
    """
    nearest = rest_tree.find_nearest(point)
    if nearest is None or nearest[2] is None:
        return Vector((0, 0, 0))
    face = faces[nearest[2]]
    triangles = ((face[0], face[1], face[2]),
                 (face[0], face[2], face[3])) if len(face) == 4 else (face,)
    closest = None
    for triangle in triangles:
        a, b, c = (original[index] for index in triangle)
        projected = geometry.closest_point_on_tri(point, a, b, c)
        distance = (point - projected).length_squared
        if closest is None or distance < closest[0]:
            closest = (distance, triangle, projected)
    _distance, triangle, projected = closest
    a, b, c = (original[index] for index in triangle)
    v0, v1, v2 = b - a, c - a, projected - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) < 1e-12:
        return Vector((0, 0, 0))
    wb = (d11 * d20 - d01 * d21) / denominator
    wc = (d00 * d21 - d01 * d20) / denominator
    wa = 1 - wb - wc
    destination = sum((positions[index] * weight
                       for index, weight in zip(triangle, (wa, wb, wc))),
                      Vector((0, 0, 0)))
    return destination - projected


def _follow_coat_surface(part):
    to_part = part.matrix_world.inverted()
    moved = 0
    if part.type == "MESH":
        for vertex in part.data.vertices:
            coat_point = coat_inverse @ (part.matrix_world @ vertex.co)
            displacement = _surface_delta(coat_point)
            vertex.co = to_part @ (coat.matrix_world @ (coat_point + displacement))
            moved += 1
        part.data.update()
    elif part.type == "CURVE":
        for spline in part.data.splines:
            if spline.type == "BEZIER":
                points = spline.bezier_points
                for bezier in points:
                    for attr in ("co", "handle_left", "handle_right"):
                        local = getattr(bezier, attr)
                        coat_point = coat_inverse @ (part.matrix_world @ local)
                        setattr(bezier, attr,
                                to_part @ (coat.matrix_world @
                                           (coat_point + _surface_delta(coat_point))))
                    moved += 1
            else:
                for spline_point in spline.points:
                    local = Vector(spline_point.co[:3])
                    coat_point = coat_inverse @ (part.matrix_world @ local)
                    new_local = to_part @ (coat.matrix_world @
                                           (coat_point + _surface_delta(coat_point)))
                    spline_point.co = (*new_local, spline_point.co.w)
                    moved += 1
    return moved


ATTACHED_DETAIL_PREFIXES = (
    "cut-and-fitted grey facing", "tailored cool-grey front panel",
    "grey facing tailored outer seam", "grey facing turned lower hem",
    "fitted construction seam", "fitted parallel topstitch",
    "fitted rolled coat hem", "front opening bound edge",
    "princess seam from yoke into flare",
)
bound_details = {}
for part in tuple(scene.objects):
    if part is coat or part in imported or not part.name.startswith(
            ATTACHED_DETAIL_PREFIXES):
        continue
    if part.type in {"MESH", "CURVE"}:
        bound_details[part.name] = _follow_coat_surface(part)

detail_gaps = {}
for token in ("tailored cool-grey front panel", "separate back ribbon",
              "back hanging hard prop"):
    for part in (obj for obj in scene.objects
                 if obj.type == "MESH" and obj.name.startswith(token)):
        samples = [coat_inverse @ (part.matrix_world @ vertex.co)
                   for vertex in part.data.vertices[::max(1, len(part.data.vertices) // 200)]]
        before = [rest_tree.find_nearest(point)[3] for point in samples]
        after = [draped_tree.find_nearest(point)[3] for point in samples]
        detail_gaps[part.name] = {
            "rest_median_cm": round(percentile(before, 0.5) * 100, 2),
            "draped_median_cm": round(percentile(after, 0.5) * 100, 2),
        }

columns = 73
if len(original) % columns:
    raise RuntimeError("Unexpected coat grid; hem row cannot be identified")
hem = positions[-columns:]
original_hem = original[-columns:]
width = max(point.x for point in hem) - min(point.x for point in hem)
original_width = max(point.x for point in original_hem) - min(point.x for point in original_hem)
report = {
    "profile": profile_name,
    "solver_inputs_unmeasured": values,
    "source_reference": "front illustration only; side/back inferred",
    "source_blend": str(SOURCE),
    "cloth_frame": 36,
    "cloth_self_collision": True,
    "vertex_count": len(original),
    "mean_displacement_cm": round(sum(displacements) / len(displacements) * 100, 2),
    "p95_displacement_cm": round(percentile(displacements, 0.95) * 100, 2),
    "hem_spread_ratio": round(width / original_width, 3),
    "p95_absolute_edge_strain_percent": round(percentile(strain, 0.95) * 100, 2),
    "vertices_within_12mm_of_standin_body": near_contact,
    "unattached_detail_to_coat_gap_cm": detail_gaps,
    "visual_surface_follow_points": bound_details,
    "visual_surface_follow_is_structural_sewing": False,
    "physical_signoff": False,
    "not_simulated": [
        "actual fabric stretch/bending/friction measured from swatches",
        "seam allowance and stitched panel strain",
        "hard accessory attachment loads or fatigue",
        "wearer-specific fit, skin comfort, walking and sitting",
        "wash/wear durability and seam/prop fastener strength",
    ],
}
evaluated.to_mesh_clear()
for vertex, location in zip(coat.data.vertices, positions):
    vertex.co = location
coat.modifiers.remove(cloth)
coat.data.update()
new_solidify = coat.modifiers.new("visual thickness", "SOLIDIFY")
new_solidify.thickness = thickness
new_solidify.offset = offset
new_bevel = coat.modifiers.new("visual sewn edge", "BEVEL")
new_bevel.width = bevel_width
new_bevel.segments = bevel_segments
scene.frame_set(1)

scene.render.engine = "CYCLES"
scene.cycles.samples = 10
scene.render.resolution_x = 680
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
camera = scene.camera
for name, position in (("front", (0, -7, 0.05)),
                       ("side", (7, 0, 0.05)),
                       ("back", (0, 7, 0.05))):
    camera.location = position
    camera.rotation_euler = (Vector((0, 0, 0.03)) - camera.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.render.filepath = str(out / f"{profile_name}_{name}.png")
    bpy.ops.render.render(write_still=True)

(out / "simulation_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(out / f"{profile_name}_fitting_study.blend"))
print("SIM_REPORT", json.dumps(report, ensure_ascii=False), flush=True)
