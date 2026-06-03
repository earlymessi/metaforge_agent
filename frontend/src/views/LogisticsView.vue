<template>
  <el-card shadow="never">
    <template #header>
      <div class="row">
        <div class="h">AGV 物流调度</div>
        <div class="spacer" />
        <el-tag v-if="viewingHistory && !hasResults" type="warning" effect="plain">历史浏览</el-tag>
        <template v-if="showLogisticsData">
          <el-tag v-if="batchId" type="info" effect="plain">批次 {{ batchId }}</el-tag>
          <el-select v-model="selectedBatchId" clearable placeholder="历史批次" style="width:220px" @change="onBatchChange">
            <el-option
              v-for="b in batchOptions"
              :key="b.batch_id"
              :label="`${b.batch_id} (${b.task_count})`"
              :value="b.batch_id"
            />
          </el-select>
          <el-button @click="fetchBatchOptions">刷新批次</el-button>
          <el-select v-model="pageSize" style="width:120px" @change="onPageSizeChange">
            <el-option :value="50" label="50/页" />
            <el-option :value="100" label="100/页" />
            <el-option :value="200" label="200/页" />
          </el-select>
          <el-button :disabled="pageOffset <= 0" @click="prevPage">上一页</el-button>
          <el-button :disabled="pageOffset + pageSize >= totalTasks" @click="nextPage">下一页</el-button>
          <el-tag type="info" effect="plain">共 {{ totalTasks }} 条</el-tag>
        </template>
        <el-select v-if="hasResults" v-model="selectedAlgo" style="width:260px">
          <el-option v-for="r in sortedResults" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-button v-if="!hasResults && !viewingHistory" @click="enterHistoryView">查看全部历史</el-button>
        <el-button v-if="!hasResults && viewingHistory" @click="exitHistoryView">退出历史浏览</el-button>
        <el-button type="primary" @click="generateTasks" :disabled="!hasResults" :loading="generating">生成物流任务</el-button>
      </div>
    </template>

    <el-alert
      v-if="scheduleStale && hasResults"
      type="warning"
      show-icon
      class="mb"
      title="排程结果已更新，建议重新生成物流任务以同步最新甘特。"
    >
      <el-button type="primary" size="small" :loading="generating" @click="generateTasks">立即重新生成</el-button>
    </el-alert>

    <el-alert
      v-if="!hasResults && !viewingHistory"
      type="info"
      show-icon
      class="mb"
      title="暂无排程结果。请先在排程中心运行算法并生成物流任务；也可手动查看历史记录。"
    >
      <el-button size="small" @click="enterHistoryView">查看全部历史</el-button>
    </el-alert>

    <el-empty
      v-if="!showLogisticsData"
      description="暂无物流任务数据"
      :image-size="80"
    />

    <template v-else>
      <el-row :gutter="12" class="mb">
        <el-col :lg="6" :md="12" :sm="24">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">准时率</div>
            <div class="kpi-value">{{ formatKpiPercent(kpi.on_time_rate) }}</div>
            <div class="kpi-sub">有评分 {{ kpi.scored_count || 0 }} / {{ kpi.total || 0 }} 条</div>
          </el-card>
        </el-col>
        <el-col :lg="6" :md="12" :sm="24">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">无缝衔接率</div>
            <div class="kpi-value">{{ formatKpiPercent(kpi.seamless_rate) }}</div>
            <div class="kpi-sub">AGV 零空驶取货</div>
          </el-card>
        </el-col>
        <el-col :lg="6" :md="12" :sm="24">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">平均空驶成本</div>
            <div class="kpi-value">{{ kpi.avg_empty_cost != null ? kpi.avg_empty_cost.toFixed(2) : '—' }}</div>
            <div class="kpi-sub">越低越好</div>
          </el-card>
        </el-col>
        <el-col :lg="6" :md="12" :sm="24">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">任务状态</div>
            <div class="kpi-value sm">
              待 {{ kpi.status?.pending || 0 }} · 执行 {{ kpi.status?.dispatched || 0 }} · 完 {{ kpi.status?.done || 0 }}
            </div>
            <div class="kpi-sub">当前批次汇总</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="12" class="mb">
        <el-col :span="24">
          <el-card shadow="never">
            <template #header><div class="h2">车间路径图（点击任务行高亮路线）</div></template>
            <AgvRouteMap
              :machines="machines"
              :fleet-status="fleetStatus"
              :tasks="tasks"
              :highlight-task-id="highlightTaskId"
            />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :lg="8" :md="24">
          <el-card shadow="never">
            <template #header><div class="h2">车队状态</div></template>
            <el-table :data="fleetStatus" size="small" max-height="360">
              <el-table-column prop="id" label="AGV" width="70" />
              <el-table-column prop="location" label="位置" />
              <el-table-column prop="free_at" label="空闲时间" width="90" align="right" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :lg="16" :md="24">
          <el-card shadow="never">
            <template #header><div class="h2">搬运任务</div></template>
            <el-table
              :data="tasks"
              size="small"
              max-height="360"
              highlight-current-row
              @row-click="onTaskRowClick"
            >
              <el-table-column prop="job_name" label="工单" min-width="120" />
              <el-table-column label="路线" min-width="120">
                <template #default="{ row }">M{{ row.from_machine }} → M{{ row.to_machine }}</template>
              </el-table-column>
              <el-table-column prop="assigned_agv" label="AGV" width="70" />
              <el-table-column prop="dispatch_rank" label="序" width="60" align="right" />
              <el-table-column prop="pickup_time" label="取货时刻" width="90" align="right" />
              <el-table-column prop="delivery_deadline" label="交付截止" width="90" align="right" />
              <el-table-column prop="score" label="评分" width="90" align="right" />
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusTag(row.dispatch_status)">{{ statusLabel(row.dispatch_status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150">
                <template #default="{ $index, row }">
                  <el-button
                    size="small"
                    type="primary"
                    :disabled="row.dispatch_status !== 'pending' || dispatching"
                    @click.stop="dispatchAGV($index)"
                  >
                    派发
                  </el-button>
                  <el-button
                    size="small"
                    type="success"
                    plain
                    :disabled="row.dispatch_status !== 'dispatched' || dispatching"
                    @click.stop="completeAGV($index)"
                  >
                    完成
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </el-card>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import AgvRouteMap from '../components/AgvRouteMap.vue'
import { formatKpiPercent } from '../utils/logisticsKpi'
import { useResultsStore } from '../stores/useResultsStore'

