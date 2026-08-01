<template>
  <el-card shadow="never">
    <template #header>
      <div class="row">
        <div class="h">人员负荷与排班</div>
        <div class="spacer" />
        <el-select v-model="selectedAlgo" style="width:260px">
          <el-option v-for="r in sortedResults" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-button type="primary" :disabled="!hasResults" @click="analyze">负荷分析</el-button>
        <el-button :disabled="!hasResults" @click="previewDispatch">排班预览</el-button>
      </div>
    </template>

    <el-alert v-if="!hasResults" type="info" show-icon title="暂无排程结果，请先在排程中心运行算法" />

    <template v-else>
      <el-row :gutter="12">
        <el-col :lg="8" :md="24">
          <el-card shadow="never">
            <template #header><div class="h2">员工花名册</div></template>
            <div class="mb">数控在岗: <b>{{ skilledActive }}</b> 人 · 峰值缺口: <b :class="{ warn: peakShortage > 0 }">{{ peakShortage }}</b></div>
            <el-table :data="staffList" size="small" max-height="320">
              <el-table-column prop="id" label="ID" width="56" />
              <el-table-column prop="name" label="姓名" width="72" />
              <el-table-column prop="role" label="角色" width="72" />
              <el-table-column label="技能" min-width="120">
                <template #default="{ row }">
                  <el-tag v-for="sk in row.skills || []" :key="sk" size="small" class="skill-tag">{{ sk }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="在岗" width="72">
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
            <el-descriptions :column="4" border size="small">
              <el-descriptions-item label="峰值需求">{{ stats.max_peak || 0 }}</el-descriptions-item>
              <el-descriptions-item label="平均">{{ stats.avg_load || 0 }}</el-descriptions-item>
              <el-descriptions-item label="总工时">{{ stats.total_hours || 0 }}</el-descriptions-item>
              <el-descriptions-item label="峰值缺口">{{ stats.peak_shortage || 0 }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mt">
        <template #header>
          <div class="row">
            <div class="h2">排班预览（与数字孪生同步）</div>
            <div class="spacer" />
            <span class="sim-label">仿真时刻 T = {{ previewSimTime }}</span>
            <el-slider v-model="previewSimTime" :min="0" :max="previewMaxTime" :step="1" style="width:220px" @change="previewDispatch" />
          </div>
        </template>
        <el-descriptions v-if="dispatchStats" :column="4" border size="small" class="mb">
          <el-descriptions-item label="运行机台">{{ dispatchStats.running_machines }}</el-descriptions-item>
          <el-descriptions-item label="已派工">{{ dispatchStats.assigned }}</el-descriptions-item>
          <el-descriptions-item label="缺人机台">{{ dispatchStats.shortage }}</el-descriptions-item>
          <el-descriptions-item label="数控在岗">{{ dispatchStats.skilled_active }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="unassignedMachines.length"
          type="warning"
          :closable="false"
          show-icon
          class="mb"
          :title="`以下机台运行中但暂无操作员：M${unassignedMachines.join('、M')}`"
        />
        <el-table :data="dispatchRows" size="small" max-height="280" empty-text="当前时刻无运行机台或未派工">
          <el-table-column prop="name" label="姓名" width="90" />
          <el-table-column prop="role" label="角色" width="80" />
          <el-table-column label="技能" min-width="140">
            <template #default="{ row }">
              <el-tag v-for="sk in row.skills || []" :key="sk" size="small" class="skill-tag">{{ sk }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="派工机台" min-width="140">
            <template #default="{ row }">M{{ row.machine_id }} · {{ row.job_name || '加工中' }}</template>
          </el-table-column>
          <el-table-column label="位置" width="120">
            <template #default="{ row }">({{ row.x }}, {{ row.z }})</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </el-card>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'

const store = useResultsStore()
const selectedAlgo = ref('')
const staffList = ref([])
const chartData = ref([])
const stats = ref({})
const dispatchRows = ref([])
const dispatchStats = ref(null)
const unassignedMachines = ref([])
const previewSimTime = ref(0)
const chartRef = ref(null)
let chart = null

const hasResults = computed(() => !!(store.results && Object.keys(store.results).length))
const sortedResults = computed(() => (store.results ? Object.values(store.results).sort((a, b) => a.best_score - b.best_score) : []))
const skilledActive = computed(() => stats.value.skilled_active ?? staffList.value.filter((s) => s.is_active && (s.skills || []).includes('数控')).length)
const peakShortage = computed(() => stats.value.peak_shortage ?? 0)

const previewMaxTime = computed(() => {
  const gantt = store.results?.[selectedAlgo.value]?.gantt_data || []
  if (!gantt.length) return 50
  return Math.ceil(Math.max(...gantt.map((t) => Number(t.end) || 0)))
})

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
    await analyze()
    await previewDispatch()
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
    try {
      renderChart()
    } catch (chartErr) {
      console.error(chartErr)
      ElMessage.warning('负荷数据已加载，但图表渲染失败，请刷新页面重试')
    }
  } catch (e) {
    ElMessage.error(`人力分析失败: ${e?.response?.data?.detail || e?.message || e}`)
  }
}

async function previewDispatch() {
  if (!selectedAlgo.value) return
  try {
    const gantt = store.results[selectedAlgo.value]?.gantt_data || []
    const { data } = await api.post('/api/staffing/dispatch', {
      schedule_data: gantt,
      sim_time: previewSimTime.value,
    })
    dispatchRows.value = data.assignments || []
    dispatchStats.value = data.stats || null
    unassignedMachines.value = data.unassigned_machines || []
  } catch (e) {
    const status = e?.response?.status
    if (status === 404) {
      ElMessage.error('排班预览接口未找到，请重启后端（cd tests && python main.py）后再试')
      return
    }
    ElMessage.error(`排班预览失败: ${e?.response?.data?.detail || e?.message || e}`)
  }
}

function renderChart() {
  if (!chartRef.value || !chartData.value.length) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const xData = chartData.value.map((d) => `T${d.time}`)
  const yData = chartData.value.map((d) => Number(d.count) || 0)
  const limit = Math.max(0, Number(skilledActive.value) || 0)
  const yMax = Math.max(...yData, limit, 1)

  const series = {
    name: '人力需求',
    type: 'line',
    smooth: true,
    data: yData,
    lineStyle: { width: 3, color: '#67c23a' },
    areaStyle: { opacity: 0.25, color: '#67c23a' },
    itemStyle: {
      color: (params) => (limit > 0 && params.value > limit ? '#f56c6c' : '#67c23a'),
    },
  }

  if (limit > 0) {
    series.markLine = {
      silent: true,
      symbol: ['none', 'none'],
      data: [{ yAxis: limit, name: '数控在岗' }],
      lineStyle: { type: 'dashed', color: '#909399' },
      label: { formatter: '数控在岗 {c}' },
    }
  }

  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { top: 36, right: 20, bottom: 30, left: 45, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: xData },
    yAxis: { type: 'value', min: 0, max: yMax + 1, minInterval: 1 },
    series: [series],
  })
}

watch(selectedAlgo, async (v) => {
  if (!v) return
  previewSimTime.value = 0
  await analyze()
  await previewDispatch()
})

onMounted(async () => {
  await fetchStaff()
  if (sortedResults.value.length) {
    selectedAlgo.value = sortedResults.value[0].id
    await analyze()
    await previewDispatch()
  }
})

onUnmounted(() => {
  if (chart) chart.dispose()
})
</script>

<style scoped>
.row { display:flex; align-items:center; gap: 12px; flex-wrap: wrap; }
.h, .h2 { font-weight: 700; }
.spacer { flex: 1; }
.chart { width: 100%; height: 320px; margin-bottom: 8px; }
.mb { margin-bottom: 8px; }
.mt { margin-top: 12px; }
.skill-tag { margin-right: 4px; margin-bottom: 2px; }
.sim-label { font-size: 13px; color: #606266; white-space: nowrap; }
.warn { color: #f56c6c; }
</style>
