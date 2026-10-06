"""Drape three *actual 2D stitch panels* on a stand-in body in Blender.

This is a hem-panel construction experiment, not a simulation of the whole
coat or proof of commercial garment quality.  The optional sewn modes join
each generated bodice and hem with cloth sewing springs; sewn-shell also
models the lower side seams.  Pattern-sleeve joins are experimental;
fasteners remain absent.

Run: blender -b -t 4 --python-exit-code 1 \
        --python scripts/simulate_endministrator_pattern_panels.py
     -- PANELS_JSON OUTPUT_DIR [SOURCE_BLEND]
        [with-body|measurement-standin|measurement-standin-with-sweater|free-hang]
        [authored-guide|pattern-bodice] [source-hem|smooth-hem]
        [INITIAL_RADIAL_FLARE_M]
        [independent|sewn-bodice|sewn-shell|welded-shell|aligned-welded-shell|
         authored-guided-welded-shell|fully-welded-shell]
        [SEWN_INITIAL_GAP_M] [baseline|structured-trial]
        [self-collision|no-self-collision]
        [no-overlays|with-overlays|with-normal-overlays|with-relaxed-overlays|
         with-relaxed-overlays-no-self|with-relaxed-overlays-no-shell|
         with-relaxed-static-overlays|with-sewn-overlays]
        [raw-shell|paper-edge-relaxed-shell]
        [OVERLAY_MOUNT_CLEARANCE_CM]
        [pattern-only|authored-front-detail-comparison]
        [authored-guide|paper-developed-trial]
        [fully-fixed-upper|neck-shoulder-anchor-trial]
        [raw-paper-height|dart-taken-up-height-trial]
        [open-bust-darts|sewn-bust-darts-trial]
        [open-shoulders|sewn-shoulders-trial]
"""

from __future__ import annotations

import json
import bisect
import hashlib
import math
import sys
from itertools import permutations
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.fitting_mannequin import axes_for_circumference
from engine.endministrator_armhole import (choose_sleeve_shoulder_station,
                                         distribute_sleeve_cap_ease)
from engine.pattern_panel_bridge import (aligned_trapezoid_distance,
                                         place_three_panel_tops,
                                         interpolate_pattern_surface_with_normal,
                                         outward_wound_faces,
                                         relax_connected_shell_to_paper_edges,
                                         relax_overlay_to_paper_edges,
                                         pair_seam_vertices,
                                         require_initial_sewing_clearance,
                                         validate_cloth_panel_mesh,
                                         weld_seam_vertices,
                                         xy_scale_for_polyline_length)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) not in range(2, 26):
    raise SystemExit("Usage: -- PANELS_JSON OUTPUT_DIR [SOURCE_BLEND] "
                     "[with-body|measurement-standin|measurement-standin-with-sweater|free-hang] "
                     "[authored-guide|pattern-bodice] "
                     "[source-hem|smooth-hem] [INITIAL_RADIAL_FLARE_M] "
                     "[independent|sewn-bodice|sewn-shell|welded-shell|"
                     "aligned-welded-shell|authored-guided-welded-shell|fully-welded-shell] "
                     "[SEWN_INITIAL_GAP_M] "
                     "[baseline|structured-trial] "
                     "[self-collision|no-self-collision] "
                     "[no-overlays|with-overlays|with-normal-overlays] "
                     "[raw-shell|paper-edge-relaxed-shell] "
                     "[OVERLAY_MOUNT_CLEARANCE_CM] "
                     "[pattern-only|authored-front-detail-comparison|"
                     "pattern-derived-front-detail|pattern-cloth-front-detail|"
                     "pattern-applique-front-detail|pattern-lapel-front-trial] "
                     "[authored-guide|paper-developed-trial|"
                     "landmark-tapered-trial] "
                     "[fully-fixed-upper|neck-shoulder-anchor-trial|"
                     "back-center-anchor-trial|back-neck-band-trial] "
                     "[raw-paper-height|dart-taken-up-height-trial] "
                     "[open-bust-darts|sewn-bust-darts-trial] "
                     "[open-shoulders|sewn-shoulders-trial] "
                     "[open-bodice-sides|sewn-bodice-sides-trial] "
                     "[borrowed-sleeves|pattern-sewn-sleeves-trial] "
                     "[render|sleeve-preflight-only] "
                     "[uniform|crown-localized|notch-anchored] [FRAMES]")
panel_file, output = Path(args[0]).resolve(), Path(args[1]).resolve()
source = Path(args[2]).resolve() if len(args) >= 3 else (
    ROOT / "output/endministrator_commercial_sewn_v4/endministrator_sewn_costume.blend")
collision_mode = args[3] if len(args) >= 4 else "with-body"
if collision_mode not in {"with-body", "measurement-standin",
                          "measurement-standin-with-sweater", "free-hang"}:
    raise ValueError("Expected with-body, measurement-standin, "
                     "measurement-standin-with-sweater or free-hang")
bodice_mode = args[4] if len(args) >= 5 else "authored-guide"
if bodice_mode not in {"authored-guide", "pattern-bodice"}:
    raise ValueError("Expected authored-guide or pattern-bodice")
guide_mode = args[5] if len(args) >= 6 else "source-hem"
if guide_mode not in {"source-hem", "smooth-hem"}:
    raise ValueError("Expected source-hem or smooth-hem")
radial_flare_m = float(args[6]) if len(args) >= 7 else .105
if not 0 <= radial_flare_m <= .2:
    raise ValueError("Initial radial flare must be between 0 and .2 m")
join_mode = args[7] if len(args) >= 8 else "independent"
if join_mode not in {"independent", "sewn-bodice", "sewn-shell",
                     "welded-shell", "aligned-welded-shell",
                     "authored-guided-welded-shell", "fully-welded-shell"}:
    raise ValueError("Expected independent, sewn-bodice, sewn-shell, "
                     "welded-shell, aligned-welded-shell, "
                     "authored-guided-welded-shell or fully-welded-shell")
shell_joined = join_mode in {"sewn-shell", "welded-shell", "aligned-welded-shell",
                             "authored-guided-welded-shell", "fully-welded-shell"}
topology_welded = join_mode in {"welded-shell", "aligned-welded-shell",
                                 "authored-guided-welded-shell", "fully-welded-shell"}
if join_mode != "independent" and bodice_mode != "pattern-bodice":
    raise ValueError("Sewn bodice mode needs generated bodice meshes")
sewn_initial_gap_m = float(args[8]) if len(args) >= 9 else .08
if not 0 <= sewn_initial_gap_m <= .1:
    raise ValueError("Sewn initial gap must be between 0 and .1 m")
if join_mode == "fully-welded-shell" and sewn_initial_gap_m != 0:
    raise ValueError("A fully welded seam must start with zero sewn gap")
fabric_profile = args[9] if len(args) >= 10 else "baseline"
if fabric_profile not in {"baseline", "structured-trial"}:
    raise ValueError("Expected baseline or structured-trial fabric profile")
self_collision_mode = args[10] if len(args) >= 11 else "self-collision"
if self_collision_mode not in {"self-collision", "no-self-collision"}:
    raise ValueError("Expected self-collision or no-self-collision")
overlay_mode = args[11] if len(args) >= 12 else "no-overlays"
if overlay_mode not in {"no-overlays", "with-overlays",
                        "with-normal-overlays", "with-relaxed-overlays",
                        "with-relaxed-overlays-no-self",
                        "with-relaxed-overlays-no-shell",
                        "with-relaxed-static-overlays", "with-sewn-overlays"}:
    raise ValueError("Expected no-overlays, with-overlays, "
                     "with-normal-overlays, with-relaxed-overlays, "
                     "with-relaxed-overlays-no-self, with-relaxed-overlays-no-shell "
                     "with-relaxed-static-overlays or with-sewn-overlays")
RELAXED_OVERLAY_MODES = {"with-relaxed-overlays",
                         "with-relaxed-overlays-no-self",
                         "with-relaxed-overlays-no-shell",
                         "with-relaxed-static-overlays"}
if overlay_mode != "no-overlays" and not shell_joined:
    raise ValueError("Overlay trial needs a sewn lower shell")
if overlay_mode == "with-sewn-overlays" and join_mode != "fully-welded-shell":
    raise ValueError("Shared-cloth overlay sewing needs fully-welded-shell")
shell_placement_mode = args[12] if len(args) >= 13 else "raw-shell"
if shell_placement_mode not in {"raw-shell", "paper-edge-relaxed-shell"}:
    raise ValueError("Expected raw-shell or paper-edge-relaxed-shell")
overlay_mount_clearance_cm = float(args[13]) if len(args) >= 14 else 0.9
if not 0.6 <= overlay_mount_clearance_cm <= 3.0:
    raise ValueError("Overlay mount clearance must be between 0.6 and 3.0 cm")
if (len(args) >= 14 and overlay_mode not in RELAXED_OVERLAY_MODES and
        abs(overlay_mount_clearance_cm - .9) > 1e-9):
    raise ValueError("Overlay mount clearance only applies to relaxed overlays")
detail_mode = args[14] if len(args) >= 15 else "pattern-only"
if detail_mode not in {"pattern-only", "authored-front-detail-comparison",
                       "pattern-derived-front-detail", "pattern-cloth-front-detail",
                       "pattern-applique-front-detail", "pattern-lapel-front-trial"}:
    raise ValueError("Expected pattern-only, authored-front-detail-comparison "
                     "pattern-derived-front-detail, pattern-cloth-front-detail "
                     "pattern-applique-front-detail or pattern-lapel-front-trial")
if detail_mode in {"pattern-derived-front-detail", "pattern-cloth-front-detail",
                   "pattern-applique-front-detail", "pattern-lapel-front-trial"} and (
        bodice_mode != "pattern-bodice" or join_mode != "fully-welded-shell"):
    raise ValueError("Pattern-derived front detail needs a welded pattern bodice")
bodice_placement_mode = args[15] if len(args) >= 16 else "authored-guide"
if bodice_placement_mode not in {"authored-guide", "paper-developed-trial",
                                "landmark-tapered-trial"}:
    raise ValueError("Expected authored-guide, paper-developed-trial "
                     "or landmark-tapered-trial")
if bodice_placement_mode in {"paper-developed-trial", "landmark-tapered-trial"} and (
        bodice_mode != "pattern-bodice"):
    raise ValueError("Paper placement needs a generated pattern bodice")
upper_pin_mode = args[16] if len(args) >= 17 else "fully-fixed-upper"
if upper_pin_mode not in {"fully-fixed-upper", "neck-shoulder-anchor-trial",
                          "back-center-anchor-trial", "back-neck-band-trial"}:
    raise ValueError("Expected fully-fixed-upper, neck-shoulder-anchor-trial "
                     "back-center-anchor-trial or back-neck-band-trial")
if upper_pin_mode in {"neck-shoulder-anchor-trial", "back-center-anchor-trial",
                      "back-neck-band-trial"} and (
        bodice_mode != "pattern-bodice" or not shell_joined):
    raise ValueError("Released upper-cloth trial needs a joined pattern bodice")
dart_height_mode = args[17] if len(args) >= 18 else "raw-paper-height"
if dart_height_mode not in {"raw-paper-height", "dart-taken-up-height-trial"}:
    raise ValueError("Expected raw-paper-height or dart-taken-up-height-trial")
if dart_height_mode == "dart-taken-up-height-trial" and (
        bodice_placement_mode != "paper-developed-trial" or
        upper_pin_mode != "neck-shoulder-anchor-trial"):
    raise ValueError("Dart-taken-up trial needs paper placement and released upper cloth")
dart_seam_mode = args[18] if len(args) >= 19 else "open-bust-darts"
if dart_seam_mode not in {"open-bust-darts", "sewn-bust-darts-trial"}:
    raise ValueError("Expected open-bust-darts or sewn-bust-darts-trial")
trial_panel_data = json.loads(panel_file.read_text(encoding="utf-8"))
upper_seam_trial_join_allowed = (join_mode == "fully-welded-shell" or
                                 (join_mode == "sewn-shell" and
                                  any(host.get("hem_waist_darts") for host in
                                      trial_panel_data["bodice_hosts"])))
if dart_seam_mode == "sewn-bust-darts-trial" and (
        not upper_seam_trial_join_allowed or
        upper_pin_mode not in {"neck-shoulder-anchor-trial",
                               "back-center-anchor-trial", "back-neck-band-trial"}):
    raise ValueError("Bust-dart sewing trial needs a released welded shell with exported darts")
shoulder_seam_mode = args[19] if len(args) >= 20 else "open-shoulders"
if shoulder_seam_mode not in {"open-shoulders", "sewn-shoulders-trial"}:
    raise ValueError("Expected open-shoulders or sewn-shoulders-trial")
if shoulder_seam_mode == "sewn-shoulders-trial" and (
        not upper_seam_trial_join_allowed or
        upper_pin_mode not in {"neck-shoulder-anchor-trial",
                               "back-center-anchor-trial", "back-neck-band-trial"}):
    raise ValueError("Shoulder sewing trial needs a released welded shell")
bodice_side_mode = args[20] if len(args) >= 21 else "open-bodice-sides"
if bodice_side_mode not in {"open-bodice-sides", "sewn-bodice-sides-trial"}:
    raise ValueError("Expected open-bodice-sides or sewn-bodice-sides-trial")
if bodice_side_mode == "sewn-bodice-sides-trial" and (
        dart_seam_mode != "sewn-bust-darts-trial" or
        shoulder_seam_mode != "sewn-shoulders-trial"):
    raise ValueError("Bodice-side sewing needs closed bust darts and shoulders")
sleeve_mode = args[21] if len(args) >= 22 else "borrowed-sleeves"
if sleeve_mode not in {"borrowed-sleeves", "pattern-sewn-sleeves-trial"}:
    raise ValueError("Expected borrowed-sleeves or pattern-sewn-sleeves-trial")
if sleeve_mode == "pattern-sewn-sleeves-trial" and (
        bodice_side_mode != "sewn-bodice-sides-trial" or
        upper_pin_mode != "back-neck-band-trial"):
    raise ValueError("Pattern sleeve trial needs sewn bodice sides and back neck support")
run_mode = args[22] if len(args) >= 23 else "render"
if run_mode not in {"render", "sleeve-preflight-only"}:
    raise ValueError("Expected render or sleeve-preflight-only")
if run_mode == "sleeve-preflight-only" and sleeve_mode != "pattern-sewn-sleeves-trial":
    raise ValueError("Sleeve preflight needs the pattern sleeve trial")
cap_ease_mode = args[23] if len(args) >= 24 else "uniform"
if cap_ease_mode not in {"uniform", "crown-localized", "notch-anchored"}:
    raise ValueError("Expected uniform, crown-localized or notch-anchored cap ease")
if cap_ease_mode != "uniform" and sleeve_mode != "pattern-sewn-sleeves-trial":
    raise ValueError("Localized ease needs the pattern sleeve trial")
frame_count = int(args[24]) if len(args) >= 25 else 48
if not 24 <= frame_count <= 240:
    raise ValueError("Frames must be between 24 and 240")
if shell_placement_mode == "paper-edge-relaxed-shell" and join_mode != "fully-welded-shell":
    raise ValueError("Paper-edge shell relaxation needs fully-welded-shell")
if join_mode == "authored-guided-welded-shell" and guide_mode != "source-hem":
    raise ValueError("Authored lower guide requires source-hem on the bodice")
output.mkdir(parents=True, exist_ok=True)
data = trial_panel_data


def input_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


input_fingerprints = {
    "pattern_json": {"path": str(panel_file), "sha256": input_sha256(panel_file)},
    "source_blend": {"path": str(source), "sha256": input_sha256(source)},
    "simulation_script_sha256": input_sha256(Path(__file__)),
}
darted_hem_hosts = [host["code"] for host in data["bodice_hosts"]
                    if host.get("hem_waist_darts")]
if darted_hem_hosts and join_mode != "sewn-shell":
    raise ValueError(
        "Darted bodice hems are exported as separate sewn runs, but this "
        "Blender adapter supports them only in the non-welded sewn-shell "
        "waist-dart diagnostic. Refusing a false continuous join.")
if dart_seam_mode == "sewn-bust-darts-trial" and not all(
        "side_bust_darts" in host for host in data["bodice_hosts"]):
    raise ValueError("Bust-dart sewing trial needs exported dart boundaries")
if shoulder_seam_mode == "sewn-shoulders-trial" and not all(
        "shoulder_mesh_paths" in host for host in data["bodice_hosts"]):
    raise ValueError("Shoulder sewing trial needs exported shoulder boundaries")
if bodice_side_mode == "sewn-bodice-sides-trial" and not all(
        "side_mesh_paths" in host for host in data["bodice_hosts"]):
    raise ValueError("Bodice-side sewing trial needs exported side boundaries")
if sleeve_mode == "pattern-sewn-sleeves-trial" and (
        len(data.get("sleeves", [])) != 2 or not all(
            "tube_side_mesh_paths" in sleeve for sleeve in data["sleeves"])):
    raise ValueError("Pattern sleeve trial needs two exported cap and tube boundaries")
if [panel["code"] for panel in data["panels"]] != ["A", "B", "C"]:
    raise ValueError("Expected the generated A/B/C stitch panels")
panel_topology_preflight = {
    panel["code"]: validate_cloth_panel_mesh(panel)
    for panel in data["panels"]}
overlay_topology_preflight = {}
sleeve_topology_preflight = {
    sleeve["side"]: validate_cloth_panel_mesh(sleeve["pattern_mesh"])
    for sleeve in data.get("sleeves", [])}
if overlay_mode != "no-overlays":
    overlay_topology_preflight = {
        overlay["code"]: validate_cloth_panel_mesh(overlay)
        for overlay in data.get("overlays", [])}
if bodice_mode == "pattern-bodice" and [host["code"] for host in data.get(
        "bodice_hosts", [])] != ["A", "B", "C"]:
    raise ValueError("Pattern bodice mode needs A/B/C generated host meshes")

bpy.ops.wm.open_mainfile(filepath=str(source))
scene = bpy.context.scene
scene.frame_set(1)

# Preserve the existing reference garments only where they clarify layering.
# The former hand-authored coat is hidden, so these renders cannot be mistaken
# for its pattern-accurate simulation.
visible_prefixes = ("ribbed inner sweater", "separate tailored shorts",
                    "separate shorts leg", "under-coat tights",
                    "curved puff technical sleeve", "cuff exposed ribbed underlayer",
                    "cut yellow panel on sleeve cap", "pauldron sewn black support",
                    "structured high stand collar", "sweater collar tie")
