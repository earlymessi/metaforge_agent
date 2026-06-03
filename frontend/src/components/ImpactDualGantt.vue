<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { buildImpactGanttOption } from '../utils/executionGantt'

const props = defineProps({
  r1Gantt: { type: Array, default: () => [] },
  r2Gantt: { type: Array, default: () => [] },
  layers: { type: Object, default: () => ({}) },
  scenarios: { type: Object, default: () => ({}) },
  rescheduledKeys: { type: Array, default: () => [] },
  insertOpKeys: { type: Array, default: () => [] },
  dueDateOpKeys: { type: Array, default: () => [] },
  eventType: { type: String, default: '' },
})

const leftRef = ref(null)
const rightRef = ref(null)
let leftChart = null
let rightChart = null

const r1Title = computed(() => {
  const label = props.scenarios?.r1?.label || 'R1 · 扰动不重排'
  const ms = props.scenarios?.r1?.makespan
  return ms != null ? `${label}（完工 ${Number(ms).toFixed(1)} h）` : label
})

const r2Title = computed(() => {
  const label = props.scenarios?.r2?.label || 'R2 · 重调度'
  const ms = props.scenarios?.r2?.makespan
  return ms != null ? `${label}（完工 ${Number(ms).toFixed(1)} h）` : label
})

function renderOne(chartInst, el, gantt, title, highlightKeys) {
  if (!el) return chartInst
  let c = chartInst
  if (!c) c = echarts.init(el)
  c.setOption(
    buildImpactGanttOption(gantt, {
      title,
      layers: props.layers,
      highlightKeys,
      makespan: Math.max(
        ...[...(gantt || [])].map((d) => Number(d.end) || 0),
        Number(props.scenarios?.r2?.makespan) || 0,
        Number(props.scenarios?.r1?.makespan) || 0,
      ),
    }),
    true,
  )
  return c
}

const captionText = computed(() => {
  if (props.eventType === 'insert_order') {
    return '左：插单仅排到队尾（原工单时间不变）；右：冻结已开工后重调度。左图蓝框为插单工序，右图蓝框为相对原计划调整的工序。'
  }
  if (props.eventType === 'due_date_change') {
    return '左：仅更新交期、排程时间不变；右：按新交期重调度。左图蓝框为改期工单，右图蓝框为相对原计划调整的工序。'
  }
  return '左：故障后仅时间推演（不调用求解器重排）；右：冻结已开工 + 原算法残段重排。红区为故障窗口，蓝框为相对原计划调整的工序。'
})

const leftHighlightKeys = computed(() => {
  if (props.eventType === 'insert_order' && props.insertOpKeys?.length) {
    return props.insertOpKeys
  }
  if (props.eventType === 'due_date_change' && props.dueDateOpKeys?.length) {
    return props.dueDateOpKeys
  }
  return []
})

function render() {
  leftChart = renderOne(leftChart, leftRef.value, props.r1Gantt, r1Title.value, leftHighlightKeys.value)
  rightChart = renderOne(rightChart, rightRef.value, props.r2Gantt, r2Title.value, props.rescheduledKeys)
}

function resize() {
  leftChart?.resize()
  rightChart?.resize()
}

onMounted(async () => {
  await nextTick()
  render()
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  leftChart?.dispose()
  rightChart?.dispose()
})

watch(
  () => [
    props.r1Gantt,
    props.r2Gantt,
    props.layers,
    props.scenarios,
    props.rescheduledKeys,
    props.insertOpKeys,
    props.dueDateOpKeys,
    props.eventType,
  ],
  () => render(),
  { deep: true },
)
</script>

<template>
  <div class="dual-gantt">
    <p class="caption">{{ captionText }}</p>
    <el-row :gutter="12">
      <el-col :span="12">
        <div ref="leftRef" class="chart" />
      </el-col>
      <el-col :span="12">
        <div ref="rightRef" class="chart" />
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dual-gantt { width: 100%; }
.caption {
  font-size: 12px;
  color: #909399;
  margin: 0 0 10px;
  line-height: 1.5;
}
.chart {
  width: 100%;
  height: 340px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
</style>
