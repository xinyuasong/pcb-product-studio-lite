import * as THREE from './vendor/three.module.min.js';
import { GLTFLoader } from './vendor/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from './vendor/addons/loaders/DRACOLoader.js';
import { OrbitControls } from './vendor/addons/controls/OrbitControls.js';
import { RoomEnvironment } from './vendor/addons/environments/RoomEnvironment.js';

const MODEL = 'assets/model/nimbus.glb';
const canvas = document.getElementById('board');
const stage = document.querySelector('.stage');
const poster = document.getElementById('poster');
const loading = document.getElementById('loading');
const copy0 = document.getElementById('copy0');
const hint = document.getElementById('hint');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const MASKS = {
  green: 0x0f5a32, black: 0x151716, blue: 0x123f86, red: 0x8f1d1d,
  white: 0xecece6, purple: 0x4b2470, yellow: 0xc9a21b,
};

function fail(msg) {
  loading.textContent = msg;
  canvas.style.display = 'none';
}

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
} catch (e) {
  fail('Your browser can’t show the 3D board here, so this is a still render instead.');
}

if (renderer) start();

function start() {
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.7;

  const camera = new THREE.PerspectiveCamera(26, 1, 0.01, 50);
  const controls = new OrbitControls(camera, canvas);
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minPolarAngle = 0.15;
  controls.maxPolarAngle = 1.35;
  controls.autoRotate = !reduceMotion;
  controls.autoRotateSpeed = 0.55;

  // key light with a soft shadow on an invisible floor; rim light kept off the camera's mirror angle
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(-1.2, 2.4, 1.4);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.radius = 6;
  key.shadow.bias = -0.0004;
  Object.assign(key.shadow.camera, { left: -1, right: 1, top: 1, bottom: -1, near: 0.1, far: 6 });
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xdfe8ff, 1.1);
  rim.position.set(1.6, 0.9, -1.8);
  scene.add(rim);

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), new THREE.ShadowMaterial({ opacity: 0.18 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // PCB materials, set here so the page controls the look
  const mats = {
    pcb_mask: new THREE.MeshPhysicalMaterial({ color: MASKS.green, roughness: 0.34, clearcoat: 0.7, clearcoatRoughness: 0.18, transmission: 0, sheen: 0 }),
    pcb_copper: new THREE.MeshStandardMaterial({ color: 0xe2b564, metalness: 1, roughness: 0.24 }),
    pcb_plating: new THREE.MeshStandardMaterial({ color: 0xe2b564, metalness: 1, roughness: 0.24 }),
    pcb_silk: new THREE.MeshStandardMaterial({ color: 0xf2f2ec, roughness: 0.62 }),
    pcb_core: new THREE.MeshStandardMaterial({ color: 0x6b6d47, roughness: 0.75 }),
    comp_black: new THREE.MeshStandardMaterial({ color: 0x0c0c0d, roughness: 0.42 }),
    comp_shield: new THREE.MeshStandardMaterial({ color: 0xc7cacd, metalness: 1, roughness: 0.28 }),
    comp_ceramic: new THREE.MeshStandardMaterial({ color: 0x8c7552, roughness: 0.55 }),
    comp_tin: new THREE.MeshStandardMaterial({ color: 0xd2d4d8, metalness: 1, roughness: 0.32 }),
    comp_led: new THREE.MeshPhysicalMaterial({ color: 0xf4f3ee, roughness: 0.15, clearcoat: 1 }),
  };

  const parts = [];           // { node, base, lift, delay }
  const model = new THREE.Group();
  scene.add(model);

  const draco = new DRACOLoader().setDecoderPath('assets/vendor/draco/');
  const loader = new GLTFLoader().setDRACOLoader(draco);

  loader.load(MODEL, (gltf) => {
    const root = gltf.scene;
    root.traverse((o) => {
      if (o.isMesh) {
        const name = (o.material && o.material.name) || '';
        if (mats[name]) o.material = mats[name];
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
    // fit: board about 1 unit long, sitting on the floor
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const s = 1.0 / Math.max(size.x, size.z);
    root.scale.setScalar(s);
    const c = box.getCenter(new THREE.Vector3()).multiplyScalar(s);
    root.position.set(-c.x, -box.min.y * s + 0.002, -c.z);
    model.add(root);
    model.rotation.y = -0.5;

    const comps = [];
    root.traverse((o) => { if (o.name && o.name.startsWith('comp_')) comps.push(o); });
    // taller parts lift further; parts near the middle go first
    comps.forEach((n) => {
      const b = new THREE.Box3().setFromObject(n);
      const d = b.getCenter(new THREE.Vector3()).length();
      parts.push({ node: n, base: n.position.y, d, h: b.getSize(new THREE.Vector3()).y / s });
    });
    const maxD = Math.max(...parts.map((p) => p.d), 1e-6);
    parts.forEach((p) => {
      p.delay = (p.d / maxD) * 0.45;
      p.spin = Math.sin(p.d * 977) * 0.06;
      p.lift = (0.006 + p.h * 1.6) ;             // in model units (metres before scaling)
    });

    try {
      const entry = performance.getEntriesByName(new URL(MODEL, location.href).href)[0];
      const bytes = entry && (entry.decodedBodySize || entry.encodedBodySize);
      if (bytes) document.getElementById('glb-size').textContent = Math.round(bytes / 1024) + ' KB';
    } catch (e) { /* keep the written size */ }

    poster.classList.add('gone');
    loading.classList.add('gone');
    resize();
  }, undefined, () => {
    fail('The 3D board didn’t load, so this is a still render instead.');
  });

  // ---------- solder mask chips ----------
  const silkWhite = new THREE.Color(0xf2f2ec), silkBlack = new THREE.Color(0x141414);
  const target = new THREE.Color(MASKS.green), silkTarget = silkWhite.clone();
  document.querySelectorAll('.chips button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.chips button').forEach((b) => b.setAttribute('aria-checked', String(b === btn)));
      const k = btn.dataset.mask;
      target.setHex(MASKS[k]);
      silkTarget.copy(k === 'white' ? silkBlack : silkWhite);
      mats.pcb_mask.roughness = k === 'black' ? 0.42 : 0.34;
      if (reduceMotion) { mats.pcb_mask.color.copy(target); mats.pcb_silk.color.copy(silkTarget); }
    });
  });
  document.querySelector('.chips').addEventListener('keydown', (e) => {
    if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(e.key)) return;
    const list = [...document.querySelectorAll('.chips button')];
    const i = list.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const n = list[(i + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : list.length - 1)) % list.length];
    n.focus(); n.click();
  });

  // ---------- scroll drives the explode ----------
  let explode = 0, scrollP = 0;
  const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  function onScroll() {
    const r = stage.getBoundingClientRect();
    const span = r.height - window.innerHeight;
    scrollP = span > 0 ? Math.min(1, Math.max(0, -r.top / span)) : 0;
    const showCopy = scrollP < 0.06;
    copy0.style.opacity = showCopy ? '1' : '0';
    copy0.style.transform = showCopy ? 'none' : 'translateY(-12px)';
    copy0.inert = !showCopy;
    hint.style.opacity = showCopy ? '1' : '0';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  const bar = document.querySelector('.bar');
  const barState = () => bar.classList.toggle('solid', window.scrollY > window.innerHeight * 0.6);
  window.addEventListener('scroll', barState, { passive: true });
  barState();
  onScroll();

  controls.addEventListener('start', () => { controls.autoRotate = false; });

  // ---------- size and loop ----------
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const narrow = w / h < 0.9;
    const dist = narrow ? 6.6 : 3.7;
    if (!camera.userData.placed) {
      camera.position.set(dist * 0.62, dist * 0.62, dist * 0.48);
      camera.userData.placed = true;
    } else {
      camera.position.setLength(dist);
    }
    // orbit around the board's own centre, so it spins on the spot; slide the picture on screen with a view
    // offset instead (board right of the headline on wide screens, above the copy on narrow ones)
    controls.target.set(0, 0.03, 0);
    const ox = narrow ? 0 : -w * 0.2;
    const oy = narrow ? h * 0.27 : -h * 0.05;
    camera.setViewOffset(w, h, ox, oy, w, h);
    camera.updateProjectionMatrix();
    controls.update();
  }
  window.addEventListener('resize', resize);
  resize();

  let visible = true;
  new IntersectionObserver((es) => { visible = es[0].isIntersecting; }).observe(stage);

  const clock = new THREE.Clock();
  renderer.setAnimationLoop(() => {
    if (!visible) return;
    const dt = Math.min(clock.getDelta(), 0.05);
    const k = 1 - Math.exp(-dt * 9);
    mats.pcb_mask.color.lerp(target, k);
    mats.pcb_silk.color.lerp(silkTarget, k);

    // Scroll sets a target; the board follows it with a soft spring, so each wheel notch becomes a glide.
    // Up between 12% and 50% of the stage, held, then back down between 70% and 96%.
    const want = smooth(0.12, 0.5, scrollP) * (1 - smooth(0.7, 0.96, scrollP));
    const ks = reduceMotion ? 1 : 1 - Math.exp(-dt * 3.2);
    explode += (want - explode) * ks;
    for (const p of parts) {
      // every part has its own window, so they peel off one after another instead of all at once
      const e = smooth(p.delay, p.delay + 0.55, explode);
      const ease = 1 - Math.pow(1 - e, 3);
      p.node.position.y = p.base + p.lift * ease * 3.2;
      p.node.rotation.z = (p.spin || 0) * ease;
    }
    model.rotation.x = -0.2 * explode;
    model.position.y = 0.06 * explode;

    controls.update();
    renderer.render(scene, camera);
  });
}