if sleeve_mode == "pattern-sewn-sleeves-trial":
    visible_prefixes = tuple(name for name in visible_prefixes if not
                             name.startswith(("curved puff technical sleeve",
                                              "cuff exposed ribbed underlayer",
                                              "cut yellow panel on sleeve cap",
                                              "pauldron sewn black support")))
if bodice_mode == "authored-guide":
    visible_prefixes += ("cut-and-fitted grey facing", "folded stand lapel")
if detail_mode == "authored-front-detail-comparison":
    # This is a controlled visual comparison, not a generated pattern piece.
    # Never enable these source-Blender objects in the pattern-only default.
    visible_prefixes += (
        "cut-and-fitted grey facing", "folded stand lapel",
        "grey facing tailored outer seam", "grey facing turned lower hem",
        "lapel topstitch", "lower front facing topstitch")
borrowed_front_detail_prefixes = (
    "cut-and-fitted grey facing", "folded stand lapel",
    "grey facing tailored outer seam", "grey facing turned lower hem",
    "lapel topstitch", "lower front facing topstitch")
for obj in scene.objects:
    if obj.type in {"MESH", "CURVE", "FONT"}:
        obj.hide_render = not obj.name.startswith(visible_prefixes)
borrowed_front_detail_names = sorted(
    obj.name for obj in scene.objects
    if obj.type in {"MESH", "CURVE"} and not obj.hide_render
    and obj.name.startswith(borrowed_front_detail_prefixes))
borrowed_sleeve_names = sorted(
    obj.name for obj in scene.objects
    if obj.type in {"MESH", "CURVE"} and not obj.hide_render
    and obj.name.startswith(("curved puff technical sleeve",
                             "cuff exposed ribbed underlayer",
                             "cut yellow panel on sleeve cap",
                             "pauldron sewn black support")))

# Show only the hip-length bodice of the previous hand-authored coat.  Its
# lower flare would otherwise occupy the same space as the pattern panels.
source_coat = bpy.data.objects["open long coat continuous outer shell"]
UNIT_M_PER_CM = .02  # authored avatar/costume is at twice human metre scale
widths = {panel["code"]: panel["top_width_cm"] for panel in data["panels"]}
guide_rows = [[source_coat.data.vertices[row * 73 + index].co.copy()
               for index in range(73)] for row in range(25)]
authored_lower_rows = None
if bodice_mode == "pattern-bodice":
    target_length = sum(widths.values()) * UNIT_M_PER_CM
    if guide_mode == "smooth-hem":
        # A smooth, constant-height open ellipse is a near-isometric starting
        # seam for the 2D cloth.  It is a *hypothesis*, not observed anatomy.
        reference = [(math.sin(math.radians(37 + index * 286 / 72)),
                      -.75 * math.cos(math.radians(37 + index * 286 / 72)),
                      0.0) for index in range(73)]
        radius = xy_scale_for_polyline_length(reference, target_length)
        smooth_hem = [Vector((point[0] * radius, point[1] * radius, -.43))
                      for point in reference]
        for row, points in enumerate(guide_rows):
            blend = (row / 24) ** 2
            for index, point in enumerate(points):
                points[index] = point.lerp(smooth_hem[index], blend)
    else:
        hem_ratio = xy_scale_for_polyline_length(
            [tuple(point) for point in guide_rows[-1]], target_length)
        for row, points in enumerate(guide_rows):
            blend = (row / 24) ** 1.5
            factor = 1.0 - (1.0 - hem_ratio) * blend
            for point in points:
                point.x *= factor
                point.y *= factor
        if join_mode == "authored-guided-welded-shell":
            authored_lower_rows = [
                [source_coat.data.vertices[row * 73 + index].co.copy()
                 for index in range(73)] for row in range(24, 36)]
            for points in authored_lower_rows:
                for point in points:
                    point.x *= hem_ratio
                    point.y *= hem_ratio
hem_row = guide_rows[-1]
hem_distance = [0.0]
for first, second in zip(hem_row, hem_row[1:]):
    hem_distance.append(hem_distance[-1] + (second - first).length)
hem_length = hem_distance[-1]
if bodice_mode == "authored-guide":
    upper_coat = source_coat.copy()
    upper_coat.data = source_coat.data.copy()
    upper_coat.name = "hip-length support bodice (not yet seam-welded)"
    scene.collection.objects.link(upper_coat)
    bm = bmesh.new()
    bm.from_mesh(upper_coat.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[vert for vert in bm.verts if vert.index >= 25 * 73],
                     context="VERTS")
    bm.to_mesh(upper_coat.data)
    bm.free()
    upper_coat.data.update()
    upper_coat.hide_render = False

existing = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "web/static/models/default-avatar.vrm"))
imported = set(scene.objects) - existing
body = next(obj for obj in imported if obj.type == "MESH" and obj.name.startswith("Body"))
armature = next(obj for obj in imported if obj.type == "ARMATURE")
armature.scale = (2.07,) * 3
armature.location.z = -1.72
bpy.context.view_layer.update()
for obj in imported:
    obj.hide_render = True
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.context.view_layer.objects.active = body
body.hide_render = True
if collision_mode == "measurement-standin-with-sweater":
    # Controlled comparison: the visible inner layer is wider than the
    # measurement-only torso.  Test whether the coat is falling *inside* it.
    # This source sweater is hand-authored, not a measured garment or scan.
    sweater = scene.objects.get("ribbed inner sweater with draped waist")
    if sweater is None or sweater.type != "MESH":
        raise ValueError("Sweater collision trial needs the source sweater mesh")
    # The source sweater's face normals point inward.  Confirm that with two
    # known probe points before reversing a *copy* for Blender collision.
    sweater_tree = BVHTree.FromPolygons(
        [sweater.matrix_world @ vertex.co for vertex in sweater.data.vertices],
        [tuple(face.vertices) for face in sweater.data.polygons])
    front_probe = Vector((0, -1, .2))
    centre_probe = Vector((0, 0, .2))
    front_hit = sweater_tree.find_nearest(front_probe)
    centre_hit = sweater_tree.find_nearest(centre_probe)
    if (front_hit is None or centre_hit is None or
            (front_probe - front_hit[0]).dot(front_hit[1]) >= 0 or
            (centre_probe - centre_hit[0]).dot(centre_hit[1]) <= 0):
        raise RuntimeError("Source sweater normal orientation changed; "
                           "re-audit collision before using it")
    collision_sweater = sweater.copy()
    collision_sweater.data = sweater.data.copy()
    collision_sweater.name = "outward sweater collision copy (not measured)"
    scene.collection.objects.link(collision_sweater)
    collision_sweater.hide_render = True
    bm = bmesh.new()
    bm.from_mesh(collision_sweater.data)
    bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    bm.to_mesh(collision_sweater.data)
    bm.free()
    collision_sweater.data.update()
    bpy.ops.object.select_all(action="DESELECT")
    collision_sweater.select_set(True)
    bpy.context.view_layer.objects.active = collision_sweater
    if not collision_sweater.collision:
        bpy.ops.object.modifier_add(type="COLLISION")
    collision_sweater.collision.thickness_outer = .008
    collision_sweater.collision.cloth_friction = 6
if collision_mode == "with-body":
    if not body.collision:
        bpy.ops.object.modifier_add(type="COLLISION")
    body.collision.thickness_outer = .012
    body.collision.cloth_friction = 6
elif collision_mode in {"measurement-standin", "measurement-standin-with-sweater"}:
    # The imported VRM has a very large lower-body outline relative to the
    # M-size test pattern.  Use a declared, reproducible measurement fixture
    # instead of treating its fashion silhouette as the wearer's body.
    body_cm = data["body_cm"]

    def add_collision_surface(name, profile, centre_x=0.0):
        vertices = []
        count = 48
        for z, circumference in profile:
            rx, ry = axes_for_circumference(circumference)
            for column in range(count):
                angle = math.tau * column / count
                vertices.append((centre_x + rx * math.sin(angle),
                                 -ry * math.cos(angle), z))
        faces = []
        for row in range(len(profile) - 1):
            for column in range(count):
                right = (column + 1) % count
                a = row * count + column
                b = row * count + right
                faces.append((a, a + count, b + count, b))
        faces.append(tuple(range(count)))
        faces.append(tuple(reversed(tuple((len(profile) - 1) * count + col
                                            for col in range(count)))))
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        obj.hide_render = True
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_add(type="COLLISION")
        obj.collision.thickness_outer = .008
        obj.collision.cloth_friction = 6
        return obj

    add_collision_surface("measured-size torso proxy (not a scan)", [
        (1.0, body_cm["bust"] * .42),
        (.72, body_cm["bust"] * .86),
        (.43, body_cm["bust"]),
        (.05, body_cm["waist"]),
        (-.20, (body_cm["waist"] + body_cm["hip"]) / 2),
        (-.43, body_cm["hip"]),
        (-.58, body_cm["hip"] * .92),
    ])
    for side in (-1, 1):
        add_collision_surface(f"measured-size leg proxy {side} (not a scan)", [
            (-.53, body_cm["hip"] * .51),
            (-.78, body_cm["hip"] * .49),
            (-1.05, body_cm["hip"] * .42),
            (-1.42, body_cm["hip"] * .33),
        ], centre_x=side * .20)
    if sleeve_mode == "pattern-sewn-sleeves-trial":
        # Nominal support only.  The user's upper-arm and wrist measurements
        # are unavailable; this is neither a scan nor a sleeve-fit result.
        for side in (-1, 1):
            rings = [(.37, .47, 30), (.55, .46, 28), (.78, .43, 24),
                     (1.00, .40, 20), (1.22, .37, 17)]
            vertices = []
            columns = 32
            for x, z, circumference_cm in rings:
                radius = circumference_cm / math.tau * UNIT_M_PER_CM
                for column in range(columns):
                    angle = math.tau * column / columns
                    vertices.append((side * x, radius * math.sin(angle),
                                     z + radius * math.cos(angle)))
            faces = []
            for row in range(len(rings) - 1):
                for column in range(columns):
                    right = (column + 1) % columns
                    a = row * columns + column
                    b = row * columns + right
                    faces.append((a, a + columns, b + columns, b))
            faces.append(tuple(range(columns)))
            faces.append(tuple(reversed(tuple(
                (len(rings) - 1) * columns + col
                for col in range(columns)))))
            if side < 0:
                faces = [tuple(reversed(face)) for face in faces]
            name = f"nominal arm proxy {side} (not a scan)"
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
            obj.hide_render = True
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_add(type="COLLISION")
            obj.collision.thickness_outer = .008
            obj.collision.cloth_friction = 6

panel_starts = place_three_panel_tops(hem_length / UNIT_M_PER_CM, widths)


def point_on_guide_row(row, fraction):
    points = guide_rows[row]
    distances = [0.0]
    for first, second in zip(points, points[1:]):
        distances.append(distances[-1] + (second - first).length)
    distance = max(0.0, min(distances[-1], fraction * distances[-1]))
    index = min(len(points) - 2, max(0, bisect.bisect_right(distances, distance) - 1))
    blend = (distance - distances[index]) / max(1e-9, distances[index + 1] - distances[index])
    return points[index].lerp(points[index + 1], blend)


def point_on_guide_surface(row_fraction, hem_fraction):
    lower = min(23, max(0, int(row_fraction)))
    blend = row_fraction - lower
    return point_on_guide_row(lower, hem_fraction).lerp(
        point_on_guide_row(lower + 1, hem_fraction), blend)


def point_on_authored_lower_surface(progress, hem_fraction):
    if authored_lower_rows is None:
        raise RuntimeError("Authored lower guide was not loaded")

    def row_point(row):
        points = authored_lower_rows[row]
        distances = [0.0]
        for first, second in zip(points, points[1:]):
            distances.append(distances[-1] + (second - first).length)
        distance = max(0.0, min(distances[-1], hem_fraction * distances[-1]))
        index = min(len(points) - 2, max(0, bisect.bisect_right(
            distances, distance) - 1))
        blend = ((distance - distances[index]) /
                 max(1e-9, distances[index + 1] - distances[index]))
        return points[index].lerp(points[index + 1], blend)

    row_fraction = progress * (len(authored_lower_rows) - 1)
    lower = min(len(authored_lower_rows) - 2, max(0, int(row_fraction)))
    return row_point(lower).lerp(row_point(lower + 1), row_fraction - lower)


def point_on_bodice_hem(distance_cm):
    distance = distance_cm * UNIT_M_PER_CM
    # Extrapolate past the end points instead of collapsing a front opening.
    if distance < 0:
        direction = (hem_row[1] - hem_row[0]).normalized()
        return hem_row[0] + direction * distance
    if distance > hem_length:
        direction = (hem_row[-1] - hem_row[-2]).normalized()
        return hem_row[-1] + direction * (distance - hem_length)
    index = min(len(hem_row) - 2, max(0, bisect.bisect_right(hem_distance, distance) - 1))
    first, second = hem_distance[index:index + 2]
    blend = (distance - first) / max(1e-9, second - first)
    return hem_row[index].lerp(hem_row[index + 1], blend)


def percentile(samples, fraction):
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


pattern_bodice_counts = {}
pattern_bodice_objects = {}
pattern_bodice_faces = {}
winding_corrections = {}
upper_anchor_counts = {}


def landmark_top_xy_cm(code, x_cm, host):
    """Nominal M-size collar/shoulder locations, never a wearer scan."""
    shoulder_half = data["body_cm"]["shoulder_width"] / 2 + 1.5
    neck_half = 7.0
    left = host["hem_stitch_left_cm"]
    right = left + host["hem_stitch_width_cm"]
    if code in {"A", "B"}:
        neck_x, shoulder_x = (point[0] for point in
                              host["shoulder_stitch_paths_cm"][0])
        knots = [(left, (0.0, -14.0)),
                 (neck_x, (neck_half, -2.0)),
                 (shoulder_x, (shoulder_half, 0.0)),
                 (right, (shoulder_half + 2.5, 0.0))]
        sign = -1 if code == "A" else 1
    else:
        left_shoulder = host["shoulder_stitch_paths_cm"][0][1][0]
        left_neck = host["shoulder_stitch_paths_cm"][0][0][0]
        right_neck = host["shoulder_stitch_paths_cm"][1][0][0]
        right_shoulder = host["shoulder_stitch_paths_cm"][1][1][0]
        knots = [(left, (shoulder_half + 2.5, 0.0)),
                 (left_shoulder, (shoulder_half, 0.0)),
                 (left_neck, (neck_half, 0.0)),
                 ((left + right) / 2, (0.0, 7.0)),
                 (right_neck, (-neck_half, 0.0)),
                 (right_shoulder, (-shoulder_half, 0.0)),
                 (right, (-shoulder_half - 2.5, 0.0))]
        sign = 1
    if x_cm <= knots[0][0]:
        return sign * knots[0][1][0], knots[0][1][1]
    for (x0, first), (x1, second) in zip(knots, knots[1:]):
        if x_cm <= x1:
            fraction = (x_cm - x0) / (x1 - x0)
            return (sign * (first[0] + (second[0] - first[0]) * fraction),
                    first[1] + (second[1] - first[1]) * fraction)
    return sign * knots[-1][1][0], knots[-1][1][1]


def upper_pin_indices(host):
    vertices = host["pattern_mesh"]["vertices_cm"]
    if upper_pin_mode == "fully-fixed-upper":
        return list(range(len(vertices)))
    if upper_pin_mode == "back-center-anchor-trial":
        if host["code"] != "C":
            return []
        mid_x = (host["hem_stitch_left_cm"] +
                 host["hem_stitch_width_cm"] / 2)
        return [index for index, (x, y) in enumerate(vertices)
                if abs(x - mid_x) <= 1.25 and y <= 3.0]
    if upper_pin_mode == "back-neck-band-trial":
        if host["code"] != "C":
            return []
        top_y = min(vertex[1] for vertex in vertices)
        return [index for index, vertex in enumerate(vertices)
                if vertex[1] <= top_y + 5.0 + 1e-6]
    top_y = min(vertex[1] for vertex in vertices)
    # This is a fixture, not a drafted collar/shoulder seam: it deliberately
    # frees the rest of the upper bodice to reveal whether the proxy constrains it.
    return [index for index, vertex in enumerate(vertices)
            if vertex[1] <= top_y + 5.0 + 1e-6]


if bodice_mode == "pattern-bodice":
    for host in data["bodice_hosts"]:
        code = host["code"]
        pattern = host["pattern_mesh"]
        left = host["hem_stitch_left_cm"]
        width = host["hem_stitch_width_cm"]
        height = host["hem_stitch_y_cm"]
        vertices = []
        for x_cm, y_cm in pattern["vertices_cm"]:
            across = ((x_cm - left) / width if bodice_placement_mode in
                      {"paper-developed-trial", "landmark-tapered-trial"} else
                      max(0.0, min(1.0, (x_cm - left) / width)))
            if code == "A":
                across = 1.0 - across
            hem_position_cm = panel_starts[code] + across * width
            if bodice_placement_mode in {"paper-developed-trial",
                                         "landmark-tapered-trial"}:
                base = point_on_bodice_hem(hem_position_cm)
                developed_height_cm = height - y_cm
                if dart_height_mode == "dart-taken-up-height-trial" and code in {"A", "B"}:
                    back_hem_y_cm = next(item["hem_stitch_y_cm"] for item in
                                         data["bodice_hosts"] if item["code"] == "C")
                    shift_cm = height - back_hem_y_cm
                    if not 0 < shift_cm < 10:
                        raise ValueError("Front/back hem-height difference is not a plausible dart intake")
                    underarm_span_cm = height - host["underarm_y_cm"]
                    takeup_fraction = min(1.0, max(0.0,
                                                   developed_height_cm / underarm_span_cm))
                    developed_height_cm -= shift_cm * takeup_fraction
                if bodice_placement_mode == "landmark-tapered-trial":
                    top_x, top_y = landmark_top_xy_cm(code, x_cm, host)
                    taper = max(0.0, min(1.0,
                                         developed_height_cm / height)) ** 1.5
                    base = Vector((base.x * (1 - taper) +
                                   top_x * UNIT_M_PER_CM * taper,
                                   base.y * (1 - taper) +
                                   top_y * UNIT_M_PER_CM * taper,
                                   base.z))
                vertices.append(tuple(base + Vector(
                    (0, 0, developed_height_cm * UNIT_M_PER_CM))))
            else:
                vertices.append(tuple(point_on_guide_surface(
                    max(0.0, min(24.0, y_cm / height * 24)),
                    hem_position_cm * UNIT_M_PER_CM / hem_length)))
        host_faces, host_flipped = outward_wound_faces(vertices, pattern["faces"])
        pattern_bodice_faces[code] = host_faces
        winding_corrections[f"upper_{code}"] = host_flipped
        mesh = bpy.data.meshes.new(f"pattern bodice {code} mesh")
        mesh.from_pydata(vertices, [], host_faces)
        mesh.update()
        mesh.materials.append(bpy.data.materials["01 charcoal woven outer shell"])
        uv = mesh.uv_layers.new(name="2D stitch coordinates")
        for polygon in mesh.polygons:
            polygon.use_smooth = True
            for loop_index in polygon.loop_indices:
                x_cm, y_cm = pattern["vertices_cm"][
                    mesh.loops[loop_index].vertex_index]
                uv.data[loop_index].uv = (x_cm / 40, y_cm / 40)
        obj = bpy.data.objects.new(f"2D-pattern-derived upper bodice {code}", mesh)
        scene.collection.objects.link(obj)
        pattern_bodice_objects[code] = obj
        solidify = obj.modifiers.new("prototype fabric thickness", "SOLIDIFY")
        solidify.thickness = .008
        solidify.offset = 0
        if join_mode != "independent":
            obj.hide_render = True
        pattern_bodice_counts[code] = len(vertices)
        upper_anchor_counts[code] = len(upper_pin_indices(host))


