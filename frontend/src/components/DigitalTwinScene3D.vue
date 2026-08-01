<template>
  <div class="scene-root">
    <div v-if="machines.length" ref="containerRef" class="scene-canvas" />
    <el-empty v-else description="暂无机台布局" :image-size="64" />
    <div v-if="hoverText" class="hover-tip">{{ hoverText }}</div>
    <div v-if="machines.length" class="hint">滚轮缩放 · 右键平移</div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import {
  createAgvGroup,
  createMachineGroup,
  createStaffGroup,
  disposeObject3D,
  updateAgvGroup,
  updateMachineGroup,
  updateStaffGroup,
} from '../utils/digitalTwinModels.js'

const props = defineProps({
  machines: { type: Array, default: () => [] },
  agvs: { type: Array, default: () => [] },
  staff: { type: Array, default: () => [] },
})

const containerRef = ref(null)
const hoverText = ref('')

let renderer = null
let scene = null
let camera = null
let controls = null
let animationId = 0
let resizeObserver = null
let raycaster = null
let pointer = null
let cameraFramed = false
let envBuilt = false

const machineMeshes = new Map()
const agvMeshes = new Map()
const staffMeshes = new Map()
let floorMesh = null
let aisleMesh = null
let gridHelper = null
let envGroup = null
let sunLight = null

function calcBounds() {
  const pts = [
    ...props.machines.map((m) => ({ x: Number(m.x), z: Number(m.z) })),
    ...props.agvs.map((a) => ({ x: Number(a.x), z: Number(a.z) })),
    ...props.staff.map((s) => ({ x: Number(s.x), z: Number(s.z) })),
  ]
  if (!pts.length) {
    return { minX: -60, maxX: 60, minZ: -60, maxZ: 60, centerX: 0, centerZ: 0, span: 120 }
  }
  const xs = pts.map((p) => p.x)
  const zs = pts.map((p) => p.z)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minZ = Math.min(...zs)
  const maxZ = Math.max(...zs)
  const span = Math.max(maxX - minX, maxZ - minZ, 80)
  return {
    minX,
    maxX,
    minZ,
    maxZ,
    centerX: (minX + maxX) / 2,
    centerZ: (minZ + maxZ) / 2,
    span,
  }
}

function clearEnvironment() {
  if (envGroup) {
    scene?.remove(envGroup)
    disposeObject3D(envGroup)
    envGroup = null
  }
  gridHelper = null
  floorMesh = null
  aisleMesh = null
  envBuilt = false
}

function rebuildEnvironment() {
  if (envBuilt || !props.machines.length) return

  const b = calcBounds()
  const pad = 48
  const floorW = b.span + pad * 2
  const floorD = b.span + pad * 2

  envGroup = new THREE.Group()

  const floorGeo = new THREE.PlaneGeometry(floorW, floorD)
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0x2b3642,
    roughness: 0.92,
    metalness: 0.05,
  })
  floorMesh = new THREE.Mesh(floorGeo, floorMat)
  floorMesh.rotation.x = -Math.PI / 2
  floorMesh.position.set(b.centerX, 0, b.centerZ)
  floorMesh.receiveShadow = true
  envGroup.add(floorMesh)

  gridHelper = new THREE.GridHelper(
    floorW,
    Math.max(14, Math.round(floorW / 18)),
    0x4a6075,
    0x34495e,
  )
  gridHelper.position.set(b.centerX, 0.06, b.centerZ)
  envGroup.add(gridHelper)

  const zs = props.machines.map((m) => Number(m.z))
  const uniqueZ = [...new Set(zs)].sort((a, b) => a - b)
  if (uniqueZ.length >= 2) {
    const aisleZ = (uniqueZ[0] + uniqueZ[uniqueZ.length - 1]) / 2
    const aisleGeo = new THREE.PlaneGeometry(floorW * 0.82, 22)
    const aisleMat = new THREE.MeshStandardMaterial({
      color: 0xf9a825,
      roughness: 0.8,
      transparent: true,
      opacity: 0.18,
    })
    aisleMesh = new THREE.Mesh(aisleGeo, aisleMat)
    aisleMesh.rotation.x = -Math.PI / 2
    aisleMesh.position.set(b.centerX, 0.1, aisleZ)
    envGroup.add(aisleMesh)

    const lineMat = new THREE.MeshStandardMaterial({ color: 0xfdd835, emissive: 0xfdd835, emissiveIntensity: 0.25 })
    for (const side of [-1, 1]) {
      const stripe = new THREE.Mesh(new THREE.PlaneGeometry(floorW * 0.78, 0.35), lineMat)
      stripe.rotation.x = -Math.PI / 2
      stripe.position.set(b.centerX, 0.12, aisleZ + side * 10.5)
      envGroup.add(stripe)
    }
  }

  const wallMat = new THREE.MeshStandardMaterial({
    color: 0x1a2330,
    roughness: 0.95,
    transparent: true,
    opacity: 0.55,
  })
  const wallH = 6
  const walls = [
    [floorW, wallH, 1, b.centerX, wallH / 2, b.centerZ - floorD / 2],
    [floorW, wallH, 1, b.centerX, wallH / 2, b.centerZ + floorD / 2],
    [1, wallH, floorD, b.centerX - floorW / 2, wallH / 2, b.centerZ],
    [1, wallH, floorD, b.centerX + floorW / 2, wallH / 2, b.centerZ],
  ]
  for (const [w, h, d, px, py, pz] of walls) {
    const wall = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallMat)
    wall.position.set(px, py, pz)
    wall.receiveShadow = true
    envGroup.add(wall)
  }

  scene.add(envGroup)
  envBuilt = true
}

