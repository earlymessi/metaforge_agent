import * as THREE from 'three'

const MAT = {
  machineBody: () =>
    new THREE.MeshStandardMaterial({ color: 0x5a6d7e, metalness: 0.55, roughness: 0.38 }),
  machineBase: () =>
    new THREE.MeshStandardMaterial({ color: 0x3d4f5f, metalness: 0.45, roughness: 0.55 }),
  machineTable: () =>
    new THREE.MeshStandardMaterial({ color: 0x8a9bab, metalness: 0.65, roughness: 0.32 }),
  machinePanel: () =>
    new THREE.MeshStandardMaterial({
      color: 0x1a2530,
      emissive: 0x1e90ff,
      emissiveIntensity: 0.15,
      metalness: 0.2,
      roughness: 0.6,
    }),
  agvBody: () =>
    new THREE.MeshStandardMaterial({ color: 0xffa726, metalness: 0.35, roughness: 0.45 }),
  agvDeck: () =>
    new THREE.MeshStandardMaterial({ color: 0xffcc80, metalness: 0.25, roughness: 0.5 }),
  agvWheel: () =>
    new THREE.MeshStandardMaterial({ color: 0x263238, metalness: 0.1, roughness: 0.85 }),
  staffVest: () =>
    new THREE.MeshStandardMaterial({ color: 0xff7043, roughness: 0.7 }),
  staffBody: () =>
    new THREE.MeshStandardMaterial({ color: 0x37474f, roughness: 0.75 }),
  staffSkin: () =>
    new THREE.MeshStandardMaterial({ color: 0xffccbc, roughness: 0.8 }),
  staffHelmet: () =>
    new THREE.MeshStandardMaterial({ color: 0xffeb3b, metalness: 0.15, roughness: 0.55 }),
}

function part(geometry, material, position, rotation, name, castShadow = true) {
  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.set(...position)
  if (rotation) mesh.rotation.set(...rotation)
  mesh.name = name
  mesh.castShadow = castShadow
  mesh.receiveShadow = true
  return mesh
}

export function createMachineGroup() {
  const group = new THREE.Group()
  group.name = 'machine'

  group.add(part(new THREE.BoxGeometry(12, 2.4, 15), MAT.machineBase(), [0, 1.2, 0], null, 'base'))
  group.add(part(new THREE.BoxGeometry(9.5, 7.2, 10.5), MAT.machineBody(), [0, 5.4, -0.5], null, 'cabinet'))
  group.add(
    part(new THREE.BoxGeometry(7.5, 0.9, 5.5), MAT.machineTable(), [0, 2.85, 3.2], null, 'table'),
  )
  group.add(
    part(new THREE.BoxGeometry(4.2, 2.8, 3.6), MAT.machineBody(), [0, 6.8, 4.2], null, 'spindle'),
  )
  group.add(
    part(new THREE.BoxGeometry(0.9, 4.2, 2.8), MAT.machinePanel(), [5.2, 5.2, 0], null, 'panel'),
  )
  group.add(
    part(
      new THREE.BoxGeometry(7.5, 0.35, 1.2),
      new THREE.MeshStandardMaterial({
        color: 0x2e7d32,
        emissive: 0x00ff88,
        emissiveIntensity: 0,
        metalness: 0.3,
        roughness: 0.4,
      }),
      [0, 9.35, 2.5],
      null,
      'statusLed',
    ),
  )
  group.add(
    part(
      new THREE.BoxGeometry(2.4, 0.8, 0.15),
      new THREE.MeshStandardMaterial({
        color: 0x111111,
        emissive: 0x00e5ff,
        emissiveIntensity: 0.25,
      }),
      [5.35, 5.8, 1.45],
      null,
      'screen',
      false,
    ),
  )

  group.traverse((child) => {
    if (child.isMesh) child.userData.root = group
  })
  return group
}

export function updateMachineGroup(group, item) {
  const running = item.status === 'running'
  const led = group.getObjectByName('statusLed')
  const screen = group.getObjectByName('screen')
  const cabinet = group.getObjectByName('cabinet')

  if (led?.material) {
    led.material.color.setHex(running ? 0x00c853 : 0x455a64)
    led.material.emissive.setHex(running ? 0x00ff88 : 0x000000)
    led.material.emissiveIntensity = running ? 0.55 : 0
  }
  if (screen?.material) {
    screen.material.emissiveIntensity = running ? 0.65 : 0.2
    screen.material.emissive.setHex(running ? 0x00e5ff : 0x1a237e)
  }
  if (cabinet?.material) {
    cabinet.material.emissive.setHex(running ? 0x1b5e20 : 0x000000)
    cabinet.material.emissiveIntensity = running ? 0.08 : 0
  }

  group.userData.kind = 'm'
  group.userData.id = item.id
  group.userData.label = buildMachineLabel(item)
  group.userData.running = running
}