cases = []
cloth_objects = []


for panel in data["panels"]:
    code = panel["code"]
    top_width = panel["top_width_cm"]
    panel_height = panel["height_cm"]
    points = []
    for x_cm, down_cm in panel["vertices_cm"]:
        progress = down_cm / panel_height
        if join_mode in {"aligned-welded-shell", "authored-guided-welded-shell",
                         "fully-welded-shell"} or (join_mode == "sewn-shell" and
                                                  darted_hem_hosts):
            distance_cm = aligned_trapezoid_distance(
                (x_cm, down_cm), panel["stitch_outline_cm"], panel_starts[code])
            if join_mode == "authored-guided-welded-shell":
                base = point_on_authored_lower_surface(
                    progress, distance_cm / (hem_length / UNIT_M_PER_CM))
            else:
                base = point_on_bodice_hem(distance_cm)
        else:
            base = point_on_bodice_hem(panel_starts[code] + x_cm)
        radial = Vector((base.x, base.y, 0)).normalized()
        if join_mode == "authored-guided-welded-shell":
            points.append(tuple(base - Vector((0, 0, sewn_initial_gap_m))))
        else:
            points.append(tuple(base + radial * (radial_flare_m * progress)
                                - Vector((0, 0, down_cm * UNIT_M_PER_CM
                                          + (sewn_initial_gap_m if join_mode !=
                                             "independent" else 0)))))
    lower_faces, lower_flipped = outward_wound_faces(points, panel["faces"])
    winding_corrections[f"lower_{code}"] = lower_flipped
    if join_mode != "independent":
        host = next(item for item in data["bodice_hosts"] if item["code"] == code)
        host_mesh = host["pattern_mesh"]
        bodice_obj = pattern_bodice_objects[code]
        bodice_points = [tuple(vertex.co) for vertex in bodice_obj.data.vertices]
        offset = len(bodice_points)
        host_x = host_mesh.get("hem_sewn_positions_cm") or [
            host_mesh["vertices_cm"][index][0]
            for index in host_mesh["hem_indices"]]
        panel_x = [panel["vertices_cm"][index][0]
                   for index in panel["top_indices"]]
        seam_pairs = pair_seam_vertices(host_x, panel_x)
        spring_edges = [(host_mesh["hem_indices"][a],
                         offset + panel["top_indices"][len(panel_x) - 1 - b
                                                       if code == "A" else b])
                        for a, b in seam_pairs]
        faces = list(pattern_bodice_faces[code])
        faces += [tuple(offset + index for index in face)
                  for face in lower_faces]
        all_points = bodice_points + points
        pin_indices = upper_pin_indices(host)
        upper_face_count = len(pattern_bodice_faces[code])
    else:
        offset = 0
        spring_edges = []
        faces = lower_faces
        all_points = points
        pin_indices = panel["top_indices"]
        upper_face_count = 0
    mesh = bpy.data.meshes.new(f"pattern panel {code} mesh")
    mesh.from_pydata(all_points, spring_edges, faces)
    mesh.update()
    mesh.materials.append(bpy.data.materials["01 charcoal woven outer shell"])
    mesh.materials.append(bpy.data.materials["11 tonal coat-hem jacquard"])
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        if polygon.index >= upper_face_count:
            progress = sum(panel["vertices_cm"][index - offset][1]
                           for index in polygon.vertices) / len(polygon.vertices) / panel_height
            polygon.material_index = 1 if progress > .68 else 0
    obj = bpy.data.objects.new(f"2D-pattern-derived coat panel {code}", mesh)
    scene.collection.objects.link(obj)
    pin = obj.vertex_groups.new(name="fixed upper bodice proxy" if join_mode !=
                                "independent" else "real pattern top seam attachment proxy")
    pin.add(pin_indices, 1.0, "REPLACE")
    cloth = obj.modifiers.new("unmeasured fabric drape", "CLOTH")
    cloth.settings.quality = 10
    if fabric_profile == "structured-trial":
        # Unmeasured virtual sensitivity study only: this is not a calibrated
        # faux-leather/interfacing property or a recommended production fabric.
        cloth.settings.mass = .12
        cloth.settings.tension_stiffness = 70
        cloth.settings.compression_stiffness = 70
        cloth.settings.shear_stiffness = 50
        cloth.settings.bending_stiffness = 100
    else:
        cloth.settings.mass = .32
        cloth.settings.tension_stiffness = 40
        cloth.settings.compression_stiffness = 40
        cloth.settings.shear_stiffness = 25
        cloth.settings.bending_stiffness = 15
    cloth.settings.vertex_group_mass = pin.name
    cloth.settings.pin_stiffness = 20
    cloth.settings.use_sewing_springs = join_mode != "independent"
    if join_mode != "independent":
        cloth.settings.sewing_force_max = 20
    cloth.collision_settings.collision_quality = 5
    cloth.collision_settings.distance_min = .005
    cloth.collision_settings.use_self_collision = self_collision_mode == "self-collision"
    cloth.collision_settings.self_distance_min = .003
    cloth_objects.append((obj, cloth, panel, all_points, offset, spring_edges, faces))
    paper = panel["vertices_cm"]
    mapped = [Vector(point) for point in points]
    edge_ratios = []
    panel_face_edges = {(min(face[index], face[(index + 1) % len(face)]),
                         max(face[index], face[(index + 1) % len(face)]))
                        for face in panel["faces"] for index in range(len(face))}
    for a, b in panel_face_edges:
        paper_length = math.dist(paper[a], paper[b]) * UNIT_M_PER_CM
        if paper_length > 1e-8:
            edge_ratios.append((mapped[a] - mapped[b]).length / paper_length)
    top_points = [Vector(points[index]) for index in panel["top_indices"]]
    top_arc = sum((b - a).length for a, b in zip(top_points, top_points[1:]))
    cases.append({"code": code, "stitch_top_cm": round(top_width, 3),
                  "initial_3d_top_arc_cm": round(top_arc / UNIT_M_PER_CM, 3),
                  "initial_edge_length_ratio_p05": round(percentile(edge_ratios, .05), 3),
                  "initial_edge_length_ratio_p95": round(percentile(edge_ratios, .95), 3),
                  "mesh_vertices": len(points),
                  "bodice_to_panel_correspondences": len(spring_edges),
                  "bodice_to_panel_sewing_springs": (
                      0 if join_mode == "fully-welded-shell" else len(spring_edges)),
                  "physical_material_measured": False})

