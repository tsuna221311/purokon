"""Build a single skinned fitting mesh from the editable costume .blend.

This is a deformation test rig, not a Unity Humanoid/VRChat-ready avatar.
Run: blender -b -t 4 --python scripts/rig_endministrator_garment.py -- SOURCE_BLEND OUTPUT_DIR [SIMPLIFY_RATIO]
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


if "--" not in sys.argv or len(sys.argv) - sys.argv.index("--") < 3:
    raise SystemExit("Expected SOURCE_BLEND OUTPUT_DIR after --")
script_args = sys.argv[sys.argv.index("--") + 1:]
if len(script_args) > 3:
    raise SystemExit("Expected SOURCE_BLEND OUTPUT_DIR [SIMPLIFY_RATIO]")
source = Path(script_args[0]).resolve()
out = Path(script_args[1]).resolve()
simplify_ratio = float(script_args[2]) if len(script_args) == 3 else 1.0
if not .3 <= simplify_ratio <= 1.0:
    raise SystemExit("SIMPLIFY_RATIO must be between 0.3 and 1.0")
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source))
scene = bpy.context.scene
source_parts = [obj for obj in scene.objects if obj.type in {"MESH", "CURVE", "FONT"}]
if len(source_parts) < 20:
    raise RuntimeError("Expected an editable, multi-part costume source")

rig_collection = bpy.data.collections.new("Fitting rig export - one skinned mesh")
scene.collection.children.link(rig_collection)
copies = []
for original in source_parts:
    duplicate = original.copy()
    duplicate.data = original.data.copy()
    rig_collection.objects.link(duplicate)
    duplicate.name = original.name + "_rig"
    if duplicate.type == "CURVE":
        # Thin stitch/piping curves dominate the old triangle count because
        # every cross-section was exported at display-render resolution.
        # Retain more sides for broad binding, fewer for sub-5 mm stitching.
        width = duplicate.data.bevel_depth
        duplicate.data.bevel_resolution = 0 if width < .005 else (1 if width < .012 else 2)
        duplicate.data.resolution_u = 1
    bpy.ops.object.select_all(action="DESELECT")
    duplicate.select_set(True)
    bpy.context.view_layer.objects.active = duplicate
    bpy.ops.object.convert(target="MESH")
    # The source components remain untouched; the export copy bakes its hem,
    # bevel and curve cross-section before the seam/cloth pieces are joined.
    for modifier in list(duplicate.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    # Trial-only mesh reduction: simplify dense sewn surfaces but retain tiny
    # hardware and trim exactly.  It is applied before painting weights so
    # every remaining vertex still receives an explicit skeleton influence.
    if simplify_ratio < 1.0 and len(duplicate.data.polygons) > 1000:
        reduction = duplicate.modifiers.new("trial mesh reduction", "DECIMATE")
        reduction.decimate_type = "COLLAPSE"
        reduction.ratio = simplify_ratio
        bpy.ops.object.modifier_apply(modifier=reduction.name)
    copies.append(duplicate)
    original.hide_render = True
    original.hide_set(True)

rig_data = bpy.data.armatures.new("Endministrator fitting skeleton")
rig = bpy.data.objects.new("Endministrator_FittingRig", rig_data)
rig_collection.objects.link(rig)
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")


def bone(name, head, tail, parent=None):
    edit = rig_data.edit_bones.new(name)
    edit.head = head
    edit.tail = tail
    edit.align_roll(Vector((0, 1, 0)))
    if parent:
        edit.parent = rig_data.edit_bones[parent]
    return edit


bone("Hips", (0, 0, -.43), (0, 0, .02))
bone("Spine", (0, 0, .02), (0, 0, 1.12), "Hips")
for label, sign in (("Left", -1), ("Right", 1)):
    bone(label + "UpperArm", (sign * .34, 0, .84),
         (sign * .99, 0, .65), "Spine")
    bone(label + "LowerArm", (sign * .99, 0, .65),
         (sign * 1.63, 0, .43), label + "UpperArm")
    bone(label + "UpperLeg", (sign * .19, 0, -.44),
         (sign * .21, 0, -1.13), "Hips")
    bone(label + "LowerLeg", (sign * .21, 0, -1.13),
         (sign * .22, 0, -1.82), label + "UpperLeg")
bpy.ops.object.mode_set(mode="OBJECT")

NAMES = tuple(b.name for b in rig_data.bones)
attachment_weight_checks = []
for obj in copies:
    groups = {name: obj.vertex_groups.new(name=name) for name in NAMES}
    name = obj.name.lower()
    arm_part = any(word in name for word in (
        "sleeve", "cuff", "wrist", "elbow", "adjustable", "pauldron",
        "yellow panel", "shoulder rivet", "upper arm",
        "water-drop decoration"))
    leg_part = any(word in name for word in ("tights", "boot", "shorts leg", "shorts turned leg hem"))
    hip_part = "shorts" in name and not leg_part
    sample = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    leg_label = ("Right" if sum(vertex.x for vertex in sample) >= 0 else "Left") if leg_part else None
    if sample and not arm_part and not leg_part and not hip_part:
        average_x = sum(abs(vertex.x) for vertex in sample) / len(sample)
        average_z = sum(vertex.z for vertex in sample) / len(sample)
        if average_x > .9 and average_z > .2:
            raise RuntimeError(f"Unclassified wrist/sleeve object: {obj.name}")
    for vertex in obj.data.vertices:
        location = obj.matrix_world @ vertex.co
        x, z = location.x, location.z
        # A boot may cross the centre line to cover the fitting avatar's shoe;
        # all its vertices must still follow the same leg.
        label = leg_label if leg_part else ("Right" if x >= 0 else "Left")
        if hip_part:
            groups["Hips"].add([vertex.index], 1.0, "REPLACE")
        elif leg_part:
            lower = max(0, min(1, (-z - 1.00) / .32))
            groups[label + "UpperLeg"].add([vertex.index], max(.001, 1 - lower), "REPLACE")
            if lower:
                groups[label + "LowerLeg"].add([vertex.index], lower, "REPLACE")
        elif arm_part:
            lower = max(0, min(1, (abs(x) - .80) / .62))
            groups[label + "UpperArm"].add([vertex.index], max(.001, 1 - lower), "REPLACE")
            if lower:
                groups[label + "LowerArm"].add([vertex.index], lower, "REPLACE")
        else:
            # Ease the upper shell toward the shoulder while leaving its
            # flared hem anchored to the spine.
            shoulder = max(0, min(.72, (abs(x) - .27) * 6.0)) if z > .72 else 0
            groups["Spine"].add([vertex.index], 1 - shoulder, "REPLACE")
            if shoulder:
                groups[label + "UpperArm"].add([vertex.index], shoulder, "REPLACE")

    if "water-drop decoration" in name:
        right_arm_index = groups["RightUpperArm"].index
        weights = [next((item.weight for item in vertex.groups
                         if item.group == right_arm_index), 0.0)
                   for vertex in obj.data.vertices]
        minimum = min(weights, default=0.0)
        attachment_weight_checks.append({
            "part": obj.name,
            "expected_bone": "RightUpperArm",
            "minimum_weight": round(minimum, 4),
            "vertices_checked": len(weights),
        })
        if minimum < .9:
            raise RuntimeError(
                f"Shoulder pendant is not attached to its upper arm: {obj.name}")

if attachment_weight_checks and len(attachment_weight_checks) != 4:
    raise RuntimeError("Shoulder pendant attachment is incomplete")
(out / "attachment_weight_audit.json").write_text(
    json.dumps({"water_drop_parts": attachment_weight_checks,
                "not_a_physical_clasp_or_swing_test": True},
               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

bpy.ops.object.select_all(action="DESELECT")
for obj in copies:
    obj.select_set(True)
bpy.context.view_layer.objects.active = copies[0]
bpy.ops.object.join()
garment = copies[0]
garment.name = "Endministrator_Costume_SingleSkinnedMesh"

# Fabric materials become one dynamically sized texture atlas. The coated shoulder
# and metal hardware stay independent so their roughness/metalness survives.
old_materials = list(garment.data.materials)
yellow_index = next(i for i, mat in enumerate(old_materials) if "yellow coated" in mat.name)
metal_index = next(i for i, mat in enumerate(old_materials) if "brushed alloy" in mat.name)
fabric_indices = [i for i in range(len(old_materials))
                  if i not in (yellow_index, metal_index)]
atlas_columns = 5
atlas_rows = math.ceil(len(fabric_indices) / atlas_columns)
atlas_width, atlas_height, tile = atlas_columns * 512, atlas_rows * 512, 512
color_pixels = [0.0] * (atlas_width * atlas_height * 4)
normal_pixels = [0.0] * len(color_pixels)


def image_pixels(mat, normal=False):
    if not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image:
            is_normal = node.image.colorspace_settings.name == "Non-Color"
            if is_normal == normal:
                return list(node.image.pixels[:])
    return None


for atlas_tile, index in enumerate(fabric_indices):
    mat = old_materials[index]
    colors = image_pixels(mat)
    normals = image_pixels(mat, True)
    tx, ty = atlas_tile % atlas_columns, atlas_tile // atlas_columns
    for y in range(tile):
        for x in range(tile):
            source_offset = (y * tile + x) * 4
            target_offset = ((ty * tile + y) * atlas_width + tx * tile + x) * 4
            color_pixels[target_offset:target_offset + 4] = (
                colors[source_offset:source_offset + 4] if colors
                else [*mat.diffuse_color[:3], 1.0])
            normal_pixels[target_offset:target_offset + 4] = (
                normals[source_offset:source_offset + 4] if normals
                else [.5, .5, 1.0, 1.0])

atlas_color = bpy.data.images.new("Endministrator fabric atlas", atlas_width, atlas_height, alpha=True)
atlas_color.pixels[:] = color_pixels
atlas_color.pack()
atlas_normal = bpy.data.images.new("Endministrator fabric normals", atlas_width, atlas_height, alpha=True)
atlas_normal.colorspace_settings.name = "Non-Color"
atlas_normal.pixels[:] = normal_pixels
atlas_normal.pack()
atlas_mat = bpy.data.materials.new("00 combined cloth atlas")
atlas_mat.use_nodes = True
nodes = atlas_mat.node_tree.nodes
nodes.clear()
shader = nodes.new("ShaderNodeBsdfPrincipled")
shader.inputs["Roughness"].default_value = .79
output = nodes.new("ShaderNodeOutputMaterial")
color_node = nodes.new("ShaderNodeTexImage")
color_node.image = atlas_color
normal_node = nodes.new("ShaderNodeTexImage")
normal_node.image = atlas_normal
normal_map = nodes.new("ShaderNodeNormalMap")
normal_map.inputs["Strength"].default_value = .22
atlas_mat.node_tree.links.new(color_node.outputs["Color"], shader.inputs["Base Color"])
atlas_mat.node_tree.links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
atlas_mat.node_tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
shader.inputs["Roughness"].default_value = .84
# Preserve a visibly different specular response for technical nylon and
# footwear without forcing Blender's glTF exporter to bake a fragile ORM map.
gloss_atlas_mat = bpy.data.materials.new("01 technical nylon and shoe leather atlas")
gloss_atlas_mat.use_nodes = True
gloss_nodes = gloss_atlas_mat.node_tree.nodes
gloss_nodes.clear()
gloss_shader = gloss_nodes.new("ShaderNodeBsdfPrincipled")
gloss_output = gloss_nodes.new("ShaderNodeOutputMaterial")
gloss_color = gloss_nodes.new("ShaderNodeTexImage")
gloss_color.image = atlas_color
gloss_normal = gloss_nodes.new("ShaderNodeTexImage")
gloss_normal.image = atlas_normal
gloss_normal_map = gloss_nodes.new("ShaderNodeNormalMap")
gloss_normal_map.inputs["Strength"].default_value = .22
gloss_atlas_mat.node_tree.links.new(gloss_color.outputs["Color"], gloss_shader.inputs["Base Color"])
gloss_atlas_mat.node_tree.links.new(gloss_normal.outputs["Color"], gloss_normal_map.inputs["Color"])
gloss_atlas_mat.node_tree.links.new(gloss_normal_map.outputs["Normal"], gloss_shader.inputs["Normal"])
gloss_atlas_mat.node_tree.links.new(gloss_shader.outputs["BSDF"], gloss_output.inputs["Surface"])
gloss_shader.inputs["Roughness"].default_value = .56
gloss_indices = {i for i in fabric_indices if any(token in old_materials[i].name
                 for token in ("sleeve nylon", "footwear leather"))}
atlas_mat.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])

old_face_materials = [poly.material_index for poly in garment.data.polygons]
uv = garment.data.uv_layers.active.data
for poly, index in zip(garment.data.polygons, old_face_materials):
    if index in fabric_indices:
        atlas_tile = fabric_indices.index(index)
        tx, ty = atlas_tile % atlas_columns, atlas_tile // atlas_columns
        for loop_index in poly.loop_indices:
            coord = uv[loop_index].uv.copy()
            uv[loop_index].uv = ((tx + .01 + .98 * (coord.x % 1)) / atlas_columns,
                                 (ty + .01 + .98 * (coord.y % 1)) / atlas_rows)
garment.data.materials.clear()
for mat in (atlas_mat, gloss_atlas_mat, old_materials[yellow_index], old_materials[metal_index]):
    garment.data.materials.append(mat)
for poly, index in zip(garment.data.polygons, old_face_materials):
    poly.material_index = (1 if index in gloss_indices else 0) if index in fabric_indices else (2 if index == yellow_index else 3)

# Do not globally decimate a joined costume: this destroys narrow binding,
# small hardware and topstitch at the same rate as broad cloth. Any later
# optimization must be part-specific and reviewed in close-up/pose tests.
source_triangles = sum(max(1, len(poly.vertices) - 2) for poly in garment.data.polygons)
print("Fitting triangles after optional part reduction:", source_triangles,
      "ratio:", simplify_ratio, flush=True)

garment.parent = rig
deform = garment.modifiers.new("Fitting bone deformation", "ARMATURE")
deform.object = rig
rig.show_in_front = False
rig.hide_render = True

bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
garment.select_set(True)
bpy.context.view_layer.objects.active = garment
bpy.ops.export_scene.gltf(filepath=str(out / "endministrator_rigged_fitting.glb"),
                          export_format="GLB", use_selection=True,
                          export_apply=False, export_animations=False,
                          export_skins=True, export_materials="EXPORT")

camera = scene.camera
camera.location = (0, -7, .05)
camera.rotation_euler = (Vector((0, 0, .03)) - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.render.filepath = str(out / "endministrator_rigged_rest.png")
bpy.ops.render.render(write_still=True)
for name, position in (("side", (7, 0, .05)),
                       ("back", (0, 7, .05))):
    camera.location = position
    camera.rotation_euler = (Vector((0, 0, .03)) -
                             camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out / f"endministrator_rigged_{name}.png")
    bpy.ops.render.render(write_still=True)
camera.location = (0, -7, .05)
camera.rotation_euler = (Vector((0, 0, .03)) -
                         camera.location).to_track_quat("-Z", "Y").to_euler()

# Raise/lower both arms to expose whether the sleeve opening actually follows
# its bones. This is a deformation smoke test, not a body-collision guarantee.
for label, sign in (("Left", -1), ("Right", 1)):
    upper = rig.pose.bones[label + "UpperArm"]
    lower = rig.pose.bones[label + "LowerArm"]
    upper.rotation_mode = "XYZ"
    lower.rotation_mode = "XYZ"
    upper.rotation_euler.z = sign * .55
    lower.rotation_euler.z = sign * .22
bpy.context.view_layer.update()
scene.render.filepath = str(out / "endministrator_rigged_arm_pose.png")
bpy.ops.render.render(write_still=True)

# A static posed comparison is useful in web viewers that do not drive the
# fitting skeleton. Keep the separate skinned GLB for deformation inspection.
evaluated = garment.evaluated_get(bpy.context.evaluated_depsgraph_get())
posed_mesh = bpy.data.meshes.new_from_object(
    evaluated, preserve_all_data_layers=True,
    depsgraph=bpy.context.evaluated_depsgraph_get())
posed = bpy.data.objects.new("Endministrator_Costume_PosedComparison", posed_mesh)
scene.collection.objects.link(posed)
posed.matrix_world = garment.matrix_world.copy()
bpy.ops.object.select_all(action="DESELECT")
posed.select_set(True)
bpy.context.view_layer.objects.active = posed
bpy.ops.export_scene.gltf(filepath=str(out / "endministrator_posed_comparison.glb"),
                          export_format="GLB", use_selection=True)
bpy.data.objects.remove(posed, do_unlink=True)

for name in NAMES:
    rig.pose.bones[name].rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(out / "endministrator_rigged_fitting.blend"))
print("RIGGED_OUTPUT", out, len(garment.data.vertices), len(garment.data.polygons))
