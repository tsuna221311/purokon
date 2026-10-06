"""Inferred detachable Endministrator hair clip; not a measured replica.

Run: blender -b -t 4 --python scripts/build_endministrator_hair_clip.py -- OUTPUT_DIR
The GLB is in metre units at actual accessory scale. The head preview is a
separate, unmeasured positioning proxy and is not exported with the accessory.
"""

import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) != 1:
    raise SystemExit("Expected OUTPUT_DIR after --")
out = Path(args[0]).resolve()
out.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


def material(name, rgba, roughness, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    shader = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return mat


shell = material("black moulded clip shell", (.032, .038, .048, 1), .59)
inlay = material("pale grey face inlay", (.68, .72, .74, 1), .47)
spring = material("steel clip spring", (.41, .46, .49, 1), .35, .65)
hair = material("preview-only dark hair proxy", (.045, .05, .06, 1), .87)
parts = []


def block(name, location, dimensions, mat, *, tilt=0, bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler[1] = tilt
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("rounded wearable edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new("weighted normals", "WEIGHTED_NORMAL")
    parts.append(obj)
    return obj


# The retailer describes a black-and-white cross hairpin. Dimensions and
# the reverse-side clasp below are explicit estimates from front-only input.
block("hair accessory backing plate", (0, .006, 0),
      (.034, .006, .064), shell, bevel=.002)
block("hair accessory dark diagonal rail A", (0, -.002, 0),
      (.013, .008, .078), shell, tilt=math.radians(34), bevel=.0017)
block("hair accessory dark diagonal rail B", (0, -.003, 0),
      (.013, .008, .078), shell, tilt=math.radians(-34), bevel=.0017)
block("hair accessory pale cross inlay", (0, -.0075, 0),
      (.0055, .002, .063), inlay, tilt=math.radians(-34), bevel=.0004)
for side in (-1, 1):
    block("hair accessory sprung prong " + str(side),
          (side * .008, .014, -.006), (.005, .004, .058), spring,
          tilt=side * math.radians(8), bevel=.0008)
block("hair accessory hinge bar", (0, .014, .030),
      (.030, .006, .006), spring, bevel=.001)

bpy.ops.object.select_all(action="DESELECT")
for obj in parts:
    obj.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.export_scene.gltf(filepath=str(out / "hair_accessory_trial.glb"),
                          export_format="GLB", use_selection=True,
                          export_apply=True, export_materials="EXPORT")
glb_data = (out / "hair_accessory_trial.glb").read_bytes()
if (glb_data[:4] != b"glTF" or
        struct.unpack_from("<I", glb_data, 8)[0] != len(glb_data)):
    raise RuntimeError("The exported hair accessory is not a complete GLB")
json_length, chunk_type = struct.unpack_from("<II", glb_data, 12)
if chunk_type != 0x4E4F534A:
    raise RuntimeError("The exported hair accessory has no JSON scene chunk")
glb_scene = json.loads(glb_data[20:20 + json_length])
node_names = {node.get("name") for node in glb_scene.get("nodes", [])}
part_names = {obj.name for obj in parts}
if (node_names != part_names or
        len(glb_scene.get("meshes", [])) != len(parts) or
        len(glb_scene.get("materials", [])) != 3):
    raise RuntimeError("The detached accessory GLB has missing or extra scene parts")

# A trial-only head proxy gives front/side/back context without implying fit.
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24,
                                     location=(0, .027, 0))
head = bpy.context.object
head.name = "preview-only head proxy - not in GLB"
head.scale = (.107, .087, .135)
head.data.materials.append(hair)
for face in head.data.polygons:
    face.use_smooth = True
for obj in parts:
    obj.location = (obj.location.x - .081, obj.location.y - .070,
                    obj.location.z + .025)
    obj.scale = (1, 1, 1)

world = bpy.data.worlds.new("neutral accessory studio")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes.clear()
background = world.node_tree.nodes.new("ShaderNodeBackground")
world_output = world.node_tree.nodes.new("ShaderNodeOutputWorld")
world.node_tree.links.new(background.outputs["Background"],
                          world_output.inputs["Surface"])
background.inputs["Color"].default_value = (.16, .18, .21, 1)
for position, energy, size in (((.4, -.4, .6), 5, .45),
                               ((-.4, .3, .5), 3, .55)):
    bpy.ops.object.light_add(type="AREA", location=position)
    light = bpy.context.object
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat(
        "-Z", "Y").to_euler()
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = .39
scene = bpy.context.scene
scene.camera = camera
scene.render.engine = "CYCLES"
scene.cycles.samples = 36
scene.render.resolution_x = 650
scene.render.resolution_y = 650
scene.render.image_settings.file_format = "PNG"
for name, position in (("front", (0, -.8, .02)),
                       ("side", (-.8, 0, .02)),
                       ("back", (0, .8, .02))):
    camera.location = position
    camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.render.filepath = str(out / f"hair_accessory_{name}.png")
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out / "hair_accessory_trial.blend"))

(out / "hair_accessory_trial.json").write_text(json.dumps({
    "status": "inferred separate accessory trial, not a measured replica",
    "asset": "hair_accessory_trial.glb",
    "unit": "metre",
    "intended_attachment_bone_on_full_avatar": "Head",
    "current_trial_garment_rig_has_head_bone": False,
    "merged_into_garment_glb": False,
    "glb_nodes": sorted(node_names),
    "mesh_count": len(glb_scene["meshes"]),
    "material_count": len(glb_scene["materials"]),
    "preview_head_exported": False,
    "head_fit_or_clamp_force_measured": False,
    "reverse_clasp_is_inferred": True,
    "front_shape_reference": (
        "https://www.gcosplay.com/products/arknights-endfield-female-"
        "endministrator-hairpin-cosplay-accessory-prop"),
    "note": ("Position, tilt and retention require fitting to the chosen wig/avatar. "
             "The current garment trial rig has no Head bone, so this accessory "
             "does not yet follow a head in a combined animated preview."),
}, indent=2) + "\n", encoding="utf-8")
print("HAIR_ACCESSORY_TRIAL", out)