shell_trial = None
side_spring_paths = {}
dart_spring_paths = {}
waist_dart_spring_paths = {}
shoulder_spring_paths = {}
bodice_side_spring_paths = {}
sleeve_components = {}
side_initial_gap_report = {}
fully_welded_seam_edge_report = {}
shell_relaxation_report = {}
sewn_overlay_components = {}
overlay_seam_preflight = {}
if shell_joined:
    all_vertices, all_faces, all_springs, all_materials = [], [], [], []
    component_starts = {}
    for obj, cloth, panel, rest, offset, springs, faces in cloth_objects:
        start = len(all_vertices)
        component_starts[panel["code"]] = (start, offset, panel, rest, faces, springs)
        all_vertices.extend(rest)
        all_faces.extend(tuple(start + index for index in face) for face in faces)
        all_springs.extend((start + a, start + b) for a, b in springs)
        all_materials.extend(face.material_index for face in obj.data.polygons)
        obj.modifiers.remove(cloth)
        obj.hide_render = True

    def side_path(code, side):
        start, offset, panel, _rest, _faces, _springs = component_starts[code]
        # Boundary 1 is the right side from top to hem; boundary 3 is the
        # left side from hem to top on a trapezoid.
        indices = panel["boundary_paths"][1 if side == "right" else 3]
        if side == "left":
            indices = list(reversed(indices))
        distance = [0.0]
        paper = panel["vertices_cm"]
        for a, b in zip(indices, indices[1:]):
            distance.append(distance[-1] + math.dist(paper[a], paper[b]))
        return [start + offset + index for index in indices], distance

    for name, left_code, right_code in (("B-C", "B", "C"),
                                        ("C-A", "C", "A")):
        left_indices, left_arc = side_path(left_code, "right")
        right_indices, right_arc = side_path(right_code, "left")
        pairs = pair_seam_vertices(left_arc, right_arc)
        edges = [(left_indices[a], right_indices[b]) for a, b in pairs]
        all_springs.extend(edges)
        side_spring_paths[name] = edges

    for name, edges in side_spring_paths.items():
        gaps = [math.dist(all_vertices[a], all_vertices[b]) / UNIT_M_PER_CM
                for a, b in edges]
        side_initial_gap_report[name] = {
            "top_cm": round(gaps[0], 3),
            "middle_cm": round(gaps[len(gaps) // 2], 3),
            "hem_cm": round(gaps[-1], 3),
            "gap_p95_cm": round(percentile(gaps, .95), 3),
            "gap_max_cm": round(max(gaps), 3)}

    if dart_seam_mode == "sewn-bust-darts-trial":
        face_edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                      for face in all_faces for index in range(3)}
        for host in data["bodice_hosts"]:
            code = host["code"]
            if code == "C":
                continue
            start = component_starts[code][0]
            for ordinal, dart in enumerate(host["side_bust_darts"], start=1):
                leg_a = dart["leg_a_mesh_indices"]
                leg_b = list(reversed(dart["leg_b_mesh_indices"]))
                if len(leg_a) != len(leg_b) or len(leg_a) < 3:
                    raise ValueError("Bust dart legs need corresponding mesh vertices")
                springs = [(start + a, start + b)
                           for a, b in zip(leg_a[:-1], leg_b[:-1])]
                if any(a == b or tuple(sorted((a, b))) in face_edges
                       for a, b in springs):
                    raise ValueError("Bust dart sewing edge overlaps a cloth face")
                dart_spring_paths[f"{code}-{ordinal}"] = springs
                all_springs.extend(springs)

    if darted_hem_hosts:
        face_edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                      for face in all_faces for index in range(3)}
        for host in data["bodice_hosts"]:
            code = host["code"]
            start = component_starts[code][0]
            paper = host["pattern_mesh"]["vertices_cm"]
            for ordinal, dart in enumerate(host["hem_waist_darts"], start=1):
                first = dart["leg_a_mesh_indices"]
                second = list(reversed(dart["leg_b_mesh_indices"]))

                def arc(path):
                    distances = [0.0]
                    for a, b in zip(path, path[1:]):
                        distances.append(distances[-1] + math.dist(paper[a], paper[b]))
                    return distances

                pairs = pair_seam_vertices(arc(first), arc(second),
                                           max_length_mismatch_cm=.1)
                springs = [(start + first[a], start + second[b])
                           for a, b in pairs if first[a] != second[b]]
                if (not springs or len(set(tuple(sorted(edge)) for edge in springs))
                        != len(springs) or any(tuple(sorted(edge)) in face_edges
                                              for edge in springs)):
                    raise RuntimeError(f"Waist dart {code}-{ordinal} is not a sewable V")
                waist_dart_spring_paths[f"{code}-{ordinal}"] = springs
                all_springs.extend(springs)

    if shoulder_seam_mode == "sewn-shoulders-trial":
        hosts_by_code = {host["code"]: host for host in data["bodice_hosts"]}
        for code, back_index in (("A", 1), ("B", 0)):
            front = hosts_by_code[code]
            back = hosts_by_code["C"]
            front_path = front["shoulder_mesh_paths"][0]
            back_path = back["shoulder_mesh_paths"][back_index]

            def arc(host, path):
                paper = host["pattern_mesh"]["vertices_cm"]
                lengths = [0.0]
                for a, b in zip(path, path[1:]):
                    lengths.append(lengths[-1] + math.dist(paper[a], paper[b]))
                return lengths

            # The generated front/back shoulder stitch lines differ by about
            # 0.32 cm in the M trial.  Pairing is exploratory, not a passed
            # sewing-length check or a production seam allowance.
            pairs = pair_seam_vertices(arc(front, front_path),
                                       arc(back, back_path),
                                       max_length_mismatch_cm=.5)
            front_start = component_starts[code][0]
            back_start = component_starts["C"][0]
            springs = [(front_start + front_path[a],
                        back_start + back_path[b]) for a, b in pairs]
            if any(a == b for a, b in springs):
                raise ValueError("Shoulder sewing has duplicate mesh vertices")
            require_initial_sewing_clearance(all_vertices, springs,
                                             unit_m_per_cm=UNIT_M_PER_CM,
                                             max_gap_cm=(40.0 if upper_pin_mode in
                                                         {"back-center-anchor-trial",
                                                          "back-neck-band-trial"}
                                                         else 10.0))
            shoulder_spring_paths[code] = springs
            all_springs.extend(springs)

    if bodice_side_mode == "sewn-bodice-sides-trial":
        hosts_by_code = {host["code"]: host for host in data["bodice_hosts"]}

        def effective_side_path(host):
            paper = host["pattern_mesh"]["vertices_cm"]
            indices, lengths = [], []
            distance_cm = 0.0
            for segment in host["side_mesh_paths"]:
                for index_in_segment, vertex_index in enumerate(segment):
                    if index_in_segment:
                        distance_cm += math.dist(
                            paper[segment[index_in_segment - 1]],
                            paper[vertex_index])
                    indices.append(vertex_index)
                    lengths.append(distance_cm)
            return indices, lengths

        for code, back_index in (("A", 1), ("B", 0)):
            front = hosts_by_code[code]
            back = hosts_by_code["C"]
            front_indices, front_distance = effective_side_path(front)
            back_host = {**back, "side_mesh_paths": [
                back["side_mesh_paths"][back_index]]}
            back_indices, back_distance = effective_side_path(back_host)
            # The two paper side seams differ by ~0.33 cm in the M trial.
            # This pairing is experimental ease, not a passed production seam.
            pairs = pair_seam_vertices(front_distance, back_distance,
                                       max_length_mismatch_cm=.5)
            front_start = component_starts[code][0]
            back_start = component_starts["C"][0]
            springs = [(front_start + front_indices[a],
                        back_start + back_indices[b]) for a, b in pairs]
            require_initial_sewing_clearance(all_vertices, springs,
                                             unit_m_per_cm=UNIT_M_PER_CM,
                                             max_gap_cm=40.0)
            bodice_side_spring_paths[code] = springs
            all_springs.extend(springs)

    if topology_welded:
        weld_pairs = [edge for edges in side_spring_paths.values()
                      for edge in edges]
        if join_mode == "fully-welded-shell":
            weld_pairs.extend((start + a, start + b)
                              for start, _offset, _panel, _rest, _faces, springs
                              in component_starts.values() for a, b in springs)
        all_vertices, all_faces, all_springs, index_map = weld_seam_vertices(
            all_vertices, all_faces, all_springs,
            weld_pairs)
    else:
        index_map = list(range(len(all_vertices)))

    if join_mode == "fully-welded-shell":
        edge_face_counts = {}
        for face in all_faces:
            for a, b in zip(face, face[1:] + face[:1]):
                key = tuple(sorted((a, b)))
                edge_face_counts[key] = edge_face_counts.get(key, 0) + 1
        seam_paths = {}
        for code, (start, offset, panel, _rest, _faces, _springs) in (
                component_starts.items()):
            seam_paths[f"upper-lower {code}"] = [
                index_map[start + offset + index]
                for index in panel["top_indices"]]
        for name, left_code, right_code in (("side B-C", "B", "C"),
                                            ("side C-A", "C", "A")):
            left_indices, _left_arc = side_path(left_code, "right")
            right_indices, _right_arc = side_path(right_code, "left")
            seam_paths[name] = [index_map[index] for index in left_indices]
            if seam_paths[name] != [index_map[index] for index in right_indices]:
                raise RuntimeError(f"{name} did not weld corresponding vertices")
        for name, path in seam_paths.items():
            counts = [edge_face_counts.get(tuple(sorted((a, b))), 0)
                      for a, b in zip(path, path[1:])]
            fully_welded_seam_edge_report[name] = {
                "edges_checked": len(counts),
                "two_face_edges": sum(count == 2 for count in counts),
                "face_count_values": sorted(set(counts)),
                "all_two_faces": bool(counts) and all(count == 2 for count in counts),
            }
        if not all(item["all_two_faces"] for item in
                   fully_welded_seam_edge_report.values()):
            print("WELDED_SEAM_EDGE_REPORT", fully_welded_seam_edge_report,
                  flush=True)
            raise RuntimeError("A welded seam contains a boundary or non-manifold edge")

    if shell_placement_mode == "paper-edge-relaxed-shell":
        pinned_shell = sorted({index_map[start + index]
                               for start, offset, _panel, _rest, _faces, _springs
                               in component_starts.values() for index in range(offset)})
        paper_edges = {}
        for code, (start, offset, panel, _rest, _faces, _springs) in (
                component_starts.items()):
            for face in panel["faces"]:
                for a, b in zip(face, face[1:] + face[:1]):
                    key = tuple(sorted((index_map[start + offset + a],
                                        index_map[start + offset + b])))
                    target = math.dist(panel["vertices_cm"][a],
                                       panel["vertices_cm"][b]) * UNIT_M_PER_CM
                    if key[0] == key[1] or (key in paper_edges and
                                           abs(paper_edges[key] - target) > 1e-5):
                        raise RuntimeError("Welded shell has conflicting paper edge lengths")
                    paper_edges[key] = target
        raw_vertices = all_vertices
        all_vertices = relax_connected_shell_to_paper_edges(
            raw_vertices, paper_edges, pinned_shell)
        inverted = 0
        for a, b, c in all_faces:
            raw_a, raw_b, raw_c = (Vector(raw_vertices[index])
                                   for index in (a, b, c))
            new_a, new_b, new_c = (Vector(all_vertices[index])
                                   for index in (a, b, c))
            raw_normal = (raw_b - raw_a).cross(raw_c - raw_a)
            new_normal = (new_b - new_a).cross(new_c - new_a)
            if raw_normal.length > 1e-9 and (
                    new_normal.length < raw_normal.length * .1 or
                    raw_normal.dot(new_normal) <= 0):
                inverted += 1
        shell_relaxation_report = {
            "paper_edges": len(paper_edges),
            "inverted_or_nearly_collapsed_faces": inverted,
            "movement_p95_cm": round(percentile([
                math.dist(before, after) / UNIT_M_PER_CM
                for before, after in zip(raw_vertices, all_vertices)], .95), 2),
            "not_a_cloth_or_body_clearance_validation": True,
        }
        if inverted:
            print("SHELL_RELAXATION_REPORT", shell_relaxation_report, flush=True)
            raise RuntimeError("Relaxed shell inverted or nearly collapsed faces")
        for code, (start, offset, panel, rest, faces, springs) in list(
                component_starts.items()):
            updated = [all_vertices[index_map[start + index]]
                       for index in range(len(rest))]
            component_starts[code] = (start, offset, panel, updated, faces, springs)
            case = next(item for item in cases if item["code"] == code)
            case["raw_initial_edge_length_ratio_p05"] = case[
                "initial_edge_length_ratio_p05"]
            case["raw_initial_edge_length_ratio_p95"] = case[
                "initial_edge_length_ratio_p95"]
            ratios = [(Vector(updated[offset + a]) -
                       Vector(updated[offset + b])).length /
                      (math.dist(panel["vertices_cm"][a],
                                 panel["vertices_cm"][b]) * UNIT_M_PER_CM)
                      for a, b in {tuple(sorted((face[i], face[(i + 1) % 3])))
                                   for face in panel["faces"] for i in range(3)}]
            case["initial_edge_length_ratio_p05"] = round(percentile(ratios, .05), 3)
            case["initial_edge_length_ratio_p95"] = round(percentile(ratios, .95), 3)
            case["relaxed_initial_p95_absolute_paper_edge_strain_percent"] = round(
                percentile([abs(ratio - 1) for ratio in ratios], .95) * 100, 2)

    if overlay_mode == "with-sewn-overlays":
        # A loose edge has no cloth face.  Blender's sewing springs can pull
        # each overlay-top vertex toward its corresponding welded bodice/lower
        # seam vertex in *the same cloth solve*.  Keep the overlay vertices
        # distinct: welding them would create a non-manifold three-face edge.
        for overlay in data["overlays"]:
            code = overlay["code"]
            start, base_offset, base_panel, _rest, _faces, _springs = (
                component_starts[code])
            base_top = base_panel["top_indices"]
            top = overlay["top_indices"]
            if len(base_top) != len(top):
                raise ValueError(f"Overlay {code} top mesh is not aligned")
            base_surface = [tuple(all_vertices[index_map[
                start + base_offset + index]])
                for index in range(len(base_panel["vertices_cm"]))]
            points = []
            support_points = []
            support_normals = []
            for x_cm, down_cm in overlay["vertices_cm"]:
                surface = interpolate_pattern_surface_with_normal(
                    (x_cm, down_cm), base_panel["vertices_cm"],
                    base_panel["faces"], base_surface)
                if surface is None:
                    raise RuntimeError(f"Overlay {code} falls outside its lower panel")
                base = Vector(surface[0])
                radial = Vector((base.x, base.y, 0)).normalized()
                normal = Vector(surface[1])
                if normal.dot(radial) < 0:
                    normal.negate()
                transition = min(1.0, max(0.0, down_cm / 8.0))
                normal = (radial * (1.0 - transition)
                          + normal * transition).normalized()
                points.append(tuple(base + normal * (.018 + .004 * transition)))
                support_points.append(tuple(base))
                support_normals.append(tuple(normal))
            for overlay_index, base_index in zip(top, base_top):
                base = Vector(base_surface[base_index])
                radial = Vector((base.x, base.y, 0)).normalized()
                points[overlay_index] = tuple(base + radial * .018)
                support_points[overlay_index] = tuple(base)
                support_normals[overlay_index] = tuple(radial)
            points = relax_overlay_to_paper_edges(
                points, overlay["vertices_cm"], overlay["faces"], top,
                support_points, support_normals, unit_m_per_cm=UNIT_M_PER_CM)
            faces, flipped = outward_wound_faces(points, overlay["faces"])
            winding_corrections[f"overlay_{code}"] = flipped
            overlay_start = len(all_vertices)
            all_vertices.extend(points)
            all_faces.extend(tuple(overlay_start + index for index in face)
                             for face in faces)
            all_materials.extend([2] * len(faces))
            springs = [(index_map[start + base_offset + base_index],
                        overlay_start + overlay_index)
                       for overlay_index, base_index in zip(top, base_top)]
            all_springs.extend(springs)
            sewn_overlay_components[code] = (overlay_start, overlay, points,
                                             springs)
        if sorted(sewn_overlay_components) != ["A", "B", "C"]:
            raise RuntimeError("Shared-cloth sewing requires all three overlays")
        face_edge_counts = {}
        for face in all_faces:
            for a, b in zip(face, face[1:] + face[:1]):
                edge = tuple(sorted((a, b)))
                face_edge_counts[edge] = face_edge_counts.get(edge, 0) + 1
        for code, (_start, _overlay, _points, springs) in (
                sewn_overlay_components.items()):
            loose = [face_edge_counts.get(tuple(sorted(edge)), 0)
                     for edge in springs]
            if len(set(tuple(sorted(edge)) for edge in springs)) != len(springs):
                raise RuntimeError(f"Overlay {code} has duplicate sewing springs")
            if not loose or any(count != 0 for count in loose):
                raise RuntimeError(f"Overlay {code} sewing spring is a cloth face edge")
            gaps = [math.dist(all_vertices[a], all_vertices[b]) / UNIT_M_PER_CM
                    for a, b in springs]
            overlay_seam_preflight[code] = {
                "loose_springs": len(springs),
                "all_springs_without_faces": True,
                "initial_gap_p95_cm": round(percentile(gaps, .95), 3),
            }

    if sleeve_mode == "pattern-sewn-sleeves-trial":
        hosts_by_code = {host["code"]: host for host in data["bodice_hosts"]}
        notch_audit = data.get("sleeve_join_audit", {})
        if cap_ease_mode == "notch-anchored" and not notch_audit.get(
                "notch_pairing_verified_on_2d_stitch_lines"):
            raise ValueError("Notch-anchored ease needs verified 2D notch pairing")

        def armhole_path(code, path_index, *, underarm_first):
            host = hosts_by_code[code]
            path = list(host["armhole_mesh_paths"][path_index])
            paper = host["pattern_mesh"]["vertices_cm"]
            first_is_underarm = paper[path[0]][1] > paper[path[-1]][1]
            if first_is_underarm != underarm_first:
                path.reverse()
            start = component_starts[code][0]
            return ([Vector(all_vertices[index_map[start + index]])
                     for index in path],
                    [paper[index] for index in path],
                    [index_map[start + index] for index in path])

        def sampled_path(positions, paper, fraction):
            distances = [0.0]
            for first, second in zip(paper, paper[1:]):
                distances.append(distances[-1] + math.dist(first, second))
            target = max(0.0, min(1.0, fraction)) * distances[-1]
            index = min(len(distances) - 2,
                        max(0, bisect.bisect_right(distances, target) - 1))
            amount = ((target - distances[index]) /
                      max(1e-8, distances[index + 1] - distances[index]))
            return positions[index].lerp(positions[index + 1], amount)

        def path_arcs(paper):
            values = [0.0]
            for first, second in zip(paper, paper[1:]):
                values.append(values[-1] + math.dist(first, second))
            return values

        for sleeve in data["sleeves"]:
            code, back_index, sign = (("A", 1, -1) if sleeve["side"] == "左"
                                      else ("B", 0, 1))
            if cap_ease_mode == "notch-anchored":
                body_marks = notch_audit[
                    "bodice_notch_distances_from_underarm_cm_by_host"]
                front_notch_distance = body_marks[code][0][0]
                back_notch_distance = max(body_marks["C"][back_index])
            else:
                front_notch_distance = back_notch_distance = None
            mesh = sleeve["pattern_mesh"]
            paper = mesh["vertices_cm"]
            cap_indices = sleeve["cap_mesh_indices"]
            cap_paper = [paper[index] for index in cap_indices]
            geometric_apex = min(range(len(cap_paper)),
                                 key=lambda index: cap_paper[index][1])
            if not 2 <= geometric_apex <= len(cap_paper) - 3 or any(
                    a[0] >= b[0] for a, b in zip(cap_paper, cap_paper[1:])):
                raise ValueError("Sleeve cap needs a monotone left-to-right apex")
            front_positions, front_paper, front_host_indices = armhole_path(
                code, 0, underarm_first=True)
            back_positions, back_paper, back_host_indices = armhole_path(
                "C", back_index, underarm_first=False)
            shoulder_middle = (front_positions[-1] + back_positions[0]) / 2
            cap_arc = path_arcs(cap_paper)
            front_host_arc = path_arcs(front_paper)
            back_host_arc = path_arcs(back_paper)
            apex = choose_sleeve_shoulder_station(
                cap_paper, front_host_arc[-1], back_host_arc[-1],
                front_notch_cm=front_notch_distance,
                back_notch_cm=back_notch_distance)
            back_cap_arc = [length - cap_arc[apex] for length in cap_arc[apex:]]
            if cap_ease_mode == "uniform":
                front_eased_arc = [length / cap_arc[apex] * front_host_arc[-1]
                                   for length in cap_arc[:apex + 1]]
                back_eased_arc = [length / back_cap_arc[-1] * back_host_arc[-1]
                                  for length in back_cap_arc]
            else:
                front_eased_arc = distribute_sleeve_cap_ease(
                    cap_arc[:apex + 1], front_host_arc[-1],
                    crown_at_start=False,
                    no_ease_from_underarm_cm=front_notch_distance)
                back_eased_arc = distribute_sleeve_cap_ease(
                    back_cap_arc, back_host_arc[-1], crown_at_start=True,
                    no_ease_from_underarm_cm=back_notch_distance)
            cap_targets = []
            for ordinal in range(len(cap_paper)):
                if ordinal <= apex:
                    fraction = front_eased_arc[ordinal] / front_host_arc[-1]
                    base = sampled_path(front_positions, front_paper, fraction)
                    base += fraction * (shoulder_middle - front_positions[-1])
                else:
                    fraction = back_eased_arc[ordinal - apex] / back_host_arc[-1]
                    base = sampled_path(back_positions, back_paper, fraction)
                    base += (1 - fraction) * (
                        shoulder_middle - back_positions[0])
                cap_targets.append(base + Vector((sign * .008, 0, 0)))

            def cap_cross_section(x_cm):
                positions_x = [point[0] for point in cap_paper]
                index = min(len(positions_x) - 2,
                            max(0, bisect.bisect_right(positions_x, x_cm) - 1))
                fraction = ((x_cm - positions_x[index]) /
                            (positions_x[index + 1] - positions_x[index]))
                y_cm = (cap_paper[index][1] * (1 - fraction) +
                        cap_paper[index + 1][1] * fraction)
                return cap_targets[index].lerp(cap_targets[index + 1], fraction), y_cm

            def nearest_cap_projection(x_cm, y_cm):
                best = None
                for index, (first, second) in enumerate(zip(cap_paper, cap_paper[1:])):
                    dx, dy = second[0] - first[0], second[1] - first[1]
                    fraction = max(0.0, min(1.0,
                        ((x_cm - first[0]) * dx + (y_cm - first[1]) * dy) /
                        max(1e-9, dx * dx + dy * dy)))
                    px, py = first[0] + fraction * dx, first[1] + fraction * dy
                    distance = math.hypot(x_cm - px, y_cm - py)
                    if best is None or distance < best[0]:
                        tangent = cap_targets[index + 1] - cap_targets[index]
                        tangent.normalize()
                        best = (distance, cap_targets[index].lerp(
                            cap_targets[index + 1], fraction), tangent)
                return best

            placed = []
            for x_cm, y_cm in paper:
                edge, cap_y = cap_cross_section(x_cm)
                extension = max(0.0, y_cm - cap_y) * UNIT_M_PER_CM
                column_guide = edge + Vector((sign * extension, 0, 0))
                distance_cm, nearest_edge, tangent = nearest_cap_projection(
                    x_cm, y_cm)
                paper_normal_world = Vector((sign, 0, 0))
                paper_normal_world -= tangent * paper_normal_world.dot(tangent)
                if paper_normal_world.length < 1e-5:
                    paper_normal_world = Vector((0, 0, -1))
                    paper_normal_world -= tangent * paper_normal_world.dot(tangent)
                paper_normal_world.normalize()
                nearest_guide = (nearest_edge + paper_normal_world *
                                 (distance_cm * UNIT_M_PER_CM))
                # Close to the curved cap, paper-normal distance is less
                # distorted than extrusion from an equal-x cap point. Fade
                # the correction out before the long straight sleeve tube.
                blend = math.exp(-distance_cm / 9.0)
                placed.append(tuple(column_guide.lerp(nearest_guide, blend)))
            for index, target in zip(cap_indices, cap_targets):
                placed[index] = tuple(target)
            raw_placed = list(placed)
            sleeve_paper_edges = {}
            for face in mesh["faces"]:
                for a, b in zip(face, face[1:] + face[:1]):
                    key = tuple(sorted((a, b)))
                    sleeve_paper_edges[key] = (
                        math.dist(paper[a], paper[b]) * UNIT_M_PER_CM)
            placed = relax_connected_shell_to_paper_edges(
                placed, sleeve_paper_edges, cap_indices,
                iterations=100, guide_pull=.01,
                max_guide_distance_m=.05)
            def inverted_face_indices(points):
                inverted_faces = []
                for face_index, (a, b, c) in enumerate(mesh["faces"]):
                    raw_a, raw_b, raw_c = (Vector(raw_placed[index])
                                           for index in (a, b, c))
                    new_a, new_b, new_c = (Vector(points[index])
                                           for index in (a, b, c))
                    raw_normal = (raw_b - raw_a).cross(raw_c - raw_a)
                    new_normal = (new_b - new_a).cross(new_c - new_a)
                    if raw_normal.length > 1e-9 and (
                            new_normal.length < raw_normal.length * .1 or
                            raw_normal.dot(new_normal) <= 0):
                        inverted_faces.append(face_index)
                return inverted_faces

            inverted_faces = inverted_face_indices(placed)
            relaxation_backtrack_factor = 1.0
            if 0 < len(inverted_faces) <= 4:
                # A local optimizer can overstep a single face even when the
                # initial placement is valid. Keep the cap fixed and accept
                # only a positive-area intermediate between the raw and
                # relaxed positions; never silently accept a folded triangle.
                fully_relaxed = placed
                for factor in (.8, .6, .4, .2):
                    candidate = [tuple(Vector(raw).lerp(Vector(relaxed), factor))
                                 for raw, relaxed in zip(raw_placed,
                                                         fully_relaxed)]
                    if not inverted_face_indices(candidate):
                        placed = candidate
                        inverted_faces = []
                        relaxation_backtrack_factor = factor
                        break
            if inverted_faces:
                raw_ratios = [abs(math.dist(raw_placed[a], raw_placed[b]) /
                                  target - 1) for (a, b), target in
                              sleeve_paper_edges.items()]
                rejection = {
                    "status": "rejected before cloth simulation",
                    "side": sleeve["side"],
                    "source_pattern_json": str(panel_file),
                    "input_fingerprints": input_fingerprints,
                    "bodice_placement_mode": bodice_placement_mode,
                    "guide_hem_geometry": guide_mode,
                    "inverted_face_count": len(inverted_faces),
                    "raw_p95_absolute_paper_edge_strain_percent": round(
                        percentile(raw_ratios, .95) * 100, 2),
                    "inverted_faces": [
                        {"face_index": face_index,
                         "vertex_indices": mesh["faces"][face_index],
                         "paper_cm": [paper[index] for index in
                                      mesh["faces"][face_index]],
                         "raw_position_m": [raw_placed[index] for index in
                                            mesh["faces"][face_index]],
                         "relaxed_position_m": [placed[index] for index in
                                                mesh["faces"][face_index]]}
                        for face_index in inverted_faces[:12]],
                    "not_a_completed_drape": True,
                }
                (output / "sleeve_rejection_report.json").write_text(
                    json.dumps(rejection, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                print("SLEEVE_RELAXATION_REJECTED", sleeve["side"],
                      "inverted", len(inverted_faces), "raw_p95_percent",
                      round(percentile(raw_ratios, .95) * 100, 2), flush=True)
                raise RuntimeError(
                    f"Sleeve {sleeve['side']} initial edge relaxation "
                    f"inverted {len(inverted_faces)} faces")
            faces, flipped = outward_wound_faces(placed, mesh["faces"])
            winding_corrections[f"sleeve_{sleeve['side']}"] = flipped
            sleeve_start = len(all_vertices)
            all_vertices.extend(placed)
            all_faces.extend(tuple(sleeve_start + index for index in face)
                             for face in faces)
            all_materials.extend([0] * len(faces))

            def stitch_cap(cap_part, host_indices, host_paper, *,
                           crown_at_start, notch_distance):
                cap_part_paper = [paper[index] for index in cap_part]
                cap_dist = path_arcs(cap_part_paper)
                host_dist = path_arcs(host_paper)
                if cap_ease_mode != "uniform":
                    mapped_cap_dist = distribute_sleeve_cap_ease(
                        cap_dist, host_dist[-1], crown_at_start=crown_at_start,
                        no_ease_from_underarm_cm=notch_distance)
                    matches = pair_seam_vertices(mapped_cap_dist, host_dist,
                                                 max_length_mismatch_cm=.05)
                else:
                    matches = pair_seam_vertices(cap_dist, host_dist,
                                                 max_length_mismatch_cm=1.5)
                return [(sleeve_start + cap_part[a], host_indices[b])
                        for a, b in matches]

            front_springs = stitch_cap(cap_indices[:apex + 1],
                                       front_host_indices, front_paper,
                                       crown_at_start=False,
                                       notch_distance=front_notch_distance)
            back_springs = stitch_cap(cap_indices[apex:],
                                      back_host_indices, back_paper,
                                      crown_at_start=True,
                                      notch_distance=back_notch_distance)
            side_paths = sleeve["tube_side_mesh_paths"]
            left_paper = [paper[index] for index in side_paths[0]]
            right_paper = [paper[index] for index in side_paths[1]]
            side_pairs = pair_seam_vertices(path_arcs(left_paper),
                                            path_arcs(right_paper))
            tube_springs = [(sleeve_start + side_paths[0][a],
                             sleeve_start + side_paths[1][b])
                            for a, b in side_pairs]
            all_springs.extend(front_springs + back_springs + tube_springs)
            sleeve_components[sleeve["side"]] = {
                "start": sleeve_start, "pattern": mesh,
                "cap_mesh_indices": cap_indices,
                "cap_and_armhole_lengths_cm": {
                    "paper_cap": round(cap_arc[-1], 3),
                    "placed_cap": round(sum((a - b).length for a, b in
                        zip(cap_targets, cap_targets[1:])) / UNIT_M_PER_CM, 3),
                    "paper_front_armhole": round(front_host_arc[-1], 3),
                    "placed_front_armhole": round(sum((a - b).length for a, b in
                        zip(front_positions, front_positions[1:])) /
                        UNIT_M_PER_CM, 3),
                    "paper_back_armhole": round(back_host_arc[-1], 3),
                    "placed_back_armhole": round(sum((a - b).length for a, b in
                        zip(back_positions, back_positions[1:])) /
                        UNIT_M_PER_CM, 3),
                },
                "front_cap_springs": front_springs,
                "back_cap_springs": back_springs,
                "tube_springs": tube_springs,
                "front_host_paper": front_paper,
                "front_host_initial": [tuple(point) for point in front_positions],
                "back_host_paper": back_paper,
                "back_host_initial": [tuple(point) for point in back_positions],
                "initial": placed,
                "raw_initial": raw_placed,
                "relaxation_backtrack_factor": relaxation_backtrack_factor,
                "cap_ease_cm": round(cap_arc[-1] -
                                     path_arcs(front_paper)[-1] -
                                     path_arcs(back_paper)[-1], 3),
                "cap_ease_distribution": cap_ease_mode,
                "geometric_apex_index": geometric_apex,
                "shoulder_station_index": apex,
                "shoulder_station_offset_cm": round(
                    cap_arc[apex] - cap_arc[geometric_apex], 3),
            }

        if run_mode == "sleeve-preflight-only":
            preflight = {}
            for side, sleeve in sleeve_components.items():
                paper = sleeve["pattern"]["vertices_cm"]
                placed = sleeve["initial"]
                edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                         for face in sleeve["pattern"]["faces"]
                         for index in range(3)}
                deviations = sorted((
                    abs(math.dist(placed[a], placed[b]) /
                        (math.dist(paper[a], paper[b]) * UNIT_M_PER_CM) - 1),
                    a, b) for a, b in edges)
                cap_set = set(sleeve["cap_mesh_indices"])
                cap_edge_errors = sorted((
                    math.dist(placed[a], placed[b]) /
                    (math.dist(paper[a], paper[b]) * UNIT_M_PER_CM) - 1,
                    a, b) for a, b in zip(sleeve["cap_mesh_indices"],
                                          sleeve["cap_mesh_indices"][1:]))
                host_local_ratios = {}
                for name in ("front", "back"):
                    points = sleeve[f"{name}_host_paper"]
                    positions = sleeve[f"{name}_host_initial"]
                    host_local_ratios[name] = [
                        round(math.dist(a, b) / (
                            math.dist(p, q) * UNIT_M_PER_CM), 4)
                        for a, b, p, q in zip(positions, positions[1:],
                                              points, points[1:])]
                paper_width = max(point[0] for point in paper)
                edge_groups = {
                    "cap_boundary": [], "underarm_side": [],
                    "other": [],
                }
                for deviation, a, b in deviations:
                    if a in cap_set and b in cap_set:
                        group = "cap_boundary"
                    elif (max(paper[a][1], paper[b][1]) < 22 and
                          (max(paper[a][0], paper[b][0]) < 3 or
                           min(paper[a][0], paper[b][0]) > paper_width - 3)):
                        group = "underarm_side"
                    else:
                        group = "other"
                    edge_groups[group].append(deviation)
                preflight[side] = {
                    "cap_and_armhole_lengths_cm": sleeve[
                        "cap_and_armhole_lengths_cm"],
                    "shoulder_station_offset_cm": sleeve[
                        "shoulder_station_offset_cm"],
                    "relaxation_backtrack_factor": sleeve[
                        "relaxation_backtrack_factor"],
                    "raw_p95_absolute_paper_edge_strain_percent": round(
                        percentile([abs(math.dist(sleeve["raw_initial"][a],
                                                  sleeve["raw_initial"][b]) /
                                        (math.dist(paper[a], paper[b]) *
                                         UNIT_M_PER_CM) - 1)
                                    for a, b in edges], .95) * 100, 2),
                    "initial_p95_absolute_paper_edge_strain_percent": round(
                        percentile([item[0] for item in deviations], .95)
                        * 100, 2),
                    "cap_to_host_initial_gap_cm": {
                        "p95": round(percentile([
                            math.dist(placed[index], sleeve["raw_initial"][index])
                            / UNIT_M_PER_CM for index in
                            sleeve["cap_mesh_indices"]], .95), 2),
                        "max": round(max(math.dist(
                            placed[index], sleeve["raw_initial"][index]) /
                            UNIT_M_PER_CM for index in
                            sleeve["cap_mesh_indices"]), 2),
                    },
                    "edge_strain_regions": {
                        name: {
                            "count": len(values),
                            "p95_absolute_paper_edge_strain_percent": round(
                                percentile(values, .95) * 100, 2),
                            "max_absolute_paper_edge_strain_percent": round(
                                max(values, default=0) * 100, 2),
                        } for name, values in edge_groups.items()},
                    "cap_boundary_signed_strain_range_percent": [
                        round(cap_edge_errors[0][0] * 100, 2),
                        round(cap_edge_errors[-1][0] * 100, 2)],
                    "host_armhole_local_placed_to_paper_edge_ratios": host_local_ratios,
                    "initial_host_endpoint_positions_m": {
                        "front_underarm": sleeve["front_host_initial"][0],
                        "front_shoulder": sleeve["front_host_initial"][-1],
                        "back_shoulder": sleeve["back_host_initial"][0],
                        "back_underarm": sleeve["back_host_initial"][-1],
                    },
                    "front_cap_first_edge_placed_to_paper_ratios": [
                        round(math.dist(placed[a], placed[b]) / (
                            math.dist(paper[a], paper[b]) * UNIT_M_PER_CM), 4)
                        for a, b in zip(sleeve["cap_mesh_indices"][:7],
                                        sleeve["cap_mesh_indices"][1:8])],
                    "worst_cap_edges": [{
                        "paper_cm": [paper[a], paper[b]],
                        "signed_strain_percent": round(error * 100, 2)}
                        for error, a, b in sorted(cap_edge_errors,
                            key=lambda item: abs(item[0]))[-6:]],
                    "worst_edges": [{"paper_cm": [paper[a], paper[b]],
                                     "strain_percent": round(error * 100, 2)}
                                    for error, a, b in deviations[-12:]],
                    "not_a_cloth_or_wearer_fit_validation": True,
                }
            upper_preflight = {}
            for host in data["bodice_hosts"]:
                code = host["code"]
                _start, offset, _panel, initial_component, _faces, _springs = (
                    component_starts[code])
                points = initial_component[:offset]
                paper = host["pattern_mesh"]["vertices_cm"]
                edges = {tuple(sorted((a, b)))
                         for face in host["pattern_mesh"]["faces"]
                         for a, b in zip(face, face[1:] + face[:1])}
                edge_strains = [(
                    abs(math.dist(points[a], points[b]) /
                        (math.dist(paper[a], paper[b]) * UNIT_M_PER_CM) - 1),
                    a, b, math.dist(paper[a], paper[b]))
                    for a, b in edges]
                strain = [item[0] for item in edge_strains]
                long_strain = [item[0] for item in edge_strains if item[3] >= 1]
                upper_preflight[code] = {
                    "initial_p95_absolute_paper_edge_strain_percent": round(
                        percentile(strain, .95) * 100, 2),
                    "initial_max_absolute_paper_edge_strain_percent": round(
                        max(strain) * 100, 2),
                    "edges_at_least_1cm_p95_strain_percent": round(
                        percentile(long_strain, .95) * 100, 2),
                    "worst_edges": [{
                        "paper_cm": [paper[a], paper[b]],
                        "paper_length_cm": round(length, 3),
                        "absolute_strain_percent": round(error * 100, 2),
                    } for error, a, b, length in sorted(edge_strains)[-5:]],
                }
            preflight["_upper_bodice_initial_geometry"] = upper_preflight
            seam_gaps = {}
            for seam_name, seam_paths in (
                    ("shoulders", shoulder_spring_paths),
                    ("bodice_sides", bodice_side_spring_paths),
                    ("bust_darts", dart_spring_paths)):
                seam_gaps[seam_name] = {}
                for label, springs in seam_paths.items():
                    gaps = [math.dist(all_vertices[index_map[a]],
                                      all_vertices[index_map[b]]) /
                            UNIT_M_PER_CM for a, b in springs]
                    seam_gaps[seam_name][label] = {
                        "pairs": len(gaps),
                        "p95_cm": round(percentile(gaps, .95), 3),
                        "max_cm": round(max(gaps, default=0), 3),
                    }
            preflight["_unsewn_bodice_initial_gaps"] = seam_gaps
            preflight["_input_fingerprints"] = input_fingerprints
            preflight_path = output / "sleeve_initial_geometry_report.json"
            preflight_path.write_text(json.dumps(preflight, ensure_ascii=False,
                                                indent=2) + "\n", encoding="utf-8")
            print("SLEEVE_INITIAL_GEOMETRY_REPORT", preflight_path, flush=True)
            raise SystemExit(0)

    shell_mesh = bpy.data.meshes.new("pattern lower shell with sewn side seams")
    shell_mesh.from_pydata(all_vertices, all_springs, all_faces)
    shell_mesh.update()
    shell_mesh.materials.append(bpy.data.materials["01 charcoal woven outer shell"])
    shell_mesh.materials.append(bpy.data.materials["11 tonal coat-hem jacquard"])
    if sewn_overlay_components:
        shell_mesh.materials.append(bpy.data.materials["11 tonal coat-hem jacquard"])
    for polygon, index in zip(shell_mesh.polygons, all_materials):
        polygon.material_index = index
        polygon.use_smooth = True
    shell_obj = bpy.data.objects.new("2D-pattern-derived sewn lower shell", shell_mesh)
    scene.collection.objects.link(shell_obj)
    fixed = shell_obj.vertex_groups.new(name="provisionally fixed upper bodices")
    pinned = sorted({index_map[start + index]
                     for code, (start, _offset, _panel, _rest, _faces, _springs)
                     in component_starts.items()
                     for index in upper_pin_indices(next(
                         host for host in data["bodice_hosts"]
                         if host["code"] == code))})
    fixed.add(pinned, 1.0, "REPLACE")
    shell_cloth = shell_obj.modifiers.new("three-panel sewn shell trial", "CLOTH")
    shell_cloth.settings.quality = 10
    if fabric_profile == "structured-trial":
        shell_cloth.settings.mass = .12
        shell_cloth.settings.tension_stiffness = 70
        shell_cloth.settings.compression_stiffness = 70
        shell_cloth.settings.shear_stiffness = 50
        shell_cloth.settings.bending_stiffness = 100
    else:
        shell_cloth.settings.mass = .32
        shell_cloth.settings.tension_stiffness = 40
        shell_cloth.settings.compression_stiffness = 40
        shell_cloth.settings.shear_stiffness = 25
        shell_cloth.settings.bending_stiffness = 15
    shell_cloth.settings.vertex_group_mass = fixed.name
    shell_cloth.settings.pin_stiffness = 20
    shell_cloth.settings.use_sewing_springs = True
    shell_cloth.settings.sewing_force_max = 20
    shell_cloth.collision_settings.collision_quality = 5
    shell_cloth.collision_settings.distance_min = .005
    shell_cloth.collision_settings.use_self_collision = self_collision_mode == "self-collision"
    shell_cloth.collision_settings.self_distance_min = .003
    shell_trial = (shell_obj, shell_cloth, all_vertices, component_starts,
                   index_map)

scene.frame_end = frame_count
for frame in range(1, frame_count + 1):
    scene.frame_set(frame)
    if frame % 12 == 0 or frame == frame_count:
        print(f"PATTERN_PANEL_FRAME {frame}/{frame_count}", flush=True)

depsgraph = bpy.context.evaluated_depsgraph_get()
for obj, cloth, panel, rest, offset, spring_edges, faces in (
        [] if shell_trial else cloth_objects):
    evaluated = obj.evaluated_get(depsgraph)
    draped = evaluated.to_mesh()
    if len(draped.vertices) != len(rest):
        raise RuntimeError(f"Panel {panel['code']} changed topology")
    positions = [vertex.co.copy() for vertex in draped.vertices]
    if any(not all(math.isfinite(co) for co in position) for position in positions):
        raise RuntimeError(f"Panel {panel['code']} has non-finite cloth positions")
    case = next(item for item in cases if item["code"] == panel["code"])
    lower_positions = positions[offset:]
    lower_rest = rest[offset:]
    case["mean_displacement_cm"] = round(
        sum((point - Vector(initial)).length for point, initial in zip(
            lower_positions, lower_rest)) / len(lower_rest) / UNIT_M_PER_CM, 2)
    case["p95_displacement_cm"] = round(percentile(
        [(point - Vector(initial)).length for point, initial in zip(
            lower_positions, lower_rest)],
        .95) / UNIT_M_PER_CM, 2)
    if spring_edges:
        seam_gaps = [(positions[a] - positions[b]).length / UNIT_M_PER_CM
                     for a, b in spring_edges]
        case["sewn_seam_gap_p95_cm"] = round(percentile(seam_gaps, .95), 3)
        case["sewn_seam_gap_max_cm"] = round(max(seam_gaps), 3)
    paper = panel["vertices_cm"]
    final_edge_strain = []
    final_to_paper_ratios = []
    lower_face_edges = {(min(face[index], face[(index + 1) % len(face)]),
                         max(face[index], face[(index + 1) % len(face)]))
                        for face in faces if all(vertex >= offset for vertex in face)
                        for index in range(len(face))}
    for a, b in lower_face_edges:
        initial_length = (Vector(rest[a]) - Vector(rest[b])).length
        if initial_length > 1e-8:
            final_edge_strain.append(abs(
                (positions[a] - positions[b]).length / initial_length - 1))
        paper_length = math.dist(paper[a - offset], paper[b - offset]) * UNIT_M_PER_CM
        if paper_length > 1e-8:
            final_to_paper_ratios.append(
                (positions[a] - positions[b]).length / paper_length)
    case["p95_absolute_edge_strain_percent"] = round(
        percentile(final_edge_strain, .95) * 100, 2)
    case["final_to_paper_edge_ratio_p05"] = round(
        percentile(final_to_paper_ratios, .05), 3)
    case["final_to_paper_edge_ratio_p95"] = round(
        percentile(final_to_paper_ratios, .95), 3)
    case["final_p95_absolute_paper_edge_strain_percent"] = round(
        percentile([abs(ratio - 1) for ratio in final_to_paper_ratios], .95) * 100, 2)
    evaluated.to_mesh_clear()
    for vertex, position in zip(obj.data.vertices, positions):
        vertex.co = position
    obj.modifiers.remove(cloth)
    obj.data.update()
    for path_index, path in enumerate(panel["boundary_paths"][1:], start=1):
        curve = bpy.data.curves.new(f"panel {panel['code']} bound edge {path_index}", "CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = .004
        curve.bevel_resolution = 2
        spline = curve.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for point, index in zip(spline.points, path):
            point.co = (*positions[index + offset], 1)
        curve.materials.append(bpy.data.materials["07 matte black webbing"])
        scene.collection.objects.link(bpy.data.objects.new(curve.name, curve))
    solidify = obj.modifiers.new("visible cloth thickness only", "SOLIDIFY")
    solidify.thickness = .006
    solidify.offset = 0
    bevel = obj.modifiers.new("soft cut edge", "BEVEL")
    bevel.width = .002
    bevel.segments = 2

side_seam_report = {}
dart_seam_report = {}
waist_dart_seam_report = {}
shoulder_seam_report = {}
bodice_side_seam_report = {}
sleeve_drape_report = {}
overlay_trial_report = {}
body_contact_report = {}
sleeve_interface_report = {}
if shell_trial:
    shell_obj, shell_cloth, initial, components, index_map = shell_trial
    evaluated = shell_obj.evaluated_get(depsgraph)
    draped = evaluated.to_mesh()
    if len(draped.vertices) != len(initial):
        raise RuntimeError("Combined shell changed topology")
    final = [vertex.co.copy() for vertex in draped.vertices]
    evaluated.to_mesh_clear()
    if any(not all(math.isfinite(co) for co in point) for point in final):
        raise RuntimeError("Combined shell has non-finite cloth positions")
    if collision_mode in {"measurement-standin", "measurement-standin-with-sweater"}:
        proxy_objects = [obj for obj in scene.objects
                         if obj.type == "MESH" and "proxy" in obj.name
                         and "(not a scan)" in obj.name]
        expected_proxies = 5 if sleeve_components else 3
        if len(proxy_objects) != expected_proxies:
            raise RuntimeError("Measurement stand-in proxy count is incomplete")
        proxy_trees = [BVHTree.FromPolygons(
            [obj.matrix_world @ vertex.co for vertex in obj.data.vertices],
            [tuple(face.vertices) for face in obj.data.polygons])
            for obj in proxy_objects]
        torso_index = next((index for index, obj in enumerate(proxy_objects)
                            if "torso proxy" in obj.name), None)
        if torso_index is None:
            raise RuntimeError("Measurement stand-in torso proxy is missing")
        lower_indices = {index_map[start + offset + index]
                         for start, offset, panel, _rest, _faces, _springs
                         in components.values()
                         for index in range(len(panel["vertices_cm"]))}
        separations_cm = sorted(min(
            hit[3] for tree in proxy_trees
            if (hit := tree.find_nearest(shell_obj.matrix_world @ final[index]))
            is not None) / UNIT_M_PER_CM for index in lower_indices)
        upper_distances = {}
        for code, (start, offset, _panel, _rest, _faces, _springs) in components.items():
            indices = {index_map[start + index] for index in range(offset)}
            distances = sorted(
                hit[3] / UNIT_M_PER_CM for index in indices
                if (hit := proxy_trees[torso_index].find_nearest(
                    shell_obj.matrix_world @ final[index])) is not None)
            if len(distances) != len(indices):
                raise RuntimeError(f"Torso proxy distance failed for bodice {code}")
            upper_distances[code] = {
                "vertices_checked": len(distances),
                "minimum_surface_distance_cm": round(distances[0], 2),
                "p05_surface_distance_cm": round(percentile(distances, .05), 2),
                "median_surface_distance_cm": round(percentile(distances, .5), 2),
                "vertices_within_1cm": sum(value <= 1 for value in distances),
            }
        body_contact_report = {
            "surface_distance_is_unsigned": True,
            "lower_vertices_checked": len(separations_cm),
            "minimum_surface_distance_cm": round(separations_cm[0], 2),
            "p05_surface_distance_cm": round(percentile(separations_cm, .05), 2),
            "lower_vertices_within_1cm": sum(value <= 1 for value in separations_cm),
            "lower_shell_contact_observed": any(value <= 1 for value in separations_cm),
            "upper_bodice_to_torso_proxy": upper_distances,
            "not_a_wearer_scan_or_fit_validation": True,
        }
    if data.get("sleeves"):
        hosts_by_code = {host["code"]: host for host in data["bodice_hosts"]}

        def seam_endpoints(points, code, path_index):
            start = components[code][0]
            path = hosts_by_code[code]["armhole_mesh_paths"][path_index]
            paper = hosts_by_code[code]["pattern_mesh"]["vertices_cm"]
            first, last = path[0], path[-1]
            shoulder, underarm = ((first, last) if paper[first][1] < paper[last][1]
                                  else (last, first))
            return (points[index_map[start + shoulder]],
                    points[index_map[start + underarm]])

        def endpoint_gaps(points, front_code, back_index):
            front_shoulder, front_underarm = seam_endpoints(
                points, front_code, 0)
            back_shoulder, back_underarm = seam_endpoints(
                points, "C", back_index)
            return (math.dist(front_shoulder, back_shoulder) / UNIT_M_PER_CM,
                    math.dist(front_underarm, back_underarm) / UNIT_M_PER_CM)

        pairing = min(permutations((0, 1)), key=lambda pair: sum(
            sum(endpoint_gaps(initial, code, back_index))
            for code, back_index in zip(("A", "B"), pair)))
        sleeve_interface_report = {
            "front_to_back_armhole_pairing": {
                code: back_index for code, back_index in zip(("A", "B"), pairing)},
            "initial_endpoint_gaps_cm": {},
            "final_endpoint_gaps_cm": {},
            "upper_front_back_shoulder_and_underarm_seams_welded": False,
            "sleeves_sewn_to_bodice": bool(sleeve_components),
        }
        for code, back_index in zip(("A", "B"), pairing):
            for label, points in (("initial", initial), ("final", final)):
                shoulder_gap, underarm_gap = endpoint_gaps(
                    points, code, back_index)
                sleeve_interface_report[f"{label}_endpoint_gaps_cm"][code] = {
                    "shoulder": round(shoulder_gap, 3),
                    "underarm": round(underarm_gap, 3),
                }
    for side, sleeve in sleeve_components.items():
        start = sleeve["start"]
        mesh = sleeve["pattern"]
        count = len(mesh["vertices_cm"])
        positions = final[start:start + count]
        paper = mesh["vertices_cm"]
        edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                 for face in mesh["faces"] for index in range(3)}
        strain = [abs(math.dist(positions[a], positions[b]) /
                      (math.dist(paper[a], paper[b]) * UNIT_M_PER_CM) - 1)
                  for a, b in edges]

        def spring_gap(springs):
            gaps = [math.dist(final[a], final[b]) / UNIT_M_PER_CM
                    for a, b in springs]
            return {"springs": len(springs),
                    "gap_p95_cm": round(percentile(gaps, .95), 3),
                    "gap_max_cm": round(max(gaps), 3)}

        sleeve_drape_report[side] = {
            "vertices": count, "faces": len(mesh["faces"]),
            "paper_cap_ease_cm": sleeve["cap_ease_cm"],
            "shoulder_station_offset_cm": sleeve[
                "shoulder_station_offset_cm"],
            "initial_relaxation_backtrack_factor": sleeve[
                "relaxation_backtrack_factor"],
            "front_cap": spring_gap(sleeve["front_cap_springs"]),
            "back_cap": spring_gap(sleeve["back_cap_springs"]),
            "tube_side": spring_gap(sleeve["tube_springs"]),
            "initial_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(math.dist(sleeve["initial"][a],
                                          sleeve["initial"][b]) /
                                (math.dist(paper[a], paper[b]) * UNIT_M_PER_CM) - 1)
                            for a, b in edges], .95) * 100, 2),
            "p95_absolute_paper_edge_strain_percent": round(
                percentile(strain, .95) * 100, 2),
            "max_absolute_paper_edge_strain_percent": round(
                max(strain) * 100, 2),
            "not_a_fabric_or_arm_fit_validation": True,
            "topologically_welded_to_bodice": False,
        }
    for code, (start, offset, panel, rest, faces, springs) in components.items():
        positions = [final[index_map[start + index]]
                     for index in range(len(rest))]
        lower = positions[offset:]
        lower_rest = rest[offset:]
        case = next(item for item in cases if item["code"] == code)
        host = next(item for item in data["bodice_hosts"] if item["code"] == code)
        upper_pattern = host["pattern_mesh"]
        upper_edges = {(min(face[index], face[(index + 1) % len(face)]),
                        max(face[index], face[(index + 1) % len(face)]))
                       for face in upper_pattern["faces"]
                       for index in range(len(face))}
        upper_paper_strains = []
        upper_initial_strains = []
        upper_long_edge_strains = []
        upper_absolute_length_errors_cm = []
        upper_worst_edge = None
        for a, b in upper_edges:
            paper_length = math.dist(upper_pattern["vertices_cm"][a],
                                     upper_pattern["vertices_cm"][b]) * UNIT_M_PER_CM
            if paper_length <= 1e-8:
                continue
            final_length = (positions[a] - positions[b]).length
            initial_length = math.dist(rest[a], rest[b])
            paper_strain = abs(final_length / paper_length - 1)
            upper_paper_strains.append(paper_strain)
            upper_absolute_length_errors_cm.append(
                abs(final_length - paper_length) / UNIT_M_PER_CM)
            if paper_length >= 1.0 * UNIT_M_PER_CM:
                upper_long_edge_strains.append(paper_strain)
            if upper_worst_edge is None or paper_strain > upper_worst_edge[0]:
                upper_worst_edge = (paper_strain, a, b, paper_length,
                                    abs(final_length - paper_length))
            if initial_length > 1e-8:
                upper_initial_strains.append(abs(final_length / initial_length - 1))
        case["upper_final_p95_absolute_paper_edge_strain_percent"] = round(
            percentile(upper_paper_strains, .95) * 100, 2)
        case["upper_final_max_absolute_paper_edge_strain_percent"] = round(
            max(upper_paper_strains) * 100, 2)
        case["upper_final_max_absolute_edge_length_error_cm"] = round(
            max(upper_absolute_length_errors_cm), 3)
        case["upper_long_edges_at_least_1cm"] = len(upper_long_edge_strains)
        case["upper_long_edge_p95_absolute_paper_strain_percent"] = (
            round(percentile(upper_long_edge_strains, .95) * 100, 2)
            if upper_long_edge_strains else None)
        case["upper_worst_paper_edge_cm"] = [
            upper_pattern["vertices_cm"][upper_worst_edge[1]],
            upper_pattern["vertices_cm"][upper_worst_edge[2]],
        ]
        case["upper_worst_paper_edge_length_cm"] = round(
            upper_worst_edge[3] / UNIT_M_PER_CM, 3)
        case["upper_worst_paper_edge_length_error_cm"] = round(
            upper_worst_edge[4] / UNIT_M_PER_CM, 3)
        case["upper_simulation_p95_absolute_edge_strain_percent"] = round(
            percentile(upper_initial_strains, .95) * 100, 2)
        changes = [(point - Vector(initial_point)).length / UNIT_M_PER_CM
                   for point, initial_point in zip(lower, lower_rest)]
        case["mean_displacement_cm"] = round(sum(changes) / len(changes), 2)
        case["p95_displacement_cm"] = round(percentile(changes, .95), 2)
        seam_gaps = [(positions[a] - positions[b]).length / UNIT_M_PER_CM
                     for a, b in springs]
        case["sewn_seam_gap_p95_cm"] = round(percentile(seam_gaps, .95), 3)
        case["sewn_seam_gap_max_cm"] = round(max(seam_gaps), 3)
        lower_edges = {(min(face[index], face[(index + 1) % len(face)]),
                        max(face[index], face[(index + 1) % len(face)]))
                       for face in faces if all(vertex >= offset for vertex in face)
                       for index in range(len(face))}
        strains = []
        final_to_paper_ratios = []
        for a, b in lower_edges:
            original_length = math.dist(rest[a], rest[b])
            if original_length > 1e-8:
                strains.append(abs((positions[a] - positions[b]).length
                                   / original_length - 1))
            paper_length = math.dist(panel["vertices_cm"][a - offset],
                                     panel["vertices_cm"][b - offset]) * UNIT_M_PER_CM
            if paper_length > 1e-8:
                final_to_paper_ratios.append(
                    (positions[a] - positions[b]).length / paper_length)
        case["p95_absolute_edge_strain_percent"] = round(
            percentile(strains, .95) * 100, 2)
        case["final_to_paper_edge_ratio_p05"] = round(
            percentile(final_to_paper_ratios, .05), 3)
        case["final_to_paper_edge_ratio_p95"] = round(
            percentile(final_to_paper_ratios, .95), 3)
        case["final_p95_absolute_paper_edge_strain_percent"] = round(
            percentile([abs(ratio - 1) for ratio in final_to_paper_ratios], .95) * 100, 2)
        for path_index, path in enumerate(panel["boundary_paths"][1:], start=1):
            curve = bpy.data.curves.new(f"panel {code} bound edge {path_index}", "CURVE")
            curve.dimensions = "3D"
            curve.bevel_depth = .004
            curve.bevel_resolution = 2
            spline = curve.splines.new("POLY")
            spline.points.add(len(path) - 1)
            for point, index in zip(spline.points, path):
                point.co = (*positions[offset + index], 1)
            curve.materials.append(bpy.data.materials["07 matte black webbing"])
            scene.collection.objects.link(bpy.data.objects.new(curve.name, curve))
    for name, edges in side_spring_paths.items():
        gaps = [(final[index_map[a]] - final[index_map[b]]).length
                / UNIT_M_PER_CM for a, b in edges]
        side_seam_report[name] = {
            "springs": 0 if topology_welded else len(edges),
            "shared_vertices": len(edges) if topology_welded else 0,
            "gap_p95_cm": round(percentile(gaps, .95), 3),
            "gap_max_cm": round(max(gaps), 3)}
    for name, edges in dart_spring_paths.items():
        initial_gaps = [math.dist(initial[index_map[a]], initial[index_map[b]])
                        / UNIT_M_PER_CM for a, b in edges]
        final_gaps = [math.dist(final[index_map[a]], final[index_map[b]])
                      / UNIT_M_PER_CM for a, b in edges]
        dart_seam_report[name] = {
            "sewing_springs": len(edges),
            "initial_mouth_gap_cm": round(initial_gaps[0], 3),
            "final_mouth_gap_cm": round(final_gaps[0], 3),
            "final_gap_p95_cm": round(percentile(final_gaps, .95), 3),
            "not_a_finished_dart_pressing_or_stitch_quality_test": True,
        }
    for name, edges in waist_dart_spring_paths.items():
        initial_gaps = [math.dist(initial[index_map[a]], initial[index_map[b]])
                        / UNIT_M_PER_CM for a, b in edges]
        final_gaps = [math.dist(final[index_map[a]], final[index_map[b]])
                      / UNIT_M_PER_CM for a, b in edges]
        waist_dart_seam_report[name] = {
            "sewing_springs": len(edges),
            "initial_gap_p95_cm": round(percentile(initial_gaps, .95), 3),
            "final_gap_p95_cm": round(percentile(final_gaps, .95), 3),
            "final_gap_max_cm": round(max(final_gaps), 3),
            "not_a_finished_waist_dart_or_fit_validation": True,
        }
    for code, edges in shoulder_spring_paths.items():
        initial_gaps = [math.dist(initial[index_map[a]], initial[index_map[b]])
                        / UNIT_M_PER_CM for a, b in edges]
        final_gaps = [math.dist(final[index_map[a]], final[index_map[b]])
                      / UNIT_M_PER_CM for a, b in edges]
        shoulder_seam_report[code] = {
            "sewing_springs": len(edges),
            "initial_gap_p95_cm": round(percentile(initial_gaps, .95), 3),
            "final_gap_p95_cm": round(percentile(final_gaps, .95), 3),
            "final_gap_max_cm": round(max(final_gaps), 3),
            "topologically_welded": False,
        }
    for code, edges in bodice_side_spring_paths.items():
        initial_gaps = [math.dist(initial[index_map[a]], initial[index_map[b]])
                        / UNIT_M_PER_CM for a, b in edges]
        final_gaps = [math.dist(final[index_map[a]], final[index_map[b]])
                      / UNIT_M_PER_CM for a, b in edges]
        bodice_side_seam_report[code] = {
            "sewing_springs": len(edges),
            "initial_gap_p95_cm": round(percentile(initial_gaps, .95), 3),
            "final_gap_p95_cm": round(percentile(final_gaps, .95), 3),
            "final_gap_max_cm": round(max(final_gaps), 3),
            "topologically_welded": False,
        }
    for code, (start, overlay, rest, springs) in sewn_overlay_components.items():
        positions = final[start:start + len(rest)]
        edge_indices = {tuple(sorted((face[index], face[(index + 1) % 3])))
                        for face in overlay["faces"] for index in range(3)}
        ratios = [math.dist(positions[a], positions[b]) /
                  (math.dist(overlay["vertices_cm"][a],
                             overlay["vertices_cm"][b]) * UNIT_M_PER_CM)
                  for a, b in edge_indices]
        top = overlay["top_indices"]
        top_ratios = [math.dist(positions[a], positions[b]) /
                      (math.dist(overlay["vertices_cm"][a],
                                 overlay["vertices_cm"][b]) * UNIT_M_PER_CM)
                      for a, b in zip(top, top[1:])]
        gaps = [(final[a] - final[b]).length / UNIT_M_PER_CM
                for a, b in springs]
        overlay_trial_report[code] = {
            "vertices": len(rest),
            "shared_cloth_sewing_springs": len(springs),
            "topologically_welded": False,
            "seam_gap_p95_cm": round(percentile(gaps, .95), 3),
            "seam_gap_max_cm": round(max(gaps), 3),
            "final_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(value - 1) for value in ratios], .95) * 100, 2),
            "final_max_absolute_paper_edge_strain_percent": round(
                max(abs(value - 1) for value in ratios) * 100, 2),
            "final_top_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(value - 1) for value in top_ratios], .95) * 100, 2),
            "material_measured": False,
            "same_cloth_material_as_lower_shell": True,
        }
        for path_index, path in enumerate(overlay["boundary_paths"][1:], start=1):
            curve = bpy.data.curves.new(
                f"overlay {code} sewn bound edge {path_index}", "CURVE")
            curve.dimensions = "3D"
            curve.bevel_depth = .003
            curve.bevel_resolution = 2
            spline = curve.splines.new("POLY")
            spline.points.add(len(path) - 1)
            for point, index in zip(spline.points, path):
                point.co = (*positions[index], 1)
            curve.materials.append(bpy.data.materials["07 matte black webbing"])
            scene.collection.objects.link(bpy.data.objects.new(curve.name, curve))
    for vertex, position in zip(shell_obj.data.vertices, final):
        vertex.co = position
    shell_obj.modifiers.remove(shell_cloth)
    shell_obj.data.update()
    solidify = shell_obj.modifiers.new("visible cloth thickness only", "SOLIDIFY")
    solidify.thickness = .006
    solidify.offset = 0
    bevel = shell_obj.modifiers.new("soft cut edge", "BEVEL")
    bevel.width = .002
    bevel.segments = 2
    if overlay_mode not in {"no-overlays", "with-sewn-overlays"} and data.get("overlays"):
        # Second, separate cloth pass: overlays are sewn only at their upper
        # edge.  The structural lower shell is now a fixed collision surface.
        shell_collision_enabled = overlay_mode != "with-relaxed-overlays-no-shell"
        if shell_collision_enabled:
            bpy.ops.object.select_all(action="DESELECT")
            shell_obj.select_set(True)
            bpy.context.view_layer.objects.active = shell_obj
            bpy.ops.object.modifier_add(type="COLLISION")
            collision_modifier = next(
                modifier for modifier in shell_obj.modifiers
                if modifier.type == "COLLISION")
            # The later Solidify/Bevel modifiers only render fabric thickness.
            # Collision must see the sewn cloth surface, not both sides of a
            # thickened shell that can trap the just-offset overlay.
            shell_obj.modifiers.move(
                shell_obj.modifiers.find(collision_modifier.name), 0)
            shell_obj.collision.thickness_outer = .008
            shell_obj.collision.cloth_friction = 5
        overlay_objects = []
        overlay_initial_metrics = {}
        for overlay in data["overlays"]:
            code = overlay["code"]
            start, base_offset, base_panel, _rest, _faces, _springs = components[code]
            base_top = base_panel["top_indices"]
            top = overlay["top_indices"]
            if len(base_top) != len(top):
                raise ValueError(f"Overlay {code} top mesh is not aligned")
            points = []
            support_points = []
            support_normals = []
            mapped_inside = 0
            base_surface = [tuple(final[index_map[start + base_offset + index]])
                            for index in range(len(base_panel["vertices_cm"]))]
            for x_cm, down_cm in overlay["vertices_cm"]:
                surface = interpolate_pattern_surface_with_normal(
                    (x_cm, down_cm), base_panel["vertices_cm"],
                    base_panel["faces"], base_surface)
                if surface is not None:
                    base = Vector(surface[0])
                    mapped_inside += 1
                    radial = Vector((base.x, base.y, 0)).normalized()
                    normal = Vector(surface[1])
                    if normal.dot(radial) < 0:
                        normal.negate()
                    if overlay_mode in RELAXED_OVERLAY_MODES:
                        transition = min(1.0, max(0.0, down_cm / 8.0))
                        normal = (radial * (1.0 - transition)
                                  + normal * transition).normalized()
                        displacement = normal * (overlay_mount_clearance_cm
                                                 * UNIT_M_PER_CM + .004 * transition)
                    elif overlay_mode == "with-normal-overlays":
                        displacement = normal * .022
                    else:
                        displacement = radial * .045
                else:
                    base = (point_on_bodice_hem(panel_starts[code] + x_cm)
                            - Vector((0, 0, down_cm * UNIT_M_PER_CM)))
                    radial = Vector((base.x, base.y, 0)).normalized()
                    normal = radial
                    displacement = radial * .08
                points.append(tuple(base + displacement))
                support_points.append(tuple(base))
                support_normals.append(tuple(normal))
            for overlay_index, base_index in zip(top, base_top):
                base = final[index_map[start + base_offset + base_index]]
                radial = Vector((base.x, base.y, 0)).normalized()
                if overlay_mode in RELAXED_OVERLAY_MODES:
                    # Per-triangle normals jump across the sewn hem and can
                    # stretch a pinned 0.6 cm stitch segment by 15-40%.
                    # The hem is a smooth open curve; offset it consistently
                    # in the horizontal outward direction for this trial.
                    normal = radial
                    points[overlay_index] = tuple(
                        base + normal * overlay_mount_clearance_cm * UNIT_M_PER_CM)
                elif overlay_mode == "with-normal-overlays":
                    paper_point = base_panel["vertices_cm"][base_index]
                    surface = interpolate_pattern_surface_with_normal(
                        paper_point, base_panel["vertices_cm"],
                        base_panel["faces"], base_surface)
                    normal = Vector(surface[1]) if surface else radial
                    if normal.dot(radial) < 0:
                        normal.negate()
                    points[overlay_index] = tuple(base + normal * .022)
                else:
                    normal = radial
                    points[overlay_index] = tuple(base + radial * .025)
                support_points[overlay_index] = tuple(base)
                support_normals[overlay_index] = tuple(normal)
            overlay_edges = {(min(face[index], face[(index + 1) % 3]),
                              max(face[index], face[(index + 1) % 3]))
                             for face in overlay["faces"] for index in range(3)}

            def overlay_ratios(vertices):
                return [math.dist(vertices[a], vertices[b]) /
                        (math.dist(overlay["vertices_cm"][a],
                                   overlay["vertices_cm"][b]) * UNIT_M_PER_CM)
                        for a, b in overlay_edges]

            before_relax = overlay_ratios(points)
            guide_points = list(points)
            if overlay_mode in RELAXED_OVERLAY_MODES:
                points = relax_overlay_to_paper_edges(
                    points, overlay["vertices_cm"], overlay["faces"], top,
                    support_points, support_normals, unit_m_per_cm=UNIT_M_PER_CM,
                    min_gap_m=overlay_mount_clearance_cm * UNIT_M_PER_CM)
            overlay_faces, overlay_flipped = outward_wound_faces(
                points, overlay["faces"])
            overlay_edge_ratios = overlay_ratios(points)
            top_edges = [(a, b) for a, b in zip(top, top[1:])]
            top_ratios = [math.dist(points[a], points[b]) /
                          (math.dist(overlay["vertices_cm"][a],
                                     overlay["vertices_cm"][b]) * UNIT_M_PER_CM)
                          for a, b in top_edges]
            overlay_initial_metrics[code] = {
                "outward_winding_corrected": overlay_flipped,
                "pre_relax_to_paper_edge_ratio_p05": round(
                    percentile(before_relax, .05), 3),
                "pre_relax_to_paper_edge_ratio_p95": round(
                    percentile(before_relax, .95), 3),
                "initial_to_paper_edge_ratio_p05": round(
                    percentile(overlay_edge_ratios, .05), 3),
                "initial_to_paper_edge_ratio_p95": round(
                    percentile(overlay_edge_ratios, .95), 3),
                "initial_top_p95_absolute_paper_edge_strain_percent": round(
                    percentile([abs(value - 1) for value in top_ratios], .95)
                    * 100, 2),
                "placement_shift_from_guide_p95_cm": round(
                    percentile([math.dist(a, b) / UNIT_M_PER_CM
                                for a, b in zip(points, guide_points)], .95), 2),
            }
            mesh = bpy.data.meshes.new(f"{code} pattern overlay drape mesh")
            mesh.from_pydata(points, [], overlay_faces)
            mesh.update()
            mesh.materials.append(bpy.data.materials["11 tonal coat-hem jacquard"])
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            obj = bpy.data.objects.new(f"2D-pattern-derived overlay {code}", mesh)
            scene.collection.objects.link(obj)
            if overlay_mode == "with-relaxed-static-overlays":
                overlay_trial_report[code] = {
                    "vertices": len(points),
                    "simulated": False,
                    "static_placement_diagnostic_only": True,
                    "material_measured": False,
                    **overlay_initial_metrics[code],
                }
                thickness = obj.modifiers.new("visible overlay thickness", "SOLIDIFY")
                thickness.thickness = .005
                thickness.offset = 0
                continue
            pinned = obj.vertex_groups.new(name="upper overlay mounting seam")
            pinned.add(top, 1.0, "REPLACE")
            cloth = obj.modifiers.new("unmeasured overlay drape", "CLOTH")
            cloth.settings.quality = 8
            cloth.settings.mass = .18
            cloth.settings.tension_stiffness = 55
            cloth.settings.compression_stiffness = 55
            cloth.settings.shear_stiffness = 35
            cloth.settings.bending_stiffness = 45
            cloth.settings.vertex_group_mass = pinned.name
            cloth.settings.pin_stiffness = 20
            cloth.collision_settings.collision_quality = 5
            cloth.collision_settings.distance_min = .005
            cloth.collision_settings.use_self_collision = (
                overlay_mode != "with-relaxed-overlays-no-self")
            cloth.collision_settings.self_distance_min = .003
            overlay_objects.append((obj, cloth, overlay, points, mapped_inside))
        for frame in range(1, frame_count + 1):
            scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for obj, cloth, overlay, rest, mapped_inside in overlay_objects:
            evaluated = obj.evaluated_get(depsgraph)
            draped = evaluated.to_mesh()
            if len(draped.vertices) != len(rest):
                raise RuntimeError(f"Overlay {overlay['code']} changed topology")
            positions = [vertex.co.copy() for vertex in draped.vertices]
            evaluated.to_mesh_clear()
            if any(not all(math.isfinite(co) for co in position)
                   for position in positions):
                raise RuntimeError(f"Overlay {overlay['code']} has non-finite cloth positions")
            changes = [(point - Vector(initial_point)).length / UNIT_M_PER_CM
                       for point, initial_point in zip(positions, rest)]
            final_edges = {(min(face[index], face[(index + 1) % 3]),
                            max(face[index], face[(index + 1) % 3]))
                           for face in overlay["faces"] for index in range(3)}
            final_ratios = [math.dist(positions[a], positions[b]) /
                            (math.dist(overlay["vertices_cm"][a],
                                       overlay["vertices_cm"][b]) * UNIT_M_PER_CM)
                            for a, b in final_edges]
            final_top_ratios = [math.dist(positions[a], positions[b]) /
                                (math.dist(overlay["vertices_cm"][a],
                                           overlay["vertices_cm"][b])
                                 * UNIT_M_PER_CM)
                                for a, b in zip(overlay["top_indices"],
                                                overlay["top_indices"][1:])]
            overlay_trial_report[overlay["code"]] = {
                "vertices": len(rest),
                "p95_displacement_cm": round(percentile(changes, .95), 2),
                "final_to_paper_edge_ratio_p05": round(
                    percentile(final_ratios, .05), 3),
                "final_to_paper_edge_ratio_p95": round(
                    percentile(final_ratios, .95), 3),
                "final_p95_absolute_paper_edge_strain_percent": round(
                    percentile([abs(value - 1) for value in final_ratios], .95)
                    * 100, 2),
                "final_max_absolute_paper_edge_strain_percent": round(
                    max(abs(value - 1) for value in final_ratios) * 100, 2),
                "final_top_p95_absolute_paper_edge_strain_percent": round(
                    percentile([abs(value - 1) for value in final_top_ratios],
                               .95) * 100, 2),
                "material_measured": False,
                "shell_collision_enabled": shell_collision_enabled,
                "shell_collision_before_visual_thickness": (
                    shell_collision_enabled and
                    shell_obj.modifiers[0].type == "COLLISION"),
                "self_collision_enabled": (
                    overlay_mode != "with-relaxed-overlays-no-self"),
                "initial_vertices_mapped_to_shell": mapped_inside,
                **overlay_initial_metrics[overlay["code"]],
            }
            for vertex, position in zip(obj.data.vertices, positions):
                vertex.co = position
            obj.modifiers.remove(cloth)
            obj.data.update()
            thickness = obj.modifiers.new("visible overlay thickness", "SOLIDIFY")
            thickness.thickness = .005
            thickness.offset = 0
            for path_index, path in enumerate(overlay["boundary_paths"][1:], start=1):
                curve = bpy.data.curves.new(
                    f"overlay {overlay['code']} bound edge {path_index}", "CURVE")
                curve.dimensions = "3D"
                curve.bevel_depth = .003
                curve.bevel_resolution = 2
                spline = curve.splines.new("POLY")
                spline.points.add(len(path) - 1)
                for point, index in zip(spline.points, path):
                    point.co = (*positions[index], 1)
                curve.materials.append(bpy.data.materials["07 matte black webbing"])
                scene.collection.objects.link(bpy.data.objects.new(curve.name, curve))