function upsertMachine(key, item) {
  const x = Number(item.x)
  const z = Number(item.z)
  let group = machineMeshes.get(key)
  if (!group) {
    group = createMachineGroup()
    scene.add(group)
    machineMeshes.set(key, group)
  }
  group.position.set(x, 0, z)
  updateMachineGroup(group, item)
}

function upsertAgv(key, item) {
  const x = Number(item.x)
  const z = Number(item.z)
  let group = agvMeshes.get(key)
  if (!group) {
    group = createAgvGroup()
    scene.add(group)
    agvMeshes.set(key, group)
  }
  group.position.set(x, 0, z)
  updateAgvGroup(group, item)
}

function upsertStaff(key, item) {
  const x = Number(item.x)
  const z = Number(item.z)
  let group = staffMeshes.get(key)
  if (!group) {
    group = createStaffGroup()
    scene.add(group)
    staffMeshes.set(key, group)
  }
  group.position.set(x, 0, z)
  updateStaffGroup(group, item)
}

function removeStale(map, keys) {
  for (const [key, obj] of map) {
    if (!keys.has(key)) {
      scene.remove(obj)
      disposeObject3D(obj)
      map.delete(key)
    }
  }
}

function syncMeshes() {
  if (!scene) return

  const machineKeys = new Set()
  for (const m of props.machines) {
    const key = `m-${m.id}`
    machineKeys.add(key)
    upsertMachine(key, m)
  }
  removeStale(machineMeshes, machineKeys)

  const agvKeys = new Set()
  for (const a of props.agvs) {
    const key = `a-${a.id}`
    agvKeys.add(key)
    upsertAgv(key, a)
  }
  removeStale(agvMeshes, agvKeys)

  const staffKeys = new Set()
  for (const s of props.staff) {
    const key = `s-${s.id}`
    staffKeys.add(key)
    upsertStaff(key, s)
  }
  removeStale(staffMeshes, staffKeys)

  rebuildEnvironment()
  if (!cameraFramed) frameCamera()
}

/**
 * 正前方俯视：相机落在 X 轴中线、-Z 侧，沿 +Z 直视车间中心，与平面图轴向一致且不偏转。
 */
function frameCamera() {
  if (!camera || !controls || !props.machines.length) return
  const b = calcBounds()
  const span = b.span
  const depth = Math.max(b.maxZ - b.minZ, 80)
  const back = depth * 0.95 + 48
  const elev = span * 0.78
  const target = new THREE.Vector3(b.centerX, 0, b.centerZ)

  camera.fov = 38
  camera.updateProjectionMatrix()
  camera.position.set(b.centerX, elev, b.minZ - back)
  camera.lookAt(target)
  camera.up.set(0, 1, 0)

  controls.target.copy(target)
  controls.enableRotate = false
  controls.enablePan = true
  controls.update()

  if (sunLight) {
    sunLight.position.set(b.centerX, elev + 60, b.minZ - back - 40)
    sunLight.target.position.copy(target)
    sunLight.target.updateMatrixWorld()
  }

  cameraFramed = true
}