export function createAgvGroup() {
  const group = new THREE.Group()
  group.name = 'agv'

  group.add(part(new THREE.BoxGeometry(6.5, 1.1, 9), MAT.agvBody(), [0, 0.75, 0], null, 'chassis'))
  group.add(part(new THREE.BoxGeometry(5.5, 0.45, 7), MAT.agvDeck(), [0, 1.45, 0], null, 'deck'))
  group.add(part(new THREE.BoxGeometry(4, 1.8, 3.5), MAT.agvDeck(), [0, 2.55, -0.5], null, 'cargo'))

  const wheelGeo = new THREE.CylinderGeometry(0.55, 0.55, 0.5, 12)
  const wheelMat = MAT.agvWheel()
  const wheels = [
    [-2.4, 0.55, 3.2],
    [2.4, 0.55, 3.2],
    [-2.4, 0.55, -3.2],
    [2.4, 0.55, -3.2],
  ]
  wheels.forEach((pos, i) => {
    group.add(
      part(wheelGeo.clone(), wheelMat, pos, [0, 0, Math.PI / 2], `wheel${i}`, false),
    )
  })
  wheelGeo.dispose()

  group.add(
    part(
      new THREE.SphereGeometry(0.35, 10, 10),
      new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0xffab00,
        emissiveIntensity: 0.5,
      }),
      [0, 3.35, 2.8],
      null,
      'beacon',
      false,
    ),
  )

  group.traverse((child) => {
    if (child.isMesh) child.userData.root = group
  })
  return group
}

export function updateAgvGroup(group, item) {
  const busy = item.status === 'busy' || item.status === 'moving'
  const beacon = group.getObjectByName('beacon')
  if (beacon?.material) {
    beacon.material.emissiveIntensity = busy ? 0.9 : 0.35
    beacon.material.emissive.setHex(busy ? 0xff6d00 : 0xffab00)
  }
  group.userData.kind = 'a'
  group.userData.id = item.id
  group.userData.label = `AGV ${item.id} · ${item.status || 'idle'}`
}

export function createStaffGroup() {
  const group = new THREE.Group()
  group.name = 'staff'

  group.add(part(new THREE.BoxGeometry(1.6, 2.2, 1), MAT.staffBody(), [0, 2.5, 0], null, 'legs'))
  group.add(part(new THREE.BoxGeometry(2.2, 2.6, 1.2), MAT.staffVest(), [0, 4.6, 0], null, 'torso'))
  group.add(part(new THREE.SphereGeometry(0.75, 12, 12), MAT.staffSkin(), [0, 6.5, 0], null, 'head'))
  group.add(
    part(
      new THREE.CylinderGeometry(0.82, 0.9, 0.55, 12),
      MAT.staffHelmet(),
      [0, 7.35, 0],
      null,
      'helmet',
    ),
  )
  group.add(
    part(
      new THREE.BoxGeometry(0.35, 1.6, 0.35),
      MAT.staffBody(),
      [-1.35, 4.8, 0],
      [0, 0, 0.35],
      'armL',
      false,
    ),
  )
  group.add(
    part(
      new THREE.BoxGeometry(0.35, 1.6, 0.35),
      MAT.staffBody(),
      [1.35, 4.8, 0],
      [0, 0, -0.35],
      'armR',
      false,
    ),
  )

  group.traverse((child) => {
    if (child.isMesh) child.userData.root = group
  })
  return group
}

export function updateStaffGroup(group, item) {
  group.userData.kind = 's'
  group.userData.id = item.id
  const skills = (item.skills || []).join('/')
  const job = item.job_name ? ` · ${item.job_name}` : ''
  group.userData.label = `${item.name || '人员'} · M${item.machine_id}${job}${skills ? ` · ${skills}` : ''}`
}

function buildMachineLabel(item) {
  const status = item.status === 'running' ? '运行中' : '空闲'
  const job = item.current_job ? ` · ${item.current_job}` : ''
  return `M${item.id} · ${status}${job}`
}

export function disposeObject3D(obj) {
  if (!obj) return
  obj.traverse((child) => {
    child.geometry?.dispose()
    if (Array.isArray(child.material)) {
      child.material.forEach((m) => m.dispose())
    } else {
      child.material?.dispose()
    }
  })
}
