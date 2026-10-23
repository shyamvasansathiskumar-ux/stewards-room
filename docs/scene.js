// Stewards' Room's world: a plain, unbranded open-wheel car inside a ring of twelve floor tiles,
// one per penalty point. Eleven are lit in the hero (Spain 2025), they expire one by one in the
// ban-clock chapter, go dark for the 2026 change, and a second car slides alongside for the
// collisions chapter. In the register chapter, decision sheets drift past.
import { createWorld, THREE, smooth, textTexture } from "./world.js";

const ACC = new THREE.Color("#9c6400");
const INK = new THREE.Color("#15120e");
const PAPER = new THREE.Color("#efe7d7");
const RED = new THREE.Color("#b3401f");

// Keyframes per stage: [x, y, z, scale, lit, rival, sheets, yaw, camX, camY, camZ]
const K = [
  /* 0 hero        */ [3.3, -0.15, -1.2, 0.82, 11, 0, 0, 0.6, 0, 1.4, 9.8],
  /* 1 ban clock   */ [-3.2, -0.3, -1.4, 0.75, 11, 0, 0, -0.5, 0, 1.6, 10.2],
  /* 2 2026        */ [3.0, 0.2, -2.0, 0.7, 0, 0, 0, 0.3, 0, 1.6, 10.2],
  /* 3 collisions  */ [3.8, -0.1, -4.6, 0.6, 3, 1, 0, 0.9, 0, 1.6, 10.0],
  /* 4 arithmetic  */ [-3.4, -0.2, -1.8, 0.7, 4, 0, 0, -0.4, 0, 1.6, 10.2],
  /* 5 register    */ [3.2, 1.3, -3.0, 0.55, 2, 0, 1, 0.4, 0, 1.8, 10.8],
  /* 6 index       */ [2.6, 0.0, -1.6, 0.8, 6, 0, 0.4, 0.7, 0, 1.6, 10.2],
  /* 7 method      */ [-3.6, 0.0, -2.2, 0.6, 0, 0, 0, -0.6, 0, 1.6, 10.6],
  /* 8 run         */ [3.3, 1.4, -3.2, 0.52, 11, 0, 0, 0.5, 0, 1.8, 10.8],
  /* end           */ [2.6, 0.0, -1.6, 0.9, 11, 0, 0, 0.6, 0, 1.4, 10.0],
];
const MOBILE = (k, i) => i === 0 ? [1.0, 2.6, -1.5, 0.5, k[4], k[5], k[6], k[7], 0, 1.4, 12.8] : [1.2, 2.8, -2.5, 0.42, k[4], k[5], k[6], k[7], 0, 1.4, 12.8];

function frame(stage, mobile) {
  const i = Math.max(0, Math.min(K.length - 2, Math.floor(stage)));
  const f = smooth(0.15, 0.85, stage - i);
  const a = mobile ? MOBILE(K[i], i) : K[i], b = mobile ? MOBILE(K[i + 1], i + 1) : K[i + 1];
  return a.map((v, j) => v + (b[j] - v) * f);
}

const shadowy = (m) => { m.castShadow = true; m.receiveShadow = true; return m; };

