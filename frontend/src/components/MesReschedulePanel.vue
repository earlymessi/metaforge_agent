<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'
import { useAssistantStore } from '../stores/useAssistantStore'
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
const assistantStore = useAssistantStore()

const insertDialogVisible = ref(false)
const breakdownDialogVisible = ref(false)
const scheduleEventDialogVisible = ref(false)
const dueDateDialogVisible = ref(false)
const impactDialogVisible = ref(false)
const dueDateRows = ref([])
const rescheduling = ref(false)
const impactLoading = ref(false)
const schedulingEvent = ref(false)
const impactTab = ref('delay')
const lastAutoNotifyKey = ref('')

const persistVisible = ref(false)
const persistToken = ref('')
const persistPreview = ref(null)
const persistSummary = ref('')
const persistExpires = ref('')

const EVENT_TYPE_OPTIONS = [
  { value: 'machine_breakdown', label: '设备故障' },
  { value: 'insert_order', label: '插单' },
  { value: 'due_date_change', label: '改交期' },
  { value: 'planned_downtime', label: '计划停机' },
  { value: 'material_delay', label: '物料晚到' },
  { value: 'priority_change', label: '调整优先级' },
  { value: 'order_cancel', label: '撤单' },
  { value: 'quantity_change', label: '数量变更' },
]

const breakdownForm = ref({
  machine_id: 0,
  breakdown_start: 0,
  breakdown_duration: 4,
  freeze_time: null,
})

const scheduleEventForm = ref({
  event_type: 'machine_breakdown',
  trigger_at: 2,
  machine_id: 0,
  breakdown_duration: 4,
  downtime_machine_id: 0,
  downtime_duration: 4,
  material_job_name: '',
  material_delay_hours: 4,
  priority_job_name: '',
  priority_value: 100,
  cancel_job_name: '',
  quantity_job_name: '',
  quantity_value: 10,
  due_date_job_name: '',
  due_date_value: 20,
  insert_mode: 'local_repair',
  insert_job: {
    name: '急单',
    priority: 100,
    tasks: [{ name: 'Op-1', machine_id: 0, duration: 5 }],
  },
})

