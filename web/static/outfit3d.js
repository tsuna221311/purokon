/* PatternForge high-fidelity outfit viewer.
 * Three.js is bundled locally (MIT) so the viewer works without a CDN.
 * VRM files are GLB containers; GLTFLoader renders their mesh/material data
 * without uploading the file. VRM-specific expressions and spring bones are
 * intentionally not required for a static costume fitting preview. */
import * as THREE from "./vendor/three/three.module.min.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";

const host = document.getElementById("outfit-webgl-view");
const fallbackCanvas = document.getElementById("outfit-preview-canvas");
const avatarFile = document.getElementById("outfit-avatar-file");
const avatarReset = document.getElementById("outfit-avatar-reset");
const avatarStatus = document.getElementById("outfit-avatar-status");

const ANCHORS = {
  head: [0, 1.55, .31], chest: [0, .56, .48], back: [0, .50, -.48],
  waist: [0, -.08, .47], left_shoulder: [-.66, .78, .12],
  right_shoulder: [.66, .78, .12], left_hip: [-.48, -.22, .32],
  right_hip: [.48, -.22, .32],
};

let renderer;
let scene;
let camera;
let controls;
let root;
let proceduralAvatar;
let importedAvatar;
let garmentGroup;
let accessoryGroup;
let floor;
let currentParts = [];
let currentState = null;
let animationFrame = 0;
let avatarLoadSequence = 0;

function setStatus(message, error = false) {
  if (!avatarStatus) return;
  avatarStatus.textContent = message;
  avatarStatus.classList.toggle("is-error", error);
}

function smoothMaterial(color, options = {}) {
  return new THREE.MeshPhysicalMaterial({
    color,
    roughness: options.roughness ?? .56,
    metalness: options.metalness ?? .02,
    clearcoat: options.clearcoat ?? .12,
    clearcoatRoughness: .55,
    sheen: options.sheen ?? .18,
    sheenRoughness: .65,
    side: THREE.DoubleSide,
  });
}