const store = useResultsStore()
const tasks = ref([])
const fleetStatus = ref([])
const machines = ref([])
const emptyKpi = () => ({
  total: 0,
  scored_count: 0,
  on_time_rate: null,
  seamless_rate: null,
  avg_empty_cost: null,
  status: { pending: 0, dispatched: 0, done: 0 },
})
const kpi = ref(emptyKpi())
const selectedAlgo = ref('')
const batchId = ref('')
const selectedBatchId = ref('')
const batchOptions = ref([])
const dispatching = ref(false)
const generating = ref(false)
const pageSize = ref(100)
const pageOffset = ref(0)
const totalTasks = ref(0)
const highlightTaskId = ref('')
const scheduleStale = ref(false)
const viewingHistory = ref(false)
let lastResultsSignature = ''

const hasResults = computed(() => !!(store.results && Object.keys(store.results).length))
const showLogisticsData = computed(() => hasResults.value || viewingHistory.value)
const sortedResults = computed(() => (store.results ? Object.values(store.results).sort((a, b) => a.best_score - b.best_score) : []))

function resultsSignature() {
  if (!store.results) return ''
  return Object.keys(store.results).sort().join('|')
}

function clearLogisticsDisplay() {
  tasks.value = []
  fleetStatus.value = []
  totalTasks.value = 0
  batchId.value = ''
  selectedBatchId.value = ''
  highlightTaskId.value = ''
  kpi.value = emptyKpi()
}

async function enterHistoryView() {
  viewingHistory.value = true
  pageOffset.value = 0
  await fetchBatchOptions()
  await loadBatchTasks()
}

function exitHistoryView() {
  viewingHistory.value = false
  clearLogisticsDisplay()
}

watch(
  () => store.results,
  () => {
    const sig = resultsSignature()
    if (lastResultsSignature && sig !== lastResultsSignature && hasResults.value) {
      scheduleStale.value = true
    }
    lastResultsSignature = sig
  },
  { deep: true },
)

watch(
  () => store.lastRescheduleResults,
  (v) => {
    if (v && Object.keys(v).length) scheduleStale.value = true
  },
)

watch(hasResults, (v) => {
  if (v) {
    viewingHistory.value = false
    if (sortedResults.value.length && !selectedAlgo.value) {
      selectedAlgo.value = sortedResults.value[0].id
    }
    pageOffset.value = 0
    fetchBatchOptions()
    loadBatchTasks()
  } else if (!viewingHistory.value) {
    clearLogisticsDisplay()
  }
})

async function fetchLayout() {
  try {
    const { data } = await api.get('/api/logistics/layout')
    machines.value = data?.machines || []
  } catch {
    machines.value = []
  }
}

async function fetchKpi(bid = selectedBatchId.value) {
  try {
    const { data } = await api.get('/api/logistics/kpi', {
      params: { batch_id: bid || undefined },
    })
    kpi.value = {
      total: data?.total || 0,
      scored_count: data?.scored_count || 0,
      on_time_rate: data?.on_time_rate,
      seamless_rate: data?.seamless_rate,
      avg_empty_cost: data?.avg_empty_cost,
      status: data?.status || { pending: 0, dispatched: 0, done: 0 },
    }
  } catch {
    kpi.value = emptyKpi()
  }
}

