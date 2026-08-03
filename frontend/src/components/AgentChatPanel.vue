<template>
  <div class="chat-panel" :class="{ compact }">
    <div v-if="showHeader" class="panel-head">
      <div class="title">{{ title }}</div>
      <div class="head-tags">
        <el-tag v-if="llmStatus.enabled" type="success" size="small">GLM</el-tag>
        <el-tag v-else type="info" size="small">规则</el-tag>
        <el-tag v-if="sessionId" size="small" effect="plain">会话 {{ sessionId.slice(0, 8) }}</el-tag>
      </div>
    </div>

    <div class="plan-bar">
      <el-select
        v-model="selectedPlanId"
        filterable
        clearable
        placeholder="选择计划 / 订单"
        size="small"
        :loading="plansLoading"
        class="plan-select"
        @change="onPlanSelectChange"
      >
        <el-option v-for="p in planOptions" :key="p.id" :label="p.label" :value="p.id" />
      </el-select>
      <el-button size="small" :loading="plansLoading" @click="fetchPlans">刷新</el-button>
      <el-button size="small" type="primary" plain @click="onCreatePlan">新建</el-button>
      <el-button v-if="workStore.planId" size="small" link type="danger" @click="clearBinding">解绑</el-button>
    </div>

    <el-alert
      :type="workStore.hasJobs ? 'success' : workStore.planId ? 'info' : 'warning'"
      :closable="false"
      show-icon
      class="ctx-alert"
    >
      <template #title>
        {{ workStore.hasJobs ? '已绑定计划工单' : workStore.planId ? '已绑定计划（暂无工单）' : '尚未绑定计划' }}
      </template>
      <template #default>
        <span v-if="workStore.hasJobs">{{ workStore.summaryLabel }}</span>
        <span v-else-if="workStore.planId">计划「{{ workStore.planName }}」已选中，可在排程中心编辑工单。</span>
        <span v-else>可说「新建计划a」「加载计划 演示-A」「列出计划」「删除计划 xxx」；新建后会自动打开排程中心。</span>
      </template>
    </el-alert>

    <div v-if="!compact" class="opts row">
      <el-select v-model="intentOverride" clearable placeholder="指定意图（可选）" size="small" style="width: 150px">
        <el-option label="排程" value="schedule" />
        <el-option label="重排" value="reschedule" />
        <el-option label="齐套" value="kitting" />
        <el-option label="交期" value="commitment" />
        <el-option label="对比" value="whatif" />
        <el-option label="计划管理" value="plans" />
      </el-select>
      <el-button size="small" @click="newSession">新会话</el-button>
    </div>
    <el-collapse v-else class="mini-opts">
      <el-collapse-item title="高级选项" name="adv">
        <el-select v-model="intentOverride" clearable placeholder="指定意图" size="small" style="width: 100%; margin-bottom: 8px">
          <el-option label="排程" value="schedule" />
          <el-option label="重排" value="reschedule" />
          <el-option label="齐套" value="kitting" />
          <el-option label="计划管理" value="plans" />
        </el-select>
        <el-button size="small" block @click="newSession">新会话</el-button>
      </el-collapse-item>
    </el-collapse>

    <div v-if="showExamples" class="examples">
      <el-button v-for="ex in examples" :key="ex" size="small" text type="primary" @click="inputText = ex">
        {{ ex }}
      </el-button>
    </div>

    <div ref="scrollRef" class="messages" :class="{ compact }">
      <div v-if="!messages.length" class="empty-hint">描述需求，将展示路由与执行过程</div>
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble" :class="{ 'bubble-trace': m.role === 'thinking' }">
          <template v-if="m.role === 'thinking' || m.role === 'trace'">
            <div class="thinking-title">
              <el-icon v-if="m.role === 'thinking'" class="is-loading"><Loading /></el-icon>
              {{ m.role === 'thinking' ? (m.statusText || '思考中…') : '思考与执行过程' }}
            </div>
            <TracePanel
              :trace="m.trace"
              :loading="m.role === 'thinking'"
              :hint="m.statusText || ''"
            />
          </template>
          <template v-else-if="m.role === 'assistant'">
            <el-tag v-if="m.agent_id" size="small" effect="plain" style="margin-bottom: 6px">{{ m.agent_id }}</el-tag>
            <div class="text">{{ m.text }}</div>
            <AgentResultCards v-if="m.artifacts" :agent-id="m.agent_id" :artifacts="m.artifacts" />
            <el-button
              v-if="m.show_reports"
              type="primary"
              size="small"
              style="margin-top: 8px"
              @click="router.push('/reports')"
            >
              查看分析报表
            </el-button>
            <el-button v-if="m.pending_confirm" type="warning" size="small" style="margin-top: 8px" @click="openConfirm(m.pending_confirm)">
              {{ m.pending_confirm?.preview?.has_existing_schedule ? '确认覆盖落库' : '确认落库' }}
            </el-button>
          </template>
          <div v-else-if="m.role === 'user'" class="text">{{ m.text }}</div>
          <div v-else-if="m.role === 'system'" class="text system">{{ m.text }}</div>
        </div>
      </div>
    </div>

    <div class="composer">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="compact ? 2 : 2"
        placeholder="例如：新建计划a；加载计划 演示-A；列出计划；3号机坏了4小时帮我重排"
        @keydown.enter.exact.prevent="send"
      />
      <el-button type="primary" :loading="loading" :disabled="!inputText.trim()" @click="send">发送</el-button>
    </div>

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

