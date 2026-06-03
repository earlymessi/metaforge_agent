<template>
  <div class="map-wrap">
    <svg
      v-if="machines.length"
      class="map-svg"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect :x="bounds.minX - 20" :y="bounds.minZ - 20" :width="bounds.w + 40" :height="bounds.h + 40" fill="#f5f7fa" rx="4" />
      <line
        v-for="(seg, i) in routeSegments"
        :key="'r' + i"
        :x1="seg.x1"
        :y1="seg.z1"
        :x2="seg.x2"
        :y2="seg.z2"
        :stroke="seg.highlight ? '#409eff' : '#c0c4cc'"
        :stroke-width="seg.highlight ? 3 : 1.5"
        stroke-dasharray="6 4"
        opacity="0.85"
      />
      <g v-for="m in machines" :key="'m' + m.id">
        <rect
          :x="m.x - 18"
          :y="flipZ(m.z) - 12"
          width="36"
          height="24"
          :fill="machineFill(m.id)"
          stroke="#606266"
          stroke-width="1"
          rx="3"
        />
        <text :x="m.x" :y="flipZ(m.z) + 4" text-anchor="middle" font-size="10" fill="#303133">M{{ m.id }}</text>
      </g>
      <g v-for="a in agvMarkers" :key="'a' + a.id">
        <circle :cx="a.x" :cy="flipZ(a.z)" r="10" fill="#e6a23c" stroke="#fff" stroke-width="2" />
        <text :x="a.x" :y="flipZ(a.z) + 4" text-anchor="middle" font-size="9" fill="#fff">A{{ a.id }}</text>
      </g>
    </svg>
    <el-empty v-else description="暂无机台布局" :image-size="64" />
    <div v-if="machines.length" class="legend">
      <span><i class="dot machine" />机台</span>
      <span><i class="dot agv" />AGV</span>
      <span><i class="dot route" />搬运路线</span>
      <span v-if="highlightId" class="hint">高亮：{{ highlightId }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  machines: { type: Array, default: () => [] },
  fleetStatus: { type: Array, default: () => [] },
  tasks: { type: Array, default: () => [] },
  highlightTaskId: { type: String, default: '' },
  maxRoutes: { type: Number, default: 80 },
})

const posById = computed(() => {
  const m = {}
  for (const x of props.machines) {
    if (x?.id != null) m[Number(x.id)] = { x: Number(x.x), z: Number(x.z) }
  }
  return m
})

const bounds = computed(() => {
  const pts = props.machines.map((m) => ({ x: Number(m.x), z: Number(m.z) }))
  if (!pts.length) return { minX: 0, minZ: 0, w: 100, h: 100 }
  const xs = pts.map((p) => p.x)
  const zs = pts.map((p) => p.z)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minZ = Math.min(...zs)
  const maxZ = Math.max(...zs)
  return { minX, minZ, w: Math.max(maxX - minX, 80), h: Math.max(maxZ - minZ, 80) }
})

const viewBox = computed(() => {
  const b = bounds.value
  return `${b.minX - 30} ${-(b.minZ + b.h + 30)} ${b.w + 60} ${b.h + 60}`
})

function flipZ(z) {
  return -Number(z)
}

function machineFill(mid) {
  const locs = props.fleetStatus.map((f) => Number(f.location))
  if (locs.includes(mid)) return '#fdf6ec'
  return '#ffffff'
}

const agvMarkers = computed(() => {
  const out = []
  for (const f of props.fleetStatus) {
    const loc = Number(f.location)
    const p = posById.value[loc]
    if (p) out.push({ id: f.id, x: p.x, z: p.z + (p.z < 0 ? 18 : -18) })
  }
  return out
})

const highlightId = computed(() => props.highlightTaskId || '')

const routeSegments = computed(() => {
  const segs = []
  const list = (props.tasks || []).slice(0, props.maxRoutes)
  for (const t of list) {
    const from = Number(t.from_machine)
    const to = Number(t.to_machine)
    const p1 = posById.value[from]
    const p2 = posById.value[to]
    if (!p1 || !p2) continue
    const tid = t.id || t.task_id || ''
    segs.push({
      x1: p1.x,
      z1: p1.z,
      x2: p2.x,
      z2: p2.z,
      highlight: highlightId.value && tid === highlightId.value,
    })
  }
  return segs.map((s) => ({
    x1: s.x1,
    z1: flipZ(s.z1),
    x2: s.x2,
    z2: flipZ(s.z2),
    highlight: s.highlight,
  }))
})
</script>

<style scoped>
.map-wrap { width: 100%; }
.map-svg {
  width: 100%;
  height: 280px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 4px;
  vertical-align: middle;
}
.dot.machine { background: #fff; border: 1px solid #606266; }
.dot.agv { background: #e6a23c; border-radius: 50%; }
.dot.route { background: #409eff; height: 2px; width: 14px; }
.hint { color: #409eff; }
</style>
