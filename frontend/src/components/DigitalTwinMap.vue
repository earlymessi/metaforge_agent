<template>
  <div class="twin-wrap">
    <svg
      v-if="machines.length"
      class="twin-svg"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect
        :x="bounds.minX - 24"
        :y="bounds.minZ - 24"
        :width="bounds.w + 48"
        :height="bounds.h + 48"
        fill="#1e2a3a"
        rx="6"
      />
      <g v-for="m in machines" :key="'m' + m.id">
        <rect
          :x="m.x - 20"
          :y="flipZ(m.z) - 14"
          width="40"
          height="28"
          :fill="m.status === 'running' ? '#00c9a7' : '#3d4f63'"
          :stroke="m.status === 'running' ? '#00ffcc' : '#5c6b7a'"
          stroke-width="1.5"
          rx="4"
        />
        <text :x="m.x" :y="flipZ(m.z) + 4" text-anchor="middle" font-size="10" :fill="m.status === 'running' ? '#00332a' : '#cfd8dc'">
          M{{ m.id }}
        </text>
        <title>{{ m.current_job || (m.status === 'running' ? '加工中' : '空闲') }}</title>
      </g>
      <g v-for="a in agvs" :key="'a' + a.id">
        <circle :cx="a.x" :cy="flipZ(a.z)" r="11" fill="#e6a23c" stroke="#fff" stroke-width="2" />
        <text :x="a.x" :y="flipZ(a.z) + 4" text-anchor="middle" font-size="9" fill="#fff">A{{ a.id }}</text>
      </g>
      <g v-for="s in staff" :key="'s' + s.id">
        <circle :cx="s.x" :cy="flipZ(s.z)" r="7" fill="#f56c6c" stroke="#fff" stroke-width="1.5" />
      </g>
    </svg>
    <el-empty v-else description="暂无机台布局" :image-size="64" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  machines: { type: Array, default: () => [] },
  agvs: { type: Array, default: () => [] },
  staff: { type: Array, default: () => [] },
})

const bounds = computed(() => {
  const pts = [
    ...props.machines.map((m) => ({ x: Number(m.x), z: Number(m.z) })),
    ...props.agvs.map((a) => ({ x: Number(a.x), z: Number(a.z) })),
    ...props.staff.map((s) => ({ x: Number(s.x), z: Number(s.z) })),
  ]
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
  return `${b.minX - 36} ${-(b.minZ + b.h + 36)} ${b.w + 72} ${b.h + 72}`
})

function flipZ(z) {
  return -Number(z)
}
</script>

<style scoped>
.twin-wrap { width: 100%; }
.twin-svg {
  width: 100%;
  height: 340px;
  border-radius: 8px;
  border: 1px solid #2c3e50;
}
</style>
