<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'
import ImpactDualGantt from './ImpactDualGantt.vue'
import {
  effectiveR1Gantt,
  effectiveR2Gantt,
  firstImpactTab,
  hasDualImpactGantt,
  isDualGanttEvent,
  normalizeEventResultBundle,
  buildImpactSummaryPayload,
} from '../utils/impactReport'
import { persistScheduleWithHitl, fetchPlanScheduleIntoStore, loadImpactAssessmentForPlan } from '../utils/planScheduleSync'
import PersistConfirmDialog from './PersistConfirmDialog.vue'

const props = defineProps({
  execution: { type: Object, default: () => ({ status: 'idle' }) },
  showImpactButton: { type: Boolean, default: true },
})

const emit = defineEmits(['rescheduled', 'refresh-execution'])

const router = useRouter()
const store = useResultsStore()

const insertDialogVisible = ref(false)
const breakdownDialogVisible = ref(false)
const dueDateDialogVisible = ref(false)
const impactDialogVisible = ref(false)
const dueDateRows = ref([])
const rescheduling = ref(false)
const impactLoading = ref(false)
const impactTab = ref('delay')

const persistVisible = ref(false)
const persistToken = ref('')
const persistPreview = ref(null)
const persistSummary = ref('')
const persistExpires = ref('')

const breakdownForm = ref({
  machine_id: 0,
  breakdown_start: 0,
  breakdown_duration: 4,
  freeze_time: null,
})

const insertForm = ref({
  mode: 'local_repair',
  freeze_time: 0,
  job: {
    name: '急单',
    priority: 100,
    tasks: [{ name: 'Op-1', machine_id: 0, machine_options_text: '0', machine_group: '', duration: 5 }],
  },
})

const canReschedule = computed(() => {
  if (props.execution?.status === 'running' || props.execution?.status === 'paused') {
    return Array.isArray(props.execution.jobs_snapshot) && props.execution.jobs_snapshot.length > 0
  }
  return !!store.results && Array.isArray(store.currentPlanInput) && store.currentPlanInput.length > 0
})

const simNow = computed(() => Number(props.execution?.sim_time ?? 0))

const impactIr = computed(() => store.activeImpactReport)

const rescheduleResults = computed(() => store.activeRescheduleResults)

const recoveryScenarioRows = computed(() => {
  const sc = impactIr.value?.scenarios
  if (!sc) return []
  return ['r0', 'r1', 'r2'].map((k) => ({
    key: k,
    label: sc[k]?.label || k,
    makespan: sc[k]?.makespan,
    weighted_tardiness_total: sc[k]?.weighted_tardiness_total,
  }))
})

const impactRows = computed(() => {
  const rows = impactIr.value?.delay_details || []
  return rows.slice().sort((a, b) => Number(b.delta || 0) - Number(a.delta || 0))
})

const commitmentRows = computed(() => impactIr.value?.commitment_changes || [])

const ganttFallbackOpts = computed(() => ({
  baselineGantt:
    impactIr.value?.r0_gantt?.length
      ? impactIr.value.r0_gantt
      : props.execution?.baseline_gantt?.length
        ? props.execution.baseline_gantt
        : rescheduleResults.value?.[impactIr.value?.baseline_solver]?.gantt_data,
  freezeTime: impactIr.value?.freeze_time,
  insertJobSnapshot: impactIr.value?.insert_job_snapshot,
}))

const impactR1Gantt = computed(() =>
  effectiveR1Gantt(impactIr.value, ganttFallbackOpts.value),
)

const impactR2Gantt = computed(() =>
  effectiveR2Gantt(impactIr.value, store.results, rescheduleResults.value),
)

const hasRecoveryDualGantt = computed(() =>
  hasDualImpactGantt(
    impactIr.value,
    store.results,
    ganttFallbackOpts.value,
    rescheduleResults.value,
  ),
)

const showGanttCompareTab = computed(
  () => isDualGanttEvent(impactIr.value) || hasRecoveryDualGantt.value,
)

const impactGanttLayers = computed(() => {
  const layers = { ...(impactIr.value?.gantt_layers || {}) }
  if (impactIr.value?.freeze_time != null) {
    layers.freeze_time = impactIr.value.freeze_time
  }
  return layers
})