<script setup>
import { defineComponent, h, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElTag } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api, streamOrchestrator } from '../api/client'
import { useWorkContextStore } from '../stores/useWorkContextStore'
import { usePlanBinding } from '../composables/usePlanBinding'
import { useResultsStore } from '../stores/useResultsStore'
import {
  hydrateFromOrchestratorDone,
  fetchPlanScheduleIntoStore,
  isValidScheduleResults,
  scheduleResultsFromArtifacts,
} from '../utils/planScheduleSync'
import { applyMesEventArtifactsToStore } from '../utils/mesEventSync'
import PersistConfirmDialog from './PersistConfirmDialog.vue'
import AgentResultCards from './AgentResultCards.vue'

defineProps({
  compact: { type: Boolean, default: false },
  showHeader: { type: Boolean, default: true },
  showExamples: { type: Boolean, default: true },
  title: { type: String, default: '车间智能助手' },
})

const router = useRouter()
const workStore = useWorkContextStore()
const resultsStore = useResultsStore()
const {
  planOptions,
  plansLoading,
  selectedPlanId,
  fetchPlans,
  clearBinding,
  createPlan,
  goToAps,
  onPlanSelectChange,
  syncSelectedFromStore,
} = usePlanBinding()

async function applyOrchestratorSideEffects(data) {
  const active = data?.artifacts?.active_plan
  if (active?.plan_id) {
    workStore.setFromPlan({
      planId: active.plan_id,
      planName: active.plan_name || '',
      jobs: Array.isArray(active.jobs) ? active.jobs : [],
      source: 'database',
    })
    selectedPlanId.value = active.plan_id
  }

  const exec = data?.production_execution || data?.artifacts?.production_execution
  if (exec?.plan_id && (exec.status === 'running' || exec.status === 'paused')) {
    workStore.setFromPlan({
      planId: exec.plan_id,
      planName: exec.plan_name || workStore.planName,
      jobs: Array.isArray(exec.jobs_snapshot) ? exec.jobs_snapshot : workStore.customJobs,
      source: 'database',
    })
    if (exec.plan_id) selectedPlanId.value = exec.plan_id
  }

  if (data?.agent_id === 'events' && data?.status !== 'pending_confirm') {
    const { applied } = applyMesEventArtifactsToStore(data, resultsStore)
    if (applied && data?.ui_action?.path === '/') {
      ElMessage.success({
        message: data.ui_action.hint || '异常重排完成，可在生产看板查看甘特对比',
        duration: 3500,
      })
      router.push('/')
      return
    }
  }

  const sid = data.session_id || sessionId.value
  const hydrated = await hydrateFromOrchestratorDone(data, sid, resultsStore, workStore)
  const hasResults = hydrated || isValidScheduleResults(resultsStore.results)

  if (data.schedule_saved_to_plan_id) {
    ElMessage.success('排程与工单已更新到当前计划')
  }

  const wantsReports =
    data?.agent_id === 'scheduling' &&
    data?.status === 'success' &&
    (data?.ui_action?.path === '/reports' || hasResults)

  if (wantsReports && hasResults) {
    ElMessage.success({
      message: '排程完成，正在打开分析报表…',
      duration: 2500,
    })
    router.push('/reports')
    return
  }

  if (wantsReports && !hasResults) {
    ElMessage.warning('排程已完成，但结果未能加载到报表，请从数据中心打开该计划的「分析报表」')
  }

  const nav = data?.ui_action
  if (nav?.type === 'navigate' && nav.path && nav.path !== '/reports') {
    if (nav.path === '/aps' && active) {
      goToAps({
        id: active.plan_id,
        plan_name: active.plan_name,
        jobs: active.jobs || [],
      })
    } else {
      router.push(nav.path)
    }
  }
}

