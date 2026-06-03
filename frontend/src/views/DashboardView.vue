<template>
  <div class="page">
    <el-row :gutter="12">
      <el-col :lg="6" :md="12" :sm="24">
        <el-card shadow="never">
          <div class="kpi-label">工单总数</div>
          <div class="kpi-value">{{ stats.total_orders || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :lg="6" :md="12" :sm="24">
        <el-card shadow="never">
          <div class="kpi-label">工序总量</div>
          <div class="kpi-value">{{ stats.total_ops || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :lg="6" :md="12" :sm="24">
        <el-card shadow="never">
          <div class="kpi-label">待排程</div>
          <div class="kpi-value">{{ stats.pending || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :lg="6" :md="12" :sm="24">
        <el-card shadow="never">
          <div class="kpi-label">数据库状态</div>
          <div class="kpi-value ok">MongoDB 正常</div>
          <div class="kpi-sub">mongodb://127.0.0.1:27017/metaforge_mes</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="row">
          <div class="h">MES 当前执行</div>
          <div class="spacer" />
          <el-tag :type="executionTagType">{{ executionStatusLabel }}</el-tag>
          <el-button size="small" @click="refreshAll" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-row :gutter="12" align="middle">
        <el-col :span="8">
          <div class="field-label">已排程计划</div>
          <el-select
            v-model="selectedPlanId"
            filterable
            placeholder="选择计划"
            style="width: 100%"
            :disabled="execution.status === 'running'"
          >
            <el-option
              v-for="p in scheduledPlans"
              :key="p._id"
              :label="p.plan_name || p._id"
              :value="p._id"
            />
          </el-select>
        </el-col>
        <el-col :span="6">
          <div class="field-label">基准算法</div>
          <el-select
            v-model="selectedSolverId"
            placeholder="算法"
            style="width: 100%"
            :disabled="!selectedPlanId || execution.status === 'running'"
          >
            <el-option
              v-for="sid in solverOptions"
              :key="sid"
              :label="solverLabel(sid)"
              :value="sid"
            />
          </el-select>
        </el-col>
        <el-col :span="5">
          <div class="field-label">仿真倍速（1 分≈N 排程 h）</div>
          <el-select v-model="simSpeed" style="width: 100%" :disabled="execution.status === 'running'">
            <el-option :value="60" label="默认 60（1分=1h）" />
            <el-option :value="1" label="实时 1（1h=1h）" />
            <el-option :value="300" label="快进 300（1分=5h）" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <div class="field-label">&nbsp;</div>
          <el-button-group>
            <el-button
              type="primary"
              :disabled="!selectedPlanId || !selectedSolverId || execution.status === 'running'"
              @click="startExecution"
            >
              开始执行
            </el-button>
            <el-button v-if="execution.status === 'running'" @click="pauseExecution">暂停</el-button>
            <el-button v-if="execution.status === 'paused'" type="success" @click="resumeExecution">继续</el-button>
            <el-button v-if="execution.status !== 'idle'" type="danger" plain @click="resetExecution">重置</el-button>
          </el-button-group>
        </el-col>
      </el-row>
      <el-descriptions v-if="showMesContext" :column="4" border class="mt">
        <el-descriptions-item label="计划">{{ mesPlanName }}</el-descriptions-item>
        <el-descriptions-item label="算法">{{ mesSolverName }}</el-descriptions-item>
        <el-descriptions-item label="仿真时刻">
          {{ fmt(unifiedSimTime) }} h / {{ fmt(unifiedMakespan) }} h
        </el-descriptions-item>
        <el-descriptions-item label="状态">{{ executionStatusLabel }}</el-descriptions-item>
      </el-descriptions>
      <el-descriptions v-if="execution.status !== 'idle'" :column="1" border class="mt">
        <el-descriptions-item label="仿真倍速">×{{ execution.sim_speed }}</el-descriptions-item>
      </el-descriptions>

      <div v-if="showMesContext && displayGantt.length" class="mt gantt-block">
        <div class="field-label">{{ execution.status !== 'idle' ? '执行甘特（实时）' : '计划甘特预览' }}</div>
        <ExecutionGanttChart
          :gantt-data="displayGantt"
          :sim-time="unifiedSimTime"
          :makespan="unifiedMakespan"
          :running="execution.status === 'running'"
          :paused="execution.status === 'paused'"
          :breakdown-windows="breakdownWindows"
          :empty-text="ganttEmptyText"
        />
        <span v-if="execution.status === 'idle'" class="hint-text">开始执行后红线将随仿真时刻移动</span>
      </div>

      <el-divider v-if="showMesContext" content-position="left">数字孪生车间</el-divider>

      <template v-if="showMesContext">
        <el-progress
          v-if="unifiedMakespan > 0"
          :percentage="mesProgressPercent"
          :stroke-width="10"
          class="mt"
        />
        <DigitalTwinMap
          class="mt"
          :machines="twinMachines"
          :agvs="twinAux.agvs"
          :staff="twinAux.staff"
        />
        <el-row :gutter="12" class="mt">
          <el-col :lg="12" :md="24">
            <el-card shadow="never">
              <template #header><div class="h2">机器状态（与甘特同步）</div></template>
              <el-table :data="twinMachines" size="small" max-height="280">
                <el-table-column prop="id" label="ID" width="70" />
                <el-table-column prop="status" label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'running' ? 'success' : 'info'">{{ row.status }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="current_job" label="当前工单" min-width="120" />
              </el-table>
            </el-card>
          </el-col>
          <el-col :lg="6" :md="12" :sm="24">
            <el-card shadow="never">
              <template #header><div class="h2">AGV 车队</div></template>
              <el-table :data="twinAux.agvs" size="small" max-height="280">
                <el-table-column prop="id" label="AGV" width="70" />
                <el-table-column prop="status" label="状态" />
              </el-table>
            </el-card>
          </el-col>
          <el-col :lg="6" :md="12" :sm="24">
            <el-card shadow="never">
              <template #header><div class="h2">在岗人员</div></template>
              <el-table :data="twinAux.staff" size="small" max-height="280">
                <el-table-column prop="id" label="ID" width="70" />
                <el-table-column prop="name" label="姓名" />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </template>

      <el-alert
        v-else
        type="info"
        show-icon
        :closable="false"
        class="mt"
        title="请选择已排程计划与基准算法，甘特与数字孪生将使用同一数据源展示。"
      />
    </el-card>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="row">
          <div class="h">异常重排</div>
          <div class="spacer" />
          <el-tag v-if="execution.status === 'running' || execution.status === 'paused'" type="success" effect="plain">
            仿真 {{ fmt(execution.sim_time) }} h
          </el-tag>
        </div>
      </template>
      <el-alert
        v-if="execution.status === 'idle'"
        type="warning"
        :closable="false"
        show-icon
        title="请先在上方选择已排程计划并点击「开始执行」，再使用插单 / 设备故障 / 改交期重排。"
        class="mb12"
      />
      <MesReschedulePanel
        :execution="execution"
        @rescheduled="onRescheduled"
      />
    </el-card>

  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import MesReschedulePanel from '../components/MesReschedulePanel.vue'
import ExecutionGanttChart from '../components/ExecutionGanttChart.vue'
import DigitalTwinMap from '../components/DigitalTwinMap.vue'
import { useResultsStore } from '../stores/useResultsStore'
import { useWorkContextStore } from '../stores/useWorkContextStore'
import {
  hasPlanSchedule,
  listSolverIdsFromPlan,
  scheduleResultsFromPlan,
  solverDisplayName,
  loadImpactAssessmentForPlan,
} from '../utils/planScheduleSync'
import { buildMachinesFromGantt } from '../utils/digitalTwinFromGantt'

const store = useResultsStore()
const workContext = useWorkContextStore()

const stats = ref({})
const layoutMachines = ref([])
const twinAux = ref({ agvs: [], staff: [] })
const execution = ref({ status: 'idle' })
const loading = ref(false)
const plans = ref([])
const selectedPlanId = ref('')
const selectedSolverId = ref('')
const simSpeed = ref(60)
let timer = null

const scheduledPlans = computed(() =>
  (plans.value || []).filter((p) => hasPlanSchedule(p))
)

const solverOptions = computed(() => {
  const plan = plans.value.find((p) => p._id === selectedPlanId.value)
  return listSolverIdsFromPlan(plan)
})

function solverLabel(sid) {
  const plan = plans.value.find((p) => p._id === selectedPlanId.value)
  return solverDisplayName(plan, sid)
}

watch(selectedPlanId, () => {
  const opts = solverOptions.value
  selectedSolverId.value = opts.includes(selectedSolverId.value) ? selectedSolverId.value : (opts[0] || '')
})

watch(solverOptions, (opts) => {
  if (opts.length && !opts.includes(selectedSolverId.value)) {
    selectedSolverId.value = opts[0]
  }
})

const executionStatusLabel = computed(() => {
  const s = execution.value.status
  if (s === 'running') return '执行中'
  if (s === 'paused') return '已暂停'
  return '未启动'
})

const executionTagType = computed(() => {
  const s = execution.value.status
  if (s === 'running') return 'success'
  if (s === 'paused') return 'warning'
  return 'info'
})

const showMesContext = computed(
  () =>
    execution.value.status !== 'idle' ||
    !!(selectedPlanId.value && selectedSolverId.value),
)

const mesPlanName = computed(() => {
  if (execution.value.status !== 'idle') {
    return execution.value.plan_name || '-'
  }
  const plan = plans.value.find((p) => p._id === selectedPlanId.value)
  return plan?.plan_name || '-'
})

const mesSolverName = computed(() => {
  if (execution.value.status !== 'idle') {
    return solverDisplayName(
      plans.value.find((p) => p._id === execution.value.plan_id),
      execution.value.baseline_solver,
    ) || execution.value.baseline_solver || '-'
  }
  return selectedSolverId.value ? solverLabel(selectedSolverId.value) : '-'
})

function ganttMakespanFromData(gantt) {
  if (!Array.isArray(gantt) || !gantt.length) return 0
  return Math.max(...gantt.map((op) => Number(op.end) || 0))
}

const previewGantt = computed(() => {
  if (execution.value.status !== 'idle') return []
  const plan = plans.value.find((p) => p._id === selectedPlanId.value)
  const results = scheduleResultsFromPlan(plan)
  const sid = selectedSolverId.value
  return results?.[sid]?.gantt_data || []
})

const displayGantt = computed(() => {
  if (execution.value.baseline_gantt?.length) return execution.value.baseline_gantt
  return previewGantt.value
})

/** 与上方甘特红线使用同一仿真时刻 */
const unifiedSimTime = computed(() => {
  if (execution.value.status === 'running' || execution.value.status === 'paused') {
    return Number(execution.value.sim_time) || 0
  }
  return 0
})

const unifiedMakespan = computed(() => {
  if (execution.value.makespan) return Number(execution.value.makespan)
  const plan = plans.value.find((p) => p._id === selectedPlanId.value)
  const results = scheduleResultsFromPlan(plan)
  const sid = selectedSolverId.value
  const entry = results?.[sid]
  return Number(entry?.best_score) || ganttMakespanFromData(displayGantt.value)
})

const mesProgressPercent = computed(() => {
  const total = unifiedMakespan.value
  if (total <= 0) return 0
  return Math.min(100, Math.max(0, (unifiedSimTime.value / total) * 100))
})

const twinMachines = computed(() =>
  buildMachinesFromGantt(displayGantt.value, unifiedSimTime.value, layoutMachines.value),
)

watch([selectedPlanId, selectedSolverId, () => execution.value.status, displayGantt], () => {
  if (showMesContext.value) fetchTwinAuxiliary()
})

const ganttEmptyText = computed(() => {
  if (!selectedPlanId.value) return '请先选择已排程计划'
  if (!selectedSolverId.value) return '请选择基准算法'
  return '该计划暂无甘特数据，请先在排程中心运行并排程'
})

const breakdownWindows = computed(() => {
  const ir = store.impactReport
  if (!ir || ir.event_type !== 'machine_breakdown') return []
  const bw = ir.gantt_layers?.breakdown_window
  if (bw && bw.machine_id != null) {
    return [{ machine_id: bw.machine_id, start: bw.start, end: bw.end }]
  }
  if (ir.breakdown_start != null && ir.machine_id != null) {
    return [{
      machine_id: ir.machine_id,
      start: ir.breakdown_start,
      end: ir.breakdown_end,
    }]
  }
  return []
})

function fmt(v) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return '-'
  return Number(v).toFixed(1)
}

async function loadPlans() {
  const { data } = await api.get('/api/db/list')
  const list = Array.isArray(data) ? data : data?.plans || []
  plans.value = list.map((p) => ({
    ...p,
    _id: String(p._id || p.id || ''),
  }))
}

async function loadExecution() {
  const { data } = await api.get('/api/execution/state')
  execution.value = data || { status: 'idle' }
  if (data?.status && data.status !== 'idle') {
    selectedPlanId.value = data.plan_id || selectedPlanId.value
    selectedSolverId.value = data.baseline_solver || selectedSolverId.value
    simSpeed.value = data.sim_speed ?? 60
    syncStoreFromPlan(data.plan_id, data.baseline_solver, data)
    if (data.plan_id) {
      workContext.setFromPlan({
        planId: data.plan_id,
        planName: data.plan_name || '',
        jobs: Array.isArray(data.jobs_snapshot) ? data.jobs_snapshot : workContext.customJobs,
        source: 'database',
      })
      await loadImpactAssessmentForPlan(data.plan_id, { executionDoc: data }, store)
    }
  }
}

async function fetchLayout() {
  try {
    const { data } = await api.get('/api/logistics/layout')
    layoutMachines.value = data?.machines || []
  } catch {
    layoutMachines.value = []
  }
}

/** 仅拉取 AGV/人员位置；机台状态由甘特本地计算，与 MES 一致 */
async function fetchTwinAuxiliary() {
  if (!showMesContext.value) {
    twinAux.value = { agvs: [], staff: [] }
    return
  }
  try {
    const { data } = await api.get('/api/digital_twin/snapshot', {
      params: twinSnapshotParams(),
    })
    twinAux.value = {
      agvs: data?.agvs || [],
      staff: data?.staff || [],
    }
  } catch {
    twinAux.value = { agvs: [], staff: [] }
  }
}

function twinSnapshotParams() {
  const ex = execution.value
  if (ex?.status === 'running' || ex?.status === 'paused') {
    return {}
  }
  if (selectedPlanId.value && selectedSolverId.value) {
    return {
      plan_id: selectedPlanId.value,
      solver_id: selectedSolverId.value,
      sim_time: unifiedSimTime.value,
    }
  }
  return {}
}

async function refreshAll() {
  loading.value = true
  try {
    await loadExecution()
    const [s] = await Promise.all([
      api.get('/api/dashboard/stats'),
      fetchTwinAuxiliary(),
    ])
    stats.value = s.data || {}
  } finally {
    loading.value = false
  }
}

function syncStoreFromPlan(planId, solverId, execData) {
  const plan = plans.value.find((p) => p._id === planId)
  store.currentPlanInput = execData?.jobs_snapshot || plan?.jobs || plan?.plan_input || []
  store.currentPlanId = planId
  store.currentPlanName = plan?.plan_name || ''

  const sid = solverId || execData?.baseline_solver
  if (
    execData?.status &&
    execData.status !== 'idle' &&
    Array.isArray(execData.baseline_gantt) &&
    execData.baseline_gantt.length &&
    sid
  ) {
    store.setResults({
      [sid]: {
        gantt_data: execData.baseline_gantt,
        metrics: { makespan: execData.makespan },
        name: sid,
      },
    })
    return
  }
  const results = scheduleResultsFromPlan(plan)
  if (results && sid && results[sid]) {
    store.setResults(results)
  }
}

async function startExecution() {
  try {
    const { data } = await api.post('/api/execution/start', {
      plan_id: selectedPlanId.value,
      solver_id: selectedSolverId.value,
      sim_speed: simSpeed.value,
    })
    execution.value = data
    syncStoreFromPlan(selectedPlanId.value, selectedSolverId.value, data)
    ElMessage.success('已开始 MES 执行')
    await refreshAll()
  } catch (e) {
    ElMessage.error(`启动失败: ${e.response?.data?.detail || e.message}`)
  }
}

function onRescheduled(resultBundle) {
  if (resultBundle?.production_execution) {
    execution.value = resultBundle.production_execution
    syncStoreFromPlan(
      execution.value.plan_id || selectedPlanId.value,
      execution.value.baseline_solver || selectedSolverId.value,
      execution.value,
    )
    fetchTwinAuxiliary()
    return
  }
  if (resultBundle?.results) {
    store.setResults(resultBundle.results)
  }
  const impact = resultBundle?.impact_report
  const sid =
    impact?.rescheduled_solver ||
    execution.value.baseline_solver ||
    selectedSolverId.value
  const gantt =
    impact?.r2_gantt ||
    resultBundle?.results?.[sid]?.gantt_data
  if (Array.isArray(gantt) && gantt.length) {
    execution.value = {
      ...execution.value,
      baseline_gantt: gantt,
      makespan: ganttMakespanFromData(gantt) || execution.value.makespan,
    }
  }
  if (Array.isArray(resultBundle?.updated_jobs) && resultBundle.updated_jobs.length) {
    execution.value = {
      ...execution.value,
      jobs_snapshot: resultBundle.updated_jobs,
    }
    store.currentPlanInput = resultBundle.updated_jobs
  }
  if (sid && execution.value.baseline_gantt?.length) {
    syncStoreFromPlan(
      execution.value.plan_id || selectedPlanId.value,
      sid,
      execution.value,
    )
  }
  fetchTwinAuxiliary()
}

async function pauseExecution() {
  const { data } = await api.post('/api/execution/pause')
  execution.value = data
  await refreshAll()
}

async function resumeExecution() {
  const { data } = await api.post('/api/execution/resume')
  execution.value = data
  await refreshAll()
}

async function resetExecution() {
  await api.post('/api/execution/reset')
  execution.value = { status: 'idle' }
  store.clearRescheduleSnapshot()
  if (selectedPlanId.value) {
      await loadImpactAssessmentForPlan(
        selectedPlanId.value,
        { executionDoc: execution.value },
        store,
      )
  } else {
    store.clearImpactAssessment()
  }
  await refreshAll()
}

onMounted(async () => {
  await loadPlans()
  await fetchLayout()
  await refreshAll()
  timer = setInterval(refreshAll, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display:flex; align-items:center; gap: 12px; }
.spacer { flex: 1; }
.h { font-weight: 700; }
.h2 { font-weight: 700; font-size: 13px; }
.mt { margin-top: 12px; }
.field-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.kpi-label { font-size: 12px; color: #909399; }
.kpi-value { font-size: 26px; font-weight: 700; margin-top: 6px; }
.kpi-value.ok { color: #67c23a; font-size: 18px; }
.kpi-sub { margin-top: 4px; font-size: 11px; color: #909399; }
.mb12 { margin-bottom: 12px; }
.gantt-block { margin-top: 16px; }
.hint-text { font-size: 12px; color: #909399; }
</style>
