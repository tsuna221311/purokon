"""Guard the cloth-specific rendering path against flat-material regressions."""

from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1] / "web" / "static" / "outfit3d.js"
PAGE = Path(__file__).resolve().parents[1] / "web" / "templates" / "index.html"


def _viewer() -> str:
    return VIEWER.read_text(encoding="utf-8")


def test_open_coat_sews_panels_to_shared_boundaries():
    source = _viewer()
    assert "function connectedCoatGeometry(shape = {})" in source
    assert "if (inArmhole(row, column)) continue" in source
    assert "ring.push(shellIndex(" in source
    assert "const strip = [shellIndex(row, edgeColumn)]" in source
    assert "const strip = [facing[row][facingColumns]]" in source
    assert 'connectedCoatGeometry({ ...state?.appearance?.shape, pose_angle: poseAngle })' in source
    assert '[outer, lining, lapel, hemJacquard]' in source
    assert 'coatShell.name = "sewn-open-long-coat"' in source
    assert "const backBillow" in source
    build = source.split("function buildOpenLongCoat(state)", 1)[1].split("function ", 1)[0]
    assert "coatFrontTailGeometry(side)" not in build
    assert "curvedClothPanel(garmentGroup," not in build
    assert "new THREE.SphereGeometry(.22, 36, 24)" not in build


def test_woven_outer_and_ribbed_knit_have_distinct_pbr_maps():
    source = _viewer()
    assert "function getCoatFabricMaps()" in source
    assert "roughnessMap: weave.roughness" in source
    assert "normalMap: weave.normal" in source
    assert "function getRibNormalTexture()" in source
    assert "normalMap: getRibNormalTexture()" in source
    assert "function getCoatJacquardTexture()" in source
    assert 'role: "coat_hem_jacquard"' in source


def test_flared_hem_and_balloon_sleeve_remain_on_connected_surface():
    source = _viewer()
    geometry = source.split("function connectedCoatGeometry(shape = {})", 1)[1].split(
        "function stitchedCoatLine", 1)[0]
    assert "const sideFan" in geometry
    assert "const frontTail" in geometry
    assert "const balloon" in geometry
    assert "const isYoke" in geometry
    assert "const fanPleat" in geometry
    assert "- .19 * Math.pow(t, 4)" in geometry
    assert "materialIndex: 2" in geometry
    assert "row >= 42 ? 3" in geometry
    assert "hemFlare" in geometry and "sleeveVolume" in geometry


def test_layered_coat_materials_follow_user_color_changes():
    source = _viewer()
    assert "Array.isArray(object.material) ? object.material : [object.material]" in source
    assert 'role === "outer" || role === "coat_hem_jacquard"' in source
    assert 'role === "coat_lapel"' in source
    assert 'shape?.accent_side === "left" ? -1 : 1' in source


def test_coat_pose_keeps_sleeves_details_and_vrm_arms_aligned():
    source = _viewer()
    assert "const COAT_FITTING_POSE = .38" in source
    assert "const COAT_SLEEVE_SCALE = .84" in source
    assert "pivot.scale.x = COAT_SLEEVE_SCALE" in source
    assert "along * Math.cos(poseAngle)" in source
    assert "along * Math.sin(poseAngle)" in source
    assert "sleeveDetailGroup(garmentGroup, side, poseAngle)" in source
    assert "importedGarment ? Number(state.authoredSleevePose || 0) : coatPoseAngle()" in source
    assert "importedAvatar && !importedVRM ? 0 : COAT_FITTING_POSE" in source
    assert "function buildBundledFittingHands()" in source
    assert "tailoredView && !importedGarment && usingBundledAvatar" in source


def test_authored_glb_does_not_masquerade_as_generated_vrc_model():
    source = _viewer()
    assert "function inspectGarmentModel(model)" in source
    assert "if (!meshes || !triangles)" in source
    assert "if (importedGarment) importedGarment.visible = state.showGarment !== false" in source
    assert 'source: "imported_glb"' in source
    assert "アバターへの骨追従やVRC対応の保証ではありません" in source
    assert "input ? Number(input.value) : (index === 0 ? 100 : 0)" in source
    page = PAGE.read_text(encoding="utf-8")
    assert 'id="outfit-garment-file"' in page
    assert 'id="outfit-garment-reset"' in page
    assert 'id="outfit-garment-status"' in page
    assert 'id="outfit-garment-fit"' in page
    assert "function applyImportedGarmentTransform()" in source
    assert "自動生成は形状確認用" in page


def test_lining_is_inset_from_same_surface_and_edge_walls_are_closed():
    source = _viewer()
    assert "positions[i * 3] - normals.getX(i) * thickness" in source
    assert "if (count !== 1) continue" in source
    assert "geometry.addGroup(liningStart, edgeStart - liningStart, 1)" in source
    assert "coatShell.receiveShadow = false" in source