const TracePanel = defineComponent({
  name: 'TracePanel',
  props: {
    trace: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    hint: { type: String, default: '' },
  },
  setup(props) {
    const plannerLabel = (p) => {
      const map = {
        llm: 'GLM',
        rule: '规则',
        rule_fallback: '规则回退',
        explicit: '手动',
        events_collab: '固定编排',
        kitting_collab: '齐套编排',
        commitment_collab: '交期编排',
        whatif_collab: '方案对比',
        plans_collab: '计划管理',
        planning_collab: '协同排产',
      }
      return map[p] || p || '—'
    }
    return () => {
      if (!props.trace?.length && props.loading) {
        return h('div', { class: 'trace-empty' }, props.hint || '正在连接编排器…')
      }
      return h(
        'div',
        { class: 'trace-list' },
        (props.trace || []).map((block, bi) =>
          h('div', { class: 'trace-block', key: bi }, [
            h('div', { class: 'trace-head' }, [
              h('span', { class: 'trace-title' }, block.title || block.phase),
              block.planner
                ? h(ElTag, { size: 'small', type: 'info', effect: 'plain' }, () => plannerLabel(block.planner))
                : null,
            ]),
            ...(block.lines || []).map((line, li) => h('div', { class: 'trace-line', key: li }, line)),
            block.steps?.length && block.steps[0]?.tool
              ? h(
                  'ul',
                  { class: 'trace-steps' },
                  block.steps.map((s, si) =>
                    h('li', { key: si }, `${s.step_id || si + 1}. ${s.tool}${s.status ? ` → ${s.status}` : ''}`)
                  )
                )
              : null,
          ])
        )
      )
    }
  },
})

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const sessionId = ref('')
const intentOverride = ref('')
const scrollRef = ref(null)
const llmStatus = ref({ enabled: false })

const persistVisible = ref(false)
const persistPreview = ref(null)
const persistToken = ref('')
const persistSummary = ref('')
const persistExpires = ref('')

const examples = [
  '新建计划a',
  '加载计划 演示计划',
  '列出计划',
  '3号机坏了4小时，帮我重排',
  '插单急单，优先级100',
  '工单A交期改为50',
]

async function onCreatePlan() {
  const r = await createPlan('', { navigateAps: true })
  if (r.ok) {
    messages.value.push({ role: 'assistant', text: r.reply })
    await scrollBottom()
  }
}

function buildRequestBody(text) {
  const context = {}
  if (sessionId.value) context.session_id = sessionId.value
  if (workStore.planId) context.plan_id = workStore.planId
  if (workStore.customJobs?.length) context.custom_data = workStore.customJobs
  const body = { message: text, context, params: {} }
  if (intentOverride.value) body.intent = intentOverride.value
  return body
}