function addMesh(parent, geometry, material, position, scale = [1, 1, 1], rotation = [0, 0, 0]) {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(...position);
  mesh.scale.set(...scale);
  mesh.rotation.set(...rotation);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function disposeObject3D(object) {
  if (!object) return;
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  object.traverse((child) => {
    if (child.geometry) geometries.add(child.geometry);
    const childMaterials = Array.isArray(child.material) ? child.material : [child.material];
    childMaterials.filter(Boolean).forEach((material) => {
      materials.add(material);
      Object.values(material).forEach((value) => {
        if (value?.isTexture) textures.add(value);
      });
    });
  });
  textures.forEach((texture) => texture.dispose?.());
  materials.forEach((material) => material.dispose?.());
  geometries.forEach((geometry) => geometry.dispose?.());
}

function clearGroup(group) {
  if (!group) return;
  [...group.children].forEach((child) => {
    group.remove(child);
    disposeObject3D(child);
  });
}

function capsule(parent, radius, length, material, position, rotation = [0, 0, 0]) {
  return addMesh(parent, new THREE.CapsuleGeometry(radius, length, 10, 24),
    material, position, [1, 1, 1], rotation);
}

function lathe(parent, profile, material, position = [0, 0, 0]) {
  const points = profile.map(([radius, y]) => new THREE.Vector2(radius, y));
  return addMesh(parent, new THREE.LatheGeometry(points, 48), material, position);
}

function buildProceduralAvatar() {
  const group = new THREE.Group();
  group.name = "standard-anime-avatar";
  const skin = smoothMaterial("#f0cdbb", { roughness: .72, sheen: .08 });
  const body = smoothMaterial("#3d4252", { roughness: .78 });
  const hair = smoothMaterial("#242533", { roughness: .52, sheen: .35 });
  const eye = smoothMaterial("#5468a8", { roughness: .25, clearcoat: .5 });

  // 大きめの頭、細い首・手足でVRCのアニメ調アバターに近い比率。
  // 髪を後ろの大きな球、顔を少し前の小さな球として重ねる。半球を
  // そのまま被せると環境によって目の高さに黒い帯が出るため、この構成にする。
  addMesh(group, new THREE.SphereGeometry(.36, 40, 28), hair,
    [0, 1.53, -.045], [1.03, 1.08, 1.0]);
  addMesh(group, new THREE.SphereGeometry(.32, 40, 28), skin,
    [0, 1.47, .095], [.91, .94, .78]);
  for (const x of [-.115, .115]) {
    addMesh(group, new THREE.SphereGeometry(.043, 24, 16), eye, [x, 1.51, .344], [1, 1.18, .34]);
    addMesh(group, new THREE.SphereGeometry(.015, 16, 12), smoothMaterial("#11131b"),
      [x, 1.51, .360]);
  }
  addMesh(group, new THREE.SphereGeometry(.025, 16, 12), skin,
    [0, 1.44, .355], [1, .75, .42]);
  addMesh(group, new THREE.TorusGeometry(.045, .008, 8, 24, Math.PI),
    smoothMaterial("#b56f78", { roughness: .7 }),
    [0, 1.37, .351], [1, .55, .35], [0, 0, Math.PI]);
  capsule(group, .105, .12, skin, [0, 1.12, 0]);
  lathe(group, [[.25, -.62], [.39, -.48], [.47, .12], [.42, .52], [.30, .64]],
    body, [0, .45, 0]);
  capsule(group, .14, .92, body, [-.57, .31, 0], [0, 0, -.10]);
  capsule(group, .14, .92, body, [.57, .31, 0], [0, 0, .10]);
  addMesh(group, new THREE.SphereGeometry(.145, 24, 16), skin, [-.61, -.22, 0], [1, 1.25, .82]);
  addMesh(group, new THREE.SphereGeometry(.145, 24, 16), skin, [.61, -.22, 0], [1, 1.25, .82]);
  capsule(group, .175, 1.05, body, [-.22, -1.02, 0], [0, 0, -.025]);
  capsule(group, .175, 1.05, body, [.22, -1.02, 0], [0, 0, .025]);
  addMesh(group, new THREE.SphereGeometry(.19, 28, 18), body, [-.22, -1.69, .10], [1, .62, 1.55]);
  addMesh(group, new THREE.SphereGeometry(.19, 28, 18), body, [.22, -1.69, .10], [1, .62, 1.55]);
  return group;
}

function hasType(types, ...names) {
  return names.some((name) => types.has(name));
}

function roundedPanelGeometry(width, height, depth) {
  const radius = Math.min(width, height) * .12;
  const x = -width / 2, y = -height / 2;
  const shape = new THREE.Shape();
  shape.moveTo(x + radius, y);
  shape.lineTo(x + width - radius, y);
  shape.quadraticCurveTo(x + width, y, x + width, y + radius);
  shape.lineTo(x + width, y + height - radius);
  shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  shape.lineTo(x + radius, y + height);
  shape.quadraticCurveTo(x, y + height, x, y + height - radius);
  shape.lineTo(x, y + radius);
  shape.quadraticCurveTo(x, y, x + radius, y);
  return new THREE.ExtrudeGeometry(shape, {
    depth, bevelEnabled: true, bevelSegments: 4,
    bevelSize: Math.min(.035, radius / 2), bevelThickness: .025, curveSegments: 12,
  });
}

function accessoryKey(part, index) {
  return part.identifier || `${part.display_name || "accessory"}-${index}`;
}

function guessedAnchor(part, index) {
  const key = accessoryKey(part, index);
  const override = currentState?.accessoryAnchors?.[key];
  if (override && ANCHORS[override]) return override;
  const label = `${part.display_name || ""} ${part.variation || ""}`.toLowerCase();
  if (/(頭|髪|帽子|冠|ティアラ|hair|head|hat|crown)/.test(label)) return "head";
  if (/(背|翼|羽|マント|wing|back|cape)/.test(label)) return "back";
  if (/(腰|帯|ベルト|バックル|belt|buckle|waist)/.test(label)) return "waist";
  if (/(肩|ショルダー|肩当|shoulder|pauldron)/.test(label)) return index % 2 ? "right_shoulder" : "left_shoulder";
  if (/(胸|ブローチ|バッジ|ネクタイ|リボン|brooch|badge|tie|ribbon)/.test(label)) return "chest";
  return ["chest", "left_shoulder", "right_shoulder", "waist", "back"][index % 5];
}

function buildGarments(parts) {
  clearGroup(garmentGroup);
  clearGroup(accessoryGroup);
  const types = new Set(parts.map((part) => part.part_type));
  const first = (type) => parts.find((part) => part.part_type === type);
  const cloth = smoothMaterial(currentState?.garmentColor || "#4f46e5", {
    roughness: .52, sheen: .62, clearcoat: .08,
  });
  const trim = smoothMaterial(currentState?.garmentColor || "#4f46e5", {
    roughness: .35, sheen: .45, clearcoat: .28,
  });
  const accessoryMaterial = smoothMaterial(currentState?.accessoryColor || "#16a34a", {
    roughness: .28, metalness: .28, clearcoat: .48,
  });

  if (hasType(types, "front_bodice", "back_bodice", "front_bodice_zip_panel", "front_princess_center")) {
    lathe(garmentGroup, [[.30, -.61], [.43, -.54], [.52, .05], [.48, .51], [.31, .61]], cloth, [0, .48, 0]);
    addMesh(garmentGroup, new THREE.TorusGeometry(.25, .035, 12, 48), trim,
      [0, 1.05, .02], [1, .72, 1], [Math.PI / 2, 0, 0]);
  }
  if (types.has("sleeve")) {
    const sleeve = first("sleeve");
    const length = Math.max(.35, Math.min(1.15, (sleeve?.height_cm || 54) / 54));
    const puff = sleeve?.variation === "puff" ? .24 : .17;
    for (const x of [-.58, .58]) {
      const mesh = addMesh(garmentGroup,
        new THREE.CylinderGeometry(puff * .72, puff, length, 32, 5), cloth,
        [x, .63 - length / 2, 0], [1, 1, .90]);
      mesh.rotation.z = x < 0 ? -.08 : .08;
    }
  }
  if (types.has("skirt")) {
    const skirt = first("skirt");
    const length = Math.max(.48, Math.min(1.35, (skirt?.height_cm || 60) / 60));
    const flare = skirt?.variation === "tight" ? .48 : skirt?.variation === "mermaid" ? .72 : .83;
    const skirtMesh = addMesh(garmentGroup,
      new THREE.CylinderGeometry(.45, flare, length, 64, 10, true), cloth,
      [0, -.13 - length / 2, 0]);
    skirtMesh.geometry.computeVertexNormals();
    addMesh(garmentGroup, new THREE.TorusGeometry(.46, .055, 12, 64), trim,
      [0, -.13, 0], [1, .75, 1], [Math.PI / 2, 0, 0]);
  }
  if (hasType(types, "front_pants", "back_pants")) {
    for (const x of [-.22, .22]) {
      addMesh(garmentGroup, new THREE.CylinderGeometry(.18, .15, 1.22, 36, 6), cloth,
        [x, -.96, 0]);
    }
  }
  if (types.has("waistband")) {
    addMesh(garmentGroup, new THREE.TorusGeometry(.47, .055, 12, 64), trim,
      [0, -.11, 0], [1, .72, 1], [Math.PI / 2, 0, 0]);
  }
  if (types.has("hood")) {
    addMesh(garmentGroup, new THREE.SphereGeometry(.43, 36, 24, 0, Math.PI * 2, 0, Math.PI * .70),
      cloth, [0, 1.30, -.13], [1, 1.12, .92], [0, 0, Math.PI]);
  }

  parts.filter((part) => part.part_type === "custom_panel").forEach((part, index) => {
    const key = accessoryKey(part, index);
    const width = Math.max(.16, Math.min(.78, (part.width_cm || 12) / 24));
    const height = Math.max(.12, Math.min(.78, (part.height_cm || 12) / 24));
    const mesh = addMesh(accessoryGroup, roundedPanelGeometry(width, height, .10),
      accessoryMaterial, [0, 0, 0]);
    mesh.name = `accessory:${key}`;
    mesh.userData = { key, index, part, baseWidth: width, baseHeight: height };
  });
}

function resize() {
  if (!renderer || !host) return;
  const width = Math.max(280, host.clientWidth);
  const height = Math.max(300, host.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function update(state) {
  if (!renderer || !root || !state) return;
  currentState = state;
  root.rotation.y = -state.angle;
  root.rotation.x = state.tilt || 0;
  const scale = state.zoom || 1;
  root.scale.setScalar(scale);
  garmentGroup.visible = state.showGarment !== false;
  accessoryGroup.visible = state.showAccessories !== false;
  proceduralAvatar.visible = state.showMannequin !== false && !importedAvatar;
  if (importedAvatar) importedAvatar.visible = state.showMannequin !== false;
  garmentGroup.traverse((object) => {
    if (object.isMesh && object.material) object.material.color.set(state.garmentColor || "#4f46e5");
  });
  accessoryGroup.traverse((object) => {
    if (!object.isMesh) return;
    if (object.material) object.material.color.set(state.accessoryColor || "#16a34a");
    const { key, index, part } = object.userData;
    if (!key) return;
    const anchorName = state.accessoryAnchors?.[key] || guessedAnchor(part, index);
    const anchor = ANCHORS[anchorName] || ANCHORS.chest;
    const transform = state.accessoryTransforms?.[key] || { scale: 1, x: 0, y: 0 };
    object.position.set(anchor[0] + (transform.x || 0), anchor[1] - (transform.y || 0), anchor[2]);
    object.scale.setScalar(transform.scale || 1);
    object.rotation.y = anchorName === "back" ? Math.PI : 0;
  });
  renderer.render(scene, camera);
}

function setOutfit(parts, state) {
  currentParts = Array.isArray(parts) ? parts : [];
  currentState = state;
  buildGarments(currentParts);
  update(state);
}

function fitImportedAvatar(model) {
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  if (!Number.isFinite(size.y) || size.y <= 0) throw new Error("モデルの大きさを取得できませんでした");
  const scale = 3.45 / size.y;
  model.scale.setScalar(scale);
  const scaled = new THREE.Box3().setFromObject(model);
  const center = scaled.getCenter(new THREE.Vector3());
  model.position.x -= center.x;
  model.position.z -= center.z;
  model.position.y += -1.72 - scaled.min.y;
}

function useStandardAvatar() {
  // Cancel a still-running File.arrayBuffer/GLTF parse before resetting.
  avatarLoadSequence += 1;
  if (importedAvatar) {
    root.remove(importedAvatar);
    disposeObject3D(importedAvatar);
  }
  importedAvatar = null;
  proceduralAvatar.visible = currentState?.showMannequin !== false;
  avatarReset?.classList.add("hidden");
  if (avatarFile) avatarFile.value = "";
  setStatus("標準アニメ調アバターを表示しています。VRM/GLBは端末内だけで処理されます。");
  update(currentState);
}

function loadAvatar(file) {
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) {
    setStatus("100MBを超えるモデルは読み込めません。軽量化したVRM/GLBをお使いください。", true);
    if (avatarFile) avatarFile.value = "";
    return;
  }
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!['vrm', 'glb'].includes(extension)) {
    setStatus("単体で読み込めるVRMまたはGLBを選んでください。", true);
    if (avatarFile) avatarFile.value = "";
    return;
  }
  const loadSequence = ++avatarLoadSequence;
  setStatus("アバターを端末内で読み込んでいます…");
  file.arrayBuffer().then((buffer) => {
    new GLTFLoader().parse(buffer, "", (gltf) => {
      const nextAvatar = gltf?.scene;
      if (loadSequence !== avatarLoadSequence) {
        disposeObject3D(nextAvatar);
        return;
      }
      try {
        if (!nextAvatar) throw new Error("モデル本体が見つかりませんでした");
        nextAvatar.traverse((object) => {
          if (!object.isMesh) return;
          object.castShadow = true;
          object.receiveShadow = true;
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.filter(Boolean).forEach((material) => {
            material.side = THREE.DoubleSide;
            material.needsUpdate = true;
          });
        });
        fitImportedAvatar(nextAvatar);
        if (importedAvatar) {
          root.remove(importedAvatar);
          disposeObject3D(importedAvatar);
        }
        importedAvatar = nextAvatar;
        root.add(importedAvatar);
        proceduralAvatar.visible = false;
        avatarReset?.classList.remove("hidden");
        setStatus(`${file.name} を読み込みました。モデルはサーバーへ送信されていません。`);
        update(currentState);
      } catch (error) {
        disposeObject3D(nextAvatar);
        setStatus(`モデルを読み込めませんでした：${error?.message || "VRM/GLBを確認してください"}`, true);
        if (avatarFile) avatarFile.value = "";
      }
    }, (error) => {
      if (loadSequence !== avatarLoadSequence) return;
      setStatus(`モデルを読み込めませんでした：${error?.message || "VRM/GLBを確認してください"}`, true);
      if (avatarFile) avatarFile.value = "";
    });
  }).catch((error) => {
    if (loadSequence !== avatarLoadSequence) return;
    setStatus(`ファイルを開けませんでした：${error.message}`, true);
    if (avatarFile) avatarFile.value = "";
  });
}

function makeFourViewSheet(title) {
  if (!renderer || !currentState) return null;
  const previousAngle = currentState.angle;
  const previousTilt = currentState.tilt;
  const sheet = document.createElement("canvas");
  sheet.width = 1600;
  sheet.height = 1500;
  const context = sheet.getContext("2d");
  context.fillStyle = "#11121d";
  context.fillRect(0, 0, sheet.width, sheet.height);
  context.fillStyle = "#f8f7ff";
  context.font = "700 42px sans-serif";
  context.fillText(`${title || "PatternForge"}　完成4面図`, 48, 62);
  context.font = "500 22px sans-serif";
  context.fillStyle = "#b9b7d2";
  context.fillText("アバター装着イメージ（製造寸法はPDF・DXF・STL・3MFを参照）", 48, 98);
  const views = [["正面", 0], ["右側面", Math.PI / 2], ["背面", Math.PI], ["左側面", -Math.PI / 2]];
  views.forEach(([label, angle], index) => {
    currentState.angle = angle;
    currentState.tilt = 0;
    update(currentState);
    const column = index % 2, row = Math.floor(index / 2);
    const x = 40 + column * 780, y = 130 + row * 670;
    context.fillStyle = "#202238";
    context.fillRect(x, y, 740, 620);
    context.drawImage(renderer.domElement, x + 16, y + 46, 708, 550);
    context.fillStyle = "#ffffff";
    context.font = "700 28px sans-serif";
    context.fillText(label, x + 22, y + 35);
  });
  currentState.angle = previousAngle;
  currentState.tilt = previousTilt;
  update(currentState);
  return sheet;
}

function initialise() {
  if (!host || !THREE.WebGLRenderer) return;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  } catch (error) {
    console.warn("WebGL viewer unavailable; using Canvas fallback", error);
    setStatus("この端末ではWebGLを使えないため、軽量プレビューを表示しています。", true);
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute("aria-label", "WebGLで描画した服と小物付き3Dアバター");
  host.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color("#11121d");
  scene.fog = new THREE.Fog("#11121d", 7.5, 12);
  camera = new THREE.PerspectiveCamera(35, 1, .1, 50);
  camera.position.set(0, .25, 6.8);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = .07;
  controls.minDistance = 3.4;
  controls.maxDistance = 9;
  controls.maxPolarAngle = Math.PI * .83;
  controls.update();

  scene.add(new THREE.HemisphereLight("#d9e2ff", "#241b32", 2.3));
  const key = new THREE.DirectionalLight("#fff3e5", 4.2);
  key.position.set(3.5, 5.5, 4.5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = key.shadow.camera.bottom = -4;
  key.shadow.camera.right = key.shadow.camera.top = 4;
  scene.add(key);
  const rim = new THREE.DirectionalLight("#7775ff", 3.2);
  rim.position.set(-4, 2.5, -4);
  scene.add(rim);
  const fill = new THREE.PointLight("#80c7ff", 1.8, 12);
  fill.position.set(-2.5, 1.5, 3);
  scene.add(fill);

  root = new THREE.Group();
  proceduralAvatar = buildProceduralAvatar();
  garmentGroup = new THREE.Group();
  accessoryGroup = new THREE.Group();
  root.add(proceduralAvatar, garmentGroup, accessoryGroup);
  scene.add(root);
  floor = addMesh(scene, new THREE.CircleGeometry(2.45, 72),
    new THREE.MeshStandardMaterial({ color: "#25263e", roughness: .88, metalness: .08 }),
    [0, -1.77, 0], [1, 1, 1], [-Math.PI / 2, 0, 0]);
  floor.receiveShadow = true;

  host.classList.remove("hidden");
  fallbackCanvas?.classList.add("is-webgl-fallback-hidden");
  resize();
  new ResizeObserver(resize).observe(host);
  const animate = () => {
    controls.update();
    renderer.render(scene, camera);
    animationFrame = window.requestAnimationFrame(animate);
  };
  animate();
  setStatus("標準アニメ調アバターを表示しています。VRM/GLBは端末内だけで処理されます。");

  window.PatternForge3D = {
    canvas: renderer.domElement,
    setOutfit,
    update,
    resize,
    makeFourViewSheet,
    useStandardAvatar,
    get ready() { return true; },
  };
  window.dispatchEvent(new CustomEvent("patternforge3dready"));
}

avatarFile?.addEventListener("change", () => loadAvatar(avatarFile.files?.[0]));
avatarReset?.addEventListener("click", useStandardAvatar);
window.addEventListener("pagehide", () => window.cancelAnimationFrame(animationFrame));
initialise();