const rescheduledOpKeys = computed(
  () => impactIr.value?.gantt_layers?.rescheduled_op_keys || [],
)

watch(impactDialogVisible, (open) => {
  if (open) {
    impactTab.value = firstImpactTab(
      impactIr.value,
      store.results,
      ganttFallbackOpts.value,
      rescheduleResults.value,
    )
  }
})

function fmt(v, digits = 2) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return '-'
  return Number(v).toFixed(digits)
}

function parseMachineOptions(text, fallbackMachineId) {
  const nums = String(text || '')
    .split(',')
    .map((x) => Number(String(x).trim()))
    .filter((n) => Number.isInteger(n) && n >= 0)
  if (!nums.length && Number.isInteger(fallbackMachineId) && fallbackMachineId >= 0) return [fallbackMachineId]
  return [...new Set(nums)]
}

function normalizeTask(t, idx = 0) {
  const machineOptions = Array.isArray(t.machine_options)
    ? t.machine_options
    : parseMachineOptions(t.machine_options_text, t.machine_id)
  const machineId = Number.isInteger(t.machine_id) ? t.machine_id : (machineOptions[0] ?? 0)
  return {
    name: t.name || `Op-${idx + 1}`,
    duration: Number(t.duration || 1),
    machine_id: machineId,
    machine_options: machineOptions,
    machine_group: t.machine_group || null,
  }
}

function normalizeJob(job) {
  return {
    name: job.name,
    priority: Number(job.priority || 10),
    due_date: job.due_date ?? null,
    tasks: (job.tasks || []).map((t, idx) => normalizeTask(t, idx)),
  }
}

function baseJobs() {
  if (props.execution?.jobs_snapshot?.length) {
    return props.execution.jobs_snapshot.map((j) => normalizeJob(j))
  }
  return (store.currentPlanInput || []).map((j) => normalizeJob(j))
}

function solverList() {
  if (props.execution?.baseline_solver) return [props.execution.baseline_solver]
  return store.lastPayload?.solvers || Object.keys(store.results || {})
}

function rescheduleOptions() {
  const opts = {
    solvers: solverList(),
    weights: props.execution?.weights || store.lastPayload?.weights,
    random_seed: store.lastPayload?.random_seed,
  }
  if (props.execution?.baseline_gantt) {
    opts.baseline_gantt = props.execution.baseline_gantt
    opts.baseline_solver = props.execution.baseline_solver
  }
  return opts
}

function openPersistConfirm(pending) {
  persistToken.value = pending?.confirm_token || ''
  persistPreview.value = pending?.preview || null
  persistSummary.value = pending?.summary_zh || ''
  persistExpires.value = pending?.expires_at || ''
  persistVisible.value = true
}

