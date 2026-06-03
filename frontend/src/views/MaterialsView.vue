<template>
  <el-card shadow="never">
    <template #header>
      <div class="row">
        <div class="h">物料库存与预测</div>
        <div class="spacer" />
        <el-select v-model="selectedAlgo" style="width:260px">
          <el-option v-for="r in sortedResults" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-button @click="fetchMaterials">刷新库存</el-button>
        <el-button type="primary" :disabled="!hasResults" @click="analyze">预测</el-button>
      </div>
    </template>

    <el-alert v-if="!hasResults" type="info" show-icon title="暂无排程结果，请先在排程中心运行算法" class="mb" />

    <el-row :gutter="12">
      <el-col :lg="8" :md="24">
        <el-card shadow="never">
          <template #header><div class="h2">库存与补货</div></template>
          <el-table :data="materials" size="small" max-height="380">
            <el-table-column prop="id" label="ID" min-width="100" />
            <el-table-column prop="name" label="物料" min-width="110" />
            <el-table-column label="库存" width="90" align="right">
              <template #default="{ row }">{{ row.current_stock }}</template>
            </el-table-column>
            <el-table-column label="安全线" width="90" align="right">
              <template #default="{ row }">{{ row.safe_level }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button size="small" @click="restock(row)">补货</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :lg="16" :md="24">
        <el-card shadow="never">
          <template #header><div class="h2">库存预测曲线</div></template>
          <div ref="chartRef" class="chart"></div>
          <el-alert
            v-if="materialAlerts.length"
            :type="alertStats.hasShortage ? 'error' : 'warning'"
            show-icon
            :title="`检测到 ${materialAlerts.length} 条缺料预警`"
            :description="alertsText"
            style="margin-top: 12px"
          />
        </el-card>
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'
import { materialAlertStats } from '../utils/materialAlerts'

const store = useResultsStore()
const selectedAlgo = ref('')
const materials = ref([])
const simulationSnapshot = ref(null)
const timelineData = ref([])
const chartRef = ref(null)
let chart = null

const hasResults = computed(() => !!(store.results && Object.keys(store.results).length))
const sortedResults = computed(() => (store.results ? Object.values(store.results).sort((a, b) => a.best_score - b.best_score) : []))
const alertStats = computed(() => materialAlertStats(simulationSnapshot.value))
const materialAlerts = computed(() => alertStats.value.all)
const alertsText = computed(() =>
  materialAlerts.value
    .map((s) => `${s.level_label || (s.level === 'shortage' ? '缺料' : '预警')}:${s.name}@T${s.time}`)
    .join('；'),
)

async function fetchMaterials() {
  try {
    const { data } = await api.get('/api/materials/list')
    materials.value = Array.isArray(data) ? data : []
    if (!materials.value.length) {
      ElMessage.warning('物料主数据为空，后端将尝试写入默认四条；请点「刷新库存」')
    }
  } catch (e) {
    ElMessage.error(`加载物料失败: ${e.response?.data?.detail || e.message}`)
  }
}

async function restock(m) {
  const input = window.prompt(`调整【${m.name}】库存（正数补货/负数扣减）`, '100')
  if (input === null || input.trim() === '') return
  const n = Number(input)
  if (Number.isNaN(n)) return ElMessage.warning('请输入有效数字')
  try {
    await api.post(`/api/materials/restock/${m.id}`, { amount: n })
    await fetchMaterials()
    if (hasResults.value) analyze()
  } catch (e) {
    ElMessage.error(`补货失败: ${e}`)
  }
}

function mapJobsForMaterialApi() {
  return (store.currentPlanInput || []).map((j) => ({
    name: j.name,
    priority: Number(j.priority || 10),
    quantity: j.quantity != null && j.quantity !== '' ? Number(j.quantity) : null,
    due_date: j.due_date ?? null,
    bom: (j.bom || []).map((b) => ({
      material_id: b.material_id,
      quantity_per_unit: Number(b.quantity_per_unit ?? 1),
      consume_mode: b.consume_mode || 'job_start',
    })),
    tasks: (j.tasks || []).map((t) => ({
      name: t.name,
      duration: Number(t.duration || 1),
      machine_id: t.machine_id,
      machine_options: String(t.machine_options_text || t.machine_id)
        .split(',')
        .map((x) => Number(x.trim()))
        .filter((n) => Number.isInteger(n) && n >= 0),
    })),
  }))
}

async function analyze() {
  if (!selectedAlgo.value) return
  try {
    const gantt = store.results[selectedAlgo.value]?.gantt_data || []
    const { data } = await api.post('/api/materials/predict', {
      schedule_data: gantt,
      jobs: mapJobsForMaterialApi(),
    })
    timelineData.value = data.timeline || []
    simulationSnapshot.value = {
      shortages: data.shortages || [],
      safe_warnings: data.safe_warnings || [],
    }
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error(`物料预测失败: ${e}`)
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!timelineData.value.length) {
    if (chart) {
      chart.dispose()
      chart = null
    }
    return
  }
  if (!materials.value.length) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)
  const xData = timelineData.value.map((d) => `T${d.time}`)
  const series = materials.value.map((m) => ({
    name: m.name,
    type: 'line',
    smooth: true,
    showSymbol: false,
    data: timelineData.value.map((d) => d[m.id]),
    markLine: { data: [{ yAxis: m.safe_level, name: '安全线' }], lineStyle: { type: 'dashed', opacity: 0.6 } },
  }))

  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { top: 20, right: 20, bottom: 55, left: 45, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: xData },
    yAxis: { type: 'value' },
    series,
  })
}

onMounted(async () => {
  await fetchMaterials()
  if (!hasResults.value) return
  if (sortedResults.value.length) {
    selectedAlgo.value = sortedResults.value[0].id
    await analyze()
  }
})

onUnmounted(() => {
  if (chart) chart.dispose()
})
</script>

<style scoped>
.row { display:flex; align-items:center; gap: 12px; }
.h, .h2 { font-weight: 700; }
.spacer { flex: 1; }
.chart { width: 100%; height: 380px; margin-bottom: 8px; }
.mb { margin-bottom: 8px; }
</style>

