"""round85: VRC級モデルを持ち込めるローカルWebGL完成プレビュー。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_result_contains_webgl_and_private_avatar_controls(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="outfit-webgl-view"' in html
    assert 'id="outfit-avatar-file"' in html
    assert 'accept=".vrm,.glb,model/gltf-binary"' in html
    assert 'id="outfit-avatar-reset"' in html
    assert "アバターを表示" in html
    assert "サーバーへ送信されません" in html
    assert 'type="module"' in html and "outfit3d.js" in html


def test_webgl_viewer_has_pbr_lighting_shadows_and_orbit_controls():
    js = _read("web/static/outfit3d.js")
    assert "new THREE.WebGLRenderer" in js
    assert "THREE.ACESFilmicToneMapping" in js
    assert "new THREE.MeshPhysicalMaterial" in js
    assert "renderer.shadowMap.enabled = true" in js
    assert "new OrbitControls" in js
    assert "new THREE.HemisphereLight" in js
    assert "new THREE.DirectionalLight" in js


def test_vrm_glb_is_parsed_from_memory_and_normalised_without_upload():
    js = _read("web/static/outfit3d.js")
    assert "file.arrayBuffer()" in js
    assert 'avatarLoader().parse(buffer, ""' in js
    assert "new VRMLoaderPlugin(parser)" in js
    assert "VRMUtils.rotateVRM0(vrm)" in js
    assert "100 * 1024 * 1024" in js
    assert "fitImportedAvatar(nextAvatar)" in js
    assert "fetch(" not in js


def test_cc0_vrm_is_bundled_as_the_default_avatar():
    html = _read("web/templates/index.html")
    assert "models/default-avatar.vrm" in html
    assert (ROOT / "web/static/models/default-avatar.vrm").stat().st_size > 10_000_000
    assert (ROOT / "web/static/models/LICENSE.md").is_file()
    assert (ROOT / "web/static/vendor/three-vrm.module.min.js").is_file()
    assert (ROOT / "web/static/vendor/THREE_VRM_LICENSE").is_file()


def test_csp_allows_embedded_vrm_textures(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "img-src 'self' data: blob:" in csp
    assert "connect-src 'self' blob:" in csp


def test_repeated_generation_and_avatar_replacement_release_gpu_resources():
    js = _read("web/static/outfit3d.js")
    assert "function disposeObject3D" in js
    assert "clearGroup(garmentGroup)" in js
    assert "clearGroup(accessoryGroup)" in js
    assert "geometry.dispose?.()" in js
    assert "material.dispose?.()" in js
    assert "texture.dispose?.()" in js
    assert "loadSequence !== avatarLoadSequence" in js


def test_existing_controls_and_exports_use_high_quality_renderer_when_ready():
    js = _read("web/static/app.js")
    assert "window.PatternForge3D?.setOutfit(parts, outfitState)" in js
    assert "window.PatternForge3D?.update(outfitState)" in js
    assert "window.PatternForge3D?.canvas || outfitCanvas" in js
    assert "window.PatternForge3D?.makeFourViewSheet" in js


def test_generated_clothing_uses_dense_tailored_surfaces_and_reference_palette():
    viewer = _read("web/static/outfit3d.js")
    app = _read("web/static/app.js")
    for feature in (
        "tailoredShellGeometry", "fittedSleeveGeometry", "drapedSkirtGeometry",
        "trouserLegGeometry", "getFabricNormalTexture", "ellipseTrim",
        "ruffledHem", "detachedDressSleeve",
    ):
        assert feature in viewer
    assert "inferOutfitPaletteFromReference" in app
    assert "inferredOutfitColor" in app
    assert 'role: "cloth"' in viewer
    assert 'role: "stitch"' in viewer


def test_threejs_is_bundled_locally_with_license_and_relative_imports():
    vendor = ROOT / "web" / "static" / "vendor" / "three"
    for name in ("three.module.min.js", "three.core.min.js", "GLTFLoader.js", "OrbitControls.js",
                 "BufferGeometryUtils.js", "LICENSE"):
        assert (vendor / name).is_file(), name
    assert "from 'three'" not in _read("web/static/vendor/three/GLTFLoader.js")
    assert "from 'three'" not in _read("web/static/vendor/three/OrbitControls.js")
    assert "from 'three'" not in _read("web/static/vendor/three/BufferGeometryUtils.js")