/** A generic open-wheel car, about 3.6 units nose to tail, built from simple shapes. No team, no livery. */
function car(bodyColor, accent) {
  const g = new THREE.Group();
  const body = new THREE.MeshPhysicalMaterial({ color: bodyColor, roughness: 0.32, clearcoat: 0.8, clearcoatRoughness: 0.2 });
  const carbon = new THREE.MeshStandardMaterial({ color: INK, roughness: 0.55 });
  const trim = new THREE.MeshStandardMaterial({ color: accent, roughness: 0.4 });
  const box = (w, h, d, m) => shadowy(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m));

  const floor = box(3.1, 0.05, 1.05, carbon); floor.position.set(0.1, 0.12, 0); g.add(floor);
  const tub = box(1.5, 0.3, 0.46, body); tub.position.set(0.15, 0.32, 0); g.add(tub);
  // nose: a cone along -x
  const nose = shadowy(new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.2, 1.25, 20), body));
  nose.rotation.z = -Math.PI / 2; nose.position.set(-1.2, 0.3, 0); nose.scale.set(1, 1, 0.75); g.add(nose);
  // sidepods
  for (const s of [-1, 1]) { const p = box(0.95, 0.24, 0.3, body); p.position.set(0.45, 0.28, s * 0.38); g.add(p); }
  // engine cover sloping to the back, with an accent stripe
  const cover = box(1.15, 0.22, 0.3, body); cover.position.set(1.15, 0.36, 0); cover.rotation.z = -0.12; g.add(cover);
  const stripe = box(1.2, 0.02, 0.08, trim); stripe.position.set(0.9, 0.49, 0); stripe.rotation.z = -0.06; g.add(stripe);
  const airbox = box(0.3, 0.22, 0.2, carbon); airbox.position.set(0.55, 0.6, 0); g.add(airbox);
  // halo: an arc over the cockpit with a centre pillar
  const halo = shadowy(new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.025, 10, 32, Math.PI), carbon));
  halo.rotation.set(0, Math.PI / 2, 0); halo.position.set(0.05, 0.5, 0); g.add(halo);
  const pillar = box(0.03, 0.18, 0.03, carbon); pillar.position.set(-0.17, 0.52, 0); pillar.rotation.z = 0.5; g.add(pillar);
  const helmet = shadowy(new THREE.Mesh(new THREE.SphereGeometry(0.12, 20, 14), trim)); helmet.position.set(0.12, 0.52, 0); g.add(helmet);
  // wings
  const fw = box(0.32, 0.03, 1.35, carbon); fw.position.set(-1.78, 0.14, 0); g.add(fw);
  const fw2 = box(0.18, 0.03, 1.3, trim); fw2.position.set(-1.7, 0.2, 0); fw2.rotation.z = 0.25; g.add(fw2);
  for (const s of [-1, 1]) { const ep = box(0.36, 0.16, 0.02, carbon); ep.position.set(-1.76, 0.2, s * 0.67); g.add(ep); }
  const rw = box(0.3, 0.04, 1.0, carbon); rw.position.set(1.72, 0.78, 0); g.add(rw);
  const rw2 = box(0.2, 0.03, 1.0, trim); rw2.position.set(1.66, 0.86, 0); rw2.rotation.z = 0.3; g.add(rw2);
  for (const s of [-1, 1]) { const ep = box(0.42, 0.42, 0.02, carbon); ep.position.set(1.7, 0.66, s * 0.51); g.add(ep); }
  const pylon = box(0.05, 0.4, 0.05, carbon); pylon.position.set(1.6, 0.5, 0); g.add(pylon);
  // wheels: front slightly narrower than rear
  const tyre = new THREE.MeshStandardMaterial({ color: "#1d1a16", roughness: 0.85 });
  const rimMat = new THREE.MeshStandardMaterial({ color: "#8d8577", roughness: 0.4, metalness: 0.6 });
  const wheels = [];
  for (const [x, w, r] of [[-1.05, 0.26, 0.27], [1.25, 0.34, 0.3]]) for (const s of [-1, 1]) {
    const wg = new THREE.Group();
    const t = shadowy(new THREE.Mesh(new THREE.CylinderGeometry(r, r, w, 28), tyre)); t.rotation.x = Math.PI / 2; wg.add(t);
    const rim = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.62, r * 0.62, w + 0.01, 20), rimMat); rim.rotation.x = Math.PI / 2; wg.add(rim);
    wg.position.set(x, r, s * (0.52 + w / 2)); g.add(wg); wheels.push(wg);
  }
  g.userData.wheels = wheels;
  return g;
}