front_detail_trial_report = {}
if detail_mode in {"pattern-derived-front-detail", "pattern-cloth-front-detail",
                   "pattern-applique-front-detail", "pattern-lapel-front-trial"}:
    if not shell_trial or [item["host_code"] for item in data.get(
            "front_details", [])] != ["A", "B"]:
        raise ValueError("Pattern-derived front detail needs two exported panels")
    material = bpy.data.materials.get("02 cool grey technical twill")
    if material is None:
        raise ValueError("The contrast fabric material is missing")
    for detail in data["front_details"]:
        code = detail["host_code"]
        host = next(item for item in data["bodice_hosts"]
                    if item["code"] == code)
        start, offset, _panel, _rest, _faces, _springs = components[code]
        host_mesh = host["pattern_mesh"]
        support = [tuple(final[index_map[start + index]])
                   for index in range(offset)]
        if len(support) != len(host_mesh["vertices_cm"]):
            raise ValueError("The upper bodice projection lost its paper vertices")
        detail_mesh = detail["pattern_mesh"]
        mapped = []
        mapped_support = []
        for point in detail_mesh["vertices_cm"]:
            surface = interpolate_pattern_surface_with_normal(
                point, host_mesh["vertices_cm"], host_mesh["faces"], support)
            if surface is None:
                raise ValueError(f"Front detail {code} leaves the generated bodice")
            base, outward = Vector(surface[0]), Vector(surface[1])
            radial = Vector((base.x, base.y, 0))
            if radial.length > 1e-8 and outward.dot(radial) < 0:
                outward.negate()
            mapped.append(tuple(base + outward * .008))
            mapped_support.append(tuple(base))
        projected = list(mapped)
        mesh = bpy.data.meshes.new(f"pattern front contrast {code} mesh")
        mesh.from_pydata(mapped, [], detail_mesh["faces"])
        mesh.update()
        obj = bpy.data.objects.new(
            f"pattern front contrast {code} ({detail_mode})", mesh)
        scene.collection.objects.link(obj)
        obj.data.materials.append(material)
        attachment_indices = []
        for index, point in enumerate(detail_mesh["vertices_cm"]):
            for first, last in zip(detail["host_attachment_line_cm"],
                                   detail["host_attachment_line_cm"][1:]):
                delta = (last[0] - first[0], last[1] - first[1])
                length_sq = delta[0] ** 2 + delta[1] ** 2
                if length_sq < 1e-12:
                    continue
                along = max(0.0, min(1.0, ((point[0] - first[0]) * delta[0]
                                               + (point[1] - first[1]) * delta[1])
                                      / length_sq))
                nearest = (first[0] + along * delta[0],
                           first[1] + along * delta[1])
                if math.dist(point, nearest) < 1e-4:
                    attachment_indices.append(index)
                    break
        if len(attachment_indices) < 20:
            raise ValueError(f"Front detail {code} has too few attachment vertices")
        pin_indices = (sorted({index for path in detail_mesh["boundary_paths"]
                               for index in path}) if detail_mode ==
                       "pattern-applique-front-detail" or detail_mode ==
                       "pattern-lapel-front-trial" else attachment_indices)
        if detail_mode in {"pattern-cloth-front-detail",
                           "pattern-applique-front-detail",
                           "pattern-lapel-front-trial"}:
            if not any(modifier.type == "COLLISION" for modifier in shell_obj.modifiers):
                bpy.ops.object.select_all(action="DESELECT")
                shell_obj.select_set(True)
                bpy.context.view_layer.objects.active = shell_obj
                bpy.ops.object.modifier_add(type="COLLISION")
                collision_modifier = next(modifier for modifier in shell_obj.modifiers
                                          if modifier.type == "COLLISION")
                shell_obj.modifiers.move(
                    shell_obj.modifiers.find(collision_modifier.name), 0)
                shell_obj.collision.thickness_outer = .008
            scene.frame_set(1)
            pinned = obj.vertex_groups.new(name="front attachment edge proxy")
            pinned.add(pin_indices, 1.0, "REPLACE")
            cloth = obj.modifiers.new("unmeasured front-detail drape", "CLOTH")
            cloth.settings.quality = 8
            cloth.settings.mass = .18
            cloth.settings.tension_stiffness = 55
            cloth.settings.compression_stiffness = 55
            cloth.settings.shear_stiffness = 35
            cloth.settings.bending_stiffness = 45
            cloth.settings.vertex_group_mass = pinned.name
            cloth.settings.pin_stiffness = 20
            cloth.collision_settings.collision_quality = 5
            cloth.collision_settings.distance_min = .005
            cloth.collision_settings.use_self_collision = True
            cloth.collision_settings.self_distance_min = .003
            for frame in range(1, frame_count + 1):
                scene.frame_set(frame)
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            draped = evaluated.to_mesh()
            if len(draped.vertices) != len(mapped):
                raise RuntimeError(f"Front detail {code} changed topology")
            mapped = [tuple(vertex.co) for vertex in draped.vertices]
            evaluated.to_mesh_clear()
            if any(not all(math.isfinite(co) for co in point) for point in mapped):
                raise RuntimeError(f"Front detail {code} has non-finite cloth positions")
            for vertex, point in zip(obj.data.vertices, mapped):
                vertex.co = point
            obj.modifiers.remove(cloth)
            obj.data.update()
        thickness = obj.modifiers.new("contrast fabric thickness preview", "SOLIDIFY")
        thickness.thickness = .004
        thickness.offset = 0
        detail_edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                        for face in detail_mesh["faces"] for index in range(3)}
        projected_ratios = [math.dist(projected[a], projected[b]) /
                            (math.dist(detail_mesh["vertices_cm"][a],
                                       detail_mesh["vertices_cm"][b]) * UNIT_M_PER_CM)
                            for a, b in detail_edges]
        detail_ratios = [math.dist(mapped[a], mapped[b]) /
                         (math.dist(detail_mesh["vertices_cm"][a],
                                    detail_mesh["vertices_cm"][b]) * UNIT_M_PER_CM)
                         for a, b in detail_edges]
        host_edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                      for face in host_mesh["faces"] for index in range(3)}
        host_ratios = [math.dist(support[a], support[b]) /
                       (math.dist(host_mesh["vertices_cm"][a],
                                  host_mesh["vertices_cm"][b]) * UNIT_M_PER_CM)
                       for a, b in host_edges]
        front_detail_trial_report[code] = {
            "source": "generated 2D front-panel stitch polygon",
            "vertices": len(mapped), "faces": len(detail_mesh["faces"]),
            "mapped_vertices": len(mapped),
            "offset_from_bodice_cm": .4,
            "attachment_vertices": len(attachment_indices),
            "pinned_vertices": len(pin_indices) if detail_mode in {
                "pattern-cloth-front-detail", "pattern-applique-front-detail",
                "pattern-lapel-front-trial"} else 0,
            "attachment_model": (
                "perimeter-pinned applique cloth proxy" if detail_mode ==
                "pattern-applique-front-detail" or detail_mode ==
                "pattern-lapel-front-trial" else
                "fixed-edge cloth proxy" if detail_mode ==
                "pattern-cloth-front-detail" else "surface projection only"),
            "final_attachment_gap_p95_cm": round(percentile([
                math.dist(mapped[index], mapped_support[index]) / UNIT_M_PER_CM
                for index in pin_indices], .95), 3),
            "projected_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(ratio - 1) for ratio in projected_ratios], .95)
                * 100, 2),
            "projected_max_absolute_paper_edge_strain_percent": round(
                max(abs(ratio - 1) for ratio in projected_ratios) * 100, 2),
            "final_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(ratio - 1) for ratio in detail_ratios], .95)
                * 100, 2),
            "final_max_absolute_paper_edge_strain_percent": round(
                max(abs(ratio - 1) for ratio in detail_ratios) * 100, 2),
            "host_bodice_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(ratio - 1) for ratio in host_ratios], .95)
                * 100, 2),
            "host_bodice_max_absolute_paper_edge_strain_percent": round(
                max(abs(ratio - 1) for ratio in host_ratios) * 100, 2),
            "separately_cloth_simulated": (
                detail_mode in {"pattern-cloth-front-detail",
                                "pattern-applique-front-detail",
                                "pattern-lapel-front-trial"}),
            "attachment_construction_verified": False,
            "physical_fabric_measured": False,
        }

