Three.js r180 (npm version 0.180.0)
Source: https://www.npmjs.com/package/three/v/0.180.0
License: MIT; see LICENSE in this directory.

Bundled files:
- build/three.module.min.js
- build/three.core.min.js
- examples/jsm/loaders/GLTFLoader.js
- examples/jsm/controls/OrbitControls.js
- examples/jsm/utils/BufferGeometryUtils.js

Only import paths in the example modules were changed from the npm package's
bare `three` specifier to the adjacent local module, so PatternForge does not
depend on a CDN or an import map at runtime.