createWorld(document.getElementById("world"), async ({ scene, camera, mobile }) => {
  await document.fonts?.load("500 64px 'Geist Mono'").catch(() => {});
  const FLOOR = -1.6;

  const rig = new THREE.Group();
  scene.add(rig);
  const main = car(PAPER, ACC);
  rig.add(main);
  const rival = car(new THREE.Color("#d9d0bf"), RED);
  rival.visible = false;
  rig.add(rival);

  // twelve floor tiles in a ring, one per penalty point, numbered
  const ring = new THREE.Group();
  rig.add(ring);
  const tiles = [];
  for (let i = 0; i < 12; i++) {
    const a = Math.PI / 2 - (i / 12) * Math.PI * 2;
    const mat = new THREE.MeshStandardMaterial({ color: PAPER, roughness: 0.7 });
    const tile = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.06, 0.34), mat);
    tile.receiveShadow = true; tile.castShadow = true;
    tile.position.set(Math.cos(a) * 2.75, 0.03, Math.sin(a) * 2.75);
    tile.rotation.y = -a + Math.PI / 2;
    const tex = textTexture(String(i + 1), { font: "500 56px 'Geist Mono'", color: "#15120e", pad: 14 });
    const lab = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.55 }));
    lab.scale.set(0.13 * tex.userData.aspect, 0.13, 1);
    lab.position.set(Math.cos(a) * 3.15, 0.14, Math.sin(a) * 3.15);
    ring.add(tile, lab);
    tiles.push(mat);
  }

  // decision sheets for the register chapter
  const sheets = [];
  const sheetMat = new THREE.MeshStandardMaterial({ color: "#f6f1e7", roughness: 0.9, side: THREE.DoubleSide, transparent: true, opacity: 0 });
  const lineMat = new THREE.MeshBasicMaterial({ color: INK, transparent: true, opacity: 0 });
  const rand = (() => { let s = 5; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();
  for (let i = 0; i < 14; i++) {
    const sg = new THREE.Group();
    const p = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.95), sheetMat); p.castShadow = true; sg.add(p);
    for (let l = 0; l < 6; l++) { const ln = new THREE.Mesh(new THREE.PlaneGeometry(l === 0 ? 0.3 : 0.5 - (l % 2) * 0.12, 0.022), lineMat); ln.position.set(-0.05, 0.32 - l * 0.11, 0.002); sg.add(ln); }
    sg.userData = { x: (rand() - 0.5) * 9, y: rand() * 4.5, z: -2 - rand() * 4, v: 0.15 + rand() * 0.25, w: rand() * 6.28 };
    scene.add(sg); sheets.push(sg);
  }

  const look = new THREE.Vector3();
  scene.userData.logo = [main, ring];   // shown small and centred while the page loads

  return (st) => {
    const [x, y, z, sc, lit, rv, sh, yaw, cx, cy, cz] = frame(st.stage, st.mobile);
    const t = st.t;
    rig.position.set(x, FLOOR + (st.mobile ? y : 0), z);   // on a phone it sits high, above the text
    rig.scale.setScalar(sc);
    rig.rotation.y = yaw + Math.sin(t * 0.25) * 0.12 + st.px * 0.25;
    main.position.y = Math.sin(t * 6) * 0.004;
    main.userData.wheels.forEach((w) => (w.children[0].rotation.y = t * 2));

    // the ban clock chapter: points expire one by one, on a loop
    const stage = st.stage;
    let on = lit;
    if (stage > 0.6 && stage < 1.6) on = Math.max(0, 11 - Math.floor((t * 0.8) % 12));
    for (let i = 0; i < 12; i++) {
      const isOn = i < Math.round(on);
      const fresh = isOn && i >= Math.round(on) - 3 && stage < 0.6;
      tiles[i].color.copy(isOn ? (fresh ? ACC : INK) : PAPER);
    }

    // a second car alongside for the collisions chapter
    rival.visible = rv > 0.02;
    rival.position.set(-0.4 + (1 - rv) * -3, 0, 1.25 - Math.max(0, Math.sin(t * 1.4)) * 0.08 * rv);
    rival.rotation.y = 0.06 * Math.sin(t * 1.4);
    rival.scale.setScalar(Math.max(0.001, rv));

    // sheets drift up in the register chapter
    sheetMat.opacity = sh * 0.95; lineMat.opacity = sh * 0.55;
    sheets.forEach((s) => {
      const u = s.userData;
      s.visible = sh > 0.02;
      s.position.set(u.x + 2 + Math.sin(t * 0.3 + u.w) * 0.3, -1 + ((u.y + t * u.v) % 5.5), u.z);
      s.rotation.set(Math.sin(t * 0.5 + u.w) * 0.3, t * 0.2 + u.w, Math.sin(t * 0.4 + u.w) * 0.15);
    });

    camera.position.set(cx + st.px * 0.35, cy - st.py * 0.2, cz);
    look.set(cx * 0.6, -0.1 + (cy - 1.4) * 0.15, -2);
    camera.lookAt(look);
  };
}, { bg: "#e8e1d3", fog: [10, 40] });