function warnIfNoJobsForSchedule(text) {
  const t = (text || '').trim()
  if (!t) return true
  const scheduleLike = /排产|排程|调度|edd|spt|交期优先|算法/.test(t)
  const eventLike = /插单|故障|坏了|改交期|重排|异常|急单|停机/.test(t)
  if (!scheduleLike && !eventLike) return true
  if (workStore.hasJobs || workStore.planId) return true
  if (eventLike) {
    ElMessage.warning('异常重排需绑定计划工单；若 MES 已在生产看板执行，可说「3号机坏了4小时」等')
  } else {
    ElMessage.warning('请先新建/选择计划并添加工单，或在排程中心编辑工单后再排产')
  }
  return false
}

function friendlyError(err) {
  if (!err) return ''
  if (String(err).includes('base_jobs is empty')) {
    return '缺少基准工单：请在上方选择/新建计划，或在排程中心编辑工单后再试'
  }
  return String(err)
}

function newSession() {
  sessionId.value = ''
  messages.value.push({ role: 'system', text: '已开始新会话。' })
}

async function scrollBottom() {
  await nextTick()
  const el = scrollRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function applyStreamEvent(msg, thinkingIdx) {
  const cur = messages.value[thinkingIdx]
  let trace = [...(cur.trace || [])]

  if (msg.event === 'status') {
    messages.value[thinkingIdx] = { ...cur, role: 'thinking', statusText: msg.text, trace }
    return null
  }

  if (msg.event === 'trace_block') {
    const pi = trace.findIndex((b) => b.phase === msg.block?.phase)
    if (pi >= 0) trace[pi] = msg.block
    else trace.push(msg.block)
    messages.value[thinkingIdx] = { ...cur, role: 'thinking', trace }
    return null
  }

  if (msg.event === 'trace_execute_line') {
    let ex = trace.find((b) => b.phase === 'execute')
    if (!ex) {
      ex = { phase: 'execute', title: '④ 执行 Tool 链', lines: [], planner: null }
      trace.push(ex)
    }
    const lines = [...(ex.lines || [])]
    if (msg.replace_running && lines.length && String(lines[lines.length - 1]).includes('执行中')) {
      lines.pop()
    }
    lines.push(msg.line)
    trace = trace.map((b) => (b.phase === 'execute' ? { ...b, lines } : b))
    messages.value[thinkingIdx] = { ...cur, role: 'thinking', trace }
    return null
  }

  if (msg.event === 'error') {
    throw new Error(msg.detail || '执行失败')
  }

  if (msg.event === 'done') {
    return msg.data
  }

  return null
}

async function send() {
  const text = inputText.value?.trim()
  if (!text || loading.value) return
  if (!warnIfNoJobsForSchedule(text)) return
  messages.value.push({ role: 'user', text })
  inputText.value = ''

  loading.value = true
  const thinkingIdx = messages.value.length
  messages.value.push({ role: 'thinking', trace: [], statusText: '思考中…' })
  await scrollBottom()
  const body = buildRequestBody(text)
  try {
    let data = null
    await streamOrchestrator(body, (msg) => {
      const done = applyStreamEvent(msg, thinkingIdx)
      if (done) data = done
      scrollBottom()
    })
    if (!data) throw new Error('未收到执行结果')
    await applyOrchestratorSideEffects(data)
    await fetchPlans()
    if (data.session_id) sessionId.value = data.session_id
    messages.value[thinkingIdx] = {
      role: 'trace',
      trace: data.execution_trace || messages.value[thinkingIdx]?.trace || [],
      agent_id: data.agent_id,
      statusText: '',
    }
    const errZh = friendlyError(data.error)
    const hasSchedule = !!scheduleResultsFromArtifacts(data?.artifacts) || !!resultsStore.results
    messages.value.push({
      role: 'assistant',
      text: data.summary_zh || errZh || '执行完成',
      agent_id: data.agent_id || data.agent,
      artifacts: data.artifacts || null,
      pending_confirm: data.status === 'pending_confirm' ? data.pending_action : null,
      show_reports: hasSchedule && data?.agent_id === 'scheduling',
    })
    if (data.status === 'failed' || data.error) ElMessage.error(errZh || data.error)
    else if (data.status === 'pending_confirm') {
      ElMessage.info(data.pending_action?.preview?.has_existing_schedule ? '请确认是否覆盖已有排程' : '请确认是否落库')
      if (data.pending_action) openConfirm(data.pending_action)
    } else if (data.status === 'out_of_scope') {
      ElMessage.info('该问题不在六个业务 Agent 范围内，请按下方说明前往对应页面')
    } else if (data.status === 'need_input') {
      ElMessage.info('请按助手提示补充信息后继续发送')
    }
  } catch (e) {
    messages.value.splice(thinkingIdx, 1)
    const detail = e?.response?.data?.detail
    const errText = typeof detail === 'string' ? friendlyError(detail) : e?.message || String(e)
    messages.value.push({ role: 'assistant', text: `请求失败：${errText}` })
    ElMessage.error(errText)
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

function openConfirm(pending) {
  persistToken.value = pending?.confirm_token || ''
  persistPreview.value = pending?.preview || null
  persistSummary.value = pending?.summary_zh || ''
  persistExpires.value = pending?.expires_at || ''
  persistVisible.value = true
}

async function onPersistConfirmed(data) {
  persistVisible.value = false
  const planId = data?.plan_id || persistPreview.value?.plan_id
  if (planId) {
    await fetchPlanScheduleIntoStore(planId, resultsStore)
    workStore.setFromPlan({
      planId,
      planName: persistPreview.value?.plan_name || workStore.planName,
      jobs: resultsStore.currentPlanInput || workStore.customJobs,
      source: 'database',
    })
  }
  messages.value.push({ role: 'system', text: '已确认落库，计划排程与工单已更新。' })
  ElMessage.success('落库成功')
}

onMounted(async () => {
  syncSelectedFromStore()
  fetchPlans()
  try {
    const { data } = await api.get('/api/llm/status')
    llmStatus.value = data
  } catch {
    /* ignore */
  }
})

defineExpose({ send, newSession })
</script>

<style scoped>
.chat-panel { display: flex; flex-direction: column; height: 100%; min-height: 320px; }
.chat-panel.compact { min-height: 0; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.title { font-weight: 600; font-size: 15px; }
.head-tags { display: flex; gap: 6px; }
.plan-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}
.plan-select { flex: 1; min-width: 160px; }
.ctx-alert { margin-bottom: 10px; }
.opts { gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.row { display: flex; align-items: center; }
.mini-opts { margin-bottom: 8px; }
.examples { margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 10px;
  min-height: 200px;
  max-height: 48vh;
}
.messages.compact { max-height: 42vh; min-height: 160px; }
.empty-hint { color: #909399; text-align: center; padding: 24px 8px; font-size: 13px; }
.msg { display: flex; margin-bottom: 10px; }
.msg.user { justify-content: flex-end; }
.msg.assistant, .msg.system, .msg.thinking { justify-content: flex-start; }
.bubble { max-width: 96%; padding: 8px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.msg.user .bubble { background: #409eff; color: #fff; }
.msg.assistant .bubble { background: #fff; border: 1px solid #e4e7ed; }
.bubble-trace { background: #fafafa; border: 1px dashed #c0c4cc; max-width: 100%; width: 100%; }
.thinking-title { display: flex; align-items: center; gap: 6px; font-weight: 600; margin-bottom: 6px; }
.composer { display: flex; gap: 8px; align-items: flex-end; }
.composer .el-textarea { flex: 1; }
.system { color: #606266; font-size: 12px; }
:deep(.trace-block) { margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #ebeef5; }
:deep(.trace-title) { font-weight: 600; color: #409eff; font-size: 12px; }
:deep(.trace-line) { font-size: 12px; color: #606266; padding-left: 6px; }
:deep(.trace-steps) { margin: 4px 0 0 16px; font-size: 12px; }
</style>
