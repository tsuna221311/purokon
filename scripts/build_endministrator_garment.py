"""Author an original, reference-inspired Endministrator costume in Blender.

The front follows the supplied illustration. Side/back construction is an
explicit design estimate, not a scan or an automatically reconstructed model.
Run: blender -b -t 4 --python scripts/build_endministrator_garment.py -- OUTPUT_DIR
"""

import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SCRIPT_ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(SCRIPT_ARGS[0]) if SCRIPT_ARGS else Path("output/endministrator_authored")
BACK_PANEL_TRIAL = "back-panel-trial" in SCRIPT_ARGS[1:]
if not OUT.is_absolute():
    OUT = Path(__file__).resolve().parent.parent / OUT
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


def fabric_image(name, color, seed, rib=False):
    image = bpy.data.images.new(name, 512, 512, alpha=True)
    random.seed(seed)
    pixels = []
    for row in range(512):
        for col in range(512):
            grain = random.uniform(-0.008, 0.008)
            warp = (0.016 if rib else 0.009) * math.sin(col * (1.4 if rib else 2.2))
            weft = (0.007 if rib else 0.005) * math.sin(row * (0.6 if rib else 2.7))
            value = grain + warp + weft
            pixels.extend((max(0, min(1, c + value)) for c in color))
            pixels.append(1)
    image.pixels[:] = pixels
    image.pack()
    return image


def normal_image(name, rib=False):
    image = bpy.data.images.new(name, 512, 512, alpha=True)
    image.colorspace_settings.name = "Non-Color"
    pixels = []
    for row in range(512):
        for col in range(512):
            x = .5 + .050 * math.cos(col * (1.4 if rib else 2.2))
            y = .5 + .035 * math.cos(row * (0.6 if rib else 2.7))
            pixels.extend((x, y, 1.0, 1.0))
    image.pixels[:] = pixels
    image.pack()
    return image


def jacquard_image():
    image = bpy.data.images.new("tonal lower-coat jacquard", 512, 512, alpha=True)
    pixels = []
    for row in range(512):
        for col in range(512):
            u, v = (col % 64) / 64, (row % 64) / 64
            diamond = abs(abs(u - .5) + abs(v - .5) - .36) < .025
            shade = .097 if diamond else .069
            pixels.extend((shade, shade * 1.08, shade * 1.18, 1))
    image.pixels[:] = pixels
    image.pack()
    return image


def material(name, color, roughness, metallic=0, texture=False, rib=False):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if texture:
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = fabric_image(name + " weave", color, len(name) * 17, rib)
        mat.node_tree.links.new(tex.outputs["Color"], shader.inputs["Base Color"])
        normal_tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        normal_tex.image = normal_image(name + " normal", rib)
        normal = mat.node_tree.nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = .28 if rib else .20
        mat.node_tree.links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        mat.node_tree.links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return mat


