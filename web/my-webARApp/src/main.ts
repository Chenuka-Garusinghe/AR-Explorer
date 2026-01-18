import * as THREE from "three";
import { ARButton } from "three/addons/webxr/ARButton.js";

let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer!: THREE.WebGLRenderer;
let cube: THREE.Mesh;

init();
renderer.setAnimationLoop(render);

function init(): void {
  scene = new THREE.Scene();

  camera = new THREE.PerspectiveCamera(
    70,
    window.innerWidth / window.innerHeight,
    0.01,
    20
  );

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.xr.enabled = true;
  document.body.appendChild(renderer.domElement);

  // AR button (no hit-test needed)
  document.body.appendChild(ARButton.createButton(renderer));

  // A cube 1m in front of the camera
  cube = new THREE.Mesh(
    // new THREE.BoxGeometry(0.15, 0.15, 0.15),
    // triangle
    // new THREE.ConeGeometry(0.1, 0.2, 3),
    // 3d hexagon
    new THREE.CylinderGeometry(0.1, 0.1, 0.2, 6),
    new THREE.MeshBasicMaterial({ color: 0xff0000 })
  );
  cube.position.set(0, 0, -1);
  camera.add(cube);     // attach cube to camera
  scene.add(camera);    // camera must be in scene to render attached objects

  window.addEventListener("resize", onResize);
}

function render(): void {
  cube.rotation.y += 0.02; // simple animation
  renderer.render(scene, camera);
}

function onResize(): void {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}
