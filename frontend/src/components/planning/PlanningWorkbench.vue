<template>
  <div class="planning-workbench">
    <div class="ops-title">排产策略工作台</div>
    <el-alert
      v-if="disabled"
      type="warning"
      :closable="false"
      title="请先配置工单（自定义/数据库模式）后再运行"
      class="wb-alert"
    />

    <el-tabs v-model="activeTab" class="wb-tabs">
      <el-tab-pane label="模板" name="template">
        <ModeTemplatePanel :disabled="disabled || running" @run="onTemplateRun" />
      </el-tab-pane>
      <el-tab-pane label="参数" name="parameter">
        <ModeParameterPanel
          :disabled="disabled || running"
          :job-ids="jobIds"
          @validate="onParameterValidate"
          @run="onParameterRun"
        />
      </el-tab-pane>
      <el-tab-pane label="AI策略" name="ai">
        <ModeAiPanel
          :disabled="disabled || running"
          :analyses="analyses"
          @run="onAiRun"
        />
      </el-tab-pane>
    </el-tabs>

    <el-alert
      v-if="validateErrors.length"
      type="error"
      :closable="false"
      class="wb-alert"
      :title="`策略校验失败（${validateErrors.length} 项）`"
    >
      <ul class="wb-error-list">
        <li v-for="(err, i) in validateErrors" :key="i">{{ formatError(err) }}</li>
      </ul>
    </el-alert>

    <div v-if="runId && runStatus === 'WAITING_APPROVAL'" class="wb-hitl">
      <div class="ops-label">策略确认（HITL）</div>
      <div v-if="runId" class="ops-tip">Run ID：{{ runId }} · {{ runStatus }}</div>
      <el-collapse v-if="strategyDraftJson" v-model="draftOpen" class="wb-draft">
        <el-collapse-item title="Strategy JSON（编辑后批准可改）" name="draft">
          <el-input
            v-model="strategyDraftJson"
            type="textarea"
            :rows="8"
            class="strategy-json-input"
          />
        </el-collapse-item>
      </el-collapse>
      <StrategyHitlBar
        :run-id="runId"
        :loading="hitlLoading"
        @approve="onApprove"
        @reject="onReject"
        @edit-approve="onEditApprove"
      />
    </div>

    <div v-else-if="runId" class="ops-tip wb-run-meta">
      Run ID：{{ runId }} · {{ runStatus || '—' }}
      <el-tag v-if="running" size="small" type="info" class="wb-running-tag">运行中</el-tag>
    </div>

    <div v-if="packageView" class="wb-result">
      <div class="ops-label">Package 结果</div>
      <PackageResultPanel
        :result="packageView"
        :sending="sendingToSim"
        @send-to-sim="onSendToSim"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { extractPackageView } from './packageExtract.js'
import ModeTemplatePanel from './ModeTemplatePanel.vue'
import ModeParameterPanel from './ModeParameterPanel.vue'
import ModeAiPanel from './ModeAiPanel.vue'
import StrategyHitlBar from './StrategyHitlBar.vue'
import PackageResultPanel from './PackageResultPanel.vue'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  jobIds: {
    type: Array,
    default: () => [],
  },
  jobs: {
    type: Array,
    default: () => [],
  },
  machines: {
    type: Array,
    default: () => [],
  },
})

const router = useRouter()
const activeTab = ref('template')
const runId = ref('')
const runStatus = ref('')
const hitlLoading = ref(false)
const running = ref(false)
const sendingToSim = ref(false)
const packageView = ref(null)
const strategyDraftJson = ref('')
const analyses = ref(null)
const validateErrors = ref([])
const draftOpen = ref(['draft'])
const lastRunPayload = ref(null)

function formatError(err) {
  if (err == null) return '—'
  if (typeof err === 'string') return err
  if (err.message) return err.message
  try {
    return JSON.stringify(err)
  } catch {
    return String(err)
  }
}

