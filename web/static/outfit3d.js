/* PatternForge high-fidelity outfit viewer.
 * Three.js is bundled locally (MIT) so the viewer works without a CDN.
 * VRM files are GLB containers; GLTFLoader renders their mesh/material data
 * without uploading the file. VRM-specific expressions and spring bones are
 * intentionally not required for a static costume fitting preview. */
import { THREE, GLTFLoader, OrbitControls, VRMLoaderPlugin, VRMUtils }
  from "./vendor/three-vrm.module.min.js?v=3.5.5-unified";

const host = document.getElementById("outfit-webgl-view");
const fallbackCanvas = document.getElementById("outfit-preview-canvas");
const avatarFile = document.getElementById("outfit-avatar-file");
const avatarReset = document.getElementById("outfit-avatar-reset");
const avatarStatus = document.getElementById("outfit-avatar-status");
const garmentFile = document.getElementById("outfit-garment-file");
const garmentReset = document.getElementById("outfit-garment-reset");
const garmentStatus = document.getElementById("outfit-garment-status");
const garmentFit = document.getElementById("outfit-garment-fit");
const garmentFitInputs = ["scale", "x", "y", "z"].map((name) =>
  document.getElementById(`outfit-garment-${name}`));
const reviewRefresh = document.getElementById("outfit-review-refresh");
const reviewStatus = document.getElementById("outfit-review-status");
const reviewMetrics = document.getElementById("outfit-review-metrics");
const reviewGrid = document.getElementById("outfit-review-grid");
const reviewInputs = Array.from(document.querySelectorAll("[data-garment-reference]"));
const reviewReferences = new Map();
let reviewSequence = 0;

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
let importedVRM;
let usingBundledAvatar = false;
let bundledShoeMaterials = [];
let bundledBodyMaterials = [];
let fittingHandsGroup;
let importedGarment;
let garmentLoadSequence = 0;
let garmentGroup;
let accessoryGroup;
let floor;
let currentParts = [];
let currentState = null;
let animationFrame = 0;
let avatarLoadSequence = 0;
let fabricTexture;
let fabricNormalTexture;
let ribTexture;
let ribNormalTexture;
let coatFabricMaps;
let coatJacquardTexture;
const COAT_FITTING_POSE = .38;
const COAT_SLEEVE_SCALE = .84;

function coatPoseAngle() {
  // A plain GLB has no reliable arm bones. Keep its garment in the neutral
  // fitting pose; a VRM or the procedural stand-in can share the lowered arm.
  return importedAvatar && !importedVRM ? 0 : COAT_FITTING_POSE;
}

function sleeveDetailGroup(parent, side, angle) {
  const pivot = new THREE.Group();
  pivot.position.set(side * .39, .88, 0);
  pivot.rotation.z = -side * angle;
  pivot.scale.x = COAT_SLEEVE_SCALE;
  const worldCoordinates = new THREE.Group();
  worldCoordinates.position.set(-side * .39, -.88, 0);
  pivot.add(worldCoordinates);
  parent.add(pivot);
  return worldCoordinates;
}

function setStatus(message, error = false) {
  if (!avatarStatus) return;
  avatarStatus.textContent = message;
  avatarStatus.classList.toggle("is-error", error);
}

function setGarmentStatus(message, error = false) {
  if (!garmentStatus) return;
  garmentStatus.textContent = message;
  garmentStatus.classList.toggle("is-error", error);
}

function smoothMaterial(color, options = {}) {
  const parameters = {
    color,
    map: options.map || null,
    normalMap: options.normalMap || null,
    roughnessMap: options.roughnessMap || null,
    bumpMap: options.bumpMap || null,
    bumpScale: options.bumpMap ? (options.bumpScale ?? .012) : 0,
    roughness: options.roughness ?? .56,
    metalness: options.metalness ?? .02,
    clearcoat: options.clearcoat ?? .12,
    clearcoatRoughness: options.clearcoatRoughness ?? .55,
    sheen: options.sheen ?? .18,
    sheenRoughness: options.sheenRoughness ?? .65,
    side: THREE.DoubleSide,
  };
  if (options.normalMap) parameters.normalScale = new THREE.Vector2(
    options.normalScale ?? .32, options.normalScale ?? .32);
  const material = new THREE.MeshPhysicalMaterial(parameters);
  material.userData.colorRole = options.role || "fixed";
  return material;
}

function getFabricTexture() {
  if (fabricTexture) return fabricTexture;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d");
  context.fillStyle = "#e8e8e8";
  context.fillRect(0, 0, 128, 128);
  context.globalAlpha = .22;
  for (let index = 0; index < 128; index += 4) {
    context.fillStyle = index % 8 ? "#ffffff" : "#777777";
    context.fillRect(index, 0, 1, 128);
    context.fillRect(0, index, 128, 1);
  }
  context.globalAlpha = .10;
  for (let index = -128; index < 128; index += 8) {
    context.strokeStyle = "#555555";
    context.beginPath();
    context.moveTo(index, 0);
    context.lineTo(index + 128, 128);
    context.stroke();
  }
  fabricTexture = new THREE.CanvasTexture(canvas);
  fabricTexture.wrapS = fabricTexture.wrapT = THREE.RepeatWrapping;
  fabricTexture.repeat.set(5, 7);
  fabricTexture.colorSpace = THREE.SRGBColorSpace;
  return fabricTexture;
}

function getFabricNormalTexture() {
  if (fabricNormalTexture) return fabricNormalTexture;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d");
  context.fillStyle = "rgb(128,128,255)";
  context.fillRect(0, 0, 128, 128);
  for (let index = 0; index < 128; index += 4) {
    const bright = index % 8 ? 133 : 121;
    context.fillStyle = `rgb(${bright},128,252)`;
    context.fillRect(index, 0, 1, 128);
    context.fillStyle = `rgb(128,${bright},252)`;
    context.fillRect(0, index, 128, 1);
  }
  fabricNormalTexture = new THREE.CanvasTexture(canvas);
  fabricNormalTexture.wrapS = fabricNormalTexture.wrapT = THREE.RepeatWrapping;
  fabricNormalTexture.repeat.set(7, 9);
  fabricNormalTexture.colorSpace = THREE.NoColorSpace;
  return fabricNormalTexture;
}

function getRibTexture() {
  if (ribTexture) return ribTexture;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d");
  context.fillStyle = "#efefed";
  context.fillRect(0, 0, 128, 128);
  for (let x = 0; x < 128; x += 7) {
    context.fillStyle = "#d6d6d3";
    context.fillRect(x, 0, 1, 128);
    context.fillStyle = "#f9f9f7";
    context.fillRect(x + 3, 0, 1, 128);
  }
  ribTexture = new THREE.CanvasTexture(canvas);
  ribTexture.wrapS = ribTexture.wrapT = THREE.RepeatWrapping;
  ribTexture.repeat.set(7, 3);
  ribTexture.colorSpace = THREE.SRGBColorSpace;
  return ribTexture;
}

function getRibNormalTexture() {
  if (ribNormalTexture) return ribNormalTexture;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d");
  const image = context.createImageData(128, 128);
  for (let y = 0; y < 128; y += 1) {
    for (let x = 0; x < 128; x += 1) {
      const index = (y * 128 + x) * 4;
      const ribSlope = Math.cos(x * Math.PI * 2 / 7);
      image.data[index] = Math.round(128 - ribSlope * 25);
      image.data[index + 1] = 128;
      image.data[index + 2] = 250;
      image.data[index + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  ribNormalTexture = new THREE.CanvasTexture(canvas);
  ribNormalTexture.wrapS = ribNormalTexture.wrapT = THREE.RepeatWrapping;
  ribNormalTexture.repeat.set(7, 3);
  ribNormalTexture.colorSpace = THREE.NoColorSpace;
  return ribNormalTexture;
}

function getCoatFabricMaps() {
  if (coatFabricMaps) return coatFabricMaps;
  const size = 256;
  const canvases = Array.from({ length: 3 }, () => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    return canvas;
  });
  const contexts = canvases.map((canvas) => canvas.getContext("2d"));
  const images = contexts.map((context) => context.createImageData(size, size));
  const colorData = images[0].data;
  const normalData = images[1].data;
  const roughnessData = images[2].data;
  const heightAt = (x, y) => {
    const warp = Math.sin(x * Math.PI * 2 / 13 + Math.floor(y / 8) * .33);
    const weft = Math.sin(y * Math.PI * 2 / 11 + Math.floor(x / 9) * .27);
    const twill = Math.sin((x + y * .55) * Math.PI * 2 / 37);
    return warp * .43 + weft * .29 + twill * .18;
  };
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const i = (y * size + x) * 4;
      const h = heightAt(x, y);
      const grain = ((x * 73 + y * 151 + x * y * 17) % 31) / 31 - .5;
      const shade = Math.round(246 + h * 2.5 + grain * 2);
      colorData[i] = colorData[i + 1] = colorData[i + 2] = shade;
      colorData[i + 3] = 255;
      const dx = (heightAt(x + 1, y) - heightAt(x - 1, y)) * .5;
      const dy = (heightAt(x, y + 1) - heightAt(x, y - 1)) * .5;
      normalData[i] = Math.round(128 - dx * 36);
      normalData[i + 1] = Math.round(128 - dy * 36);
      normalData[i + 2] = 246;
      normalData[i + 3] = 255;
      const rough = Math.round(216 + h * 6 + grain * 6);
      roughnessData[i] = roughnessData[i + 1] = roughnessData[i + 2] = rough;
      roughnessData[i + 3] = 255;
    }
  }
  contexts.forEach((context, index) => context.putImageData(images[index], 0, 0));
  const [color, normal, roughness] = canvases.map((canvas, index) => {
    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(1, 1);
    texture.anisotropy = Math.min(8, renderer?.capabilities?.getMaxAnisotropy?.() || 1);
    texture.colorSpace = index === 0 ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    return texture;
  });
  coatFabricMaps = { color, normal, roughness };
  return coatFabricMaps;
}

function getCoatJacquardTexture() {
  if (coatJacquardTexture) return coatJacquardTexture;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const context = canvas.getContext("2d");
  context.fillStyle = "#f0f0ef";
  context.fillRect(0, 0, 256, 256);
  // Low-contrast woven diamond/chevron texture, limited to the lower coat.
  // It supplies visual textile information without pretending to recover the
  // reference character's exact unobservable embroidery from one image.
  for (let y = -48; y < 304; y += 64) {
    for (let x = -48; x < 304; x += 64) {
      context.strokeStyle = "rgba(50,52,56,.19)";
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(x + 32, y + 5);
      context.lineTo(x + 58, y + 32);
      context.lineTo(x + 32, y + 59);
      context.lineTo(x + 6, y + 32);
      context.closePath();
      context.stroke();
      context.strokeStyle = "rgba(90,91,93,.13)";
      context.beginPath();
      context.moveTo(x + 18, y + 32);
      context.lineTo(x + 32, y + 18);
      context.lineTo(x + 46, y + 32);
      context.stroke();
    }
  }
  coatJacquardTexture = new THREE.CanvasTexture(canvas);
  coatJacquardTexture.wrapS = coatJacquardTexture.wrapT = THREE.RepeatWrapping;
  coatJacquardTexture.repeat.set(1.5, 1.5);
  coatJacquardTexture.colorSpace = THREE.SRGBColorSpace;
  coatJacquardTexture.anisotropy = Math.min(8, renderer?.capabilities?.getMaxAnisotropy?.() || 1);
  return coatJacquardTexture;
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
  // Dispose once per resource, even when many panels share one material/map.
  disposeObject3D(group);
  group.clear();
  if (group === garmentGroup) {
    fabricTexture = null;
    fabricNormalTexture = null;
    ribTexture = null;
    ribNormalTexture = null;
    coatFabricMaps = null;
    coatJacquardTexture = null;
  }
}