coat = material("01 charcoal woven outer shell", (.118, .129, .145), .84, texture=True)
side_panel = material("02 cool grey technical twill", (.31, .34, .38), .75, texture=True)
lining = material("03 graphite lining", (.225, .236, .255), .8, texture=True)
knit = material("04 warm-grey rib knit", (.57, .58, .57), .91, texture=True, rib=True)
nylon = material("05 near-black sleeve nylon", (.064, .073, .086), .55, texture=True)
yellow = material("06 yellow coated shoulder panel", (.92, .76, .012), .45)
black = material("07 matte black webbing", (.055, .058, .068), .78)
silver = material("08 brushed alloy hardware", (.53, .58, .63), .32, .72)
edge = material("09 silver-grey binding", (.46, .49, .53), .68)
dark_knit = material("10 dark charcoal tights", (.055, .059, .067), .94, texture=True)
hem_jacquard = material("11 tonal coat-hem jacquard", (.08, .09, .10), .9)
shoe_leather = material("12 soft black footwear leather", (.066, .069, .077), .38, texture=True)
shorts_fabric = material("13 black tailored shorts", (.095, .102, .112), .72, texture=True)
back_webbing = material("14 deep charcoal back webbing", (.023, .027, .034), .91, texture=True)
jacquard_node = hem_jacquard.node_tree.nodes.new("ShaderNodeTexImage")
jacquard_node.image = jacquard_image()
hem_shader = next(node for node in hem_jacquard.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
hem_jacquard.node_tree.links.new(jacquard_node.outputs["Color"],
                                 hem_shader.inputs["Base Color"])

GARMENT = []


def mesh(name, verts, faces, mat, thickness=0, smooth=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(mat)
    uv = data.uv_layers.new(name="fabric UV")
    for poly in data.polygons:
        for loop_index in poly.loop_indices:
            vertex = data.vertices[data.loops[loop_index].vertex_index].co
            uv.data[loop_index].uv = ((vertex.x + vertex.y) * 1.15 + 1.5, vertex.z * 1.25 + 1.7)
        poly.use_smooth = smooth
    if thickness:
        mod = obj.modifiers.new("hem and cloth thickness", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = 0
        bevel = obj.modifiers.new("soft sewn edge", "BEVEL")
        bevel.width = min(thickness * .34, .008)
        bevel.segments = 2
    GARMENT.append(obj)
    return obj


def grid(name, rows, mat, thickness=.007):
    verts = [point for row in rows for point in row]
    columns = len(rows[0])
    faces = []
    for r in range(len(rows) - 1):
        for c in range(columns - 1):
            a = r * columns + c
            faces.append((a, a + 1, a + columns + 1, a + columns))
    return mesh(name, verts, faces, mat, thickness)


def seam(name, points, mat=edge, radius=.007):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for p, co in zip(spline.points, points):
        p.co = (*co, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(mat)
    GARMENT.append(obj)
    return obj


def cube(name, center, scale, mat, bevel=.01):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("rounded manufactured edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new("weighted normals", "WEIGHTED_NORMAL")
    GARMENT.append(obj)
    return obj


def ring(name, center, major, minor, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=40, minor_segments=10,
        location=center, rotation=rotation, major_radius=major, minor_radius=minor)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    GARMENT.append(obj)
    return obj


def printed_label(name, words, location, size, mat):
    """Small flat lettering; placement is an inferred prop detail."""
    letters = bpy.data.curves.new(name, "FONT")
    letters.body = words
    letters.align_x = "CENTER"
    letters.align_y = "CENTER"
    letters.size = size
    # A printed label should not need thousands of bevel-side triangles.
    letters.extrude = 0
    letters.bevel_depth = 0
    obj = bpy.data.objects.new(name, letters)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    # The back of this trial garment faces world +Y. Rotate the lettering
    # onto its back label before converting/exporting it as a mesh.
    obj.rotation_euler = (-math.pi / 2, 0, math.pi)
    letters.materials.append(mat)
    GARMENT.append(obj)
    return obj


# Dense loft with eased bust, waist and cloth gathers; the earlier six-ring
# oval looked like a rigid tube when the coat was open.
torso_profile = [(1.03, .25, .31), (.81, .38, .41), (.45, .39, .42),
                 (.08, .36, .38), (-.22, .37, .37), (-.42, .385, .355)]
torso_rows = []
for row in range((len(torso_profile) - 1) * 5 + 1):
    segment = min(len(torso_profile) - 2, row // 5)
    blend = (row - segment * 5) / 5
    z, rx, ry = (torso_profile[segment][i] * (1 - blend)
                 + torso_profile[segment + 1][i] * blend for i in range(3))
    row_points = []
    for a in range(49):
        angle = a * math.tau / 48
        front = max(0, math.cos(angle))
        # Local folds are intentionally asymmetric, strongest around the
        # lower pocket and ribbed hem, and fade across the back.
        gather = front * (.007 * math.sin(z * 18 + angle * 5)
                          + .004 * math.sin(z * 31 - angle * 8))
        depth = ry if front else min(.265, ry * .68)
        width = rx + .006 * math.sin(z * 11 + angle * 7) * front
        hem_wave = .013 * math.sin(angle * 4 + .7) * max(0, (-z - .08) / .34)
        row_points.append((width * math.sin(angle),
                           -(depth + gather) * math.cos(angle), z + hem_wave))
    torso_rows.append(row_points)
grid("ribbed inner sweater with draped waist", torso_rows, knit, .012)
for x in (-.14, -.07, 0, .07, .14):
    seam("knit vertical rib", [(x, -.345, -.32), (x, -.375, .03),
         (x, -.415, .42)], knit, .003)
seam("sweater lower ribbed hem", [(.385 * math.sin(a * math.tau / 48),
    -(.355 if a <= 12 or a >= 36 else .23) * math.cos(a * math.tau / 48), -.395)
    for a in range(49)], knit, .009)
for side in (-1, 1):
    seam("sweater shoulder knit shaping" + str(side), [
        (side * .12, -.303, .96), (side * .25, -.373, .78),
        (side * .30, -.401, .58)], knit, .005)
ring("raised knit collar", (0, 0, 1.055), .217, .027, knit)

# The reference outfit has three independently worn cloth layers. In the
# previous preview the sweater ended directly on the tights, so the black
# shorts listed and photographed by costume makers disappeared entirely.
shorts_waist = []
for z, rx, front_depth, rear_depth in ((-.38, .365, .352, .255),
                                        (-.47, .398, .365, .280),
                                        (-.54, .397, .352, .280)):
    shorts_waist.append([(rx * math.sin(a * math.tau / 48),
                          -(front_depth if a <= 12 or a >= 36 else rear_depth)
                          * math.cos(a * math.tau / 48), z)
                         for a in range(49)])
grid("separate tailored shorts hip shell", shorts_waist, shorts_fabric, .008)
seam("shorts waistband lower topstitch", shorts_waist[1], black, .004)
for side in (-1, 1):
    leg_rows = []
    for z, rx, ry in ((-.49, .204, .252), (-.60, .194, .245),
                       (-.70, .180, .229)):
        leg_rows.append([(side * .198 + rx * math.sin(a * math.tau / 32),
                          -.025 - ry * math.cos(a * math.tau / 32), z)
                         for a in range(33)])
    grid("separate shorts leg" + str(side), leg_rows, shorts_fabric, .008)
    seam("shorts turned leg hem" + str(side), leg_rows[-1], black, .008)
    seam("shorts outer side seam" + str(side),
         [(side * .40, -.02, -.45), (side * .397, -.02, -.55),
          (side * .378, -.02, -.69)], black, .004)
seam("shorts front fly seam", [(0, -.371, -.47), (0, -.373, -.56),
                                (.045, -.355, -.60)], black, .004)

# Single sewn sweep for the coat, open in front and with an asymmetric hem.
coat_rows = []
levels = [(1.02, .285, .25), (.91, .37, .32), (.62, .40, .36),
          (.24, .39, .36), (-.18, .425, .38), (-.57, .56, .425),
          (-.98, .77, .49), (-1.33, .735, .53)]
coat_steps = (len(levels) - 1) * 5
for row in range(coat_steps + 1):
    segment = min(len(levels) - 2, row // 5)
    blend = (row - segment * 5) / 5
    height, rx, ry = tuple(levels[segment][i] * (1 - blend)
                           + levels[segment + 1][i] * blend for i in range(3))
    points = []
    for i in range(73):
        angle = math.radians(37 + i * (286 / 72))
        front = max(0, math.cos(angle))
        progress = row / coat_steps
        fold = progress ** 2 * (.047 * math.sin(angle * 13) + .026 * math.sin(angle * 19))
        diagonal_wrinkle = .013 * math.sin(22 * progress + 5 * angle) * math.sin(math.pi * progress) ** 2
        side_wing = (.065 * math.exp(-((height + .87) / .28) ** 2)
                     * (math.exp(-((angle - math.pi / 2) / .49) ** 2)
                        + math.exp(-((angle - 3 * math.pi / 2) / .49) ** 2)))
        x = (rx + fold + side_wing) * math.sin(angle)
        y = -(ry + fold * .6) * math.cos(angle) + diagonal_wrinkle
        # The opening corners fall into the two irregular pointed coat tails;
        # the side and rear hem stay higher. This is part of the same shell,
        # rather than a flat ornament floating in front of it.
        tail = math.exp(-((angle - math.radians(53)) / .23) ** 2)
        tail += math.exp(-((angle - math.radians(307)) / .23) ** 2)
        z = height + progress ** 3 * (.19 * front + .06 * math.sin(angle * 3)
                                     - .27 * tail)
        points.append((x, y, z))
    coat_rows.append(points)
coat_shell = grid("open long coat continuous outer shell", coat_rows, coat, .012)
coat_shell.data.materials.append(hem_jacquard)
for polygon in coat_shell.data.polygons:
    if sum(coat_shell.data.vertices[index].co.z for index in polygon.vertices) / len(polygon.vertices) < -.57:
        polygon.material_index = 1
if BACK_PANEL_TRIAL:
    # An inferred rear colour-block study, *not* a scanned garment or a
    # drafted rear inset.  Assign the existing continuous shell faces a
    # second fabric.  A separate inset mesh intersected the thickened shell
    # and produced black slivers at the hem in the render.
    centre = 36
    coat_shell.data.materials.append(side_panel)
    for row_index in range(2, len(coat_rows) - 1):
        progress = row_index / (len(coat_rows) - 1)
        halfspan = round(4.0 + 8.5 * progress)
        for column in range(centre - halfspan,
                            centre + halfspan):
            coat_shell.data.polygons[row_index * 72 + column].material_index = 2
    def inset_edge(sign):
        points = []
        for row_index in range(2, len(coat_rows)):
            progress = row_index / (len(coat_rows) - 1)
            column = centre + sign * round(4.0 + 8.5 * progress)
            point = Vector(coat_rows[row_index][column])
            point += Vector((point.x, point.y, 0)).normalized() * .008
            points.append(tuple(point))
        return points
    seam("rear inset left join trial", inset_edge(-1), edge, .0035)
    seam("rear inset right join trial", inset_edge(1), edge, .0035)
    # The yellow hanging accent is a separate textile/webbing study; it is
    # not an assertion about the hidden official rear sewing construction.
    accent = []
    for row in coat_rows[10:]:
        p = Vector(row[centre + 1])
        p += Vector((p.x, p.y, 0)).normalized() * .012
        accent.append(tuple(p))
    seam("inferred rear yellow hanging accent trial", accent, yellow, .014)
for side, col in ((-1, 72), (1, 0)):
    seam("front opening bound edge", [row[col] for row in coat_rows], edge, .012)
    seam("princess seam from yoke into flare", [
        (side * .35, -.13, .88), (side * .38, -.16, .57),
        (side * .39, -.19, .21), (side * .46, -.27, -.27),
        (side * .58, -.30, -.86), (side * .65, -.26, -1.09)],
        black, .005)

# The grey facings end above the waist. Below them the continuous dark shell
# carries the coat front; long grey rectangles made it read as a raincoat.
for side in (-1, 1):
    rows = []
    for z, inside, outside, depth in [(.94, .18, .37, -.26), (.74, .20, .40, -.33),
                                      (.46, .22, .39, -.38), (.20, .23, .37, -.38),
                                      (-.05, .24, .34, -.36), (-.29, .28, .37, -.36)]:
        rows.append([(side * inside, depth - .013, z),
                     (side * (inside + outside) / 2, depth - .038, z - .012),
                     (side * outside, depth + .04, z + .022)])
    grid("tailored cool-grey front panel" + str(side), rows, side_panel, .009)
    seam("facing lower turned hem" + str(side), rows[-1], edge, .005)
    seam("facing waist dart" + str(side), [
        (side * .32, -.383, .27), (side * .325, -.390, .06),
        (side * .315, -.385, -.14)], lining, .004)
    lapel = [(side * .17, -.347, 1.055), (side * .36, -.365, .98),
             (side * .44, -.41, .76), (side * .34, -.444, .49),
             (side * .22, -.41, .67), (side * .28, -.36, .89)]
    mesh("folded stand lapel" + str(side), lapel, [tuple(range(6))], lining, .013)
    seam("lapel topstitch" + str(side), [lapel[i] for i in (0, 1, 2, 3)], edge, .006)
    # Narrow bound opening continues through the dark skirt, with a curved
    # secondary stitch line describing the constructed lower front panel.
    seam("lower front facing topstitch" + str(side), [
        (side * .29, -.38, -.27), (side * .36, -.375, -.48),
        (side * .43, -.36, -.72), (side * .54, -.32, -.96),
        (side * .61, -.27, -1.12)], edge, .005)
    seam("lower front transverse shaping" + str(side), [
        (side * .36, -.375, -.48), (side * .44, -.365, -.51),
        (side * .51, -.35, -.54)], black, .006)
    # Hem corner label/weight and front flap hardware.
    cube("front tab" + str(side), (side * .51, -.38, -.90), (.13, .025, .23), black, .012)
    cube("front tab metal" + str(side), (side * .51, -.403, -.89), (.068, .014, .07), silver, .008)

# Anatomical sleeves: lofted and gently bent, rather than primitive cylinders.
for side in (-1, 1):
    sleeve_rows = []
    # The previous almost-constant 0.30 m radius made the arms read as rigid
    # tubes. A fitted cap, controlled upper-arm ease and tapered forearm give
    # the fabric a garment silhouette before any texture is applied.
    sleeve_profile = [(0, .35, .82, .205), (.16, .54, .78, .230),
                      (.40, .85, .67, .247), (.68, 1.20, .56, .230),
                      (.85, 1.44, .48, .187), (1, 1.63, .43, .158)]
    for step in range(25):
        t = step / 24
        span = next((i for i in range(len(sleeve_profile) - 1)
                     if sleeve_profile[i][0] <= t <= sleeve_profile[i + 1][0]), 4)
        first, last = sleeve_profile[span:span + 2]
        blend = (t - first[0]) / (last[0] - first[0])
        cx, cz, radius = [first[i] * (1 - blend) + last[i] * blend
                          for i in (1, 2, 3)]
        ring_points = []
        for a in range(33):
            angle = a * math.tau / 32
            gathered = math.sin(math.pi * t) ** 2
            elbow_ease = math.exp(-((t - .62) / .18) ** 2)
            wrinkle = (.008 * math.sin(t * 26 + angle * 2.4)
                       + .005 * math.sin(t * 41 - angle * 5)) * gathered
            r = radius + wrinkle + .004 * elbow_ease * math.sin(angle * 6 + t * 7)
            ring_points.append((side * (cx + .014 * math.cos(angle)),
                                -r * math.cos(angle),
                                cz + r * math.sin(angle)
                                - .024 * gathered * max(0, -math.sin(angle))))
        sleeve_rows.append(ring_points)
    grid("curved puff technical sleeve" + str(side), sleeve_rows, nylon, .012)
    seam("elbow construction seam" + str(side), sleeve_rows[15], black, .009)
    seam("cuff binding" + str(side), sleeve_rows[-1], black, .023)
    cuff_rows = []
    for cx, cz, radius in ((1.61, .434, .143), (1.68, .426, .137),
                           (1.75, .419, .130)):
        cuff_rows.append([(side * cx, -radius * math.cos(i * math.tau / 32),
                           cz + radius * math.sin(i * math.tau / 32))
                          for i in range(33)])
    grid("cuff exposed ribbed underlayer" + str(side), cuff_rows, lining, .009)
    seam("cuff inner finished edge" + str(side), cuff_rows[-1], black, .009)
    for a in range(0, 32, 4):
        seam("cuff knit radial rib" + str(side) + "_" + str(a),
             [row[a] for row in cuff_rows], edge, .003)
    if side == 1:
        seam("right wrist caution piping", sleeve_rows[-3], yellow, .007)
    for t, cx, cz, depth in ((.21, .60, .77, -.245),
                              (.88, 1.49, .48, -.197)):
        cube("adjustable sleeve tab" + str(side) + str(t),
             (side * cx, depth, cz), (.25, .025, .055), side_panel, .008)
        cube("sleeve buckle" + str(side) + str(t),
             (side * (cx + .09), depth - .025, cz), (.08, .018, .075), silver, .008)
    seam("sleeve forward seam" + str(side), [
        (side * .43, -.205, .73), (side * .81, -.252, .62),
        (side * 1.21, -.238, .50), (side * 1.60, -.158, .40)], edge, .006)
    # Commercial cuff/arm props wrap the sleeve. A small rectangular badge
    # alone reads as a floating sticker, so give each badge a separate,
    # curved textile mounting band with finished edges.
    upper_band_rows = []
    for cx, cz, radius in ((1.00, .625, .255), (1.09, .602, .250),
                           (1.18, .573, .242)):
        upper_band_rows.append([(side * cx, -radius * math.cos(a * math.tau / 32),
                                 cz + radius * math.sin(a * math.tau / 32))
                                for a in range(33)])
    grid("upper arm removable wrap band" + str(side), upper_band_rows,
         back_webbing, .005)
    for edge_row in (upper_band_rows[0], upper_band_rows[-1]):
        seam("upper arm wrap bound edge" + str(side), edge_row, edge, .003)
    cuff_band_rows = []
    for cx, cz, radius in ((1.57, .442, .173), (1.665, .430, .158),
                           (1.745, .421, .149)):
        cuff_band_rows.append([(side * cx, -radius * math.cos(a * math.tau / 32),
                                cz + radius * math.sin(a * math.tau / 32))
                               for a in range(33)])
    grid("cuff removable wrap band" + str(side), cuff_band_rows,
         back_webbing, .005)
    for edge_row in (cuff_band_rows[0], cuff_band_rows[-1]):
        seam("cuff wrap bound edge" + str(side), edge_row, edge, .003)
    cube("upper arm removable prop base" + str(side),
         (side * 1.09, -.247, .603), (.145, .021, .105), black, .014)
    cube("upper arm raised alloy badge" + str(side),
         (side * 1.09, -.265, .603), (.085, .012, .054), silver, .009)
    cube("cuff removable prop base" + str(side),
         (side * 1.675, -.151, .430), (.14, .023, .135), black, .015)
    ring("cuff radial alloy mount" + str(side),
         (side * 1.675, -.169, .430), .038, .007, silver,
         (math.pi / 2, 0, 0))
    mesh("cuff yellow triangle inset" + str(side),
         [(side * 1.675, -.178, .454),
          (side * 1.654, -.178, .414),
          (side * 1.696, -.178, .414)],
         [(0, 1, 2)], yellow, .002)

# Off-centre shoulder laminate follows the curved sleeve cap rather than a
# planar n-gon. Its backing remains a distinct flexible black component.
pauldron_rows = []
for left, right, top, depth in ((.29, .55, 1.055, -.280),
                                (.32, .68, .995, -.292),
                                (.39, .83, .875, -.295),
                                (.47, .91, .765, -.280),
                                (.59, .87, .655, -.250)):
    pauldron_rows.append([(left + (right - left) * i / 4,
                           depth - .045 * math.sin(math.pi * i / 4),
                           top - .035 * i / 4) for i in range(5)])
mesh("pauldron dark resilient underlay",
     [(x, y + .028, z - .009) for row in pauldron_rows for x, y, z in row],
     [(r * 5 + c, r * 5 + c + 1, (r + 1) * 5 + c + 1,
       (r + 1) * 5 + c) for r in range(4) for c in range(4)], black, .013)
grid("asymmetric yellow right shoulder pauldron", pauldron_rows, yellow, .020)
pauldron_border = (pauldron_rows[0]
                    + [row[-1] for row in pauldron_rows[1:]]
                    + list(reversed(pauldron_rows[-1][:-1]))
                    + [row[0] for row in reversed(pauldron_rows[1:-1])]
                    + [pauldron_rows[0][0]])
seam("yellow panel perimeter", pauldron_border, black, .009)
for point in ((.38, -.303, .966), (.78, -.284, .736)):
    ring("shoulder rivet", point, .022, .007, silver, (math.pi / 2, 0, 0))

# A retailer's shoulder close-up shows a separate dark teardrop suspended
# below the yellow laminate.  This is a front-reference placement estimate;
# the real clasp dimensions and attachment strength remain unmeasured.
ring("water-drop decoration shoulder clasp", (.78, -.312, .711),
     .016, .004, silver, (math.pi / 2, 0, 0))
seam("water-drop decoration short flexible tether", [
    (.78, -.317, .700), (.795, -.324, .647)], black, .005)
drop_outline = [(.795, -.337, .658), (.778, -.337, .614),
                (.764, -.337, .585), (.759, -.337, .553),
                (.772, -.337, .534), (.795, -.337, .525),
                (.818, -.337, .534), (.831, -.337, .553),
                (.826, -.337, .585), (.812, -.337, .614)]
mesh("water-drop decoration removable dark pendant", drop_outline,
     [tuple(range(len(drop_outline)))], black, .012, smooth=False)
seam("water-drop decoration narrow alloy rim", drop_outline +
     [drop_outline[0]], silver, .002)

# An upright, double-faced stand collar follows the neck opening. Its broad
# surface reads as fabric; the narrow seams are only edge binding.
collar_rows = []
for z, rx, ry in ((.99, .31, .275), (1.105, .295, .285), (1.20, .265, .272)):
    collar_rows.append([(rx * math.sin(math.radians(39 + i * 282 / 48)),
                         -ry * math.cos(math.radians(39 + i * 282 / 48)),
                         z + .018 * math.sin(math.pi * i / 48)) for i in range(49)])
grid("structured high stand collar", collar_rows, side_panel, .022)
seam("collar rolled top binding", collar_rows[-1], edge, .011)
for end in (0, -1):
    seam("collar front bound edge", [row[end] for row in collar_rows], black, .009)
ring("central carabiner", (-.03, -.456, .99), .115, .017, silver,
     (math.pi / 2, .2, .35))
seam("collar black tether", [(-.32, -.29, .91), (-.21, -.40, 1.01),
     (-.03, -.465, .98), (.19, -.40, .91)], black, .026)
cube("separate collar prop anchor", (0, -.473, 1.055),
     (.18, .026, .073), black, .010)
for side in (-1, 1):
    seam("sweater collar tie" + str(side), [
        (side * .13, -.397, 1.06), (side * .085, -.467, .91),
        (side * .11, -.470, .80)], black, .012)
    cube("collar tie metal end" + str(side),
         (side * .11, -.480, .795), (.025, .014, .036), silver, .004)

# Only a short fold is inferable from the front reference. Form a cloth yoke
# on the back instead of the pointed open hood or projecting tube in side view.
hood_profile = [(1.035, .285, .285), (.99, .365, .34),
                (.925, .385, .395), (.85, .35, .41), (.78, .275, .37)]
hood_rows = []
for z, half_width, base_y in hood_profile:
    hood_rows.append([(half_width * (i - 8) / 8,
                       base_y + .026 * math.sin(math.pi * i / 16),
                       z - .018 * abs((i - 8) / 8)) for i in range(17)])
grid("inferred folded hood yoke", hood_rows, coat, .022)
seam("folded hood upper topstitch", hood_rows[0], edge, .005)
seam("folded hood lower bound edge", hood_rows[-1], lining, .012)
seam("yellow hood lining narrow reveal", hood_rows[1], yellow, .006)
for side in (-1, 1):
    cord = [(side * .285, -.345, .985),
            (side * .315, -.424, .915),
            (side * .300, -.456, .812),
            (side * .287, -.464, .724)]
    seam("inferred yellow hood drawcord" + str(side), cord, yellow, .006)
    cube("black hood drawcord tip" + str(side), cord[-1],
         (.018, .017, .042), black, .003)
for side in (-1, 1):
    seam("back harness webbing" + str(side), [
        (side * .26, .30, .89), (side * .33, .38, .49),
        (side * .27, .40, .10), (side * .23, .39, -.19)], black, .032)
    cube("back buckle" + str(side), (side * .28, .432, .13),
         (.10, .028, .095), silver, .012)
    ribbon_rows = []
    for z, y, centre, width in ((.10, .443, .25, .058),
                                (-.23, .470, .267, .058),
                                (-.54, .522, .296, .050),
                                (-.83, .560, .330, .038)):
        ribbon_rows.append([(side * centre - width, y, z),
                            (side * centre, y + .009, z - .012),
                            (side * centre + width, y, z)])
    grid("separate back ribbon" + str(side), ribbon_rows,
         back_webbing, .005)
    seam("back ribbon outer topstitch" + str(side),
         [row[0] for row in ribbon_rows], edge, .003)
    cube("back hanging hard prop" + str(side),
         (side * .25, .540, -.56), (.095, .035, .125), silver, .012)
    cube("back prop dark inset" + str(side),
         (side * .25, .562, -.56), (.063, .008, .082), black, .007)
seam("back centre split binding", [(0, .39, -.22), (0, .43, -.60),
     (0, .50, -1.12)], edge, .009)
cube("back utility label", (0, .397, .60), (.28, .016, .09), black, .006)
printed_label("back utility label lettering", "ENDFIELD",
              (0, .408, .598), .039, edge)

# Provide leg reference pieces but keep focus and detailed modelling on costume.
for side in (-1, 1):
    rows = []
    for z, rx, ry, x in ((-.43, .19, .20, .19), (-.75, .175, .18, .20),
                         (-1.10, .145, .15, .19), (-1.50, .10, .115, .16),
                         (-1.69, .085, .10, .16)):
        rows.append([(side * x + rx * math.sin(i * math.tau / 24),
                      -ry * math.cos(i * math.tau / 24), z) for i in range(25)])
    grid("under-coat tights" + str(side), rows, dark_knit, .004)
    # The shoe is separate from the tights: narrower ankle, long vamp, shaped
    # toe, and a bound sole. It is still a fitting proxy, not a scanned shoe.
    boot_rows = []
    for z, x, rx, front, rear in ((-1.55, .16, .112, -.16, .13),
                                  (-1.65, .16, .12, -.20, .15),
                                  (-1.73, .17, .142, -.33, .18),
                                  (-1.79, .17, .157, -.44, .20),
                                  (-1.85, .17, .165, -.46, .21)):
        boot_rows.append([(side * x + rx * math.sin(i * math.tau / 24),
                           (front + rear) / 2 - (rear - front) / 2
                           * math.cos(i * math.tau / 24), z)
                          for i in range(25)])
    grid("black low boot" + str(side), boot_rows, shoe_leather, .016)
    seam("boot upper binding" + str(side), boot_rows[0], black, .012)
    seam("boot stitched outsole" + str(side), boot_rows[-1], black, .020)
    seam("shoe instep band" + str(side), [
        (side * .055, -.285, -1.73),
        (side * .15, -.335, -1.72),
        (side * .275, -.265, -1.71)], black, .017)
    cube("instep buckle" + str(side), (side * .23, -.292, -1.715),
         (.048, .012, .037), silver, .005)

# Export only costume pieces, then restore scene for studio renders.
bpy.ops.object.select_all(action="DESELECT")
for obj in GARMENT:
    obj.select_set(True)
bpy.context.view_layer.objects.active = GARMENT[0]
bpy.ops.export_scene.gltf(filepath=str(OUT / "endministrator_authored_costume.glb"),
                          export_format="GLB", use_selection=True,
                          export_apply=True, export_materials="EXPORT")

world = bpy.data.worlds.new("neutral studio")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes.clear()
background = world.node_tree.nodes.new("ShaderNodeBackground")
world_output = world.node_tree.nodes.new("ShaderNodeOutputWorld")
world.node_tree.links.new(background.outputs["Background"], world_output.inputs["Surface"])
background.inputs["Color"].default_value = (.13, .15, .19, 1)
background.inputs["Strength"].default_value = .7
for name, position, energy, size in (("key", (3, -4, 5), 850, 3),
                                     ("fill", (-4, -2, 3), 550, 4),
                                     ("rim", (1, 4, 4), 950, 2)):
    bpy.ops.object.light_add(type="AREA", location=position)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = 3.85
bpy.context.scene.camera = camera
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.render.resolution_x = 850
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX"
for name, position in (("front", (0, -7, .05)),
                       ("side", (7, 0, .05)), ("back", (0, 7, .05))):
    camera.location = position
    camera.rotation_euler = (Vector((0, 0, .03)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(OUT / f"endministrator_{name}.png")
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "endministrator_authored_costume.blend"))
print("AUTHORED_OUTPUT", OUT, "BACK_PANEL_TRIAL", BACK_PANEL_TRIAL)
