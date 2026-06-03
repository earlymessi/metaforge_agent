<template>
  <div class="page">
    <el-card shadow="never" class="top">
      <template #header>
        <div class="row">
          <div class="h">能耗负荷全景监控</div>
          <div class="spacer" />
          <el-button @click="refreshAll" :loading="loading">刷新数据</el-button>
        </div>
      </template>

      <el-descriptions :column="4" border>
        <el-descriptions-item label="当前小时">{{ hour }}</el-descriptions-item>
        <el-descriptions-item label="当前电价">{{ currentPrice }} 元/kWh</el-descriptions-item>
        <el-descriptions-item label="最优能耗算法">{{ bestAlgoName }}</el-descriptions-item>
        <el-descriptions-item label="算法数量">{{ ranked.length }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="row">
          <div class="h">设备停机 / 保养窗口</div>
          <div class="spacer" />
          <el-button size="small" @click="addDowntimeBlock">新增窗口</el-button>
          <el-button type="primary" size="small" :loading="savingDowntime" @click="saveDowntimeBlocks">保存到配置</el-button>
        </div>
      </template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="排程仿真会避开下列时段（写入 resource_config.downtime_blocks）"
        style="margin-bottom: 12px"
      />
      <el-table :data="downtimeBlocks" size="small" border empty-text="暂无停机窗口">
        <el-table-column label="机台 ID" width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.machine_id" :min="0" :step="1" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.start" :min="0" :step="1" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="结束时间" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.end" :min="0" :step="1" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.label" placeholder="保养/故障" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ $index }">
            <el-button type="danger" text @click="downtimeBlocks.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-alert
      v-if="!store.results"
      type="info"
      show-icon
      title="暂无排程数据"
      description="请先在“排程中心”运行一次排程，再查看能耗曲线和排名。"
      class="mt"
    />

    <el-row v-if="store.results" :gutter="12" class="mt">
      <el-col :lg="18" :md="24">
        <el-card shadow="never">
          <template #header>
            <div class="h">各算法实时功率负荷对比 (kW)</div>
          </template>
          <div ref="chartRef" class="chart"></div>
        </el-card>
      </el-col>
      <el-col :lg="6" :md="24">
        <el-card shadow="never">
          <template #header>
            <div class="h">能耗成本估算排名</div>
          </template>
          <el-table :data="ranked" stripe size="small">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="name" label="算法" min-width="120" />
            <el-table-column label="总能耗" width="90" align="right">
              <template #default="{ row }">{{ fmt(row.totalEnergy) }}</template>
            </el-table-column>
            <el-table-column label="预估成本" width="90" align="right">
              <template #default="{ row }">{{ fmt(row.totalCost) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'

const store = useResultsStore()
const loading = ref(false)
const savingDowntime = ref(false)
const config = ref(null)
const downtimeBlocks = ref([])
const chartRef = ref(null)
let chart = null

const hour = new Date().getHours()

const currentPrice = computed(() => {
  const prices = config.value?.hourly_prices
  if (!prices || !Array.isArray(prices)) return '-'
  return prices[hour] ?? '-'
})

function hourlyPriceAt(t) {
  const prices = config.value?.hourly_prices
  if (!prices || !prices.length) return 1
  return Number(prices[Math.floor(t) % 24] ?? 1)
}

function powerForMachine(machineId) {
  const p = config.value?.machine_powers?.[String(machineId)]
  return Number(p ?? 1)
}

function buildSeriesFromGantt(ganttData) {
  if (!Array.isArray(ganttData) || !ganttData.length) return { timeline: [], power: [], energy: 0, cost: 0 }
  const maxEnd = Math.ceil(Math.max(...ganttData.map((x) => Number(x.end || 0))))
  const timeline = Array.from({ length: maxEnd + 1 }, (_, i) => i)
  const power = new Array(timeline.length).fill(0)

  for (const op of ganttData) {
    const start = Math.floor(Number(op.start || 0))
    const end = Math.ceil(Number(op.end || 0))
    const p = powerForMachine(op.machine_id)
    for (let t = start; t < end && t < power.length; t += 1) {
      power[t] += p
    }
  }

  let totalEnergy = 0
  let totalCost = 0
  for (let t = 0; t < power.length; t += 1) {
    totalEnergy += power[t]
    totalCost += power[t] * hourlyPriceAt(t)
  }
  return { timeline, power, energy: totalEnergy, cost: totalCost }
}

