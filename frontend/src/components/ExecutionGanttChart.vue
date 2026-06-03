<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { buildExecutionGanttOption } from '../utils/executionGantt'

const props = defineProps({
  ganttData: { type: Array, default: () => [] },
  simTime: { type: Number, default: 0 },
  makespan: { type: Number, default: 0 },
  running: { type: Boolean, default: false },
  paused: { type: Boolean, default: false },
  breakdownWindows: { type: Array, default: () => [] },
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

function onWindowResize() {
  chart?.resize()
}

const statusHint = computed(() => {
  if (props.breakdownWindows?.length) return '红区 = 故障机台时段'
  if (props.running) return '仿真进行中 · 红线为当前时刻'
  if (props.paused) return '已暂停 · 黄框为进行中工序'
  if (props.simTime > 0) return '计划回放'
  return '静态预览（开始执行后红线随时间推进）'
})

function render() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const showNow = props.running || props.paused || props.simTime > 0
  chart.setOption(
    buildExecutionGanttOption(props.ganttData, props.simTime, {
      makespan: props.makespan,
      showNowLine: showNow,
      emptyText: props.emptyText,
      breakdownWindows: props.breakdownWindows,
    }),
    true,
  )
}

function dispose() {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
}

onMounted(async () => {
  await nextTick()
  render()
  if (typeof ResizeObserver !== 'undefined' && chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
  window.addEventListener('resize', onWindowResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  dispose()
})

watch(
  () => [props.ganttData, props.simTime, props.makespan, props.running, props.paused, props.breakdownWindows],
  () => render(),
  { deep: true },
)
</script>

<template>
  <div class="exec-gantt-wrap">
    <div class="legend-row">
      <span class="dot done" /> 已完成
      <span class="dot run" /> 进行中
      <span class="dot pending" /> 未开始
      <span class="hint">{{ statusHint }}</span>
    </div>
    <div ref="chartRef" class="chart" />
  </div>
</template>

<style scoped>
.exec-gantt-wrap { width: 100%; }
.legend-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 4px;
  vertical-align: middle;
}
.dot.done { background: #909399; opacity: 0.7; }
.dot.run { background: #409eff; box-shadow: 0 0 0 2px #ffd04b; }
.dot.pending { background: #409eff; }
.hint { margin-left: auto; color: #909399; }
.chart {
  width: 100%;
  height: 420px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
</style>
