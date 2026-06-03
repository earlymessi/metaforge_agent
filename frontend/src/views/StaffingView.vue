<template>
  <el-card shadow="never">
    <template #header>
      <div class="row">
        <div class="h">人员负荷分析</div>
        <div class="spacer" />
        <el-select v-model="selectedAlgo" style="width:260px">
          <el-option v-for="r in sortedResults" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-button type="primary" :disabled="!hasResults" @click="analyze">分析</el-button>
      </div>
    </template>

    <el-alert v-if="!hasResults" type="info" show-icon title="暂无排程结果，请先在排程中心运行算法" />

    <el-row v-else :gutter="12">
      <el-col :lg="8" :md="24">
        <el-card shadow="never">
          <template #header><div class="h2">员工花名册（在岗阈值）</div></template>
          <div class="mb">当前在岗: <b>{{ activeStaffCount }}</b> 人</div>
          <el-table :data="staffList" size="small" max-height="360">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="姓名" />
            <el-table-column prop="role" label="角色" />
            <el-table-column label="在岗" width="90">
              <template #default="{ row }">
                <el-switch v-model="row.is_active" @change="toggleStaff(row)" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :lg="16" :md="24">
        <el-card shadow="never">
          <template #header><div class="h2">人力需求曲线</div></template>
          <div ref="chartRef" class="chart"></div>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="峰值">{{ stats.max_peak || 0 }}</el-descriptions-item>
            <el-descriptions-item label="平均">{{ stats.avg_load || 0 }}</el-descriptions-item>
            <el-descriptions-item label="总工时">{{ stats.total_hours || 0 }}</el-descriptions-item>
          </el-descriptions>
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

const store = useResultsStore()
const selectedAlgo = ref('')
const staffList = ref([])
const chartData = ref([])
const stats = ref({})
const chartRef = ref(null)
let chart = null

const hasResults = computed(() => !!(store.results && Object.keys(store.results).length))
const sortedResults = computed(() => (store.results ? Object.values(store.results).sort((a, b) => a.best_score - b.best_score) : []))
const activeStaffCount = computed(() => staffList.value.filter((s) => s.is_active).length)

async function fetchStaff() {
  try {
    const { data } = await api.get('/api/staff/list')
    staffList.value = Array.isArray(data) ? data : []
  } catch (e) {
    ElMessage.error(`获取员工失败: ${e}`)
  }
}

async function toggleStaff(staff) {
  try {
    await api.post(`/api/staff/toggle/${staff.id}`, { is_active: staff.is_active })
    renderChart()
  } catch (e) {
    staff.is_active = !staff.is_active
    ElMessage.error(`更新员工状态失败: ${e}`)
  }
}

async function analyze() {
  if (!selectedAlgo.value) return
  try {
    const gantt = store.results[selectedAlgo.value]?.gantt_data || []
    const { data } = await api.post('/api/staffing/analyze', gantt)
    chartData.value = data.timeline || []
    stats.value = data.stats || {}
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error(`人力分析失败: ${e}`)
  }
}

function renderChart() {
  if (!chartRef.value || !chartData.value.length) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const xData = chartData.value.map((d) => `T${d.time}`)
  const yData = chartData.value.map((d) => d.count)
  const limit = activeStaffCount.value

  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { top: 30, right: 20, bottom: 30, left: 45, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: xData },
    yAxis: { type: 'value', minInterval: 1 },
    visualMap: { show: false, dimension: 1, pieces: [{ gt: 0, lte: limit, color: '#67c23a' }, { gt: limit, color: '#f56c6c' }] },
    series: [
      {
        name: '人力需求',
        type: 'line',
        smooth: true,
        data: yData,
        lineStyle: { width: 3 },
        areaStyle: { opacity: 0.25 },
        markLine: { data: [{ yAxis: limit, name: '在岗阈值' }], lineStyle: { type: 'dashed' } },
      },
    ],
  })
}

onMounted(async () => {
  await fetchStaff()
  if (sortedResults.value.length) {
    selectedAlgo.value = sortedResults.value[0].id
    analyze()
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
.chart { width: 100%; height: 360px; margin-bottom: 8px; }
.mb { margin-bottom: 8px; }
</style>