lapel_trial_report = {}
if detail_mode == "pattern-lapel-front-trial":
    if [item["host_code"] for item in data.get("lapels", [])] != ["A", "B"]:
        raise ValueError("The lapel trial needs two generated neckline pieces")

    def paper_line_distance(point, path):
        distances = []
        for first, last in zip(path, path[1:]):
            delta = (last[0] - first[0], last[1] - first[1])
            length_sq = delta[0] ** 2 + delta[1] ** 2
            if length_sq < 1e-12:
                continue
            t = max(0.0, min(1.0, ((point[0] - first[0]) * delta[0]
                                    + (point[1] - first[1]) * delta[1])
                                   / length_sq))
            distances.append(math.dist(point, (first[0] + t * delta[0],
                                               first[1] + t * delta[1])))
        return min(distances)

    for lapel in data["lapels"]:
        code = lapel["host_code"]
        host = next(item for item in data["bodice_hosts"]
                    if item["code"] == code)
        start, offset, _panel, _rest, _faces, _springs = components[code]
        host_mesh = host["pattern_mesh"]
        support = [tuple(final[index_map[start + index]])
                   for index in range(offset)]
        lapel_mesh = lapel["pattern_mesh"]
        attachment = lapel["host_attachment_line_cm"]
        distances_cm = [paper_line_distance(point, attachment)
                        for point in lapel_mesh["vertices_cm"]]
        pinned_indices = [index for index, value in enumerate(distances_cm)
                          if value < 1e-4]
        if len(pinned_indices) < 10:
            raise ValueError(f"Lapel {code} lacks its neckline attachment mesh")
        initial = []
        lapel_support = []
        lapel_normals = []
        for point, distance_cm in zip(lapel_mesh["vertices_cm"], distances_cm):
            surface = interpolate_pattern_surface_with_normal(
                point, host_mesh["vertices_cm"], host_mesh["faces"], support)
            if surface is None:
                raise ValueError(f"Lapel {code} leaves the generated bodice")
            base, outward = Vector(surface[0]), Vector(surface[1])
            radial = Vector((base.x, base.y, 0))
            if radial.length > 1e-8 and outward.dot(radial) < 0:
                outward.negate()
            clearance = .008 + .03 * min(1, distance_cm / 10)
            initial.append(tuple(base + outward * clearance))
            lapel_support.append(tuple(base))
            lapel_normals.append(tuple(outward))
        raw_initial = list(initial)
        initial = relax_overlay_to_paper_edges(
            initial, lapel_mesh["vertices_cm"], lapel_mesh["faces"],
            pinned_indices, lapel_support, lapel_normals,
            unit_m_per_cm=UNIT_M_PER_CM, min_gap_m=.008,
            max_guide_distance_m=.12)
        faces, flipped = outward_wound_faces(initial, lapel_mesh["faces"])
        mesh = bpy.data.meshes.new(f"pattern neckline lapel {code} mesh")
        mesh.from_pydata(initial, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"pattern neckline lapel {code} (cloth trial)", mesh)
        scene.collection.objects.link(obj)
        obj.data.materials.append(material)
        scene.frame_set(1)
        pin = obj.vertex_groups.new(name="neckline attachment proxy")
        pin.add(pinned_indices, 1.0, "REPLACE")
        cloth = obj.modifiers.new("unmeasured lapel drape", "CLOTH")
        cloth.settings.quality = 8
        cloth.settings.mass = .18
        cloth.settings.tension_stiffness = 55
        cloth.settings.compression_stiffness = 55
        cloth.settings.shear_stiffness = 35
        cloth.settings.bending_stiffness = 70
        cloth.settings.vertex_group_mass = pin.name
        cloth.settings.pin_stiffness = 20
        cloth.collision_settings.collision_quality = 5
        cloth.collision_settings.distance_min = .005
        cloth.collision_settings.use_self_collision = True
        cloth.collision_settings.self_distance_min = .003
        for frame in range(1, frame_count + 1):
            scene.frame_set(frame)
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        draped = evaluated.to_mesh()
        if len(draped.vertices) != len(initial):
            raise RuntimeError(f"Lapel {code} changed topology")
        final_lapel = [tuple(vertex.co) for vertex in draped.vertices]
        evaluated.to_mesh_clear()
        if any(not all(math.isfinite(co) for co in point) for point in final_lapel):
            raise RuntimeError(f"Lapel {code} has non-finite cloth positions")
        for vertex, point in zip(obj.data.vertices, final_lapel):
            vertex.co = point
        obj.modifiers.remove(cloth)
        obj.data.update()
        thickness = obj.modifiers.new("lapel visible thickness", "SOLIDIFY")
        thickness.thickness = .004
        thickness.offset = 0
        edges = {tuple(sorted((face[index], face[(index + 1) % 3])))
                 for face in lapel_mesh["faces"] for index in range(3)}
        initial_ratios = [math.dist(initial[a], initial[b]) /
                          (math.dist(lapel_mesh["vertices_cm"][a],
                                     lapel_mesh["vertices_cm"][b]) * UNIT_M_PER_CM)
                          for a, b in edges]
        raw_ratios = [math.dist(raw_initial[a], raw_initial[b]) /
                      (math.dist(lapel_mesh["vertices_cm"][a],
                                 lapel_mesh["vertices_cm"][b]) * UNIT_M_PER_CM)
                      for a, b in edges]
        ratios = [math.dist(final_lapel[a], final_lapel[b]) /
                  (math.dist(lapel_mesh["vertices_cm"][a],
                             lapel_mesh["vertices_cm"][b]) * UNIT_M_PER_CM)
                  for a, b in edges]
        lapel_trial_report[code] = {
            "vertices": len(final_lapel), "faces": len(faces),
            "neckline_attachment_vertices": len(pinned_indices),
            "outward_winding_corrected": flipped,
            "neckline_gap_p95_cm": round(percentile([
                math.dist(final_lapel[index], lapel_support[index]) / UNIT_M_PER_CM
                for index in pinned_indices], .95), 3),
            "raw_projection_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(ratio - 1) for ratio in raw_ratios], .95)
                * 100, 2),
            "initial_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(ratio - 1) for ratio in initial_ratios], .95)
                * 100, 2),
            "initial_max_absolute_paper_edge_strain_percent": round(
                max(abs(ratio - 1) for ratio in initial_ratios) * 100, 2),
            "final_p95_absolute_paper_edge_strain_percent": round(
                percentile([abs(ratio - 1) for ratio in ratios], .95) * 100, 2),
            "final_max_absolute_paper_edge_strain_percent": round(
                max(abs(ratio - 1) for ratio in ratios) * 100, 2),
            "material_measured": False,
            "fold_shape_verified": False,
            "attachment_is_fixed_edge_proxy_not_real_stitching": True,
        }