function capsule(parent, radius, length, material, position, rotation = [0, 0, 0]) {
  return addMesh(parent, new THREE.CapsuleGeometry(radius, length, 10, 24),
    material, position, [1, 1, 1], rotation);
}

function lathe(parent, profile, material, position = [0, 0, 0]) {
  const points = profile.map(([radius, y]) => new THREE.Vector2(radius, y));
  return addMesh(parent, new THREE.LatheGeometry(points, 48), material, position);
}

function shapeMesh(parent, points, material, position, depth = .035) {
  const shape = new THREE.Shape();
  points.forEach(([x, y], index) => index ? shape.lineTo(x, y) : shape.moveTo(x, y));
  shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth, bevelEnabled: true, bevelSegments: 3, bevelSize: .012,
    bevelThickness: .012, curveSegments: 8,
  });
  geometry.computeVertexNormals();
  return addMesh(parent, geometry, material, position);
}

function curvedClothPanel(parent, corners, material, depth, bow = .08, thickness = .014) {
  const rows = 18, columns = 18;
  const positions = [], uvs = [], indices = [];
  for (let layer = 0; layer < 2; layer += 1) {
    for (let row = 0; row <= rows; row += 1) {
      const v = row / rows;
      for (let column = 0; column <= columns; column += 1) {
        const u = column / columns;
        const topX = THREE.MathUtils.lerp(corners[0][0], corners[1][0], u);
        const topY = THREE.MathUtils.lerp(corners[0][1], corners[1][1], u);
        const bottomX = THREE.MathUtils.lerp(corners[3][0], corners[2][0], u);
        const bottomY = THREE.MathUtils.lerp(corners[3][1], corners[2][1], u);
        const lift = bow * Math.sin(Math.PI * u) * Math.sin(Math.PI * v);
        const twist = .035 * (u - .5) * (v - .5);
        positions.push(THREE.MathUtils.lerp(topX, bottomX, v),
          THREE.MathUtils.lerp(topY, bottomY, v), depth + lift + twist - layer * thickness);
        uvs.push(u, v);
        if (row < rows && column < columns) {
          const i = layer * (rows + 1) * (columns + 1) + row * (columns + 1) + column;
          const n = i + columns + 1;
          if (layer === 0) indices.push(i, n, i + 1, n, n + 1, i + 1);
          else indices.push(i, i + 1, n, n, i + 1, n + 1);
        }
      }
    }
  }
  const layerSize = (rows + 1) * (columns + 1);
  const perimeter = [];
  for (let c = 0; c <= columns; c += 1) perimeter.push(c);
  for (let r = 1; r <= rows; r += 1) perimeter.push(r * (columns + 1) + columns);
  for (let c = columns - 1; c >= 0; c -= 1) perimeter.push(rows * (columns + 1) + c);
  for (let r = rows - 1; r > 0; r -= 1) perimeter.push(r * (columns + 1));
  for (let p = 0; p < perimeter.length; p += 1) {
    const a = perimeter[p], b = perimeter[(p + 1) % perimeter.length];
    indices.push(a, b, a + layerSize, b, b + layerSize, a + layerSize);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return addMesh(parent, geometry, material, [0, 0, 0]);
}

function seam(parent, points, color = "#d7d5df") {
  const curve = new THREE.CatmullRomCurve3(points.map((point) => new THREE.Vector3(...point)));
  return addMesh(parent, new THREE.TubeGeometry(curve, 32, .008, 8, false),
    smoothMaterial(color, { roughness: .8, role: "stitch" }), [0, 0, 0]);
}

function ellipseTrim(parent, radiusX, radiusZ, y, material, tube = .012) {
  const points = [];
  for (let index = 0; index < 64; index += 1) {
    const angle = index / 64 * Math.PI * 2;
    points.push(new THREE.Vector3(Math.cos(angle) * radiusX, y, Math.sin(angle) * radiusZ));
  }
  const curve = new THREE.CatmullRomCurve3(points, true, "centripetal");
  return addMesh(parent, new THREE.TubeGeometry(curve, 96, tube, 8, true), material, [0, 0, 0]);
}

function ruffledHem(parent, radiusX, radiusZ, y, material, waves = 18) {
  const points = [];
  for (let index = 0; index < 144; index += 1) {
    const angle = index / 144 * Math.PI * 2;
    const wave = Math.sin(angle * waves);
    points.push(new THREE.Vector3(
      Math.cos(angle) * (radiusX + wave * .028),
      y + Math.cos(angle * waves) * .018,
      Math.sin(angle) * (radiusZ + wave * .018),
    ));
  }
  const curve = new THREE.CatmullRomCurve3(points, true, "centripetal");
  return addMesh(parent, new THREE.TubeGeometry(curve, 180, .022, 10, true),
    material, [0, 0, 0]);
}

function buildProceduralAvatar() {
  const group = new THREE.Group();
  group.name = "standard-anime-avatar";
  const skin = smoothMaterial("#f0cdbb", { roughness: .72, sheen: .08 });
  const body = smoothMaterial("#3d4252", { roughness: .78 });
  const hair = smoothMaterial("#242533", { roughness: .52, sheen: .35 });
  const eye = smoothMaterial("#5468a8", { roughness: .25, clearcoat: .5 });

  // 衣装の丈・袖幅・シルエットを読み取りやすい、7頭身寄りの試着モデル。
  // The fitting stand-in shares the coat's relaxed arm angle.
  addMesh(group, new THREE.SphereGeometry(.31, 48, 32), hair,
    [0, 1.55, -.045], [1.02, 1.10, .96]);
  addMesh(group, new THREE.SphereGeometry(.285, 48, 32), skin,
    [0, 1.50, .080], [.88, 1.03, .76]);
  for (const x of [-.245, .245]) {
    addMesh(group, new THREE.CapsuleGeometry(.085, .34, 10, 20), hair,
      [x, 1.39, -.025], [1, 1, .72], [0, 0, x < 0 ? -.08 : .08]);
  }
  addMesh(group, new THREE.SphereGeometry(.275, 40, 24, 0, Math.PI * 2, 0, Math.PI * .55),
    hair, [0, 1.66, .085], [1, .82, .90], [0, 0, Math.PI]);
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
  capsule(group, .085, .16, skin, [0, 1.16, 0]);
  lathe(group, [[.23, -.63], [.34, -.53], [.43, .03], [.38, .50], [.25, .62]],
    body, [0, .47, 0]);
  for (const side of [-1, 1]) {
    const arm = sleeveDetailGroup(group, side, COAT_FITTING_POSE);
    capsule(arm, .105, .78, body, [side * .82, .79, 0], [0, 0, Math.PI / 2]);
    capsule(arm, .09, .58, body, [side * 1.46, .79, 0], [0, 0, Math.PI / 2]);
    addMesh(arm, new THREE.SphereGeometry(.11, 28, 18), skin,
      [side * 1.82, .79, 0], [1.28, .70, .72]);
  }
  capsule(group, .145, 1.10, body, [-.18, -.98, 0], [0, 0, -.015]);
  capsule(group, .145, 1.10, body, [.18, -.98, 0], [0, 0, .015]);
  addMesh(group, new THREE.SphereGeometry(.17, 32, 20), body, [-.18, -1.70, .09], [1, .58, 1.62]);
  addMesh(group, new THREE.SphereGeometry(.17, 32, 20), body, [.18, -1.70, .09], [1, .58, 1.62]);
  return group;
}

function buildBundledFittingHands() {
  // The bundled VRM's hands end inside the oversized costume cuffs. These
  // display-only hands complete the silhouette; they are hidden for user VRMs.
  const group = new THREE.Group();
  const skin = smoothMaterial("#e9cabb", { roughness: .79, sheen: .08 });
  for (const side of [-1, 1]) {
    const sleeve = sleeveDetailGroup(group, side, COAT_FITTING_POSE);
    const forward = new THREE.Group();
    forward.position.set(side * 1.67, .88, .035);
    forward.rotation.y = -side * .44;
    const hand = new THREE.Group();
    hand.position.set(-side * 1.67, -.88, -.035);
    forward.add(hand);
    sleeve.add(forward);
    capsule(hand, .065, .13, skin, [side * 1.76, .88, .035],
      [0, 0, Math.PI / 2]);
    addMesh(hand, new THREE.SphereGeometry(.10, 32, 20), skin,
      [side * 1.87, .88, .045], [1.35, .72, .78]);
    for (let finger = 0; finger < 4; finger += 1) {
      capsule(hand, .019, .09 + .018 * Math.sin(finger * Math.PI / 3), skin,
        [side * (2.01 + .018 * Math.sin(finger * Math.PI / 3)),
          .84 + finger * .027, .062], [0, 0, Math.PI / 2]);
    }
    capsule(hand, .026, .085, skin,
      [side * 1.88, .785, .105], [0, 0, side * .90]);
  }
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

function tailoredShellGeometry(sections, radialSegments = 64) {
  const positions = [];
  const uvs = [];
  const indices = [];
  sections.forEach((section, row) => {
    for (let column = 0; column <= radialSegments; column += 1) {
      const angle = (column / radialSegments) * Math.PI * 2;
      const sideBias = Math.sign(Math.cos(angle)) * Math.pow(Math.abs(Math.cos(angle)), .72);
      const frontBias = Math.sign(Math.sin(angle)) * Math.pow(Math.abs(Math.sin(angle)), .78);
      positions.push(section.width * sideBias, section.y, section.depth * frontBias);
      uvs.push(column / radialSegments, row / Math.max(1, sections.length - 1));
      if (row < sections.length - 1 && column < radialSegments) {
        const current = row * (radialSegments + 1) + column;
        const next = current + radialSegments + 1;
        indices.push(current, next, current + 1, next, next + 1, current + 1);
      }
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function softKnitShellGeometry() {
  const profile = new THREE.CatmullRomCurve3([
    new THREE.Vector3(.34, -.34, .265),
    new THREE.Vector3(.39, -.13, .29),
    new THREE.Vector3(.38, .18, .315),
    new THREE.Vector3(.425, .49, .335),
    new THREE.Vector3(.40, .78, .31),
    new THREE.Vector3(.255, .99, .225),
  ]);
  const rows = 52, columns = 72;
  const positions = [], uvs = [], indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const t = row / rows;
    const point = profile.getPoint(t);
    for (let column = 0; column <= columns; column += 1) {
      const u = column / columns;
      const angle = u * Math.PI * 2;
      const fold = (.009 * Math.sin(21 * t + 4 * Math.sin(angle * 2))
        + .004 * Math.sin(39 * t + angle * 4)) * Math.sin(Math.PI * t);
      const radius = 1 + fold;
      positions.push(Math.cos(angle) * point.x * radius, point.y,
        Math.sin(angle) * point.z * radius);
      uvs.push(u, t);
      if (row < rows && column < columns) {
        const i = row * (columns + 1) + column;
        const n = i + columns + 1;
        indices.push(i, n, i + 1, n, n + 1, i + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function fittedSleeveGeometry(length, shoulderRadius, cuffRadius, side, wrinkled = false) {
  const rows = wrinkled ? 64 : 20;
  const radialSegments = 40;
  const positions = [];
  const uvs = [];
  const indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const t = row / rows;
    const eased = t * t * (3 - 2 * t);
    const elbow = Math.exp(-Math.pow((t - .56) / .22, 2));
    const cuff = Math.exp(-Math.pow((t - .85) / .13, 2));
    const radius = THREE.MathUtils.lerp(shoulderRadius, cuffRadius, eased)
      + Math.sin(Math.PI * t) * .018 + (wrinkled ? .014 * elbow : 0);
    const x = side * (.37 + length * t);
    const y = .91 - .018 * Math.sin(Math.PI * t);
    for (let column = 0; column <= radialSegments; column += 1) {
      const angle = (column / radialSegments) * Math.PI * 2;
      // VRMの腕はモデルごとに前後位置が少し違うため、奥行きを厚めに取り、
      // 肌が袖を突き抜けるのを防ぐ。
      const fold = wrinkled ? (
        .009 * elbow * Math.sin(t * Math.PI * 9 + Math.cos(angle * 2))
        + .006 * cuff * Math.sin(t * Math.PI * 14 + Math.sin(angle * 3))
      ) : 0;
      positions.push(x, y + Math.cos(angle) * (radius + fold),
        .035 + Math.sin(angle) * (radius + fold) * 1.28);
      uvs.push(t, column / radialSegments);
      if (row < rows && column < radialSegments) {
        const current = row * (radialSegments + 1) + column;
        const next = current + radialSegments + 1;
        const winding = side > 0
          ? [current, next, current + 1, next, next + 1, current + 1]
          : [current, current + 1, next, next, current + 1, next + 1];
        indices.push(...winding);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function drapedSkirtGeometry(length, waistRadius, hemRadius, tight = false) {
  const rows = 24;
  const radialSegments = 96;
  const positions = [];
  const uvs = [];
  const indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const t = row / rows;
    const fall = Math.pow(t, tight ? 1.5 : .78);
    const baseRadius = THREE.MathUtils.lerp(waistRadius, hemRadius, fall);
    for (let column = 0; column <= radialSegments; column += 1) {
      const angle = (column / radialSegments) * Math.PI * 2;
      const pleat = tight ? 0 : Math.sin(angle * 12) * (.012 + .035 * t);
      const radius = baseRadius + pleat;
      const y = -.13 - length * t + (tight ? 0 : Math.cos(angle * 12) * .012 * t);
      positions.push(Math.cos(angle) * radius, y, Math.sin(angle) * radius * .72);
      uvs.push(column / radialSegments, t);
      if (row < rows && column < radialSegments) {
        const current = row * (radialSegments + 1) + column;
        const next = current + radialSegments + 1;
        indices.push(current, next, current + 1, next, next + 1, current + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function trouserLegGeometry(side, variation = "") {
  const rows = 26;
  const radialSegments = 48;
  const positions = [];
  const uvs = [];
  const indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const t = row / rows;
    const wide = variation === "wide" || variation === "flare";
    const radius = THREE.MathUtils.lerp(.205, wide ? .19 : .125, t)
      + (variation === "flare" ? Math.max(0, t - .70) * .16 : 0);
    const centerX = side * THREE.MathUtils.lerp(.205, .18, t);
    const y = -.18 - 1.48 * t;
    for (let column = 0; column <= radialSegments; column += 1) {
      const angle = column / radialSegments * Math.PI * 2;
      const crease = Math.pow(Math.max(0, Math.sin(angle)), 12) * .018;
      positions.push(centerX + Math.cos(angle) * radius, y,
        Math.sin(angle) * radius * .72 + crease);
      uvs.push(column / radialSegments, t);
      if (row < rows && column < radialSegments) {
        const current = row * (radialSegments + 1) + column;
        const next = current + radialSegments + 1;
        indices.push(current, next, current + 1, next, next + 1, current + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
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

function coatShellGeometry(inset = 0) {
  const rows = 56, segments = 112;
  const positions = [], uvs = [], indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const t = row / rows;
    const skirt = Math.max(0, (t - .44) / .56);
    const gap = THREE.MathUtils.lerp(.49, .69, Math.pow(t, 1.15));
    const waistShape = .06 * Math.exp(-Math.pow((t - .48) / .19, 2));
    const width = .425 + .075 * t + .35 * Math.pow(skirt, 1.38) - waistShape - inset;
    const depth = .375 + .025 * t + .19 * Math.pow(skirt, 1.35) - inset;
    for (let column = 0; column <= segments; column += 1) {
      const u = column / segments;
      // A continuous back with two separate front edges, never a closed dress.
      const angle = Math.PI / 2 + gap + (Math.PI * 2 - gap * 2) * u;
      const pleat = Math.pow(Math.sin(angle * 5.5 + .30), 2) * .09 * skirt * skirt;
      const drape = Math.sin(angle * 2.7 + t * 1.7) * .035 * skirt;
      const clothFold = Math.sin(angle * 8 + t * 3.5) * .028 * skirt * skirt;
      const backBillow = .14 * Math.exp(-Math.pow((t - .78) / .15, 2))
        * Math.max(0, -Math.sin(angle));
      const sideHem = Math.pow(Math.abs(Math.cos(angle)), 2) * .52 * Math.pow(skirt, 2.5);
      const backHem = Math.max(0, -Math.sin(angle)) * .075 * skirt * skirt;
      const y = THREE.MathUtils.lerp(.91, -1.30, t) + sideHem - backHem
        + Math.sin(angle * 5.5 + .30) * .028 * skirt * skirt;
      positions.push(Math.cos(angle) * (width + pleat + drape + clothFold), y,
        Math.sin(angle) * (depth + pleat * .55 + drape + clothFold * .7)
          - backBillow - .005);
      uvs.push(u * 2.5, t * 3.5);
      if (row < rows && column < segments) {
        const i = row * (segments + 1) + column;
        const n = i + segments + 1;
        indices.push(i, n, i + 1, n, n + 1, i + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

// One indexed surface is used for the coat body, front facings, folded lapels,
// and sleeves.  An armscye is removed from each side of the body; the first
// sleeve ring reuses those exact boundary vertex indices instead of hiding a
// cylinder/body intersection with a shoulder sphere.
function connectedCoatGeometry(shape = {}) {
  const rows = 64, segments = 112;
  const positions = [], uvs = [], faces = [];
  const outerGroups = [];
  const hemFlare = THREE.MathUtils.clamp(Number(shape?.hem_flare) || .65, .15, .95);
  const sleeveVolume = THREE.MathUtils.clamp(Number(shape?.sleeve_volume) || .65, .20, .90);
  const poseAngle = THREE.MathUtils.clamp(Number(shape?.pose_angle) || 0, 0, .65);
  const accentSide = shape?.accent_side === "left" ? -1 : 1;
  const addVertex = (point, uv) => {
    const index = positions.length / 3;
    positions.push(point[0], point[1], point[2]);
    uvs.push(uv[0], uv[1]);
    return index;
  };
  const vertexPoint = (index) => positions.slice(index * 3, index * 3 + 3);
  const shellPoint = (row, column) => {
    const t = row / rows;
    const skirt = Math.max(0, (t - .44) / .56);
    const gap = THREE.MathUtils.lerp(.49, .69, Math.pow(t, 1.15));
    const angle = Math.PI / 2 + gap + (Math.PI * 2 - gap * 2) * column / segments;
    const shoulder = Math.min(1, t / .13);
    const shoulderEase = shoulder * shoulder * (3 - 2 * shoulder);
    const waistShape = .06 * Math.exp(-Math.pow((t - .48) / .19, 2));
    const width = THREE.MathUtils.lerp(.31,
      .425 + .075 * t + (.18 + .20 * hemFlare) * Math.pow(skirt, 1.38)
        - waistShape, shoulderEase);
    const depth = THREE.MathUtils.lerp(.30,
      .375 + .025 * t + .19 * Math.pow(skirt, 1.35), shoulderEase);
    const pleat = Math.pow(Math.sin(angle * 5.5 + .30), 2) * .12 * skirt * skirt;
    const drape = Math.sin(angle * 2.7 + t * 1.7) * .035 * skirt;
    const clothFold = Math.sin(angle * 8 + t * 3.5) * .052 * skirt * skirt;
    const backBillow = .19 * Math.exp(-Math.pow((t - .78) / .15, 2))
      * Math.max(0, -Math.sin(angle));
    const sideFan = (.10 + .28 * hemFlare) * Math.pow(Math.abs(Math.cos(angle)), 7)
      * Math.pow(skirt, 1.75);
    const sideHem = Math.pow(Math.abs(Math.cos(angle)), 2) * .37 * Math.pow(skirt, 2.5);
    const backHem = Math.max(0, -Math.sin(angle)) * .075 * skirt * skirt;
    const frontTail = Math.pow(Math.max(0, Math.sin(angle)), 3)
      * (.05 + .11 * hemFlare) * skirt * skirt;
    const fanPleat = .055 * Math.sin(angle * 10 + .4 + t * 1.2) * Math.pow(skirt, 2.2);
    const yokeDistance = accentSide > 0 ? column : segments - column;
    const yokeLift = .026 * Math.max(0, 1 - row / 18)
      * Math.max(0, 1 - yokeDistance / 19);
    const y = THREE.MathUtils.lerp(1.05, -1.30, t) + sideHem - backHem
      - frontTail + Math.sin(angle * 5.5 + .30) * .042 * skirt * skirt
      - fanPleat * .30;
    return [Math.cos(angle) * (width + pleat + drape + clothFold + sideFan + fanPleat), y,
      Math.sin(angle) * (depth + pleat * .55 + drape + clothFold * .7)
        - backBillow - .005 - sideFan * .12 + yokeLift];
  };
  const shellIndex = (row, column) => row * (segments + 1) + column;
  for (let row = 0; row <= rows; row += 1) {
    for (let column = 0; column <= segments; column += 1) {
      addVertex(shellPoint(row, column), [column / segments * 2.5, row / rows * 3.5]);
    }
  }

  const holeTop = 1, holeBottom = 12, holeHalfWidth = 10;
  const armholes = [23, 89].map((center) => ({
    left: center - holeHalfWidth, right: center + holeHalfWidth,
  }));
  const inArmhole = (row, column) => armholes.some(({ left, right }) =>
    row >= holeTop && row < holeBottom && column >= left && column < right);
  let activeMaterial = null, activeStart = 0;
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < segments; column += 1) {
      if (inArmhole(row, column)) continue;
      const yokeWidth = Math.round(18 * Math.max(0, 1 - row / 18));
      const isYoke = row < 18 && (accentSide > 0
        ? column <= yokeWidth : column >= segments - yokeWidth);
      const materialIndex = row >= 42 ? 3 : isYoke ? 2 : 0;
      if (materialIndex !== activeMaterial) {
        if (activeMaterial !== null) outerGroups.push({ start: activeStart,
          count: faces.length - activeStart, materialIndex: activeMaterial });
        activeMaterial = materialIndex;
        activeStart = faces.length;
      }
      const a = shellIndex(row, column), b = shellIndex(row + 1, column);
      // The shell winds outward, so its normals agree with the sleeve normals.
      faces.push(a, a + 1, b, b, a + 1, b + 1);
    }
  }
  outerGroups.push({ start: activeStart,
    count: faces.length - activeStart, materialIndex: activeMaterial });

  const sleeveStart = faces.length;
  for (const [holeNumber, hole] of armholes.entries()) {
    const side = holeNumber === 0 ? -1 : 1;
    const ring = [];
    for (let c = hole.left; c <= hole.right; c += 1) ring.push(shellIndex(holeTop, c));
    for (let r = holeTop + 1; r <= holeBottom; r += 1) ring.push(shellIndex(r, hole.right));
    for (let c = hole.right - 1; c >= hole.left; c -= 1) ring.push(shellIndex(holeBottom, c));
    for (let r = holeBottom - 1; r > holeTop; r -= 1) ring.push(shellIndex(r, hole.left));
    let previous = ring;
    const sleeveRows = 38;
    for (let row = 1; row <= sleeveRows; row += 1) {
      const t = row / sleeveRows;
      const blend = Math.min(1, t * 4);
      const easing = blend * blend * (3 - 2 * blend);
      const balloon = (.026 + .060 * sleeveVolume)
        * Math.exp(-Math.pow((t - .54) / .22, 2));
      const radius = THREE.MathUtils.lerp(.235, .157, t * t * (3 - 2 * t)) + balloon;
      const elbow = Math.exp(-Math.pow((t - .56) / .22, 2));
      const next = ring.map((rootIndex, column) => {
        const root = vertexPoint(rootIndex);
        const angle = Math.atan2(root[2] - .005, root[1] - .84);
        const fold = .019 * elbow * Math.sin(t * 31 + angle * 2.4)
          + .007 * Math.sin(t * 52 + angle * 4) * Math.pow(t, 3);
        const radialY = Math.cos(angle) * (radius + fold)
          - .046 * Math.sin(Math.PI * t);
        const along = 1.29 * COAT_SLEEVE_SCALE * t;
        const x = THREE.MathUtils.lerp(root[0], side * (
          .39 + along * Math.cos(poseAngle) + radialY * Math.sin(poseAngle)), easing);
        const y = THREE.MathUtils.lerp(root[1],
          .88 - along * Math.sin(poseAngle) + radialY * Math.cos(poseAngle), easing);
        const z = THREE.MathUtils.lerp(root[2],
          .035 + .018 * Math.sin(Math.PI * t)
            + Math.sin(angle) * (radius + fold) * 1.24, easing);
        return addVertex([x, y, z], [t * 2.2, column / ring.length * 1.3]);
      });
      for (let column = 0; column < ring.length; column += 1) {
        const following = (column + 1) % ring.length;
        faces.push(previous[column], previous[following], next[column],
          next[column], previous[following], next[following]);
      }
      previous = next;
    }
  }
  outerGroups.push({ start: sleeveStart, count: faces.length - sleeveStart, materialIndex: 0 });

  // Each facing uses the coat's existing front-edge vertices.  The lapel then
  // folds back from the facing's inner edge, making the fold a real shared edge.
  for (const side of [-1, 1]) {
    const facingStart = faces.length;
    const edgeColumn = side < 0 ? 0 : segments;
    const facing = [];
    const facingColumns = 12;
    for (let row = 0; row <= rows; row += 1) {
      const t = row / rows;
      const root = vertexPoint(shellIndex(row, edgeColumn));
      const strip = [shellIndex(row, edgeColumn)];
      for (let column = 1; column <= facingColumns; column += 1) {
        const u = column / facingColumns;
        const innerX = side * (.105 + .28 * t);
        const x = THREE.MathUtils.lerp(root[0], innerX, u);
        const y = root[1] + .026 * Math.sin(Math.PI * u) * t * t
          - .19 * Math.pow(t, 4) * Math.pow(u, 1.6);
        const z = root[2] + .022 * u + .042 * Math.sin(Math.PI * u) * t * t;
        strip.push(addVertex([x, y, z], [u * 1.4, t * 3.5]));
      }
      facing.push(strip);
      if (row) {
        for (let column = 0; column < facingColumns; column += 1) {
          const a = facing[row - 1][column], b = facing[row][column];
          const c = facing[row - 1][column + 1], d = facing[row][column + 1];
          if (side < 0) faces.push(a, b, c, b, d, c);
          else faces.push(a, c, b, b, c, d);
        }
      }
    }
    outerGroups.push({ start: facingStart, count: faces.length - facingStart, materialIndex: 0 });
    const lapelStart = faces.length;
    const lapelRows = 20, lapelColumns = 8;
    let previous = null;
    for (let row = 0; row <= lapelRows; row += 1) {
      const t = row / lapelRows;
      const root = vertexPoint(facing[row][facingColumns]);
      const strip = [facing[row][facingColumns]];
      const width = (.09 + .27 * Math.sin(Math.PI * Math.pow(t, .62))) * (1 - .56 * t);
      for (let column = 1; column <= lapelColumns; column += 1) {
        const u = column / lapelColumns;
        strip.push(addVertex([
          root[0] + side * width * u,
          root[1] - .035 * Math.sin(Math.PI * u) * t,
          root[2] + .016 + .068 * Math.sin(Math.PI * u) + .018 * u,
        ], [u, t * 1.4]));
      }
      if (previous) {
        for (let column = 0; column < lapelColumns; column += 1) {
          const a = previous[column], b = strip[column];
          const c = previous[column + 1], d = strip[column + 1];
          if (side < 0) faces.push(a, c, b, b, c, d);
          else faces.push(a, b, c, b, d, c);
        }
      }
      previous = strip;
    }
    outerGroups.push({ start: lapelStart, count: faces.length - lapelStart, materialIndex: 2 });
  }

  // The outer and lining are offsets of exactly the same sewn surface.  Close
  // only its free boundaries: front opening, neck, hem, and cuffs.
  const surface = new THREE.BufferGeometry();
  surface.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  surface.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  surface.setIndex(faces);
  surface.computeVertexNormals();
  const normals = surface.getAttribute("normal");
  const vertexCount = positions.length / 3;
  const thickness = .018;
  const solidPositions = positions.slice(), solidUVs = uvs.slice();
  for (let i = 0; i < vertexCount; i += 1) {
    solidPositions.push(
      positions[i * 3] - normals.getX(i) * thickness,
      positions[i * 3 + 1] - normals.getY(i) * thickness,
      positions[i * 3 + 2] - normals.getZ(i) * thickness);
    solidUVs.push(uvs[i * 2], uvs[i * 2 + 1]);
  }
  const indices = faces.slice();
  const liningStart = indices.length;
  for (let i = 0; i < faces.length; i += 3) {
    indices.push(faces[i] + vertexCount, faces[i + 2] + vertexCount,
      faces[i + 1] + vertexCount);
  }
  const edgeUses = new Map();
  for (let i = 0; i < faces.length; i += 3) {
    for (const [a, b] of [[faces[i], faces[i + 1]], [faces[i + 1], faces[i + 2]],
      [faces[i + 2], faces[i]]]) {
      const key = `${Math.min(a, b)}:${Math.max(a, b)}`;
      const entry = edgeUses.get(key);
      if (entry) entry.count += 1;
      else edgeUses.set(key, { a, b, count: 1 });
    }
  }
  const edgeStart = indices.length;
  let openEdges = 0, nonManifoldEdges = 0;
  for (const { a, b, count } of edgeUses.values()) {
    if (count > 2) nonManifoldEdges += 1;
    if (count !== 1) continue;
    openEdges += 1;
    indices.push(a, a + vertexCount, b, b, a + vertexCount, b + vertexCount);
  }
  const parent = Int32Array.from({ length: vertexCount }, (_, index) => index);
  const find = (index) => {
    while (parent[index] !== index) {
      parent[index] = parent[parent[index]];
      index = parent[index];
    }
    return index;
  };
  for (let i = 0; i < faces.length; i += 3) {
    parent[find(faces[i])] = find(faces[i + 1]);
    parent[find(faces[i + 1])] = find(faces[i + 2]);
  }
  // Hole interiors have unused grid vertices; count only vertices belonging to
  // triangles when checking whether the actual cloth is a single component.
  const surfaceComponents = new Set([...new Set(faces)].map(find)).size;
  const solidEdgeUses = new Map();
  for (let i = 0; i < indices.length; i += 3) {
    for (const [a, b] of [[indices[i], indices[i + 1]],
      [indices[i + 1], indices[i + 2]], [indices[i + 2], indices[i]]]) {
      const key = `${Math.min(a, b)}:${Math.max(a, b)}`;
      solidEdgeUses.set(key, (solidEdgeUses.get(key) || 0) + 1);
    }
  }
  let solidBoundaryEdges = 0, solidNonManifoldEdges = 0;
  for (const uses of solidEdgeUses.values()) {
    if (uses === 1) solidBoundaryEdges += 1;
    if (uses > 2) solidNonManifoldEdges += 1;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(solidPositions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(solidUVs, 2));
  geometry.setIndex(indices);
  outerGroups.forEach(({ start, count, materialIndex }) =>
    geometry.addGroup(start, count, materialIndex));
  geometry.addGroup(liningStart, edgeStart - liningStart, 1);
  geometry.addGroup(edgeStart, indices.length - edgeStart, 0);
  geometry.computeVertexNormals();
  geometry.userData.construction = {
    bodyPanels: 3, joinedSleeves: 2, foldedLapels: 2,
    shellStride: segments + 1,
    hemFlare, sleeveVolume, poseAngle,
    surfaceComponents, sourceBoundaryEdges: openEdges, nonManifoldEdges,
    solidBoundaryEdges, solidNonManifoldEdges,
  };
  surface.dispose();
  return geometry;
}

function stitchedCoatLine(parent, coat, column, firstRow, lastRow, color) {
  const positions = coat.geometry.getAttribute("position");
  const normals = coat.geometry.getAttribute("normal");
  const stride = coat.geometry.userData.construction.shellStride;
  const points = [];
  for (let row = firstRow; row <= lastRow; row += 2) {
    const index = row * stride + column;
    points.push([
      positions.getX(index) + normals.getX(index) * .007,
      positions.getY(index) + normals.getY(index) * .007,
      positions.getZ(index) + normals.getZ(index) * .007,
    ]);
  }
  return addMesh(parent, new THREE.TubeGeometry(
    new THREE.CatmullRomCurve3(points.map((point) => new THREE.Vector3(...point))),
    points.length * 3, .0045, 6, false),
  smoothMaterial(color, { roughness: .92, role: "stitch" }), [0, 0, 0]);
}

function coatEdge(parent, side, material) {
  const points = [];
  for (let i = 0; i <= 40; i += 1) {
    const t = i / 40;
    const skirt = Math.max(0, (t - .44) / .56);
    const gap = THREE.MathUtils.lerp(.49, .69, Math.pow(t, 1.15));
    const angle = Math.PI / 2 + side * gap;
    const waistShape = .06 * Math.exp(-Math.pow((t - .48) / .19, 2));
    const width = .425 + .075 * t + .35 * Math.pow(skirt, 1.38) - waistShape;
    const depth = .375 + .025 * t + .19 * Math.pow(skirt, 1.35);
    const pleat = Math.pow(Math.sin(angle * 5.5 + .30), 2) * .09 * skirt * skirt;
    const drape = Math.sin(angle * 2.7 + t * 1.7) * .035 * skirt;
    const clothFold = Math.sin(angle * 8 + t * 3.5) * .028 * skirt * skirt;
    const y = THREE.MathUtils.lerp(.91, -1.30, t)
      + Math.pow(Math.abs(Math.cos(angle)), 2) * .52 * Math.pow(skirt, 2.5)
      - Math.max(0, -Math.sin(angle)) * .075 * skirt * skirt
      + Math.sin(angle * 5.5 + .30) * .028 * skirt * skirt;
    points.push(new THREE.Vector3(Math.cos(angle) * (width + pleat + drape + clothFold), y,
      Math.sin(angle) * (depth + pleat * .55 + drape + clothFold * .7) + .012));
  }
  addMesh(parent, new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 88, .012, 8, false),
    material, [0, 0, 0]);
}

function coatFrontTailGeometry(side) {
  const rows = 44, columns = 24;
  const positions = [], uvs = [], indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const t = row / rows;
    const inner = .29 + .10 * t;
    const outer = .49 + .49 * Math.pow(t, 1.05);
    for (let column = 0; column <= columns; column += 1) {
      const u = column / columns;
      const billow = Math.sin(u * Math.PI * 4) * .025 * t * t;
      const x = side * (THREE.MathUtils.lerp(inner, outer, u) + billow
        + .055 * Math.sin(Math.PI * t) * Math.sin(Math.PI * u));
      const y = -.05 - 1.33 * t + .28 * u * t * t
        + .055 * Math.sin(u * Math.PI * 2) * t * t;
      const z = .35 + .13 * u + .11 * Math.sin(Math.PI * t) * Math.sin(Math.PI * u)
        + .035 * Math.sin(u * Math.PI * 4 + t * 2) * t * t;
      positions.push(x, y, z);
      uvs.push(u * 2.1, t * 2.5);
      if (row < rows && column < columns) {
        const i = row * (columns + 1) + column;
        const n = i + columns + 1;
        indices.push(i, n, i + 1, n, n + 1, i + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function coatTailEdge(parent, side, material) {
  const points = [];
  for (let index = 0; index <= 32; index += 1) {
    const u = index / 32;
    const x = side * (THREE.MathUtils.lerp(.39, .98, u) + Math.sin(u * Math.PI * 4) * .025);
    const y = -1.38 + .28 * u + .055 * Math.sin(u * Math.PI * 2);
    const z = .35 + .13 * u + .035 * Math.sin(u * Math.PI * 4 + 2) + .008;
    points.push(new THREE.Vector3(x, y, z));
  }
  addMesh(parent, new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 72, .009, 6),
    material, [0, 0, 0]);
}

function hoodGeometry() {
  const rows = 20, columns = 48;
  const positions = [], uvs = [], indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const v = row / rows;
    for (let column = 0; column <= columns; column += 1) {
      const u = column / columns;
      const angle = u * Math.PI;
      const width = (.25 + .09 * Math.sin(Math.PI * v)) * Math.cos(angle);
      const z = -.19 - (.055 + .075 * Math.sin(Math.PI * v)) * Math.sin(angle);
      const y = .94 + .20 * v - .06 * Math.pow(Math.abs(Math.cos(angle)), 2);
      positions.push(width, y, z);
      uvs.push(u, v);
      if (row < rows && column < columns) {
        const i = row * (columns + 1) + column;
        const n = i + columns + 1;
        indices.push(i, n, i + 1, n, n + 1, i + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function buildOpenLongCoat(state) {
  const palette = state?.appearance?.palette || {};
  const outerColor = state?.garmentColor || palette.outer || "#303139";
  const innerColor = palette.inner || "#aaa9a8";
  const accentColor = palette.accent || "#d9c900";
  const weave = getCoatFabricMaps();
  const outer = smoothMaterial(outerColor, {
    roughness: .88, roughnessMap: weave.roughness,
    sheen: .28, sheenRoughness: .84, clearcoat: .025,
    map: weave.color, normalMap: weave.normal, normalScale: .24, role: "outer",
  });
  const lining = smoothMaterial("#767882", {
    roughness: .95, sheen: .10, map: weave.color,
    normalMap: weave.normal, normalScale: .22, role: "coat_lining",
  });
  const lapel = smoothMaterial("#62656d", {
    roughness: .83, roughnessMap: weave.roughness,
    sheen: .30, sheenRoughness: .82, map: weave.color,
    normalMap: weave.normal, normalScale: .22, role: "coat_lapel",
  });
  const hemJacquard = smoothMaterial(outerColor, {
    roughness: .91, roughnessMap: weave.roughness,
    sheen: .16, sheenRoughness: .90,
    map: getCoatJacquardTexture(), normalMap: weave.normal,
    normalScale: .22, role: "coat_hem_jacquard",
  });
  const edging = smoothMaterial("#72757d", { roughness: .51, role: "coat_edging" });
  const knit = smoothMaterial(innerColor, {
    roughness: .96, sheen: .18, clearcoat: 0,
    map: getRibTexture(), normalMap: getRibNormalTexture(), normalScale: .30,
    role: "inner_knit",
  });
  const accent = smoothMaterial(accentColor, {
    roughness: .32, clearcoat: .48, role: "coat_accent",
  });
  const silver = smoothMaterial("#abb4ba", {
    roughness: .25, metalness: .62, clearcoat: .45, role: "coat_hardware",
  });
  const black = smoothMaterial("#22232b", { roughness: .68, role: "tights" });
  const ribbon = smoothMaterial("#191b24", { roughness: .55, role: "coat_strap" });
  const poseAngle = coatPoseAngle();

  // Independent sweater and leg layers remain visible in the coat opening.
  addMesh(garmentGroup, softKnitShellGeometry(), knit, [0, 0, 0]);
  ellipseTrim(garmentGroup, .345, .267, -.32, knit, .028);
  addMesh(garmentGroup, tailoredShellGeometry([
    { y: -.30, width: .38, depth: .30 }, { y: -.43, width: .38, depth: .30 },
    { y: -.59, width: .32, depth: .24 },
  ]), black, [0, 0, 0]);
  // The dark high-waist layer must remain in front of the VRM body and knit hem.
  shapeMesh(garmentGroup,
    [[-.365, -.315], [.365, -.315], [.33, -.57], [-.33, -.57]],
    black, [0, 0, .355], .014);
  for (const side of [-1, 1]) {
    addMesh(garmentGroup, trouserLegGeometry(side, "tapered"), black, [0, 0, 0]);
    const sleeveDetails = sleeveDetailGroup(garmentGroup, side, poseAngle);
    // Hardware is attached over the sewn sleeve, never used to hide its root.
    for (const [x, radius] of [[1.67, .164], [.83, .225]]) {
      addMesh(sleeveDetails, new THREE.TorusGeometry(radius, .024, 12, 50), ribbon,
        [side * x, .91, .035], [1, 1, 1], [0, Math.PI / 2, 0]);
      addMesh(sleeveDetails, new THREE.BoxGeometry(.065, .075, .03), silver,
        [side * x, .75, .17]);
    }
    // A broad forearm overlay gives the sleeve a cut-and-sewn profile.
    shapeMesh(sleeveDetails,
      [[side * 1.07, 1.045], [side * 1.49, .995], [side * 1.55, .83],
        [side * 1.20, .82]], edging, [0, 0, .188], .016);
    seam(sleeveDetails, [[side * 1.08, .95, .216], [side * 1.42, .91, .213],
      [side * 1.51, .84, .192]], "#a0a4aa");
  }

  const coatShell = addMesh(garmentGroup,
    connectedCoatGeometry({ ...state?.appearance?.shape, pose_angle: poseAngle }),
    [outer, lining, lapel, hemJacquard], [0, 0, 0]);
  coatShell.name = "sewn-open-long-coat";
  host.dataset.coatConstruction = JSON.stringify(coatShell.geometry.userData.construction);
  // A single indexed shell avoids the former overlapping lining; disable its
  // own shadow receiver to prevent acne on the densely folded back panel.
  coatShell.receiveShadow = false;
  for (const column of [8, 104]) {
    stitchedCoatLine(garmentGroup, coatShell, column, 14, 60, "#555960");
  }
  for (const column of [47, 65]) {
    stitchedCoatLine(garmentGroup, coatShell, column, 18, 60, "#555960");
  }
  // Large single-side accent is a separate rigid piece, not the base colour.
  const accentSide = state?.appearance?.shape?.accent_side === "left" ? -1 : 1;
  shapeMesh(garmentGroup,
    [[.27, 1.055], [.62, 1.07], [.99, .84], [.87, .60], [.46, .71], [.31, .86]]
      .map(([x, y]) => [x * accentSide, y]),
    edging, [0, 0, .452], .048);
  shapeMesh(garmentGroup,
    [[.29, 1.03], [.60, 1.04], [.96, .82], [.84, .63], [.48, .74], [.34, .88]]
      .map(([x, y]) => [x * accentSide, y]),
    accent, [0, 0, .47], .05);
  for (const [x, y] of [[.38, .91], [.75, .77]]) {
    addMesh(garmentGroup, new THREE.SphereGeometry(.025, 18, 12), silver,
      [x * accentSide, y, .545], [1, 1, .58]);
  }
  const shoulderHardware = sleeveDetailGroup(garmentGroup, accentSide, poseAngle);
  addMesh(shoulderHardware, new THREE.CylinderGeometry(.115, .115, .018, 48), edging,
    [1.17 * accentSide, .91, .27], [1, 1, 1], [Math.PI / 2, 0, 0]);
  addMesh(shoulderHardware, new THREE.TorusGeometry(.080, .015, 12, 48), silver,
    [1.17 * accentSide, .91, .286]);
  addMesh(garmentGroup, new THREE.TorusGeometry(.165, .038, 18, 56), edging,
    [0, 1.02, -.02], [1, .68, 1], [Math.PI / 2, 0, 0]);
  addMesh(garmentGroup, new THREE.TorusGeometry(.115, .019, 12, 50), silver,
    [-.08, .90, .40], [1.32, .62, 1], [0, 0, -.28]);

  // Plausible reverse of the coat. A front-only image cannot verify this
  // layout, so the UI explicitly calls the whole preview an estimate.
  addMesh(garmentGroup, hoodGeometry(), outer, [0, 0, 0]);
  seam(garmentGroup, [[-.34, 1.10, -.30], [-.23, 1.23, -.36],
    [0, 1.26, -.38], [.23, 1.23, -.36], [.34, 1.10, -.30]], "#92959e");
  for (const side of [-1, 1]) {
    addMesh(garmentGroup, roundedPanelGeometry(.16, .17, .018), ribbon,
      [side * .25, .57, -.36], [1, 1, 1], [0, Math.PI, 0]);
    addMesh(garmentGroup, new THREE.BoxGeometry(.085, .085, .045), silver,
      [side * .25, .55, -.398]);
  }
  shapeMesh(garmentGroup,
    [[-.025, .22], [.025, .22], [.055, -.98], [-.045, -.98]],
    edging, [0, 0, -.48], .014);
}

function buildGarments(parts) {
  clearGroup(garmentGroup);
  clearGroup(accessoryGroup);
  const types = new Set(parts.map((part) => part.part_type));
  const first = (type) => parts.find((part) => part.part_type === type);
  const cloth = smoothMaterial(currentState?.garmentColor || "#4f46e5", {
    roughness: .68, sheen: .52, clearcoat: .04, map: getFabricTexture(),
    normalMap: getFabricNormalTexture(), role: "cloth",
  });
  const trim = smoothMaterial(currentState?.garmentColor || "#4f46e5", {
    roughness: .40, sheen: .45, clearcoat: .20, role: "trim",
  });
  const accessoryMaterial = smoothMaterial(currentState?.accessoryColor || "#16a34a", {
    roughness: .28, metalness: .42, clearcoat: .48, role: "metal",
  });
  const lining = smoothMaterial("#e7e3ed", {
    roughness: .78, sheen: .35, normalMap: getFabricNormalTexture(), role: "lining",
  });
  const accent = smoothMaterial("#f2edf4", {
    roughness: .48, sheen: .56, clearcoat: .08, role: "accent",
  });

  if (currentState?.appearance?.silhouette === "open_long_coat") {
    buildOpenLongCoat(currentState);
  } else {

  if (hasType(types, "front_bodice", "back_bodice", "front_bodice_zip_panel", "front_princess_center")) {
    const shell = addMesh(garmentGroup, tailoredShellGeometry([
      { y: -.15, width: .35, depth: .29 },
      { y: .02, width: .39, depth: .31 },
      { y: .36, width: .43, depth: .34 },
      { y: .68, width: .47, depth: .33 },
      { y: .86, width: .42, depth: .29 },
      { y: 1.00, width: .26, depth: .24 },
    ]), cloth, [0, 0, 0]);
    shell.geometry.computeTangents?.();
    seam(garmentGroup, [[0, -.13, .305], [0, .45, .355], [0, .97, .255]], "#b8b4c3");
    for (const x of [-.25, .25]) {
      seam(garmentGroup, [[x * .70, -.10, .292], [x, .42, .342], [x * .72, .86, .292]], "#aaa6b5");
    }
    // 肩・袖山の境目を丸い別パネルで覆い、胴と円筒袖が直角に交差する
    // 「箱を組み合わせた見た目」をなくす。
    for (const x of [-.43, .43]) {
      addMesh(garmentGroup, new THREE.SphereGeometry(.24, 48, 28), cloth,
        [x, .88, 0], [.92, .76, 1.08]);
    }
    ellipseTrim(garmentGroup, .355, .295, -.14, trim, .016);

    if (types.has("skirt")) {
      // ドレスの身頃はコルセット風の切替と胸元の装飾を追加する。単色の筒に
      // 見えないよう、別材質のパイピングとリボンを面として重ねる。
      shapeMesh(garmentGroup,
        [[-.19, .88], [-.04, .72], [-.04, .57], [-.25, .76]],
        accent, [0, 0, .355], .014);
      shapeMesh(garmentGroup,
        [[.19, .88], [.04, .72], [.04, .57], [.25, .76]],
        accent, [0, 0, .355], .014);
      shapeMesh(garmentGroup,
        [[-.13, .64], [0, .72], [.13, .64], [0, .57]],
        trim, [0, 0, .378], .018);
      for (const x of [-.47, .47]) {
        addMesh(garmentGroup, new THREE.SphereGeometry(.25, 48, 28), trim,
          [x, .84, -.005], [1.05, .42, 1.16]);
        addMesh(garmentGroup, new THREE.TorusGeometry(.20, .018, 10, 48, Math.PI * 1.25),
          accent, [x, .88, .13], [1.05, .72, 1], [0, 0, x < 0 ? -.30 : .30]);
      }
    }

    // 長袖の身頃＋パンツは、舞台衣装・制服・コート型でよく現れる構成。
    // 腰で唐突に切らず、前開きの裾パネルとラペルを重ねてジャケットとして
    // 読めるシルエットにする。パンツ自体は内側に残るため360°でも破綻しない。
    if (types.has("sleeve") && hasType(types, "front_pants", "back_pants")) {
      shapeMesh(garmentGroup,
        [[-.39, -.09], [-.025, -.12], [-.035, -.78], [-.33, -.69], [-.44, -.37]],
        cloth, [0, 0, .305], .024);
      shapeMesh(garmentGroup,
        [[.025, -.12], [.39, -.09], [.44, -.37], [.33, -.69], [.035, -.78]],
        cloth, [0, 0, .305], .024);
      shapeMesh(garmentGroup,
        [[-.25, .92], [-.025, .62], [-.08, .30], [-.34, .76]],
        trim, [0, 0, .355], .018);
      shapeMesh(garmentGroup,
        [[.25, .92], [.025, .62], [.08, .30], [.34, .76]],
        trim, [0, 0, .355], .018);
      seam(garmentGroup, [[-.035, -.12, .345], [-.035, -.46, .35], [-.035, -.76, .33]]);
      seam(garmentGroup, [[.035, -.12, .345], [.035, -.46, .35], [.035, -.76, .33]]);
      for (const y of [.54, .35, .16, -.03]) {
        addMesh(garmentGroup, new THREE.SphereGeometry(.027, 18, 12), accessoryMaterial,
          [-.10, y, .39], [1, 1, .48]);
        addMesh(garmentGroup, new THREE.SphereGeometry(.027, 18, 12), accessoryMaterial,
          [.10, y, .39], [1, 1, .48]);
      }
    }
  }
  if (types.has("sleeve")) {
    const sleeve = first("sleeve");
    const measuredLength = Math.max(.45, Math.min(1.42, (sleeve?.height_cm || 54) / 48));
    const detachedDressSleeve = types.has("skirt") && sleeve?.variation === "straight";
    const length = detachedDressSleeve ? .43 : measuredLength;
    const puff = sleeve?.variation === "puff" || detachedDressSleeve ? .255 : .205;
    for (const x of [-1, 1]) {
      addMesh(garmentGroup, fittedSleeveGeometry(length, puff, Math.max(.12, puff * .64), x), cloth,
        [0, 0, 0]);
      seam(garmentGroup, [[x * .43, .905, puff * .94], [x * (length + .37), .905, Math.max(.11, puff * .58)]], "#aaa6b5");
      // 袖口の厚みと、肘付近の自然な横じわ。
      addMesh(garmentGroup, new THREE.TorusGeometry(Math.max(.11, puff * .60), .018, 10, 48), trim,
        [x * (length + .37), .91, 0], [1, 1, .92], [0, Math.PI / 2, 0]);
      for (const offset of [-.035, .035]) {
        addMesh(garmentGroup, new THREE.TorusGeometry(puff * .76, .006, 8, 40), trim,
          [x * (.37 + length * .52 + offset), .90, 0], [1, 1, .90], [0, Math.PI / 2, 0]);
      }
    }
    if (detachedDressSleeve) {
      // ゴシック／アイドル衣装で多い「肩袖と手甲が分離した」構成。腕全体を
      // 単純な筒で覆わず、肌を見せて装飾密度とシルエットを両立する。
      for (const x of [-1, 1]) {
        addMesh(garmentGroup, new THREE.CylinderGeometry(.135, .115, .38, 48, 8), trim,
          [x * 1.48, .91, .035], [1, 1, 1.18], [0, 0, Math.PI / 2]);
        addMesh(garmentGroup, new THREE.TorusGeometry(.14, .018, 10, 48), accent,
          [x * 1.29, .91, .035], [1, 1, 1.12], [0, Math.PI / 2, 0]);
        addMesh(garmentGroup, new THREE.TorusGeometry(.12, .015, 10, 48), accent,
          [x * 1.67, .91, .035], [1, 1, 1.12], [0, Math.PI / 2, 0]);
      }
    }
  }
  if (types.has("skirt")) {
    const skirt = first("skirt");
    const length = Math.max(.48, Math.min(1.35, (skirt?.height_cm || 60) / 60));
    const tight = skirt?.variation === "tight";
    const flare = tight ? .42 : skirt?.variation === "mermaid" ? .68 : .72;
    // VRC衣装で一般的な「外スカート＋段差パネル＋内スカート」の3層構造。
    // 単一円錐よりシルエットと陰影が明確になり、横・後ろからも層が読める。
    addMesh(garmentGroup,
      drapedSkirtGeometry(length * 1.05, .34, Math.max(.42, flare * .92), tight),
      lining, [0, -.015, 0]);
    addMesh(garmentGroup, drapedSkirtGeometry(length, .37, flare, tight), cloth, [0, 0, 0]);
    if (!tight) {
      const upperLayer = addMesh(garmentGroup,
        drapedSkirtGeometry(length * .64, .385, flare * .88, false),
        trim, [0, .012, 0]);
      upperLayer.rotation.y = Math.PI / 24;
      const middleLayer = addMesh(garmentGroup,
        drapedSkirtGeometry(length * .82, .37, flare * .94, false),
        cloth, [0, -.005, 0]);
      middleLayer.rotation.y = -Math.PI / 28;
      ruffledHem(garmentGroup, flare * .94, flare * .68,
        -.13 - length * .82, accent, 20);
    }
    addMesh(garmentGroup, new THREE.TorusGeometry(.405, .035, 12, 72), trim,
      [0, -.13, 0], [1, .75, 1], [Math.PI / 2, 0, 0]);
    seam(garmentGroup, [[0, -.18, .31], [0, -.55 - length * .35, flare * .68], [0, -.13 - length, flare * .70]], "#aaa6b5");
    ellipseTrim(garmentGroup, flare, flare * .72, -.13 - length, trim, .018);
    ruffledHem(garmentGroup, Math.max(.42, flare * .92), Math.max(.32, flare * .66),
      -.145 - length * 1.05, accent, 22);
  }
  if (hasType(types, "front_pants", "back_pants")) {
    const pants = first("front_pants") || first("back_pants");
    // 股上は左右の脚を別々に作るだけだと中央が三角形に開く。腰から股までを
    // 1枚の連続した高密度シェルで覆い、その内側へ脚を重ねてVRC衣装らしい
    // 一体のパンツシルエットにする。
    addMesh(garmentGroup, tailoredShellGeometry([
      { y: -.18, width: .40, depth: .29 },
      { y: -.34, width: .44, depth: .31 },
      { y: -.52, width: .36, depth: .27 },
    ], 72), cloth, [0, 0, 0]);
    for (const x of [-.22, .22]) {
      addMesh(garmentGroup, trouserLegGeometry(Math.sign(x), pants?.variation || ""), cloth,
        [0, 0, 0]);
      seam(garmentGroup, [[x, -.26, .17], [x * .92, -.92, .13], [x * .82, -1.62, .10]], "#aaa6b5");
    }
    ellipseTrim(garmentGroup, .405, .29, -.18, trim, .018);
  }
  if (types.has("waistband")) {
    const band = first("waistband");
    const thickness = band?.variation === "wide" ? .09 : .055;
    addMesh(garmentGroup, new THREE.TorusGeometry(.43, thickness, 16, 72), trim,
      [0, -.10, 0], [1, .78, 1], [Math.PI / 2, 0, 0]);
    addMesh(garmentGroup, new THREE.BoxGeometry(.13, .13, .055), accessoryMaterial,
      [0, -.10, .49]);
  }
  if (types.has("collar")) {
    const collar = first("collar");
    addMesh(garmentGroup, new THREE.TorusGeometry(.255, .045, 16, 72), trim,
      [0, 1.03, .015], [1, .74, 1], [Math.PI / 2, 0, 0]);
    if (["convertible_collar", "notched", "tailored"].includes(collar?.variation)) {
      shapeMesh(garmentGroup, [[-.25, .55], [-.02, .31], [-.05, .02], [-.35, .49]],
        trim, [0, .48, .455], .022);
      shapeMesh(garmentGroup, [[.25, .55], [.02, .31], [.05, .02], [.35, .49]],
        trim, [0, .48, .455], .022);
    }
  }
  if (types.has("cuffs")) {
    for (const x of [-1, 1]) {
      addMesh(garmentGroup, new THREE.CylinderGeometry(.15, .15, .18, 40), trim,
        [x * 1.68, .79, 0], [1, 1, .92], [0, 0, Math.PI / 2]);
      addMesh(garmentGroup, new THREE.SphereGeometry(.025, 16, 12), accessoryMaterial,
        [x * 1.68, .70, .145]);
    }
  }
  if (types.has("front_bodice_zip_panel") || types.has("collar")) {
    for (const y of [.76, .57, .38, .19, 0]) {
      addMesh(garmentGroup, new THREE.SphereGeometry(.032, 18, 12), accessoryMaterial,
        [-.09, y, .485], [1, 1, .45]);
    }
  }
  if (types.has("hood")) {
    addMesh(garmentGroup, new THREE.SphereGeometry(.43, 36, 24, 0, Math.PI * 2, 0, Math.PI * .70),
      cloth, [0, 1.30, -.13], [1, 1.12, .92], [0, 0, Math.PI]);
  }
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
  const tailoredView = state.appearance?.silhouette === "open_long_coat";
  poseVRMArms(importedVRM, tailoredView
    ? (importedGarment ? Number(state.authoredSleevePose || 0) : coatPoseAngle())
    : 0);
  poseEndministratorFittingArms(importedGarment,
    tailoredView ? Number(state.garmentArmAngle || 0) : 0);
  const backdrop = tailoredView ? "#454b51" : "#222738";
  scene.background.set(backdrop);
  scene.fog.color.set(backdrop);
  renderer.toneMappingExposure = tailoredView ? 1.28 : 1.02;
  root.rotation.y = -state.angle;
  root.rotation.x = state.tilt || 0;
  const scale = state.zoom || 1;
  root.scale.setScalar(scale);
  garmentGroup.visible = state.showGarment !== false && !importedGarment;
  if (importedGarment) importedGarment.visible = state.showGarment !== false;
  const bespokeFootwear = usingBundledAvatar && importedGarment
    && /endministrator|管理人/i.test(importedGarment.userData.sourceName || "")
    && state.showGarment !== false;
  for (const material of bundledShoeMaterials) material.visible = !bespokeFootwear;
  for (const material of bundledBodyMaterials) {
    // The bundled fitting VRM has shorter arms and different feet from this
    // bespoke costume. Do not show its hands floating outside the cuffs;
    // uploaded user avatars remain untouched and need their own fit check.
    material.visible = !bespokeFootwear;
    material.needsUpdate = true;
  }
  accessoryGroup.visible = state.showAccessories !== false;
  proceduralAvatar.visible = state.showMannequin !== false && !importedAvatar;
  if (importedAvatar) importedAvatar.visible = state.showMannequin !== false;
  fittingHandsGroup.visible = tailoredView && !importedGarment && usingBundledAvatar
    && state.showMannequin !== false;
  garmentGroup.traverse((object) => {
    if (!object.isMesh || !object.material) return;
    const base = new THREE.Color(state.garmentColor || "#4f46e5");
    const outerColor = state.garmentColor || state.appearance?.palette?.outer || "#303139";
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      const role = material.userData?.colorRole;
      if (role === "cloth") material.color.copy(base);
      if (role === "trim") material.color.copy(base).multiplyScalar(.62);
      if (role === "stitch") material.color.copy(base).lerp(new THREE.Color("#f3e9e6"), .48);
      if (role === "lining") material.color.copy(base).lerp(new THREE.Color("#f5f0f7"), .72);
      if (role === "accent") material.color.copy(base).lerp(new THREE.Color("#fffafc"), .86);
      if (role === "metal") material.color.set(state.accessoryColor || "#16a34a");
      if (role === "outer" || role === "coat_hem_jacquard") material.color.set(outerColor);
      if (role === "coat_lapel") material.color.set(outerColor)
        .lerp(new THREE.Color("#a7aab0"), .40);
      if (role === "outer_panel") material.color.set(outerColor)
        .lerp(new THREE.Color("#858993"), .16);
      if (role === "inner_knit") material.color.set(state.appearance?.palette?.inner || "#aaa9a8");
      if (role === "coat_accent") material.color.set(state.appearance?.palette?.accent || "#d9c900");
    }
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
  clearImportedGarment();
  currentParts = Array.isArray(parts) ? parts : [];
  currentState = state;
  buildGarments(currentParts);
  update(state);
}

function inspectGarmentModel(model) {
  let meshes = 0, skinnedMeshes = 0, triangles = 0, meshesWithUV = 0;
  const materials = new Set();
  const textures = new Set();
  let pbrMaterials = 0, normalMaps = 0, roughnessMaps = 0;
  model.traverse((object) => {
    if (!object.isMesh || !object.geometry?.getAttribute("position")) return;
    meshes += 1;
    if (object.isSkinnedMesh) skinnedMeshes += 1;
    if (object.geometry.getAttribute("uv")) meshesWithUV += 1;
    triangles += Math.floor((object.geometry.index?.count
      || object.geometry.getAttribute("position").count) / 3);
    for (const material of (Array.isArray(object.material) ? object.material : [object.material])) {
      if (!material || materials.has(material)) continue;
      materials.add(material);
      if (material.isMeshStandardMaterial || material.isMeshPhysicalMaterial) pbrMaterials += 1;
      if (material.normalMap?.isTexture) normalMaps += 1;
      if (material.roughnessMap?.isTexture) roughnessMaps += 1;
      for (const key of ["map", "normalMap", "roughnessMap", "metalnessMap", "aoMap"]) {
        if (material[key]?.isTexture) textures.add(material[key]);
      }
    }
  });
  if (!meshes || !triangles) throw new Error("衣装メッシュが入っていません");
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  if (![size.x, size.y, size.z].every(Number.isFinite) || size.y < .01) {
    throw new Error("衣装の寸法を取得できません");
  }
  return { meshes, skinnedMeshes, triangles, meshesWithUV,
    materials: materials.size, pbrMaterials, textures: textures.size,
    normalMaps, roughnessMaps };
}

function setReviewStatus(message, error = false) {
  if (!reviewStatus) return;
  reviewStatus.textContent = message;
  reviewStatus.classList.toggle("is-error", error);
}

function renderReviewMetrics() {
  if (!reviewMetrics) return;
  reviewMetrics.replaceChildren();
  const report = importedGarment?.userData.qualityReport;
  const checks = report ? [
    [`形状`, `${report.triangles.toLocaleString()}三角形・${report.meshes}メッシュ`],
    [`UV`, `${report.meshesWithUV}/${report.meshes}メッシュ`],
    [`材質`, `PBR ${report.pbrMaterials}/${report.materials}材質`],
    [`布の細部`, `法線マップ ${report.normalMaps}・粗さマップ ${report.roughnessMaps}`],
    [`骨追従`, `${report.skinnedMeshes}スキンメッシュ（動作未検証）`],
  ] : [["自動生成", "形状確認用ラフ。UV・布の接続・骨追従の品質は保証しません。"]];
  for (const [label, value] of checks) {
    const item = document.createElement("div");
    const title = document.createElement("strong");
    const detail = document.createElement("span");
    title.textContent = label;
    detail.textContent = value;
    item.append(title, detail);
    reviewMetrics.appendChild(item);
  }
}

function setReferenceImages(files, replace = true) {
  if (replace) {
    for (const reference of reviewReferences.values()) URL.revokeObjectURL(reference.url);
    reviewReferences.clear();
  }
  const allowed = new Set(["image/png", "image/jpeg", "image/webp"]);
  for (const kind of ["front", "side", "back"]) {
    const file = files?.[kind];
    if (!file) continue;
    if (!allowed.has(file.type) || file.size > 20 * 1024 * 1024) {
      setReviewStatus(`${kind}：20MB以下のPNG/JPEG/WebPを選んでください。`, true);
      continue;
    }
    const previous = reviewReferences.get(kind);
    if (previous) URL.revokeObjectURL(previous.url);
    reviewReferences.set(kind, { url: URL.createObjectURL(file), name: file.name });
  }
  const count = reviewReferences.size;
  setReviewStatus(count
    ? `資料画像${count}方向を端末内に保持しました。「比較を更新」で3Dと並べて確認できます。`
    : "資料画像がありません。正面・側面・背面を追加してください。");
  renderReviewMetrics();
}

function capturedReviewView(angle) {
  const previousAngle = currentState.angle;
  const previousTilt = currentState.tilt;
  try {
    currentState.angle = angle;
    currentState.tilt = 0;
    update(currentState);
    return renderer.domElement.toDataURL("image/png");
  } finally {
    currentState.angle = previousAngle;
    currentState.tilt = previousTilt;
    update(currentState);
  }
}

function renderReferenceReview() {
  renderReviewMetrics();
  if (!reviewGrid || !renderer || !currentState) {
    setReviewStatus("3Dビューがまだ利用できません。WebGLを確認してください。", true);
    return;
  }
  const sequence = ++reviewSequence;
  reviewGrid.replaceChildren();
  for (const [kind, label, angle] of [
    ["front", "正面", 0], ["side", "側面", Math.PI / 2], ["back", "背面", Math.PI],
  ]) {
    const row = document.createElement("div");
    row.className = "outfit-review-row";
    const heading = document.createElement("strong");
    heading.textContent = label;
    const ref = document.createElement("figure");
    const result = document.createElement("figure");
    const refImage = document.createElement("img");
    const resultImage = document.createElement("img");
    const refCaption = document.createElement("figcaption");
    const resultCaption = document.createElement("figcaption");
    const reference = reviewReferences.get(kind);
    if (reference) {
      refImage.src = reference.url;
      refImage.alt = `${label}の資料画像：${reference.name}`;
      ref.appendChild(refImage);
    } else {
      const missing = document.createElement("p");
      missing.textContent = "資料なし（3D側の形状は推定）";
      ref.appendChild(missing);
    }
    refCaption.textContent = reference ? "資料画像" : "資料未提供";
    resultImage.src = capturedReviewView(angle);
    resultImage.alt = `${label}から見た現在の3D衣装`;
    resultCaption.textContent = importedGarment ? "読み込んだ衣装GLB" : "自動生成ラフ";
    ref.appendChild(refCaption);
    result.append(resultImage, resultCaption);
    row.append(heading, ref, result);
    reviewGrid.appendChild(row);
  }
  if (sequence !== reviewSequence) return;
  reviewGrid.classList.remove("hidden");
  setReviewStatus(importedGarment
    ? "三方向を並べました。見た目の一致・貫通・ポーズ変形は目視で確認してください。数値だけではVRC品質を認定できません。"
    : "三方向を並べました。現在の3Dは簡易ラフで、資料と似ていても完成衣装メッシュではありません。");
}

function clearImportedGarment() {
  garmentLoadSequence += 1;
  if (importedGarment) {
    root?.remove(importedGarment);
    disposeObject3D(importedGarment);
    importedGarment = null;
  }
  if (garmentFile) garmentFile.value = "";
  garmentReset?.classList.add("hidden");
  garmentFit?.classList.add("hidden");
  setGarmentStatus("自動生成の衣装は形状確認用です。高品質の衣装GLBは端末内で読み込めます。");
  renderReviewMetrics();
  reviewGrid?.classList.add("hidden");
  if (currentState) update(currentState);
}

function applyImportedGarmentTransform() {
  if (!importedGarment) return;
  // A standalone validation page may omit fitting sliders. In that case the
  // imported garment must retain its authored 1:1 size, not shrink to 30%.
  const [scale, x, y, z] = garmentFitInputs.map((input, index) =>
    input ? Number(input.value) : (index === 0 ? 100 : 0));
  importedGarment.scale.setScalar(Math.max(.3, scale / 100));
  importedGarment.position.set(x / 100, y / 100, z / 100);
  garmentFitInputs.forEach((input, index) => {
    const output = input?.parentElement?.querySelector("output");
    if (output) output.textContent = index === 0
      ? `${(scale / 100).toFixed(2)}倍`
      : (Number(input.value) / 100).toFixed(2);
  });
  update(currentState);
}

function loadGarment(file) {
  if (!file) return;
  if (file.size > 100 * 1024 * 1024 || file.name.split(".").pop()?.toLowerCase() !== "glb") {
    setGarmentStatus("100MB以下の単体GLBを選んでください。", true);
    if (garmentFile) garmentFile.value = "";
    return;
  }
  const sequence = ++garmentLoadSequence;
  setGarmentStatus("衣装モデルを端末内で検査しています…");
  file.arrayBuffer().then((buffer) => {
    if (sequence !== garmentLoadSequence) return;
    if (buffer.byteLength < 20 || new DataView(buffer).getUint32(0, true) !== 0x46546c67) {
      throw new Error("GLB形式のファイルではありません");
    }
    new GLTFLoader().parse(buffer, "", (gltf) => {
      const model = gltf.scene;
      if (sequence !== garmentLoadSequence) {
        disposeObject3D(model);
        return;
      }
      try {
        const report = inspectGarmentModel(model);
        if (importedGarment) {
          root.remove(importedGarment);
          disposeObject3D(importedGarment);
        }
        importedGarment = model;
        importedGarment.userData.sourceName = file.name;
        importedGarment.userData.qualityReport = report;
        model.traverse((object) => {
          if (object.isMesh) object.castShadow = true;
        });
        root.add(model);
        garmentReset?.classList.remove("hidden");
        garmentFitInputs.forEach((input) => {
          if (input) input.value = input.id.endsWith("-scale") ? "100" : "0";
        });
        garmentFit?.classList.remove("hidden");
        applyImportedGarmentTransform();
        setGarmentStatus(`${file.name}：${report.triangles.toLocaleString()}三角形、`
          + `UV ${report.meshesWithUV}/${report.meshes}メッシュ、`
          + `PBR材質 ${report.pbrMaterials}/${report.materials}、`
          + `テクスチャ ${report.textures}枚、スキンメッシュ ${report.skinnedMeshes}。`
          + "これは品質の目安であり、アバターへの骨追従やVRC対応の保証ではありません。");
        renderReviewMetrics();
        reviewGrid?.classList.add("hidden");
        update(currentState);
      } catch (error) {
        disposeObject3D(model);
        setGarmentStatus(`衣装モデルを使用できません：${error.message}`, true);
        if (garmentFile) garmentFile.value = "";
      }
    }, (error) => {
      if (sequence !== garmentLoadSequence) return;
      setGarmentStatus(`GLBを読み込めません：${error?.message || "ファイルを確認してください"}`, true);
      if (garmentFile) garmentFile.value = "";
    });
  }).catch((error) => {
    if (sequence !== garmentLoadSequence) return;
    setGarmentStatus(`ファイルを開けませんでした：${error.message}`, true);
    if (garmentFile) garmentFile.value = "";
  });
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

function avatarLoader() {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  return loader;
}

function poseVRMArms(vrm, angle) {
  if (!vrm?.humanoid?.getNormalizedBoneNode) return;
  for (const [name, side] of [["left", -1], ["right", 1]]) {
    const upper = vrm.humanoid.getNormalizedBoneNode(`${name}UpperArm`);
    if (upper) upper.rotation.z = -side * angle;
    const lower = vrm.humanoid.getNormalizedBoneNode(`${name}LowerArm`);
    if (lower) lower.rotation.z = -side * angle * .08;
  }
  vrm.humanoid.update?.();
}

function poseEndministratorFittingArms(model, angle) {
  if (!model) return;
  for (const [label, side] of [["Left", -1], ["Right", 1]]) {
    for (const [suffix, factor] of [["UpperArm", 1], ["LowerArm", .4]]) {
      const bone = model.getObjectByName(label + suffix);
      if (!bone?.isBone) continue;
      if (!bone.userData.fittingRestQuaternion) {
        bone.userData.fittingRestQuaternion = bone.quaternion.clone();
      }
      const delta = new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0, 0, 1), side * angle * factor);
      bone.quaternion.copy(bone.userData.fittingRestQuaternion).multiply(delta);
    }
  }
}

function installAvatar(gltf, label, loadSequence, bundled = false) {
  const vrm = gltf?.userData?.vrm || null;
  const nextAvatar = vrm?.scene || gltf?.scene;
  if (loadSequence !== avatarLoadSequence) {
    disposeObject3D(nextAvatar);
    return;
  }
  try {
    if (!nextAvatar) throw new Error("モデル本体が見つかりませんでした");
    if (vrm) VRMUtils.rotateVRM0(vrm);
    bundledShoeMaterials = [];
    bundledBodyMaterials = [];
    nextAvatar.traverse((object) => {
      if (!object.isMesh) return;
      object.castShadow = true;
      object.receiveShadow = true;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.filter(Boolean).forEach((material) => {
        // The bundled VRoid is a fitting body. Hide its sample top/dress so the
        // generated garment replaces it instead of z-fighting through it.
        // Skin, face and hair remain visible. Bundled shoes are hidden only
        // while the bespoke Endministrator footwear is being previewed;
        // uploaded user avatars are never altered this way.
        if (bundled && /_Tops_.*_CLOTH/i.test(material.name || "")) {
          material.visible = false;
        }
        if (bundled && /_Shoes_.*_CLOTH/i.test(material.name || "")) {
          bundledShoeMaterials.push(material);
        }
        if (bundled && /_Body_.*_SKIN/i.test(material.name || "")) {
          bundledBodyMaterials.push(material);
        }
        material.needsUpdate = true;
      });
    });
    fitImportedAvatar(nextAvatar);
    if (importedAvatar) {
      root.remove(importedAvatar);
      disposeObject3D(importedAvatar);
    }
    importedAvatar = nextAvatar;
    importedVRM = vrm;
    usingBundledAvatar = bundled;
    root.add(importedAvatar);
    proceduralAvatar.visible = false;
    if (currentState) buildGarments(currentParts);
    avatarReset?.classList.toggle("hidden", bundled);
    setStatus(bundled
      ? "CC0の高精細VRM標準アバターを表示しています。"
      : `${label} をVRMマテリアル・骨格込みで読み込みました。モデルはサーバーへ送信されていません。`);
    update(currentState);
  } catch (error) {
    disposeObject3D(nextAvatar);
    throw error;
  }
}

function useProceduralFallback(message) {
  if (importedAvatar) {
    root.remove(importedAvatar);
    disposeObject3D(importedAvatar);
  }
  importedAvatar = null;
  importedVRM = null;
  usingBundledAvatar = false;
  proceduralAvatar.visible = currentState?.showMannequin !== false;
  if (currentState) buildGarments(currentParts);
  avatarReset?.classList.add("hidden");
  setStatus(message || "標準VRMを利用できないため軽量アバターを表示しています。", true);
  update(currentState);
}

function loadBundledAvatar() {
  const url = host?.dataset.defaultAvatarUrl;
  if (!url) {
    useProceduralFallback();
    return;
  }
  const loadSequence = ++avatarLoadSequence;
  setStatus("高精細VRM標準アバターを読み込んでいます…");
  avatarLoader().load(url, (gltf) => {
    try {
      installAvatar(gltf, "標準VRM", loadSequence, true);
    } catch (error) {
      useProceduralFallback(`標準VRMを読み込めませんでした：${error?.message || "不明なエラー"}`);
    }
  }, undefined, (error) => {
    if (loadSequence !== avatarLoadSequence) return;
    useProceduralFallback(`標準VRMを読み込めませんでした：${error?.message || "不明なエラー"}`);
  });
}

function useStandardAvatar() {
  if (avatarFile) avatarFile.value = "";
  loadBundledAvatar();
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
    avatarLoader().parse(buffer, "", (gltf) => {
      try {
        installAvatar(gltf, file.name, loadSequence, false);
      } catch (error) {
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
  context.fillText(`${title || "PatternForge"}　衣装4面図`, 48, 62);
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
  scene.background = new THREE.Color("#222738");
  scene.fog = new THREE.Fog("#222738", 8.5, 14);
  camera = new THREE.PerspectiveCamera(32, 1, .1, 50);
  camera.position.set(0, .18, 7.6);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = .07;
  controls.minDistance = 3.4;
  controls.maxDistance = 9;
  controls.maxPolarAngle = Math.PI * .83;
  controls.update();

  scene.add(new THREE.HemisphereLight("#ffffff", "#626972", 2.8));
  const key = new THREE.DirectionalLight("#fffaf2", 4.0);
  key.position.set(3.5, 5.5, 4.5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = key.shadow.camera.bottom = -4;
  key.shadow.camera.right = key.shadow.camera.top = 4;
  scene.add(key);
  const rim = new THREE.DirectionalLight("#d6e3ef", 2.0);
  rim.position.set(-4, 2.5, -4);
  scene.add(rim);
  const fill = new THREE.PointLight("#e6f0f6", 1.9, 12);
  fill.position.set(-2.5, 1.5, 3);
  scene.add(fill);

  root = new THREE.Group();
  proceduralAvatar = buildProceduralAvatar();
  fittingHandsGroup = buildBundledFittingHands();
  garmentGroup = new THREE.Group();
  accessoryGroup = new THREE.Group();
  root.add(proceduralAvatar, garmentGroup, accessoryGroup, fittingHandsGroup);
  scene.add(root);
  floor = addMesh(scene, new THREE.CircleGeometry(2.45, 72),
    new THREE.MeshStandardMaterial({ color: "#555b60", roughness: .92, metalness: .02 }),
    [0, -1.77, 0], [1, 1, 1], [-Math.PI / 2, 0, 0]);
  floor.receiveShadow = true;

  host.classList.remove("hidden");
  fallbackCanvas?.classList.add("is-webgl-fallback-hidden");
  resize();
  new ResizeObserver(resize).observe(host);
  const clock = new THREE.Clock();
  const animate = () => {
    importedVRM?.update(clock.getDelta());
    controls.update();
    renderer.render(scene, camera);
    animationFrame = window.requestAnimationFrame(animate);
  };
  animate();
  loadBundledAvatar();

  window.PatternForge3D = {
    canvas: renderer.domElement,
    setOutfit,
    update,
    resize,
    makeFourViewSheet,
    setReferenceImages,
    renderReferenceReview,
    useStandardAvatar,
    loadGarment,
    clearImportedGarment,
    getGarmentDiagnostics() {
      if (importedGarment) {
        return { source: "imported_glb", ...importedGarment.userData.qualityReport };
      }
      const coat = garmentGroup.getObjectByName("sewn-open-long-coat");
      if (!coat) return null;
      const attribute = coat.geometry.getAttribute("position");
      return {
        ...coat.geometry.userData.construction,
        vertices: attribute.count,
        triangles: coat.geometry.index.count / 3,
        materialGroups: coat.geometry.groups.length,
        finite: Array.from(attribute.array).every(Number.isFinite),
      };
    },
    get ready() { return true; },
  };
  window.dispatchEvent(new CustomEvent("patternforge3dready"));
}

avatarFile?.addEventListener("change", () => loadAvatar(avatarFile.files?.[0]));
avatarReset?.addEventListener("click", useStandardAvatar);
garmentFile?.addEventListener("change", () => loadGarment(garmentFile.files?.[0]));
garmentReset?.addEventListener("click", clearImportedGarment);
garmentFitInputs.forEach((input) => input?.addEventListener("input", applyImportedGarmentTransform));
reviewRefresh?.addEventListener("click", renderReferenceReview);
reviewInputs.forEach((input) => input.addEventListener("change", () => {
  const file = input.files?.[0];
  if (file) setReferenceImages({ [input.dataset.garmentReference]: file }, false);
  input.value = "";
}));
window.addEventListener("pagehide", () => {
  for (const reference of reviewReferences.values()) URL.revokeObjectURL(reference.url);
  reviewReferences.clear();
});
window.addEventListener("pagehide", () => window.cancelAnimationFrame(animationFrame));
initialise();
