<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { buildImpactGanttOption } from '../utils/executionGantt'

const props = defineProps({
  r0Gantt: { type: Array, default: () => [] },
  r1Gantt: { type: Array, default: () => [] },
  r2Gantt: { type: Array, default: () => [] },
  layers: { type: Object, default: () => ({}) },
  scenarios: { type: Object, default: () => ({}) },
  rescheduledKeys: { type: Array, default: () => [] },
  eventType: { type: String, default: '' },
})

const r0Ref = ref(null)
const r1Ref = ref(null)
const r2Ref = ref(null)
let charts = [null, null, null]

function titleFor(key, fallback) {
  const label = props.scenarios?.[key]?.label || fallback
  const ms = props.scenarios?.[key]?.makespan
  return ms != null ? `${label}（完工 ${Number(ms).toFixed(1)} h）` : label
}

function renderOne(chartInst, el, gantt, title, highlightKeys) {
  if (!el) return chartInst
  let c = chartInst
  if (!c) c = echarts.init(el)
  const ms = Math.max(
    ...[...(gantt || [])].map((d) => Number(d.end) || 0),
    Number(props.scenarios?.r0?.makespan) || 0,
    Number(props.scenarios?.r1?.makespan) || 0,
    Number(props.scenarios?.r2?.makespan) || 0,
  )
  c.setOption(
    buildImpactGanttOption(gantt, {
      title,
      layers: props.layers,
      highlightKeys,
      makespan: ms,
    }),
    true,
  )
  return c
}

function render() {
  charts[0] = renderOne(charts[0], r0Ref.value, props.r0Gantt, titleFor('r0', 'R0 · 原计划'), [])
  charts[1] = renderOne(charts[1], r1Ref.value, props.r1Gantt, titleFor('r1', 'R1 · 扰动不重排'), [])
  charts[2] = renderOne(
    charts[2],
    r2Ref.value,
    props.r2Gantt,
    titleFor('r2', 'R2 · 重调度'),
    props.rescheduledKeys,
  )
}

function resize() {
  charts.forEach((c) => c?.resize())
}

onMounted(async () => {
  await nextTick()
  render()
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  charts.forEach((c) => c?.dispose())
  charts = [null, null, null]
})

watch(
  () => [props.r0Gantt, props.r1Gantt, props.r2Gantt, props.layers, props.scenarios, props.rescheduledKeys],
  () => render(),
  { deep: true },
)

const caption = computed(() => {
  if (props.eventType === 'insert_order') return '三列：原计划 / 插单队尾（不重排） / 冻结重排'
  if (props.eventType === 'due_date_change') return '三列：原计划 / 仅改交期 / 按新交期重排'
  return '三列：R0 原计划 / R1 扰动传播不重排 / R2 冻结已开工后重排'
})
</script>

<template>
  <div class="triple-gantt">
    <p class="caption">{{ caption }}</p>
    <el-row :gutter="8">
      <el-col :span="8"><div ref="r0Ref" class="chart" /></el-col>
      <el-col :span="8"><div ref="r1Ref" class="chart" /></el-col>
      <el-col :span="8"><div ref="r2Ref" class="chart" /></el-col>
    </el-row>
  </div>
</template>

<style scoped>
.triple-gantt {
  width: 100%;
}
.caption {
  margin: 0 0 8px;
  font-size: 12px;
  color: #909399;
}
.chart {
  width: 100%;
  height: 360px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
</style>