function pickLabel(hit) {
  const root = hit.object.userData?.root || hit.object
  return root.userData?.label || ''
}

function onPointerMove(event) {
  if (!raycaster || !camera || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const targets = [...machineMeshes.values(), ...agvMeshes.values(), ...staffMeshes.values()]
  const hits = raycaster.intersectObjects(targets, true)
  hoverText.value = hits.length ? pickLabel(hits[0]) : ''
  document.body.style.cursor = hits.length ? 'pointer' : ''
}

function animate() {
  animationId = requestAnimationFrame(animate)
  const pulse = 0.45 + Math.sin(Date.now() * 0.005) * 0.25
  for (const group of machineMeshes.values()) {
    if (!group.userData.running) continue
    const led = group.getObjectByName('statusLed')
    if (led?.material) led.material.emissiveIntensity = pulse
  }
  controls?.update()
  renderer?.render(scene, camera)
}

function initScene() {
  if (!containerRef.value) return
  const el = containerRef.value
  const w = el.clientWidth || 640
  const h = 420

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0f1620)
  scene.fog = new THREE.Fog(0x0f1620, spanFallback() * 1.2, spanFallback() * 3.5)

  camera = new THREE.PerspectiveCamera(40, w / h, 0.5, 2500)
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.07
  controls.minDistance = spanFallback() * 0.5
  controls.maxDistance = spanFallback() * 2.0

  const hemi = new THREE.HemisphereLight(0xddeeff, 0x2a3540, 0.65)
  scene.add(hemi)

  sunLight = new THREE.DirectionalLight(0xfff5e6, 1.05)
  sunLight.castShadow = true
  sunLight.shadow.mapSize.set(1024, 1024)
  sunLight.shadow.camera.near = 10
  sunLight.shadow.camera.far = 500
  sunLight.shadow.camera.left = -200
  sunLight.shadow.camera.right = 200
  sunLight.shadow.camera.top = 200
  sunLight.shadow.camera.bottom = -200
  scene.add(sunLight)
  scene.add(sunLight.target)

  const fill = new THREE.DirectionalLight(0x90caf9, 0.28)
  fill.position.set(0, 120, 80)
  scene.add(fill)

  raycaster = new THREE.Raycaster()
  pointer = new THREE.Vector2()
  renderer.domElement.addEventListener('pointermove', onPointerMove)

  resizeObserver = new ResizeObserver(() => {
    if (!containerRef.value || !renderer || !camera) return
    const nw = containerRef.value.clientWidth || 640
    const nh = 420
    camera.aspect = nw / nh
    camera.updateProjectionMatrix()
    renderer.setSize(nw, nh)
  })
  resizeObserver.observe(el)

  syncMeshes()
  animate()
}

function spanFallback() {
  return calcBounds().span || 120
}

function disposeMap(map) {
  for (const [, obj] of map) {
    scene?.remove(obj)
    disposeObject3D(obj)
  }
  map.clear()
}

function disposeScene() {
  cancelAnimationFrame(animationId)
  renderer?.domElement?.removeEventListener('pointermove', onPointerMove)
  resizeObserver?.disconnect()
  disposeMap(machineMeshes)
  disposeMap(agvMeshes)
  disposeMap(staffMeshes)
  clearEnvironment()
  controls?.dispose()
  renderer?.dispose()
  if (renderer?.domElement?.parentNode) {
    renderer.domElement.parentNode.removeChild(renderer.domElement)
  }
  document.body.style.cursor = ''
  renderer = null
  scene = null
  camera = null
  controls = null
  sunLight = null
  cameraFramed = false
  hoverText.value = ''
}

onMounted(() => {
  if (props.machines.length) initScene()
})

onUnmounted(disposeScene)

watch(
  () => [props.machines, props.agvs, props.staff],
  () => {
    if (!props.machines.length) {
      disposeScene()
      return
    }
    if (!scene) {
      initScene()
      return
    }
    syncMeshes()
  },
  { deep: true },
)
</script>

<style scoped>
.scene-root {
  position: relative;
  width: 100%;
}
.scene-canvas {
  width: 100%;
  height: 420px;
  border-radius: 8px;
  border: 1px solid #2c3e50;
  overflow: hidden;
}
.hover-tip {
  position: absolute;
  left: 12px;
  top: 12px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.72);
  color: #e8f4ff;
  font-size: 12px;
  pointer-events: none;
  z-index: 2;
}
.hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