const scheduledEvent = computed(() => {
  const se = props.execution?.scheduled_event
  if (se && se.event_type) return se
  const sb = props.execution?.scheduled_breakdown
  if (!sb) return null
  return {
    event_type: 'machine_breakdown',
    trigger_at: sb.breakdown_start,
    params: {
      machine_id: sb.machine_id,
      breakdown_duration: sb.breakdown_duration,
    },
    status: sb.status,
    summary_zh: sb.summary_zh,
    fired_at_sim: sb.fired_at_sim,
    error: sb.error,
  }
})
const scheduledPending = computed(() => scheduledEvent.value?.status === 'pending')
const scheduledEventLabel = computed(() => {
  const et = scheduledEvent.value?.event_type
  return EVENT_TYPE_OPTIONS.find((o) => o.value === et)?.label || et || '事件'
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

const recoveryScenarioRows = computed(() => {
  const sc = impactIr.value?.scenarios
  if (!sc) return []
  const ganttByKey = {
    r0: impactIr.value?.r0_gantt,
    r1: impactR1Gantt.value,
    r2: impactR2Gantt.value,
  }
  const msFromGantt = (gantt) => {
    if (!Array.isArray(gantt) || !gantt.length) return null
    return Math.max(...gantt.map((op) => Number(op.end) || 0))
  }
  return ['r0', 'r1', 'r2'].map((k) => {
    const fromGantt = msFromGantt(ganttByKey[k])
    const fromSc = sc[k]?.makespan
    return {
      key: k,
      label: sc[k]?.label || k,
      makespan: fromGantt != null ? Number(fromGantt.toFixed(4)) : fromSc,
      weighted_tardiness_total: sc[k]?.weighted_tardiness_total,
    }
  })
})

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
  const ir = impactIr.value || {}
  const layers = { ...(ir.gantt_layers || {}) }
  if (ir.freeze_time != null) layers.freeze_time = ir.freeze_time
  // 兜底：即使 gantt_layers 丢失，也从影响报告顶栏字段拼出故障/停机窗
  if (
    !layers.breakdown_window
    && ir.event_type === 'machine_breakdown'
    && ir.machine_id != null
    && ir.breakdown_start != null
  ) {
    layers.breakdown_window = {
      machine_id: ir.machine_id,
      start: ir.breakdown_start,
      end: ir.breakdown_end != null
        ? ir.breakdown_end
        : Number(ir.breakdown_start) + Number(ir.breakdown_duration || 0),
      label: '故障',
    }
  }
  if (
    !layers.downtime_windows?.length
    && ir.event_type === 'planned_downtime'
    && Array.isArray(ir.downtime_blocks)
  ) {
    layers.downtime_windows = ir.downtime_blocks.map((b) => ({
      machine_id: b.machine_id,
      start: b.start,
      end: b.end,
      label: b.label || '停机',
    }))
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
  const duration = 4
  breakdownForm.value = {
    machine_id: pickMachineHitByBreakdown(t, duration, 0),
    breakdown_start: t,
    breakdown_duration: duration,
    freeze_time: t,
  }
  breakdownDialogVisible.value = true
}

function jobNames() {
  const jobs = props.execution?.jobs_snapshot || store.currentPlanInput || []
  return jobs.map((j) => j.name).filter(Boolean)
}

/** 在 baseline 甘特上找故障窗内有工序的机台（演示默认避免「空闲机台故障→左右一样」） */
function pickMachineHitByBreakdown(triggerAt, duration, fallback = 0) {
  const gantt = props.execution?.baseline_gantt || []
  const b0 = Number(triggerAt)
  const b1 = b0 + Number(duration)
  if (!gantt.length || !Number.isFinite(b0) || !Number.isFinite(b1)) return fallback
  const hits = new Map()
  for (const op of gantt) {
    const s = Number(op.start)
    const e = Number(op.end)
    const mid = Number(op.machine_id)
    if (!Number.isFinite(mid) || !Number.isFinite(s) || !Number.isFinite(e)) continue
    if (s < b1 && e > b0) hits.set(mid, (hits.get(mid) || 0) + 1)
  }
  if (!hits.size) return fallback
  return [...hits.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

function breakdownHitsOps(machineId, triggerAt, duration) {
  const gantt = props.execution?.baseline_gantt || []
  const b0 = Number(triggerAt)
  const b1 = b0 + Number(duration)
  const mid = Number(machineId)
  return gantt.some((op) => {
    const s = Number(op.start)
    const e = Number(op.end)
    return Number(op.machine_id) === mid && s < b1 && e > b0
  })
}

const scheduleBreakdownNoHit = computed(() => {
  if (scheduleEventForm.value.event_type !== 'machine_breakdown') return false
  return !breakdownHitsOps(
    scheduleEventForm.value.machine_id,
    scheduleEventForm.value.trigger_at,
    scheduleEventForm.value.breakdown_duration,
  )
})

function openScheduleEventDialog() {
  if (props.execution?.status !== 'running' && props.execution?.status !== 'paused') {
    ElMessage.warning('请先开始 MES 执行，再预约动态事件')
    return
  }
  const t = Math.floor(simNow.value || 0)
  const triggerAt = Math.max(t + 1, 1)
  const duration = 4
  const names = jobNames()
  const first = names[0] || ''
  scheduleEventForm.value = {
    ...scheduleEventForm.value,
    event_type: 'machine_breakdown',
    trigger_at: triggerAt,
    machine_id: pickMachineHitByBreakdown(triggerAt, duration, 0),
    breakdown_duration: duration,
    downtime_machine_id: 0,
    downtime_duration: 4,
    material_job_name: first,
    material_delay_hours: 4,
    priority_job_name: first,
    priority_value: 100,
    cancel_job_name: first,
    quantity_job_name: first,
    quantity_value: 10,
    due_date_job_name: first,
    due_date_value: 20,
    insert_mode: 'local_repair',
    insert_job: {
      name: '急单',
      priority: 100,
      tasks: [{ name: 'Op-1', machine_id: 0, duration: 5 }],
    },
  }
  scheduleEventDialogVisible.value = true
}

function buildScheduleParams() {
  const f = scheduleEventForm.value
  const et = f.event_type
  if (et === 'machine_breakdown') {
    return {
      machine_id: Number(f.machine_id),
      breakdown_start: Number(f.trigger_at),
      breakdown_duration: Number(f.breakdown_duration),
    }
  }
  if (et === 'insert_order') {
    return {
      mode: f.insert_mode || 'local_repair',
      insert_job: {
        name: f.insert_job.name,
        priority: Number(f.insert_job.priority),
        tasks: (f.insert_job.tasks || []).map((t) => ({
          name: t.name,
          machine_id: Number(t.machine_id),
          duration: Number(t.duration),
        })),
      },
    }
  }
  if (et === 'due_date_change') {
    return {
      due_date_changes: [{
        job_name: f.due_date_job_name,
        new_due_date: Number(f.due_date_value),
      }],
    }
  }
  if (et === 'planned_downtime') {
    const start = Number(f.trigger_at)
    const dur = Number(f.downtime_duration)
    return {
      downtime_blocks: [{
        machine_id: Number(f.downtime_machine_id),
        start,
        end: start + dur,
        label: 'planned_downtime',
      }],
    }
  }
  if (et === 'material_delay') {
    return {
      job_name: f.material_job_name,
      delay_hours: Number(f.material_delay_hours),
    }
  }
  if (et === 'priority_change') {
    return {
      changes: [{ job_name: f.priority_job_name, new_priority: Number(f.priority_value) }],
    }
  }
  if (et === 'order_cancel') {
    return { job_names: [f.cancel_job_name].filter(Boolean) }
  }
  if (et === 'quantity_change') {
    return {
      changes: [{ job_name: f.quantity_job_name, new_quantity: Number(f.quantity_value) }],
    }
  }
  return {}
}

async function submitScheduleEvent() {
  schedulingEvent.value = true
  try {
    const { data } = await api.post('/api/execution/schedule_event', {
      event_type: scheduleEventForm.value.event_type,
      trigger_at: Number(scheduleEventForm.value.trigger_at),
      params: buildScheduleParams(),
    })
    scheduleEventDialogVisible.value = false
    ElMessage.success(
      data?.scheduled_event?.summary_zh
        || `已预约：仿真到达 ${scheduleEventForm.value.trigger_at}h 后自动重排`,
    )
    emit('refresh-execution')
  } catch (e) {
    ElMessage.error(`预约失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    schedulingEvent.value = false
  }
}

async function cancelScheduledEvent() {
  try {
    await api.post('/api/execution/cancel_scheduled_event')
    ElMessage.info('已取消预约事件')
    emit('refresh-execution')
  } catch (e) {
    ElMessage.error(`取消失败: ${e.response?.data?.detail || e.message}`)
  }
}

async function consumeAutoRescheduleNotify(notify) {
  if (!notify || notify.acked) return
  const key = `${notify.fired_at_sim}-${notify.summary_zh || ''}`
  if (key === lastAutoNotifyKey.value) return
  lastAutoNotifyKey.value = key

  const raw = notify.result
  if (raw && !raw.error) {
    await applyResultBundle(raw)
    impactDialogVisible.value = true
    ElMessage.warning({
      message: notify.summary_zh || '预约事件已触发，仿真已暂停，请查看影响并确认落库',
      duration: 4500,
    })
  } else {
    ElMessage.error(raw?.error || notify.summary_zh || '预约事件自动重排失败')
  }

  assistantStore.pushSystemNotice({
    text: notify.summary_zh
      || '系统已按预约注入动态事件并完成自动重排；请在看板确认 HITL 落库。',
    openDrawer: true,
  })

  try {
    await api.post('/api/execution/ack_auto_reschedule')
  } catch {
    /* ignore */
  }
  emit('refresh-execution')
}

watch(
  () => props.execution?.auto_reschedule_notify,
  (n) => {
    if (n && !n.acked) consumeAutoRescheduleNotify(n)
  },
  { deep: true },
)

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

function goCompare() {
  const ir = impactIr.value
  if (ir) {
    try {
      sessionStorage.setItem('metaforge_last_impact', JSON.stringify(ir))
    } catch {
      /* ignore */
    }
  }
  impactDialogVisible.value = false
  router.push('/compare')
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
      <el-button type="danger" plain :disabled="!canReschedule" @click="openBreakdownDialog">立即故障重排</el-button>
      <el-button
        type="danger"
        :disabled="execution?.status !== 'running' && execution?.status !== 'paused'"
        :loading="schedulingEvent"
        @click="openScheduleEventDialog"
      >
        预约动态事件
      </el-button>
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
      <el-tag v-if="scheduledPending" type="danger" effect="plain" class="sched-tag">
        已预约：{{ scheduledEventLabel }} @ {{ fmt(scheduledEvent.trigger_at) }}h
        <el-button link type="danger" size="small" @click="cancelScheduledEvent">取消</el-button>
      </el-tag>
      <el-tag v-else-if="scheduledEvent?.status === 'firing'" type="warning" effect="plain">事件触发中…</el-tag>
      <el-tag v-else-if="scheduledEvent?.status === 'fired'" type="success" effect="plain">
        已自动重排 @ {{ fmt(scheduledEvent.fired_at_sim) }}h
      </el-tag>
      <span v-if="execution?.status === 'running' || execution?.status === 'paused'" class="hint">
        预约后仿真到达时刻将自动重排并暂停；当前 {{ fmt(simNow) }} h
      </span>
      <span v-else-if="!canReschedule" class="hint warn">按钮暂不可用：需先开始 MES 执行</span>
    </div>

    <el-dialog v-model="scheduleEventDialogVisible" title="预约动态事件（仿真时钟自动触发）" width="640px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="不写聊天框：仿真时刻到达后系统自动注入事件 → 重排 → 暂停 → HITL 确认落库。"
        style="margin-bottom: 12px"
      />
      <el-form label-width="130px">
        <el-form-item label="事件类型">
          <el-select v-model="scheduleEventForm.event_type" style="width: 240px">
            <el-option
              v-for="opt in EVENT_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="触发时刻 (h)">
          <el-input-number v-model="scheduleEventForm.trigger_at" :min="0" :step="0.5" />
          <div class="hint">建议大于当前仿真 {{ fmt(simNow) }} h</div>
        </el-form-item>

        <template v-if="scheduleEventForm.event_type === 'machine_breakdown'">
          <el-form-item label="故障机台 ID">
            <el-input-number v-model="scheduleEventForm.machine_id" :min="0" :step="1" />
            <div class="hint">0 起算；界面「{{ scheduleEventForm.machine_id + 1 }} 号机」= ID {{ scheduleEventForm.machine_id }}。已按甘特自动选「故障窗内有工序」的机台。</div>
          </el-form-item>
          <el-form-item label="故障时长 (h)">
            <el-input-number v-model="scheduleEventForm.breakdown_duration" :min="0.1" :step="0.5" />
          </el-form-item>
          <el-alert
            v-if="scheduleBreakdownNoHit"
            type="warning"
            :closable="false"
            show-icon
            title="当前机台在故障窗内没有工序：左右甘特会几乎一样。请换一台在该时段有加工的机台（如 1 号机 / ID 0）。"
            style="margin-bottom: 8px"
          />
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'insert_order'">
          <el-form-item label="插单名称">
            <el-input v-model="scheduleEventForm.insert_job.name" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-input-number v-model="scheduleEventForm.insert_job.priority" :min="1" />
          </el-form-item>
          <el-form-item label="工序机台">
            <el-input-number v-model="scheduleEventForm.insert_job.tasks[0].machine_id" :min="0" />
          </el-form-item>
          <el-form-item label="工序时长">
            <el-input-number v-model="scheduleEventForm.insert_job.tasks[0].duration" :min="1" />
          </el-form-item>
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'due_date_change'">
          <el-form-item label="工单">
            <el-select v-model="scheduleEventForm.due_date_job_name" filterable allow-create style="width: 240px">
              <el-option v-for="n in jobNames()" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <el-form-item label="新交期 (h)">
            <el-input-number v-model="scheduleEventForm.due_date_value" :min="0" :step="1" />
          </el-form-item>
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'planned_downtime'">
          <el-form-item label="停机台 ID">
            <el-input-number v-model="scheduleEventForm.downtime_machine_id" :min="0" />
          </el-form-item>
          <el-form-item label="停机时长 (h)">
            <el-input-number v-model="scheduleEventForm.downtime_duration" :min="0.1" :step="0.5" />
          </el-form-item>
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'material_delay'">
          <el-form-item label="工单">
            <el-select v-model="scheduleEventForm.material_job_name" filterable allow-create style="width: 240px">
              <el-option v-for="n in jobNames()" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <el-form-item label="延迟 (h)">
            <el-input-number v-model="scheduleEventForm.material_delay_hours" :min="0.1" :step="0.5" />
          </el-form-item>
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'priority_change'">
          <el-form-item label="工单">
            <el-select v-model="scheduleEventForm.priority_job_name" filterable allow-create style="width: 240px">
              <el-option v-for="n in jobNames()" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <el-form-item label="新优先级">
            <el-input-number v-model="scheduleEventForm.priority_value" :min="1" />
          </el-form-item>
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'order_cancel'">
          <el-form-item label="撤单工单">
            <el-select v-model="scheduleEventForm.cancel_job_name" filterable allow-create style="width: 240px">
              <el-option v-for="n in jobNames()" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
        </template>

        <template v-else-if="scheduleEventForm.event_type === 'quantity_change'">
          <el-form-item label="工单">
            <el-select v-model="scheduleEventForm.quantity_job_name" filterable allow-create style="width: 240px">
              <el-option v-for="n in jobNames()" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <el-form-item label="新数量">
            <el-input-number v-model="scheduleEventForm.quantity_value" :min="1" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="scheduleEventDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="schedulingEvent" @click="submitScheduleEvent">确认预约</el-button>
      </template>
    </el-dialog>

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
              ({
                due_date_change: '改交期',
                insert_order: '插单',
                machine_breakdown: '设备故障',
                planned_downtime: '计划停机',
                material_delay: '物料晚到',
                priority_change: '调整优先级',
                order_cancel: '撤单',
                quantity_change: '数量变更',
              })[impactIr?.event_type] || impactIr?.event_type || '-'
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
        <el-button type="success" plain @click="goCompare">打开对比页</el-button>
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
.sched-tag { display: inline-flex; align-items: center; gap: 4px; }
</style>