scene.frame_set(1)
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.render.resolution_x = 850
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
camera = scene.camera
for view, position in (("front", (0, -7, -.15)),
                       ("side", (7, 0, -.15)),
                       ("back", (0, 7, -.15))):
    camera.location = position
    camera.rotation_euler = (Vector((0, 0, -.18)) - camera.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.render.filepath = str(output / f"pattern_panels_{view}.png")
    bpy.ops.render.render(write_still=True)

# The borrowed sweater was authored for a different 3D body.  In the
# measurement-standin experiment it can hide the actual pattern-derived coat
# completely.  Keep the layered comparison, but also render the shell alone
# so that this visual-size mismatch cannot be mistaken for a missing bodice.
shell_only_diagnostic_views = {}
smoothed_shell_diagnostic_views = {}
if bodice_mode == "pattern-bodice" and collision_mode == "measurement-standin":
    hidden_inner = [obj for obj in scene.objects if not obj.hide_render and
                    obj.name.startswith(("ribbed inner sweater",
                                         "structured high stand collar",
                                         "sweater collar tie"))]
    for obj in hidden_inner:
        obj.hide_render = True
    for view, position in (("front", (0, -7, -.15)),
                           ("side", (7, 0, -.15)),
                           ("back", (0, 7, -.15))):
        camera.location = position
        camera.rotation_euler = (Vector((0, 0, -.18)) - camera.location).to_track_quat(
            "-Z", "Y").to_euler()
        path = output / f"pattern_shell_only_{view}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        shell_only_diagnostic_views[view] = str(path)
    if shell_trial is not None:
        # Standard render-only subdivision smooths the cloth after the
        # simulated positions and edge-strain audit have been fixed.  Preserve
        # the unsmoothed triptych above: subdivision cannot repair a bad seam,
        # penetration, fabric fit, or a missing physical component.
        surface = shell_obj.modifiers.new("render-only cloth subdivision", "SUBSURF")
        surface.levels = 1
        surface.render_levels = 1
        collision_index = next((index for index, modifier in enumerate(
            shell_obj.modifiers) if modifier.type == "COLLISION"), -1)
        shell_obj.modifiers.move(shell_obj.modifiers.find(surface.name),
                                 collision_index + 1)
        for view, position in (("front", (0, -7, -.15)),
                               ("side", (7, 0, -.15)),
                               ("back", (0, 7, -.15))):
            camera.location = position
            camera.rotation_euler = (Vector((0, 0, -.18)) - camera.location).to_track_quat(
                "-Z", "Y").to_euler()
            path = output / f"pattern_shell_smoothed_{view}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            smoothed_shell_diagnostic_views[view] = str(path)
    for obj in hidden_inner:
        obj.hide_render = False

report = {"status": (
              "comparison with borrowed authored front detail; not pattern-complete"
              if detail_mode == "authored-front-detail-comparison" else
              "2D-derived neckline lapel cloth trial; not commercial construction"
              if detail_mode == "pattern-lapel-front-trial" else
              "2D-derived perimeter-pinned applique cloth trial; not stitched"
              if detail_mode == "pattern-applique-front-detail" else
              "2D-derived pinned-edge front-detail cloth trial; not sewn"
              if detail_mode == "pattern-cloth-front-detail" else
              "2D-derived projected front detail trial; not sewn or cloth-simulated"
              if detail_mode == "pattern-derived-front-detail" else
              "2D-pattern-derived hem panel drape prototype"),
          "not_a_commercial_quality_certification": True,
          "source_pattern_json": str(panel_file),
          "input_fingerprints": input_fingerprints,
          "body_is_avatar_standin": collision_mode == "with-body",
          "collision_mode": collision_mode,
          "authored_sweater_collision_copy_not_measured": (
              collision_mode == "measurement-standin-with-sweater"),
          "body_scale_is_calibrated_to_wearer": False,
          "measurement_fixture_is_wearer_scan": False,
          "body_contact_report": body_contact_report,
          "shell_only_diagnostic_views": shell_only_diagnostic_views,
          "smoothed_shell_diagnostic_views": smoothed_shell_diagnostic_views,
          "render_subdivision_changes_simulated_geometry": False,
          "borrowed_sweater_fit_to_measurement_fixture_verified": False,
          "panel_top_placed_on_bodice_hem": True,
          "panel_top_anchored_to_real_bodice_mesh": False,
          "bodice_to_panel_join_mode": join_mode,
          "sewn_initial_gap_m": sewn_initial_gap_m if join_mode !=
          "independent" else None,
          "support_bodice_is_pattern_derived": bodice_mode == "pattern-bodice",
          "pattern_sleeves_exported": bool(data.get("sleeves")),
          "pattern_sleeves_rendered": bool(sleeve_components),
          "borrowed_source_sleeve_objects": borrowed_sleeve_names,
          "sleeve_drape_mode": sleeve_mode,
          "sleeve_cap_ease_distribution": cap_ease_mode,
          "sleeve_drape_report": sleeve_drape_report,
          "sleeve_topology_preflight": sleeve_topology_preflight,
          "sleeve_join_audit": data.get("sleeve_join_audit"),
          "sleeve_interface_report": sleeve_interface_report,
          "bodice_placement_mode": bodice_placement_mode,
          "upper_pin_mode": upper_pin_mode,
          "dart_height_placement_mode": dart_height_mode,
          "bust_dart_seam_mode": dart_seam_mode,
          "bust_dart_seam_report": dart_seam_report,
          "waist_dart_seam_report": waist_dart_seam_report,
          "waist_dart_3d_trial": bool(darted_hem_hosts),
          "waist_dart_trial_closure_limit_cm": 0.2 if darted_hem_hosts else None,
          "waist_dart_trial_closure_pass": (
              bool(waist_dart_seam_report) and
              all(item["final_gap_p95_cm"] <= 0.2
                  for item in waist_dart_seam_report.values())
              if darted_hem_hosts else None),
          "shoulder_seam_mode": shoulder_seam_mode,
          "shoulder_seam_report": shoulder_seam_report,
          "bodice_side_seam_mode": bodice_side_mode,
          "bodice_side_seam_report": bodice_side_seam_report,
          "dart_height_shift_is_inferred_not_sewn": (
              dart_height_mode == "dart-taken-up-height-trial"),
          "upper_anchor_counts": upper_anchor_counts,
          "upper_bodice_is_fit_validated": False,
          "front_detail_comparison_mode": detail_mode,
          "front_detail_trial_report": front_detail_trial_report,
          "lapel_trial_report": lapel_trial_report,
          "generated_front_detail_has_pattern": (
              detail_mode in {"pattern-derived-front-detail",
                              "pattern-cloth-front-detail",
                              "pattern-applique-front-detail",
                              "pattern-lapel-front-trial"}),
          "authored_front_detail_has_generated_pattern": False,
          "borrowed_front_detail_objects": borrowed_front_detail_names,
          "not_a_pattern_complete_preview": True,
          "bodice_surface_uses_authored_guide": (
              bodice_placement_mode == "authored-guide"),
          "guide_hem_geometry": guide_mode,
          "lower_initial_placement_uses_authored_guide": (
              join_mode == "authored-guided-welded-shell"),
          "winding_outward_corrections": winding_corrections,
          "initial_radial_flare_m": radial_flare_m,
          "shell_placement_mode": shell_placement_mode,
          "shell_relaxation_report": shell_relaxation_report,
          "panel_topology_preflight": panel_topology_preflight,
          "overlay_topology_preflight": overlay_topology_preflight,
          "unmeasured_fabric_profile": fabric_profile,
          "self_collision_enabled": self_collision_mode == "self-collision",
          "pattern_bodice_mesh_vertices": pattern_bodice_counts,
          "bodice_hem_length_cm_in_scene_scale": round(hem_length / UNIT_M_PER_CM, 3),
          "unstitched_side_gaps_cm_in_scene_scale": round(
              (hem_length / UNIT_M_PER_CM - sum(widths.values())) / 2, 3),
          "panel_to_panel_side_seams_simulated": shell_joined,
          "bodice_to_panel_seam_topologically_welded": (
              join_mode == "fully-welded-shell"),
          "fully_welded_seam_edge_report": fully_welded_seam_edge_report,
          "side_seam_report": side_seam_report,
          "side_initial_gap_report": side_initial_gap_report,
          "virtual_side_seam_gap_limit_cm": 0.2,
          "virtual_side_seam_closure_pass": (
              shell_joined
              and self_collision_mode == "self-collision"
              and bool(side_seam_report)
              and all(item["gap_p95_cm"] <= 0.2
                      for item in side_seam_report.values())),
          "provisional_geometry_screen": {
              "not_a_material_certification": True,
              "initial_side_gap_limit_cm": 0.2,
              "initial_edge_ratio_window": [0.95, 1.05],
              "final_p95_edge_strain_limit_percent": 5.0,
             "final_to_paper_edge_ratio_window": [0.95, 1.05],
             "final_p95_absolute_paper_edge_strain_limit_percent": 5.0,
              "passed": (shell_joined and
                         self_collision_mode == "self-collision" and
                         (not darted_hem_hosts or
                          (bool(waist_dart_seam_report) and
                           all(item["final_gap_p95_cm"] <= 0.2
                               for item in waist_dart_seam_report.values()))) and
                         len(side_initial_gap_report) == 2 and
                         all(item["gap_p95_cm"] <= 0.2 for item in
                             side_initial_gap_report.values()) and
                         all(0.95 <= item["initial_edge_length_ratio_p05"]
                             and item["initial_edge_length_ratio_p95"] <= 1.05
                             and item["p95_absolute_edge_strain_percent"] <= 5.0
                             and 0.95 <= item["final_to_paper_edge_ratio_p05"]
                             and item["final_to_paper_edge_ratio_p95"] <= 1.05
                             and item["final_p95_absolute_paper_edge_strain_percent"] <= 5.0
                             for item in cases)),
          },
          "overlay_trial_report": overlay_trial_report,
          "overlay_mode": overlay_mode,
          "overlay_seam_preflight": overlay_seam_preflight,
          "overlay_mounting_model": (
              "shared_cloth_loose_edge_sewing_springs" if
              overlay_mode == "with-sewn-overlays" else
              "fixed_offset_top_edge" if overlay_mode != "no-overlays" else None),
          "overlay_mount_clearance_cm": overlay_mount_clearance_cm if
          overlay_mode in RELAXED_OVERLAY_MODES else None,
          "three_layer_seam_topologically_simulated": False,
          "three_layer_seam_springs_simulated": bool(sewn_overlay_components),
          "overlay_preview_approved": False,
          "reference_visual_review_pass": False,
          "commercial_quality_approved": False,
          "fabric_inputs_measured": False,
          "frame": frame_count, "panels": cases,
          "not_simulated": (["complete bodice-to-panel seam"] if join_mode ==
                            "independent" else []) + ([
                            "inter-panel side seams or collisions"] if not
                            shell_joined else []) + ([
                            "upper bodice bust seams" if dart_seam_mode ==
                            "open-bust-darts" else "bust seam weld and pressing",
                            "upper bodice shoulder seams" if shoulder_seam_mode ==
                            "open-shoulders" else "shoulder seam weld and finish",
                            "upper bodice side seams" if bodice_side_mode ==
                            "open-bodice-sides" else "bodice side seam weld and finish",
                            "pattern-derived sleeves" if sleeve_mode ==
                            "borrowed-sleeves" else "sleeve seam weld and finish",
                            "waist dart pressing and seam strength",
                            "physical fit of waist-dart garment",
                            ] if darted_hem_hosts else []) + [
                            "fasteners and props", "movement and wear fatigue"]}
(output / "pattern_panel_drape_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(output / "pattern_panel_drape.blend"))
print("PATTERN_PANEL_REPORT", json.dumps(report, ensure_ascii=False), flush=True)
