"""Fitting prototype: panel-aware UVs and cloth relaxation of the coat shell.

The supplied illustration is a front-only reference. This is an authored
fitting study, not an automatic reconstruction or a finished VRChat asset.

Run from the repository root:
  blender -b -t 4 --python scripts/build_endministrator_sewn.py -- OUTPUT_DIR
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "assets/endministrator/endministrator_authored_costume.blend"
AVATAR = ROOT / "web/static/models/default-avatar.vrm"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(args[0]) if args else ROOT / "output/endministrator_sewn_v1"
SOURCE = Path(args[1]) if len(args) > 1 else DEFAULT_SOURCE
if not OUT.is_absolute():
    OUT = ROOT / OUT
if not SOURCE.is_absolute():
    SOURCE = ROOT / SOURCE
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
scene.frame_set(1)
coat = bpy.data.objects["open long coat continuous outer shell"]
mesh = coat.data
solidify = next(mod for mod in coat.modifiers if mod.type == "SOLIDIFY")
bevel = next(mod for mod in coat.modifiers if mod.type == "BEVEL")
solidify_thickness, solidify_offset = solidify.thickness, solidify.offset
bevel_width, bevel_segments = bevel.width, bevel.segments
coat.modifiers.clear()
columns = 73
rows = len(mesh.vertices) // columns
assert len(mesh.vertices) == columns * rows and len(mesh.polygons) == (columns - 1) * (rows - 1)

# The four longitudinal pattern regions have independent UV islands. The
# side seams remain welded in 3D so the cloth solve cannot open gaps.
panel_ranges = [(0, 13), (13, 36), (36, 59), (59, 72)]
uv = mesh.uv_layers.active or mesh.uv_layers.new(name="pattern panel UV")
for poly in mesh.polygons:
    first_col = poly.index % (columns - 1)
    left, right = next((a, b) for a, b in panel_ranges if a <= first_col < b)
    for loop_index in poly.loop_indices:
        vertex_index = mesh.loops[loop_index].vertex_index
        row, col = divmod(vertex_index, columns)
        uv.data[loop_index].uv = ((col - left) / (right - left), row / (rows - 1))
for edge in mesh.edges:
    col_a = edge.vertices[0] % columns
    col_b = edge.vertices[1] % columns
    edge.use_seam = col_a == col_b and col_a in (13, 36, 59)

anchors = coat.vertex_groups.new(name="upper yoke and waist fitting anchors")
for vert in mesh.vertices:
    if vert.co.z > 0.10:
        anchors.add([vert.index], 1.0, "REPLACE")
    elif vert.co.z > -0.18:
        anchors.add([vert.index], max(0.0, (vert.co.z + 0.18) / 0.28), "REPLACE")

garment_objects = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=str(AVATAR))
avatar_objects = set(scene.objects) - garment_objects
body = next(obj for obj in avatar_objects if obj.type == "MESH" and obj.name.startswith("Body"))
avatar_armature = next(obj for obj in avatar_objects if obj.type == "ARMATURE")
avatar_armature.scale = (2.07, 2.07, 2.07)
avatar_armature.location.z = -1.72
bpy.context.view_layer.update()

# Only the fitted body is a collider. Hair and face are irrelevant to the coat.
bpy.context.view_layer.objects.active = body
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.ops.object.modifier_add(type="COLLISION")
body.collision.thickness_outer = 0.012
body.collision.cloth_friction = 6.0

bpy.context.view_layer.objects.active = coat
bpy.ops.object.select_all(action="DESELECT")
coat.select_set(True)
cloth = coat.modifiers.new("gravity drape over fitting body", "CLOTH")
cloth.settings.quality = 6
cloth.settings.mass = 0.32
cloth.settings.tension_stiffness = 20
cloth.settings.compression_stiffness = 20
cloth.settings.shear_stiffness = 12
cloth.settings.bending_stiffness = 5
cloth.settings.vertex_group_mass = anchors.name
cloth.settings.pin_stiffness = 20
cloth.collision_settings.collision_quality = 4
cloth.collision_settings.distance_min = 0.012
cloth.collision_settings.use_self_collision = False
# Simulate the zero-thickness panel mesh; manufactured thickness is added only
# afterward. This also guarantees vertex correspondence when transferring folds.

scene.frame_end = 36
for frame in range(1, 37):
    scene.frame_set(frame)
    if frame % 6 == 0:
        print(f"Drape evaluation frame {frame}/36", flush=True)

evaluated = coat.evaluated_get(bpy.context.evaluated_depsgraph_get())
draped_mesh = evaluated.to_mesh(preserve_all_data_layers=True,
                                depsgraph=bpy.context.evaluated_depsgraph_get())
# Full gravity relaxation collapses the intentionally asymmetric coat tails,
# and also detaches the authored piping. Keep the silhouette and transfer a
# modest amount of physically formed folds only to the free lower panels.
assert len(draped_mesh.vertices) == len(mesh.vertices)
displacement_sum = sum((draped_mesh.vertices[v.index].co - v.co).length for v in mesh.vertices)
print(f"Mean cloth displacement: {displacement_sum / len(mesh.vertices):.3f}", flush=True)
for vert in mesh.vertices:
    height_fraction = max(0.0, min(1.0, (0.10 - vert.co.z) / 1.40))
    influence = 0.32 * height_fraction
    vert.co = vert.co.lerp(draped_mesh.vertices[vert.index].co, influence)
evaluated.to_mesh_clear()
coat.modifiers.remove(cloth)
mesh.update()
solidify = coat.modifiers.new("hem and cloth thickness", "SOLIDIFY")
solidify.thickness = solidify_thickness
solidify.offset = solidify_offset
bevel = coat.modifiers.new("soft sewn edge", "BEVEL")
bevel.width = bevel_width
bevel.segments = bevel_segments

# The early mock-up used independent rectangular facings and nearest-surface
# shrinkwrap. Their corners jumped across the front opening and created thin,
# torn-looking ribbons. Recut the visible facings from the actual draped coat
# surface instead. Each row has a shaped width and every vertex has a direct
# parent on the coat shell; the outer seam is then topstitched on this patch.
for old in list(scene.objects):
    if old.name.startswith(("tailored cool-grey front panel",
                            "facing lower turned hem", "facing waist dart")):
        bpy.data.objects.remove(old, do_unlink=True)


def coat_surface_point(row, column):
    lower = int(column)
    upper = min(columns - 1, lower + 1)
    blend = column - lower
    point = mesh.vertices[row * columns + lower].co.lerp(
        mesh.vertices[row * columns + upper].co, blend)
    radial = Vector((point.x, point.y, 0))
    return point + radial.normalized() * .019


facing_borders = []
for side in (-1, 1):
    first_row, last_row, patch_columns = 1, 22, 13
    vertices, faces = [], []
    for row in range(first_row, last_row + 1):
        progress = (row - first_row) / (last_row - first_row)
        # Wider through the chest, pinched at the waist, then turned inward.
        width = 8.0 + 4.0 * math.sin(math.pi * progress) ** 1.5
        for col in range(patch_columns):
            angle_column = width * col / (patch_columns - 1)
            shell_column = angle_column if side == 1 else columns - 1 - angle_column
            vertices.append(coat_surface_point(row, shell_column))
    for row in range(last_row - first_row):
        for col in range(patch_columns - 1):
            index = row * patch_columns + col
            face = (index, index + 1, index + patch_columns + 1,
                    index + patch_columns)
            faces.append(face if side == 1 else face[::-1])
    data = bpy.data.meshes.new(f"shaped grey facing {side}")
    data.from_pydata(vertices, [], faces)
    data.update()
    data.materials.append(bpy.data.materials["02 cool grey technical twill"])
    uv_patch = data.uv_layers.new(name="cut facing UV")
    for polygon in data.polygons:
        polygon.use_smooth = True
        for loop_index in polygon.loop_indices:
            vertex_index = data.loops[loop_index].vertex_index
            r, c = divmod(vertex_index, patch_columns)
            uv_patch.data[loop_index].uv = (c / (patch_columns - 1),
                                            r / (last_row - first_row))
    facing = bpy.data.objects.new(f"cut-and-fitted grey facing {side}", data)
    scene.collection.objects.link(facing)
    thickness = facing.modifiers.new("folded facing thickness", "SOLIDIFY")
    thickness.thickness = .008
    thickness.offset = 0
    bevel_facing = facing.modifiers.new("rounded facing edge", "BEVEL")
    bevel_facing.width = .002
    bevel_facing.segments = 2
    facing_borders.append((side, [vertices[row * patch_columns + patch_columns - 1]
                                  for row in range(last_row - first_row + 1)],
                           [vertices[(last_row - first_row) * patch_columns + col]
                            for col in range(patch_columns)]))


def sewn_edge(name, indices, material_name, radius):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(indices) - 1)
    for point, index in zip(spline.points, indices):
        co = mesh.vertices[index].co.copy()
        radial = Vector((co.x, co.y, 0))
        if radial.length:
            co += radial.normalized() * (solidify_thickness * 0.58 + radius)
        point.co = (*co, 1)
    curve.materials.append(bpy.data.materials[material_name])
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)


def facing_binding(name, points, material_name, radius):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for spline_point, position in zip(spline.points, points):
        spline_point.co = (*position, 1)
    curve.materials.append(bpy.data.materials[material_name])
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)


for side, outer_edge, lower_edge in facing_borders:
    facing_binding(f"grey facing tailored outer seam {side}", outer_edge,
                   "07 matte black webbing", .004)
    facing_binding(f"grey facing turned lower hem {side}", lower_edge,
                   "09 silver-grey binding", .004)

# The original yellow shoulder was a broad, nearly planar n-gon. Replace it
# with two layers sampled directly from the sleeve cap. The visible coated
# layer is smaller than its dark support and both have a rolled sewn edge.
for old in list(scene.objects):
    if old.name.startswith(("asymmetric yellow right shoulder pauldron",
                            "pauldron dark resilient underlay",
                            "yellow panel perimeter", "shoulder rivet")):
        bpy.data.objects.remove(old, do_unlink=True)

sleeve = bpy.data.objects["curved puff technical sleeve1"]
sleeve_columns = 33
assert len(sleeve.data.vertices) == 25 * sleeve_columns


def sleeve_surface_point(row, angular_column, offset):
    lower = int(angular_column)
    upper = min(sleeve_columns - 1, lower + 1)
    blend = angular_column - lower
    ring_start = row * sleeve_columns
    point = sleeve.data.vertices[ring_start + lower].co.lerp(
        sleeve.data.vertices[ring_start + upper].co, blend)
    top = sleeve.data.vertices[ring_start + 8].co
    bottom = sleeve.data.vertices[ring_start + 24].co
    center_z = (top.z + bottom.z) * .5
    outward = Vector((0, point.y, point.z - center_z)).normalized()
    return point + outward * offset


def shoulder_layer(name, material_name, width_factor, offset, thickness):
    vertex_rows, faces = [], []
    for row in range(12):
        progress = row / 11
        centre = 6.2 - 1.2 * progress
        half_width = (5.2 - 1.7 * progress) * width_factor
        sleeve_row = row
        points = [sleeve_surface_point(
            sleeve_row,
            centre - half_width + 2 * half_width * col / 12,
            offset) for col in range(13)]
        vertex_rows.append(points)
    vertices = [point for row in vertex_rows for point in row]
    for row in range(11):
        for col in range(12):
            index = row * 13 + col
            faces.append((index, index + 1, index + 14, index + 13))
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    data.materials.append(bpy.data.materials[material_name])
    uv_layer = data.uv_layers.new(name="shoulder pattern UV")
    for polygon in data.polygons:
        polygon.use_smooth = True
        for loop_index in polygon.loop_indices:
            r, c = divmod(data.loops[loop_index].vertex_index, 13)
            uv_layer.data[loop_index].uv = (c / 12, r / 11)
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    fold = obj.modifiers.new("panel cloth thickness", "SOLIDIFY")
    fold.thickness = thickness
    fold.offset = 0
    border = (vertex_rows[0] + [row[-1] for row in vertex_rows[1:]]
              + list(reversed(vertex_rows[-1][:-1]))
              + [row[0] for row in reversed(vertex_rows[1:-1])]
              + [vertex_rows[0][0]])
    return obj, border


shoulder_layer("pauldron sewn black support", "07 matte black webbing",
               1.08, .010, .013)
_, yellow_border = shoulder_layer("cut yellow panel on sleeve cap",
                                  "06 yellow coated shoulder panel",
                                  .84, .023, .011)
facing_binding("yellow shoulder rolled edge", yellow_border,
               "07 matte black webbing", .007)


# Follow the solved surface, rather than leaving decorative strips floating at
# their original parametric positions. Dark construction seam + close topstitch.
for panel_col in (13, 36, 59):
    sewn_edge(f"fitted construction seam {panel_col}",
               [row * columns + panel_col for row in range(rows)],
               "07 matte black webbing", 0.0035)
for panel_col in (12, 14, 35, 37, 58, 60):
    sewn_edge(f"fitted parallel topstitch {panel_col}",
               [row * columns + panel_col for row in range(rows)],
               "09 silver-grey binding", 0.0012)
sewn_edge("fitted rolled coat hem", [(rows - 1) * columns + col for col in range(columns)],
           "07 matte black webbing", 0.006)

for obj in avatar_objects:
    bpy.data.objects.remove(obj, do_unlink=True)

scene.frame_set(1)
scene.frame_end = 250
scene.render.engine = "CYCLES"
scene.cycles.samples = 24
scene.render.resolution_x = 850
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
camera = scene.camera
for name, position in (("front", (0, -7, 0.05)),
                       ("side", (7, 0, 0.05)),
                       ("back", (0, 7, 0.05))):
    camera.location = position
    camera.rotation_euler = (Vector((0, 0, .03)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(OUT / f"endministrator_{name}.png")
    bpy.ops.render.render(write_still=True)

bpy.ops.object.select_all(action="DESELECT")
for obj in scene.objects:
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT / "endministrator_sewn_costume.glb"),
                          export_format="GLB", use_selection=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "endministrator_sewn_costume.blend"))

report = {
    "status": "fitting prototype; not VRChat-ready",
    "source_blend": str(SOURCE),
    "reference": "front illustration only; side/back estimated",
    "method": "four UV panel regions, shaped facings cut from the draped coat surface, welded seams, pinned upper yoke, body-collision cloth drape blended at 32% to preserve the silhouette",
    "cloth_frame": 36,
    "panel_uv_regions": panel_ranges,
    "finished_checks": ["front/side/back rendered", "GLB exported"],
    "unfinished_checks": ["pattern-cut accuracy", "sleeve/body sewing", "topology retopology", "skin weights", "Unity/VRChat validation"],
}
(OUT / "fitting_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
