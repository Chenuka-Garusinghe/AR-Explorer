import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import Stats from "three/addons/libs/stats.module.js";
import { ARButton } from "three/addons/webxr/ARButton.js";
import JSZIP from "jszip";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

// Use env override when provided; otherwise default to same origin (proxied by Vite dev server)
const API_BASE = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

class App {
  constructor(prompt) {
    this.prompt = prompt;  // Store the prompt
    
    const container = document.createElement("div");
    document.body.appendChild(container);

    this.clock = new THREE.Clock();

    this.camera = new THREE.PerspectiveCamera(
      70,
      window.innerWidth / window.innerHeight,
      0.01,
      20,
    );

    this.scene = new THREE.Scene();

    this.scene.add(new THREE.HemisphereLight(0x606060, 0x404040));

    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(1, 1, 1).normalize();
    this.scene.add(light);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 3.5, 0);
    this.controls.update();

    this.stats = new Stats();

    this.initScene();
    this.setupVR();

    window.addEventListener("resize", this.resize.bind(this));
  }

  async handleFile(blob) {
    const folderPath = "";
    const fileList = [];

    let zip;
    try {
      zip = await JSZIP.loadAsync(blob);
    } catch (err) {
      console.error("Failed to read asset bundle as zip", err);
      return [];
    }
    const allPaths = Object.keys(zip.files);

    let ptr_1 = 0;
    let ptr_2 = allPaths.length - 1;

    while (allPaths.length > 0) {
      if (ptr_1 == ptr_2) {
        break;
      }
      let currentPath = allPaths[ptr_1];
      if (allPaths[ptr_2].includes(currentPath.split("/")[1])) {
        fileList.push([allPaths[ptr_1], allPaths[ptr_2]]);
        allPaths.splice(ptr_2, 1);
        allPaths.splice(ptr_1, 1);
        ptr_1 = 0;
        ptr_2 = allPaths.length - 1;
      } else {
        ptr_1 += 1;
      }
    }

    const sceneData = [];
    for (let itemPair of fileList) {
      let glbFile = null;
      let posTextFile = null;
      if (itemPair[0].endsWith(".glb")) {
        glbFile = itemPair[0];
        posTextFile = itemPair[1];
      } else {
        glbFile = itemPair[1];
        posTextFile = itemPair[0];
      }

      const posData = await zip.file(posTextFile).async("string");
      const positionValues = posData.split(",").map(parseFloat);

      const position = new THREE.Vector3(
        positionValues[0],
        positionValues[1],
        positionValues[2],
      );

      const glbBlob = await zip.file(glbFile).async("blob");
      const glbUrl = URL.createObjectURL(glbBlob);

      const promise = new Promise((resolve, reject) => {
        const loader = new GLTFLoader();
        loader.load(
          glbUrl,
          (gltf) => resolve(gltf),
          undefined,
          (error) => reject(error),
        );
      });
      sceneData.push([promise, position]);
    }
    return sceneData;
  }

  // fetch the information from python server running via uvicorn server:app --reload --port 8000
  async fetchAssets(prompt) {
    try {
      // Use GET to avoid preflight on mobile; rely on Vite proxy during dev so path is same-origin.
      const url = `${API_BASE}/generate?prompt=${encodeURIComponent(prompt)}`;
      const response = await fetch(url, {
        method: "GET",
      });

      if (!response.ok) {
        console.error("Asset fetch failed", response.status, response.statusText);
        return null;
      }

      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("zip")) {
        console.error("Unexpected response type; expected zip, got:", contentType);
        return null;
      }

      return await response.blob();
    } catch (error) {
      console.error("Error fetching assets:", error);
      return null;
    }
  }

  async initScene() {
    try {
      const blob = await this.fetchAssets(this.prompt);
      if (!blob) {
        console.error("No asset bundle returned for prompt:", this.prompt);
        return;
      }
      const sceneData = await this.handleFile(blob);

      // let allGltfs = await Promise.all(sceneData[0])

      for (let sceneDataPair of sceneData) {
        let gltf = await sceneDataPair[0];
        let position = sceneDataPair[1];
        let model = gltf.scene;
        model.position.copy(position);
        this.scene.add(model);
        console.log("add a model")
      }
    } catch (err) {
      console.error("Failed to initialize scene", err);
    }

    this.geometry = new THREE.BoxGeometry(0.06, 0.06, 0.06);
    this.meshes = [];

    // Add a test cube so we can see something initially
    const material = new THREE.MeshPhongMaterial({ color: 0x00ff00 });
    const testCube = new THREE.Mesh(this.geometry, material);
    testCube.position.set(0, 0, -0.5);
    this.scene.add(testCube);
    this.meshes.push(testCube);
  }

  setupVR() {
    this.renderer.xr.enabled = true;

    const self = this;
    let controller;

    function onSelect() {}

    const btn = ARButton.createButton(this.renderer);
    document.body.appendChild(btn);

    controller = this.renderer.xr.getController(0);
    controller.addEventListener("select", onSelect);
    this.scene.add(controller);

    this.renderer.setAnimationLoop(this.render.bind(this));
  }

  resize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  render() {
    this.stats.update();
    this.meshes.forEach((mesh) => {
      mesh.rotateY(0.01);
    });
    this.renderer.render(this.scene, this.camera);
  }
}

export { App };