const ranked = computed(() => {
  if (!store.results) return []
  const arr = []
  for (const k of Object.keys(store.results)) {
    const r = store.results[k]
    const built = buildSeriesFromGantt(r.gantt_data || [])
    arr.push({
      id: r.id,
      name: r.name,
      totalEnergy: built.energy,
      totalCost: built.cost,
    })
  }
  return arr.sort((a, b) => a.totalCost - b.totalCost)
})

const bestAlgoName = computed(() => (ranked.value.length ? ranked.value[0].name : '-'))

function fmt(v, digits = 2) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return '-'
  return Number(v).toFixed(digits)
}

function renderChart() {
  if (!chartRef.value || !store.results) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const palette = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4']
  const series = []
  let maxT = 0
  let i = 0

  for (const k of Object.keys(store.results)) {
    const r = store.results[k]
    const built = buildSeriesFromGantt(r.gantt_data || [])
    maxT = Math.max(maxT, built.timeline.length)
    series.push({
      name: r.name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: palette[i % palette.length] },
      data: built.power,
    })
    i += 1
  }

  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: '3%', right: '3%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: Array.from({ length: maxT }, (_, t) => t) },
    yAxis: { type: 'value', name: 'kW' },
    series,
  })
}

function syncDowntimeFromConfig() {
  const blocks = config.value?.downtime_blocks
  downtimeBlocks.value = Array.isArray(blocks)
    ? blocks.map((b) => ({
        machine_id: Number(b.machine_id ?? 0),
        start: Number(b.start ?? 0),
        end: Number(b.end ?? 0),
        label: b.label || 'downtime',
      }))
    : []
}

function addDowntimeBlock() {
  downtimeBlocks.value.push({
    machine_id: 0,
    start: 0,
    end: 8,
    label: '保养',
  })
}

async function saveDowntimeBlocks() {
  if (!config.value?.machine_powers || !config.value?.hourly_prices) {
    ElMessage.warning('请先加载资源配置')
    return
  }
  for (const b of downtimeBlocks.value) {
    if (Number(b.end) <= Number(b.start)) {
      ElMessage.warning(`机台 ${b.machine_id} 的结束时间必须大于开始时间`)
      return
    }
  }
  savingDowntime.value = true
  try {
    const payload = {
      machine_powers: config.value.machine_powers,
      hourly_prices: config.value.hourly_prices,
      maintenance_limits: config.value.maintenance_limits || {},
      downtime_blocks: downtimeBlocks.value.map((b) => ({
        machine_id: Number(b.machine_id),
        start: Number(b.start),
        end: Number(b.end),
        label: b.label || 'downtime',
      })),
    }
    const { data } = await api.put('/api/resources/config', payload)
    if (data?.status === 'success') {
      config.value = data.config || payload
      syncDowntimeFromConfig()
      ElMessage.success('停机窗口已保存，下次排程将生效')
    } else {
      ElMessage.error('保存失败')
    }
  } catch (e) {
    ElMessage.error(`保存失败: ${e}`)
  } finally {
    savingDowntime.value = false
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const { data } = await api.get('/api/resources/config')
    config.value = data
    syncDowntimeFromConfig()
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await loadConfig()
  await nextTick()
  renderChart()
}

watch(
  () => [store.results, config.value],
  async () => {
    await nextTick()
    renderChart()
  },
  { deep: true },
)

onMounted(refreshAll)
onUnmounted(() => {
  if (chart) chart.dispose()
})
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display:flex; align-items:center; gap: 12px; }
.h { font-weight: 700; }
.spacer { flex: 1; }
.mt { margin-top: 0; }
.top :deep(.el-card__body) { padding-top: 8px; }
.chart { width: 100%; height: 520px; }
</style>