async function openImpactAssessment() {
  const planId = props.execution?.plan_id || store.currentPlanId
  if (!planId) {
    ElMessage.warning('请先绑定或选择计划')
    return
  }
  impactLoading.value = true
  try {
    const ok = await loadImpactAssessmentForPlan(planId, { executionDoc: props.execution }, store)
    if (!ok || !store.activeImpactReport) {
      ElMessage.info('该计划暂无影响评估记录，请先执行一次重排')
      return
    }
    impactDialogVisible.value = true
  } catch (e) {
    ElMessage.error(`加载影响评估失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    impactLoading.value = false
  }
}

async function onPersistConfirmed(data) {
  persistVisible.value = false
  const planId = data?.plan_id || persistPreview.value?.plan_id || props.execution?.plan_id
  if (planId) {
    await fetchPlanScheduleIntoStore(planId, store)
    await loadImpactAssessmentForPlan(planId, { executionDoc: props.execution }, store)
  }
  ElMessage.success('计划排程与工单已更新')
}

async function maybePersistRescheduleToPlan(resultBundle) {
  const planId = props.execution?.plan_id
  const results = resultBundle?.results
  if (!planId || !results || !Object.keys(results).length) return
  const impact = resultBundle.impact_report
  try {
    const outcome = await persistScheduleWithHitl(planId, results, {
      plan_name: props.execution?.plan_name,
      impact_summary: buildImpactSummaryPayload(impact),
      jobs: resultBundle.updated_jobs,
    })
    if (outcome.kind === 'pending') {
      openPersistConfirm(outcome.pending_action)
      ElMessage.info('请确认是否覆盖计划排程与工单')
    } else if (outcome.kind === 'saved') {
      ElMessage.success({ message: '已更新计划排程与工单', duration: 2500 })
    }
  } catch (e) {
    ElMessage.warning(`重排完成，写入计划库失败: ${e.response?.data?.detail || e.message}`)
  }
}

async function applyResultBundle(body) {
  const resultBundle = normalizeEventResultBundle(body)
  store.setResults(resultBundle.results || null)
  const impact = resultBundle.impact_report
  const ig = resultBundle.impact_gantt
  const planId = props.execution?.plan_id || store.currentPlanId
  if (planId) store.impactPlanId = planId
  store.setImpactReport(impact || null, { impact_gantt: ig })
  store.setRescheduleSnapshot(resultBundle.results, impact, { impact_gantt: ig })
  if (Array.isArray(resultBundle.updated_jobs) && resultBundle.updated_jobs.length) {
    store.currentPlanInput = resultBundle.updated_jobs.map((j) => normalizeJob(j))
  }
  emit('rescheduled', resultBundle)
  await maybePersistRescheduleToPlan(resultBundle)
}

function warnIfNoExecution() {
  if (props.execution?.status !== 'running' && props.execution?.status !== 'paused') {
    ElMessage.warning('建议先在上方「开始执行」MES 计划，重排将使用当前仿真时刻与基准甘特')
    return false
  }
  return true
}

function openInsertDialog() {
  if (!canReschedule.value) {
    ElMessage.warning('请先开始 MES 执行，或在排程中心完成排程')
    return
  }
  insertForm.value.freeze_time = Math.floor(simNow.value || 0)
  insertDialogVisible.value = true
}

function openBreakdownDialog() {
  if (!canReschedule.value) {
    ElMessage.warning('请先开始 MES 执行，或在排程中心完成排程')
    return
  }
  const t = Math.floor(simNow.value || 0)
  breakdownForm.value = {
    machine_id: 0,
    breakdown_start: t,
    breakdown_duration: 4,
    freeze_time: t,
  }
  breakdownDialogVisible.value = true
}

function openDueDateDialog() {
  if (!canReschedule.value) {
    ElMessage.warning('请先开始 MES 执行，或在排程中心完成排程')
    return
  }
  const jobs = props.execution?.jobs_snapshot || store.currentPlanInput || []
  dueDateRows.value = jobs.map((j) => ({
    job_name: j.name,
    old_due_date: j.due_date ?? null,
    new_due_date: j.due_date ?? null,
  }))
  dueDateDialogVisible.value = true
}

function addInsertTask() {
  insertForm.value.job.tasks.push({
    name: `Op-${insertForm.value.job.tasks.length + 1}`,
    machine_id: 0,
    machine_options_text: '0',
    machine_group: '',
    duration: 5,
  })
}

async function submitDueDateReschedule() {
  const changes = dueDateRows.value
    .filter((r) => r.new_due_date != null && r.new_due_date !== '' && Number(r.new_due_date) !== Number(r.old_due_date))
    .map((r) => ({ job_name: r.job_name, new_due_date: Number(r.new_due_date) }))
  if (!changes.length) {
    ElMessage.warning('请至少修改一条工单的新交期')
    return
  }
  rescheduling.value = true
  try {
    const { data } = await api.post('/api/events/due_date_reschedule', {
      due_date_changes: changes,
      solvers: solverList(),
      weights: store.lastPayload?.weights,
      random_seed: store.lastPayload?.random_seed,
      base_jobs: baseJobs(),
    })
    if (data?.error) throw new Error(data.error)
    applyResultBundle(data)
    dueDateDialogVisible.value = false
    impactDialogVisible.value = true
    ElMessage.success(`改期重排完成：调整 ${changes.length} 单`)
  } catch (e) {
    ElMessage.error(`改期重排失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    rescheduling.value = false
  }
}

async function submitBreakdownReschedule() {
  warnIfNoExecution()
  rescheduling.value = true
  try {
    const { data } = await api.post('/api/events/machine_breakdown_reschedule', {
      machine_id: Number(breakdownForm.value.machine_id),
      breakdown_start: Number(breakdownForm.value.breakdown_start),
      breakdown_duration: Number(breakdownForm.value.breakdown_duration),
      freeze_time: breakdownForm.value.freeze_time ?? breakdownForm.value.breakdown_start,
      ...rescheduleOptions(),
      base_jobs: baseJobs(),
    })
    if (data?.error) throw new Error(data.error)
    applyResultBundle(data)
    breakdownDialogVisible.value = false
    impactDialogVisible.value = true
    const impact = data?.data?.impact_report || {}
    const imp = impact.improvement_vs_r1
    const msg = imp?.makespan_delta < 0
      ? `故障重排完成，相对不重排缩短 ${Math.abs(imp.makespan_delta).toFixed(1)}h`
      : `故障重排完成（受影响工单 ${impact.affected_jobs ?? 0}）`
    ElMessage.success(msg)
  } catch (e) {
    ElMessage.error(`故障重排失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    rescheduling.value = false
  }
}

async function submitInsertReschedule() {
  const jobName = String(insertForm.value.job.name || '').trim()
  if (!jobName) {
    ElMessage.warning('请填写插单名称')
    return
  }
  const tasks = insertForm.value.job.tasks || []
  if (!tasks.length) {
    ElMessage.warning('插单至少包含 1 道工序')
    return
  }
  rescheduling.value = true
  try {
    const { data } = await api.post('/api/events/insert_order_reschedule', {
      mode: insertForm.value.mode,
      freeze_time: Number(insertForm.value.freeze_time ?? simNow.value ?? 0),
      ...rescheduleOptions(),
      base_jobs: baseJobs(),
      insert_job: {
        name: jobName,
        priority: Number(insertForm.value.job.priority || 100),
        tasks: tasks.map((t, idx) => normalizeTask(t, idx)),
      },
    })
    if (data?.error) throw new Error(data.error)
    applyResultBundle(data)
    if (props.execution?.jobs_snapshot && !data?.data?.updated_jobs) {
      store.currentPlanInput = [...baseJobs(), normalizeJob(insertForm.value.job)]
    }
    insertDialogVisible.value = false
    impactDialogVisible.value = true
    store.setHighlightJobNames([jobName])
    ElMessage.success(`插单重排完成：${jobName}`)
  } catch (e) {
    ElMessage.error(`重排失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    rescheduling.value = false
  }
}

function goReports() {
  impactDialogVisible.value = false
  router.push('/reports')
}

function riskLabel(level) {
  const map = { on_time: '按期', low: '低风险', medium: '中风险', high: '高风险', critical: '严重', unknown: '未设交期' }
  return map[level] || level
}

function riskTagType(level) {
  const map = { on_time: 'success', low: 'success', medium: 'warning', high: 'danger', critical: 'danger', unknown: 'info' }
  return map[level] || 'info'
}

defineExpose({ openImpactDialog: openImpactAssessment })
</script>

<template>
  <div class="mes-reschedule">
    <div class="row actions">
      <el-button type="warning" :disabled="!canReschedule" @click="openInsertDialog">插单局部重排</el-button>
      <el-button type="danger" plain :disabled="!canReschedule" @click="openBreakdownDialog">设备故障重排</el-button>
      <el-button type="primary" plain :disabled="!canReschedule" @click="openDueDateDialog">改交期重排</el-button>
      <el-button
        v-if="showImpactButton && (execution?.plan_id || store.currentPlanId)"
        type="info"
        plain
        :loading="impactLoading"
        @click="openImpactAssessment"
      >
        查看影响评估
      </el-button>
      <span v-if="execution?.status === 'running' || execution?.status === 'paused'" class="hint">
        冻结/故障时刻默认 = 当前仿真 {{ fmt(simNow) }} h
      </span>
      <span v-else-if="!canReschedule" class="hint warn">按钮暂不可用：需先开始 MES 执行</span>
    </div>

    <el-dialog v-model="dueDateDialogVisible" title="批量改交期 + 全局重排" width="640px">
      <el-alert type="info" :closable="false" show-icon title="仅修改填写了新交期的工单；完成后可查看 R0/R1/R2 对比。" style="margin-bottom: 12px" />
      <el-table :data="dueDateRows" size="small" border max-height="360">
        <el-table-column prop="job_name" label="工单" min-width="140" />
        <el-table-column label="原交期" width="110" align="right">
          <template #default="{ row }">{{ row.old_due_date == null ? '自动' : fmt(row.old_due_date) }}</template>
        </el-table-column>
        <el-table-column label="新交期" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.new_due_date" :min="0" :step="1" controls-position="right" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="dueDateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="rescheduling" @click="submitDueDateReschedule">执行重排</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="breakdownDialogVisible" title="设备故障 + 局部重排" width="520px">
      <el-form label-width="120px">
        <el-form-item label="故障机台 ID">
          <el-input-number v-model="breakdownForm.machine_id" :min="0" :step="1" />
          <div class="hint">0 起算；界面「3 号机」= ID 2</div>
        </el-form-item>
        <el-form-item label="故障开始 (h)">
          <el-input-number v-model="breakdownForm.breakdown_start" :min="0" :step="0.5" />
        </el-form-item>
        <el-form-item label="故障时长 (h)">
          <el-input-number v-model="breakdownForm.breakdown_duration" :min="0.1" :step="0.5" />
        </el-form-item>
        <el-form-item label="冻结时刻 (h)">
          <el-input-number v-model="breakdownForm.freeze_time" :min="0" :step="0.5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="breakdownDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="rescheduling" @click="submitBreakdownReschedule">执行重排</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="insertDialogVisible" title="插单 + 局部修复重排" width="760px">
      <el-form label-width="130px">
        <el-form-item label="重排模式">
          <el-select v-model="insertForm.mode" style="width: 220px">
            <el-option label="局部修复（冻结已开始）" value="local_repair" />
            <el-option label="全局重排" value="global" />
          </el-select>
        </el-form-item>
        <el-form-item label="冻结时刻 (h)">
          <el-input-number v-model="insertForm.freeze_time" :min="0" :step="0.5" />
        </el-form-item>
        <el-form-item label="插单名称">
          <el-input v-model="insertForm.job.name" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="insertForm.job.priority" :min="1" />
        </el-form-item>
        <el-form-item label="工序">
          <el-table :data="insertForm.job.tasks" size="small" border>
            <el-table-column label="名" min-width="100"><template #default="{ row }"><el-input v-model="row.name" /></template></el-table-column>
            <el-table-column label="机台" width="90"><template #default="{ row }"><el-input-number v-model="row.machine_id" :min="0" controls-position="right" /></template></el-table-column>
            <el-table-column label="时长" width="90"><template #default="{ row }"><el-input-number v-model="row.duration" :min="1" controls-position="right" /></template></el-table-column>
            <el-table-column width="60"><template #default="{ $index }"><el-button type="danger" text @click="insertForm.job.tasks.splice($index, 1)">删</el-button></template></el-table-column>
          </el-table>
          <el-button size="small" class="mt8" @click="addInsertTask">加工序</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="insertDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="rescheduling" @click="submitInsertReschedule">执行重排</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="impactDialogVisible" title="重排影响评估" width="1180px" top="4vh">
      <el-empty v-if="!impactIr" description="暂无影响评估" />
      <template v-else>
        <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
          <el-descriptions-item label="事件">
            {{
              impactIr?.event_type === 'due_date_change'
                ? '改交期'
                : impactIr?.event_type === 'insert_order'
                  ? '插单'
                  : impactIr?.event_type === 'machine_breakdown'
                    ? '设备故障'
                    : impactIr?.event_type || '-'
            }}
          </el-descriptions-item>
          <el-descriptions-item v-if="impactIr?.mode" label="模式">{{ impactIr.mode }}</el-descriptions-item>
          <el-descriptions-item v-if="impactIr?.insert_job_name" label="插单">
            {{ impactIr.insert_job_name }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="impactIr?.due_date_changes?.length"
            label="改期工单"
            :span="2"
          >
            {{
              impactIr.due_date_changes
                .map((c) => `${c.job_name}→${c.new_due_date}h`)
                .join('；')
            }}
          </el-descriptions-item>
          <el-descriptions-item v-if="impactIr?.machine_label_zh" label="机台">
            {{ impactIr.machine_label_zh }}
          </el-descriptions-item>
          <el-descriptions-item v-if="impactIr?.breakdown_start != null" label="故障窗">
            {{ fmt(impactIr.breakdown_start) }}–{{ fmt(impactIr.breakdown_end) }} h
          </el-descriptions-item>
        </el-descriptions>
        <el-tabs v-model="impactTab">
          <el-tab-pane v-if="showGanttCompareTab" label="甘特对比" name="gantt">
            <template v-if="hasRecoveryDualGantt">
              <ImpactDualGantt
                :r1-gantt="impactR1Gantt"
                :r2-gantt="impactR2Gantt"
                :layers="impactGanttLayers"
                :scenarios="impactIr?.scenarios"
                :rescheduled-keys="rescheduledOpKeys"
                :insert-op-keys="impactIr?.gantt_layers?.insert_op_keys || []"
                :due-date-op-keys="impactIr?.gantt_layers?.due_date_op_keys || []"
                :event-type="impactIr?.event_type || ''"
              />
              <p v-if="impactIr?.improvement_vs_r1" class="hint imp-hint">
                相对不重排：完工时间变化 {{ fmt(impactIr.improvement_vs_r1.makespan_delta) }} h，
                加权拖期变化 {{ fmt(impactIr.improvement_vs_r1.tardiness_delta) }}
              </p>
            </template>
            <el-alert
              v-else
              type="warning"
              :closable="false"
              show-icon
              title="甘特数据未加载完整"
              description="请重启后端并 Ctrl+F5 强刷页面后重新执行重排。若仍无图，请在开发者工具 Network 中检查接口响应是否包含 impact_gantt 或 impact_report.r1_gantt / r2_gantt。"
            />
          </el-tab-pane>
          <el-tab-pane v-if="recoveryScenarioRows.length" label="R0/R1/R2" name="recovery">
            <el-table :data="recoveryScenarioRows" stripe size="small">
              <el-table-column prop="label" label="场景" width="140" />
              <el-table-column prop="makespan" label="完工时间" width="120" align="right" />
              <el-table-column prop="weighted_tardiness_total" label="加权拖期" width="120" align="right" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="完工变化" name="delay">
            <el-table :data="impactRows" stripe max-height="320" size="small">
              <el-table-column prop="job_name" label="工单" />
              <el-table-column prop="old_completion" label="原完工" width="100" align="right" />
              <el-table-column prop="new_completion" label="新完工" width="100" align="right" />
              <el-table-column prop="delta" label="变化" width="90" align="right" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="承诺" name="commitment">
            <el-table :data="commitmentRows" stripe size="small" empty-text="无">
              <el-table-column prop="job_name" label="工单" />
              <el-table-column label="原风险" width="90">
                <template #default="{ row }"><el-tag :type="riskTagType(row.old_risk)" size="small">{{ riskLabel(row.old_risk) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="新风险" width="90">
                <template #default="{ row }"><el-tag :type="riskTagType(row.new_risk)" size="small">{{ riskLabel(row.new_risk) }}</el-tag></template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
      <template #footer>
        <el-button @click="impactDialogVisible = false">关闭</el-button>
        <el-button type="primary" plain @click="goReports">打开报表分析</el-button>
      </template>
    </el-dialog>

    <PersistConfirmDialog
      v-model="persistVisible"
      :preview="persistPreview"
      :confirm-token="persistToken"
      :summary-zh="persistSummary"
      :expires-at="persistExpires"
      @confirmed="onPersistConfirmed"
    />
  </div>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hint { font-size: 12px; color: #909399; }
.hint.warn { color: #e6a23c; }
.imp-hint { margin-top: 10px; }
.mt8 { margin-top: 8px; }
</style>