function requireJobs() {
  if (props.disabled || !props.jobs?.length) {
    ElMessage.warning('请先配置工单数据（自定义/数据库模式）')
    return false
  }
  return true
}

function applyRunResponse(data, { successMsg } = {}) {
  if (!data) return
  lastRunPayload.value = data
  runId.value = data.run_id || runId.value
  runStatus.value = data.status || ''
  if (data.artifacts) {
    analyses.value = {
      order_analysis: data.artifacts.order_analysis || null,
      constraint_analysis: data.artifacts.constraint_analysis || null,
      resource_analysis: data.artifacts.resource_analysis || null,
    }
  }
  if (data.strategy_draft) {
    strategyDraftJson.value = JSON.stringify(data.strategy_draft, null, 2)
  }
  if (Array.isArray(data.validation_errors) && data.validation_errors.length) {
    validateErrors.value = data.validation_errors
  }
  if (data.status === 'COMPLETED') {
    packageView.value = extractPackageView(data)
    if (successMsg) ElMessage.success(successMsg)
  } else if (data.status === 'WAITING_APPROVAL') {
    packageView.value = null
    ElMessage.info('策略已生成，请确认后批准')
  } else if (data.status === 'CANCELLED') {
    packageView.value = null
  } else if (data.status === 'FAILED') {
    packageView.value = null
    ElMessage.error(data.error || '排产运行失败')
  }
}