async function generateTasks() {
  if (!selectedAlgo.value && sortedResults.value.length) selectedAlgo.value = sortedResults.value[0].id
  if (!selectedAlgo.value) return
  generating.value = true
  try {
    const ganttData = store.results[selectedAlgo.value]?.gantt_data || []
    const { data } = await api.post('/api/logistics/generate', ganttData)
    batchId.value = data.batch_id || ''
    selectedBatchId.value = batchId.value
    scheduleStale.value = false
    await fetchBatchOptions()
    await loadBatchTasks(batchId.value)
    tasks.value = (data.tasks || []).map(normalizeTask)
    fleetStatus.value = data.fleet_status || []
    await fetchKpi(batchId.value)
    ElMessage.success(`已生成 ${data.tasks?.length || 0} 条物流任务`)
  } catch (e) {
    ElMessage.error(`物流任务生成失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    generating.value = false
  }
}

function normalizeTask(t) {
  return {
    ...t,
    id: t.id || t.task_id,
    dispatched: !!t.dispatched,
    dispatch_status: t.dispatch_status || (t.dispatched ? 'dispatched' : 'pending'),
  }
}

async function fetchBatchOptions() {
  try {
    const { data } = await api.get('/api/logistics/batches')
    batchOptions.value = data?.batches || []
  } catch (e) {
    ElMessage.error(`批次加载失败: ${e?.response?.data?.detail || e?.message || e}`)
  }
}

async function loadBatchTasks(bid = selectedBatchId.value) {
  if (!showLogisticsData.value) return
  try {
    const params = {
      batch_id: bid || undefined,
      limit: pageSize.value,
      offset: pageOffset.value,
    }
    const { data } = await api.get('/api/logistics/tasks', { params })
    const list = data?.tasks || []
    tasks.value = list.map(normalizeTask)
    fleetStatus.value = data?.fleet_status || []
    totalTasks.value = Number(data?.pagination?.total || 0)
    batchId.value = bid || data?.tasks?.[0]?.batch_id || ''
    await fetchKpi(bid || batchId.value)
  } catch (e) {
    ElMessage.error(`任务加载失败: ${e?.response?.data?.detail || e?.message || e}`)
  }
}

function onBatchChange() {
  pageOffset.value = 0
  highlightTaskId.value = ''
  loadBatchTasks(selectedBatchId.value)
}

function onPageSizeChange() {
  pageOffset.value = 0
  loadBatchTasks(selectedBatchId.value)
}

function prevPage() {
  pageOffset.value = Math.max(0, pageOffset.value - pageSize.value)
  loadBatchTasks(selectedBatchId.value)
}

function nextPage() {
  if (pageOffset.value + pageSize.value >= totalTasks.value) return
  pageOffset.value += pageSize.value
  loadBatchTasks(selectedBatchId.value)
}

function onTaskRowClick(row) {
  highlightTaskId.value = row?.id || row?.task_id || ''
}

async function dispatchAGV(idx) {
  const row = tasks.value[idx]
  if (!row?.id) return
  dispatching.value = true
  try {
    await api.post('/api/logistics/dispatch', { task_id: row.id })
    tasks.value[idx].dispatched = true
    tasks.value[idx].dispatch_status = 'dispatched'
    await loadBatchTasks(selectedBatchId.value)
    ElMessage.success('派发成功')
  } catch (e) {
    ElMessage.error(`派发失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    dispatching.value = false
  }
}

async function completeAGV(idx) {
  const row = tasks.value[idx]
  if (!row?.id) return
  dispatching.value = true
  try {
    await api.post('/api/logistics/complete', { task_id: row.id })
    tasks.value[idx].dispatch_status = 'done'
    await loadBatchTasks(selectedBatchId.value)
    ElMessage.success('任务已完成')
  } catch (e) {
    ElMessage.error(`完成失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    dispatching.value = false
  }
}

function statusLabel(status) {
  if (status === 'done') return '已完成'
  if (status === 'dispatched') return '执行中'
  return '待派发'
}

function statusTag(status) {
  if (status === 'done') return 'success'
  if (status === 'dispatched') return 'primary'
  return 'warning'
}

onMounted(() => {
  if (sortedResults.value.length) selectedAlgo.value = sortedResults.value[0].id
  lastResultsSignature = resultsSignature()
  fetchLayout()
  if (hasResults.value) {
    fetchBatchOptions()
    loadBatchTasks()
  }
})
</script>

<style scoped>
.row { display:flex; align-items:center; gap: 12px; flex-wrap: wrap; }
.h, .h2 { font-weight: 700; }
.spacer { flex: 1; }
.mb { margin-bottom: 12px; }
.kpi-card { min-height: 96px; }
.kpi-label { font-size: 13px; color: #909399; }
.kpi-value { font-size: 22px; font-weight: 700; margin-top: 4px; color: #303133; }
.kpi-value.sm { font-size: 16px; }
.kpi-sub { font-size: 12px; color: #c0c4cc; margin-top: 4px; }
</style>