async function onSendToSim() {
  if (!packageView.value?.hasRecommendation) {
    ElMessage.warning('请先完成排产并获得推荐方案')
    return
  }
  sendingToSim.value = true
  try {
    const fromRun = lastRunPayload.value?.candidate_schedules
    const fromView = packageView.value.candidates
    const pickWithGantt = (list) =>
      (Array.isArray(list) ? list : []).filter((c) => Array.isArray(c?.gantt_data) && c.gantt_data.length)
    const candidates =
      (pickWithGantt(fromRun).length ? fromRun : null) ||
      (pickWithGantt(fromView).length ? fromView : null) ||
      fromRun ||
      fromView ||
      []
    const payload = {
      run_id: runId.value || undefined,
      package: lastRunPayload.value?.package || {
        recommended_schedule_id: packageView.value.recommended_schedule_id,
      },
      candidates,
      jobs: props.jobs,
      persist_plan: true,
      plan_name: 'Package 推荐计划',
      sim_speed: 60,
    }
    if (!pickWithGantt(candidates).length && !payload.run_id) {
      ElMessage.error('推荐方案缺少甘特数据，请重新排产后再送入仿真')
      return
    }
    await api.post('/api/execution/start_from_package', payload)
    ElMessage.success('已送入执行仿真')
    await router.push({ path: '/dashboard', query: { from_package: '1' } })
  } catch (e) {
    ElMessage.error(`送入仿真失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    sendingToSim.value = false
  }
}

async function onTemplateRun(payload) {
  if (!requireJobs()) return
  running.value = true
  packageView.value = null
  validateErrors.value = []
  try {
    const { data } = await api.post('/api/planning/run', {
      preset_id: payload.preset_id,
      jobs: props.jobs,
      machines: props.machines,
      skip_strategy_hitl: payload.skip_strategy_hitl !== false,
      user_goal: payload.user_goal || '',
    })
    applyRunResponse(data, { successMsg: '模板排产完成' })
  } catch (e) {
    ElMessage.error(`运行失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    running.value = false
  }
}

async function onParameterValidate(payload) {
  if (!requireJobs()) return
  validateErrors.value = []
  try {
    const { data } = await api.post('/api/planning/strategy/validate', {
      strategy: payload.strategy,
      jobs: props.jobs,
      machines: props.machines,
    })
    if (data?.ok === false || data?.valid === false || data?.validation_errors?.length) {
      validateErrors.value = data.validation_errors || data.errors || ['校验未通过']
      ElMessage.warning(`策略校验未通过（${validateErrors.value.length} 项）`)
      return
    }
    validateErrors.value = []
    ElMessage.success('策略校验通过')
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (Array.isArray(detail)) {
      validateErrors.value = detail
    } else if (detail?.validation_errors) {
      validateErrors.value = detail.validation_errors
    } else {
      validateErrors.value = [detail || e?.message || String(e)]
    }
    ElMessage.error(`校验失败: ${formatError(validateErrors.value[0])}`)
  }
}

async function onParameterRun(payload) {
  if (!requireJobs()) return
  running.value = true
  packageView.value = null
  validateErrors.value = []
  try {
    const { data } = await api.post('/api/planning/run', {
      strategy: payload.strategy,
      jobs: props.jobs,
      machines: props.machines,
      skip_strategy_hitl: false,
      user_goal: '',
    })
    applyRunResponse(data, { successMsg: '参数排产完成' })
  } catch (e) {
    ElMessage.error(`运行失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    running.value = false
  }
}

async function onAiRun(payload) {
  if (!requireJobs()) return
  running.value = true
  packageView.value = null
  analyses.value = null
  validateErrors.value = []
  try {
    const { data } = await api.post('/api/planning/collab/run', {
      user_goal: payload.user_goal,
      jobs: props.jobs,
      machines: props.machines,
      skip_strategy_hitl: false,
    })
    applyRunResponse(data, { successMsg: 'AI 协同排产完成' })
  } catch (e) {
    ElMessage.error(`运行失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    running.value = false
  }
}

async function onApprove() {
  if (!runId.value) return
  hitlLoading.value = true
  try {
    const { data } = await api.post(`/api/planning/runs/${runId.value}/strategy/approve`, {})
    applyRunResponse(data, { successMsg: '策略已批准，排产完成' })
  } catch (e) {
    ElMessage.error(`批准失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    hitlLoading.value = false
  }
}

async function onReject() {
  if (!runId.value) return
  hitlLoading.value = true
  try {
    const { data } = await api.post(`/api/planning/runs/${runId.value}/strategy/reject`, {
      reason: '用户拒绝',
    })
    applyRunResponse(data)
    ElMessage.info('已拒绝策略')
  } catch (e) {
    ElMessage.error(`拒绝失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    hitlLoading.value = false
  }
}

async function onEditApprove() {
  if (!runId.value) return
  if (!strategyDraftJson.value?.trim()) {
    return ElMessage.warning('请先填写 Strategy JSON')
  }
  let strategy
  try {
    strategy = JSON.parse(strategyDraftJson.value)
  } catch {
    return ElMessage.error('Strategy JSON 格式无效')
  }
  hitlLoading.value = true
  try {
    const { data } = await api.post(
      `/api/planning/runs/${runId.value}/strategy/edit_and_approve`,
      {
        strategy,
        jobs: props.jobs,
        machines: props.machines,
      },
    )
    applyRunResponse(data, { successMsg: '已编辑并批准，排产完成' })
  } catch (e) {
    ElMessage.error(`编辑批准失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    hitlLoading.value = false
  }
}
</script>

<style scoped>
.planning-workbench {
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #f6ffed;
}

.ops-title {
  font-size: 13px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 10px;
}

.ops-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
  font-weight: 600;
}

.ops-tip {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.3;
}

.wb-tabs {
  margin-bottom: 8px;
}

.wb-alert {
  margin-bottom: 8px;
}

.wb-error-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
}

.wb-hitl {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #dcdfe6;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wb-draft {
  border: none;
}

.wb-draft :deep(.el-collapse-item__header) {
  font-size: 12px;
  height: 36px;
}

.strategy-json-input :deep(textarea) {
  font-family: Consolas, Monaco, monospace;
  font-size: 11px;
}

.wb-run-meta {
  margin-top: 8px;
}

.wb-running-tag {
  margin-left: 6px;
}

.wb-result {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
}
</style>
