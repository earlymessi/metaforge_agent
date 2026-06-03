<template>
  <el-card shadow="never">
    <template #header>
      <div class="row">
        <div class="h">报表分析</div>
        <div class="spacer" />
        <el-tag v-if="store.lastStrategyName" type="info" effect="plain">
          排程策略：{{ store.lastStrategyName }}（排名按综合评分，权重已在排程时生效）
        </el-tag>
        <el-tag v-if="energyMetricMissing" type="warning" effect="plain">
          能耗成本未计入：请在「能耗管控调度」配置机台功率与分时电价后重新排程
        </el-tag>
        <el-segmented v-model="activeTab" :options="tabs" />
        <el-select v-model="sortKey" style="width: 240px">
          <el-option
            v-for="(meta, key) in SORT_METRICS"
            :key="key"
            :label="meta.label"
            :value="key"
          />
        </el-select>
        <el-button
          v-if="materialDialogReport"
          type="warning"
          plain
          @click="materialCheckDialogVisible = true"
        >
          物料预检明细
        </el-button>
        <el-button
          v-if="store.currentPlanId || workContext.planId"
          type="info"
          plain
          :loading="impactLoading"
          @click="openImpactAssessment"
        >
          查看影响评估
        </el-button>
        <el-button type="success" :disabled="!selectedAlgoId" @click="saveResultToDB">保存结果到DB</el-button>
        <el-button type="primary" plain @click="openGlobalAssistant">智能助手</el-button>
      </div>
    </template>

    <el-empty v-if="!hasReportData" description="暂无分析数据，请先去排程中心运行一次" />

    <el-alert
      v-else
      type="info"
      :closable="false"
      show-icon
      class="mb12"
      title="插单 / 设备故障 / 改交期等异常重排已移至「生产看板」，请先开始 MES 执行后再操作。"
    >
      <router-link to="/dashboard">前往生产看板 →</router-link>
    </el-alert>

    <div v-if="hasReportData">
      <el-alert
        v-if="materialReportForAlgo && materialAlertStatsForAlgo.total > 0"
        :type="materialAlertStatsForAlgo.hasShortage ? 'error' : 'warning'"
        show-icon
        :closable="false"
        title="当前方案存在缺料预警"
        style="margin-bottom: 12px"
      >
        <template #default>
          <div class="alert-row">
            <span>{{ materialAlertSummaryText }}</span>
            <el-button type="warning" link @click="materialCheckDialogVisible = true">查看明细</el-button>
          </div>
        </template>
      </el-alert>
      <el-table v-show="activeTab === 'overview'" :data="sorted" stripe @row-click="onRowClick">
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="name" label="策略" min-width="160" />
        <el-table-column prop="best_score" label="完工时间" width="110" align="right" />
        <el-table-column label="综合评分" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.score) }}</template>
        </el-table-column>
        <el-table-column label="交期违约(加权)" width="140" align="right">
          <template #default="{ row }">{{ fmt(row?.metrics?.weighted_tardiness_total) }}</template>
        </el-table-column>
        <el-table-column label="能耗成本" width="120" align="right">
          <template #default="{ row }">{{ fmt(row?.metrics?.energy_cost) }}</template>
        </el-table-column>
        <el-table-column label="负载CV" width="110" align="right">
          <template #default="{ row }">{{ fmt(row?.metrics?.machine_busy_cv, 4) }}</template>
        </el-table-column>
        <el-table-column prop="runtime_sec" label="耗时(s)" width="100" align="right" />
      </el-table>

      <div v-show="activeTab === 'gantt'" class="chart-wrap">
        <div class="row" style="margin-bottom: 8px">
          <span class="small-title">甘特图算法选择</span>
          <el-select v-model="selectedAlgoId" style="width: 320px" @change="renderGantt">
            <el-option
              v-for="r in sorted"
              :key="r.id"
              :label="`${r.name} (makespan=${r.best_score}, score=${fmt(r.score)})`"
              :value="r.id"
            />
          </el-select>
          <el-tag v-if="materialAlertStatsForAlgo.total > 0" type="warning" effect="dark" size="small">
            缺料预警 {{ materialAlertStatsForAlgo.total }}
          </el-tag>
        </div>
        <div ref="ganttRef" class="chart"></div>
      </div>

      <div v-show="activeTab === 'convergence'" class="chart-wrap">
        <div ref="convRef" class="chart"></div>
      </div>

      <div v-show="activeTab === 'delivery'">
        <div class="row" style="margin-bottom: 8px">
          <span class="small-title">交期承诺基于算法</span>
          <el-select v-model="selectedAlgoId" style="width: 320px">
            <el-option
              v-for="r in sorted"
              :key="r.id"
              :label="`${r.name} (makespan=${r.best_score})`"
              :value="r.id"
            />
          </el-select>
        </div>
        <el-table :data="deliveryRows" stripe empty-text="暂无交期预测数据">
          <el-table-column prop="job_name" label="工单" min-width="140" />
          <el-table-column label="交期" width="100" align="right">
            <template #default="{ row }">{{ row.due_date == null ? '自动' : fmt(row.due_date) }}</template>
          </el-table-column>
          <el-table-column label="预计完工" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.predicted_completion) }}</template>
          </el-table-column>
          <el-table-column label="延期" width="90" align="right">
            <template #default="{ row }">{{ fmt(row.tardiness) }}</template>
          </el-table-column>
          <el-table-column label="风险" width="100">
            <template #default="{ row }">
              <el-tag :type="riskTagType(row.risk_level)" size="small">{{ riskLabel(row.risk_level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="risk_reason" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column prop="commitment_text" label="对外承诺口径" min-width="200" show-overflow-tooltip />
        </el-table>
      </div>

      <div v-show="activeTab === 'bottleneck'">
        <div class="row" style="margin-bottom: 8px">
          <span class="small-title">瓶颈分析基于算法</span>
          <el-select v-model="selectedAlgoId" style="width: 320px">
            <el-option
              v-for="r in sorted"
              :key="r.id"
              :label="`${r.name} (makespan=${r.best_score})`"
              :value="r.id"
            />
          </el-select>
        </div>
        <el-alert
          v-if="bottleneckReport?.bottleneck_machine_id != null"
          type="warning"
          :closable="false"
          show-icon
          :title="`瓶颈机台：Machine-${bottleneckReport.bottleneck_machine_id}（忙碌时间最高）`"
          style="margin-bottom: 12px"
        />
        <el-row :gutter="12">
          <el-col :md="12" :span="24">
            <div class="small-title" style="margin-bottom: 8px">机台负荷</div>
            <el-table :data="bottleneckMachines" stripe size="small" empty-text="暂无数据">
              <el-table-column prop="machine_id" label="机台" width="90">
                <template #default="{ row }">M{{ row.machine_id }}</template>
              </el-table-column>
              <el-table-column prop="busy_time" label="忙碌时间" width="110" align="right">
                <template #default="{ row }">{{ fmt(row.busy_time) }}</template>
              </el-table-column>
              <el-table-column prop="utilization" label="利用率" width="100" align="right">
                <template #default="{ row }">{{ fmt(row.utilization * 100, 1) }}%</template>
              </el-table-column>
            </el-table>
          </el-col>
          <el-col :md="12" :span="24">
            <div class="small-title" style="margin-bottom: 8px">延期贡献工单</div>
            <el-table :data="bottleneckTardy" stripe size="small" empty-text="无延期或均未设交期">
              <el-table-column prop="job_name" label="工单" min-width="120" />
              <el-table-column prop="tardiness" label="延期量" width="100" align="right">
                <template #default="{ row }">{{ fmt(row.tardiness) }}</template>
              </el-table-column>
            </el-table>
          </el-col>
        </el-row>
      </div>
    </div>
  </el-card>

  <el-dialog v-model="impactDialogVisible" title="重排影响评估" width="1180px" top="4vh">
    <el-empty v-if="!impactIr" description="暂无影响评估数据" />
    <template v-else>
      <el-descriptions :column="4" border size="small" style="margin-bottom: 12px">
        <el-descriptions-item label="事件">
          {{
            impactIr.event_type === 'machine_breakdown'
              ? '设备故障'
              : impactIr.event_type === 'due_date_change'
                ? '改交期'
                : impactIr.event_type === 'insert_order'
                  ? '插单重排'
                  : impactIr.event_type || '-'
          }}
        </el-descriptions-item>
        <el-descriptions-item label="模式">{{ impactIr.mode || '-' }}</el-descriptions-item>
        <el-descriptions-item v-if="impactIr.machine_id != null" label="故障机台">
          {{ impactIr.machine_label_zh || `M${impactIr.machine_id}` }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="impactIr.breakdown_start != null"
          label="故障窗口"
        >
          {{ fmt(impactIr.breakdown_start) }}–{{ fmt(impactIr.breakdown_end) }} h
        </el-descriptions-item>
        <el-descriptions-item label="冻结时间">{{ fmt(impactIr.freeze_time) }}</el-descriptions-item>
        <el-descriptions-item label="受影响工单">{{ impactIr.affected_jobs }}</el-descriptions-item>
        <el-descriptions-item label="最大延期">{{ fmt(impactIr.max_delay) }}</el-descriptions-item>
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
            <p v-if="impactIr?.improvement_vs_r1" class="hint" style="margin-top: 8px">
              相对不重排：完工 {{ fmt(impactIr.improvement_vs_r1.makespan_delta) }} h，
              拖期 {{ fmt(impactIr.improvement_vs_r1.tardiness_delta) }}
            </p>
          </template>
          <el-alert
            v-else
            type="warning"
            :closable="false"
            show-icon
            title="甘特数据未加载完整"
            description="请重启后端并强刷页面后重新执行重排。"
          />
        </el-tab-pane>
        <el-tab-pane v-if="recoveryScenarioRows.length" label="R0/R1/R2对比" name="recovery">
          <el-table :data="recoveryScenarioRows" stripe size="small">
            <el-table-column prop="label" label="场景" width="140" />
            <el-table-column prop="makespan" label="完工时间" width="120" align="right" />
            <el-table-column prop="weighted_tardiness_total" label="加权拖期" width="120" align="right" />
          </el-table>
          <p v-if="impactIr?.improvement_vs_r1" class="hint" style="margin-top: 8px">
            相对不重排(R1) makespan 变化：{{ fmt(impactIr.improvement_vs_r1.makespan_delta) }} h
          </p>
        </el-tab-pane>
        <el-tab-pane label="完工变化" name="delay">
          <el-table :data="impactRows" stripe max-height="360">
            <el-table-column prop="job_name" label="工单" min-width="160" />
            <el-table-column prop="old_completion" label="原完工" width="120" align="right">
              <template #default="{ row }">{{ fmt(row.old_completion) }}</template>
            </el-table-column>
            <el-table-column prop="new_completion" label="新完工" width="120" align="right">
              <template #default="{ row }">{{ fmt(row.new_completion) }}</template>
            </el-table-column>
            <el-table-column prop="delta" label="变化量(+)延期" width="130" align="right">
              <template #default="{ row }">
                <span :style="{ color: row.delta > 0 ? '#f56c6c' : '#67c23a', fontWeight: 700 }">
                  {{ fmt(row.delta) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="承诺变化" name="commitment">
          <el-table :data="commitmentRows" stripe max-height="360" empty-text="无承诺变化记录">
            <el-table-column prop="job_name" label="工单" min-width="140" />
            <el-table-column label="原风险" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.old_risk" :type="riskTagType(row.old_risk)" size="small">{{ riskLabel(row.old_risk) }}</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="新风险" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.new_risk" :type="riskTagType(row.new_risk)" size="small">{{ riskLabel(row.new_risk) }}</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="预计完工变化" width="130" align="right">
              <template #default="{ row }">{{ fmt(row.delta) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </template>
    <template #footer>
      <el-button @click="impactDialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <MaterialCheckDialog v-model="materialCheckDialogVisible" :report="materialDialogReport" />

</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'
import { useWorkContextStore } from '../stores/useWorkContextStore'
import {
  consumeReportsScheduleFromSession,
  hydrateResultsStoreFromPlan,
  isValidScheduleResults,
  loadImpactAssessmentForPlan,
} from '../utils/planScheduleSync'
import MaterialCheckDialog from '../components/MaterialCheckDialog.vue'
import ImpactDualGantt from '../components/ImpactDualGantt.vue'
import {
  effectiveR1Gantt,
  effectiveR2Gantt,
  firstImpactTab,
  hasDualImpactGantt,
  isDualGanttEvent,
} from '../utils/impactReport'
import { buildShortageMarkPoints, shortageJobIdSet } from '../utils/ganttMaterial.js'
import { materialAlertStats } from '../utils/materialAlerts'
import { useAssistantStore } from '../stores/useAssistantStore'
import { SORT_METRICS, DEFAULT_REPORT_SORT_KEY } from '../utils/strategySort'

const route = useRoute()
const store = useResultsStore()
const workContext = useWorkContextStore()
const assistantStore = useAssistantStore()
const hasReportData = computed(() => isValidScheduleResults(store.results))
const sortKey = ref(DEFAULT_REPORT_SORT_KEY)
const activeTab = ref('overview')
const tabs = [
  { label: 'KPI 概览', value: 'overview' },
  { label: '甘特图', value: 'gantt' },
  { label: '收敛曲线', value: 'convergence' },
  { label: '交期承诺', value: 'delivery' },
  { label: '瓶颈分析', value: 'bottleneck' },
]
const impactTab = ref('delay')
const selectedAlgoId = ref('')
const impactDialogVisible = ref(false)
const impactLoading = ref(false)
const materialCheckDialogVisible = ref(false)

async function openImpactAssessment() {
  const planId = store.currentPlanId || workContext.planId
  if (!planId) {
    ElMessage.warning('请先加载计划')
    return
  }
  impactLoading.value = true
  try {
    const ok = await loadImpactAssessmentForPlan(planId, {}, store)
    if (!ok || !store.activeImpactReport) {
      ElMessage.info('该计划暂无影响评估记录')
      return
    }
    impactDialogVisible.value = true
  } catch (e) {
    ElMessage.error(`加载影响评估失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    impactLoading.value = false
  }
}

const ganttRef = ref(null)
const convRef = ref(null)
let ganttChart = null
let convChart = null
let highlightTimer = null

const CONV_LINE_STYLES = ['solid', 'dashed', 'dotted', [8, 4], [2, 2], [10, 5, 2, 5]]
const CONV_COLORS = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9b59b6', '#16a085', '#e91e63']

const sorted = computed(() => {
  const arr = store.resultsArray.slice()
  const pick = SORT_METRICS[sortKey.value]?.pick || ((r) => r?.[sortKey.value])
  return arr.sort((a, b) => {
    const av = pick(a) ?? Number.POSITIVE_INFINITY
    const bv = pick(b) ?? Number.POSITIVE_INFINITY
    return Number(av) - Number(bv)
  })
})
const energyMetricMissing = computed(() => {
  if (!hasReportData.value) return false
  const arr = store.resultsArray
  if (!arr.length) return false
  return arr.every((r) => r?.metrics?.energy_cost == null)
})
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

const ganttFallbackOpts = computed(() => {
  const ir = impactIr.value
  const sid = ir?.baseline_solver
  const baseFromResults = sid && rescheduleResults.value?.[sid]?.gantt_data
  return {
    baselineGantt:
      (Array.isArray(ir?.r0_gantt) && ir.r0_gantt.length ? ir.r0_gantt : null) || baseFromResults,
    freezeTime: ir?.freeze_time,
    insertJobSnapshot: ir?.insert_job_snapshot,
  }
})

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
  if (impactIr.value?.freeze_time != null) layers.freeze_time = impactIr.value.freeze_time
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

const deliveryRows = computed(() => {
  if (!selectedAlgoId.value || !store.results?.[selectedAlgoId.value]) return []
  return store.results[selectedAlgoId.value].delivery_predictions || []
})
const materialReportForAlgo = computed(() => {
  if (!selectedAlgoId.value || !store.results?.[selectedAlgoId.value]) return null
  return store.results[selectedAlgoId.value].material_report || null
})
const materialDialogReport = computed(() => materialReportForAlgo.value || store.materialCheck || null)
const materialAlertStatsForAlgo = computed(() =>
  materialAlertStats(materialReportForAlgo.value?.simulation),
)
const materialAlertSummaryText = computed(() => {
  const { total, shortageCount, warningCount } = materialAlertStatsForAlgo.value
  if (!total) return ''
  const parts = []
  if (shortageCount) parts.push(`缺料 ${shortageCount} 条`)
  if (warningCount) parts.push(`预警 ${warningCount} 条`)
  return `${parts.join('，')}，请查看明细或调整 BOM/补货`
})
const bottleneckReport = computed(() => {
  if (!selectedAlgoId.value || !store.results?.[selectedAlgoId.value]) return null
  return store.results[selectedAlgoId.value].bottleneck_report || null
})
const bottleneckMachines = computed(() => {
  const rows = bottleneckReport.value?.machines || []
  return rows.slice().sort((a, b) => Number(b.busy_time) - Number(a.busy_time))
})
const bottleneckTardy = computed(() => bottleneckReport.value?.tardiness_contributors || [])

function riskLabel(level) {
  const map = {
    on_time: '按期',
    low: '低风险',
    medium: '中风险',
    high: '高风险',
    critical: '严重',
    unknown: '未设交期',
  }
  return map[level] || level
}

function riskTagType(level) {
  const map = {
    on_time: 'success',
    low: 'success',
    medium: 'warning',
    high: 'danger',
    critical: 'danger',
    unknown: 'info',
  }
  return map[level] || 'info'
}

function fmt(v, digits = 2) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return '-'
  return Number(v).toFixed(digits)
}

function onRowClick(row) {
  selectedAlgoId.value = row.id
}

function ensureDefaultAlgo() {
  if (!selectedAlgoId.value && sorted.value.length > 0) {
    selectedAlgoId.value = sorted.value[0].id
  }
}

function renderConvergence() {
  if (!convRef.value || !store.results) return
  if (convChart) convChart.dispose()
  convChart = echarts.init(convRef.value)

  const entries = Object.values(store.results)
  if (!entries.length) return

  const series = []
  const legends = []
  let maxIter = 10

  entries.forEach((v) => {
    const len = v.history?.length || 0
    if (len > maxIter) maxIter = len
  })

  entries.forEach((val, idx) => {
    const color = CONV_COLORS[idx % CONV_COLORS.length]
    const lineType = CONV_LINE_STYLES[idx % CONV_LINE_STYLES.length]
    legends.push(val.name)

    if (val.history && val.history.length > 0) {
      series.push({
        name: val.name,
        type: 'line',
        showSymbol: false,
        smooth: true,
        z: idx + 1,
        lineStyle: { width: 2, color, type: lineType },
        itemStyle: { color },
        data: val.history.map((y, i) => [i + 1, Number(y)]),
      })
    } else {
      const y = Number(val.best_score ?? 0)
      series.push({
        name: `${val.name}（单次）`,
        type: 'line',
        showSymbol: false,
        z: idx + 1,
        lineStyle: { width: 2, color, type: 'dashed' },
        itemStyle: { color },
        data: [
          [1, y],
          [maxIter, y],
        ],
      })
      legends[legends.length - 1] = `${val.name}（单次）`
    }
  })

  convChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        if (!Array.isArray(params)) return ''
        return params
          .map((p) => `${p.seriesName}: ${p.value?.[1] ?? p.value}`)
          .join('<br/>')
      },
    },
    legend: {
      data: legends,
      bottom: 0,
      type: 'scroll',
      selectedMode: true,
    },
    grid: { left: '3%', right: '3%', bottom: '14%', containLabel: true },
    xAxis: {
      type: 'value',
      name: '迭代次数',
      min: 1,
      max: maxIter,
      splitLine: { show: true },
    },
    yAxis: {
      type: 'value',
      name: 'Makespan',
      scale: true,
      splitLine: { show: true },
    },
    series,
  })
}

function renderGantt() {
  if (!ganttRef.value || !store.results || !selectedAlgoId.value) return
  const data = store.results[selectedAlgoId.value]?.gantt_data || []
  if (ganttChart) ganttChart.dispose()
  ganttChart = echarts.init(ganttRef.value)

  if (!data.length) {
    ganttChart.setOption({ title: { text: '无甘特图数据', left: 'center', top: 'middle' } })
    return
  }

  const machines = [...new Set(data.map((d) => d.machine_id))].sort((a, b) => a - b)
  const jobIds = [...new Set(data.map((d) => d.job_id))].sort((a, b) => a - b)
  const normalColors = ['#305680', '#008b8b', '#4682b4', '#6b8e23', '#5f9ea0', '#708090', '#2e8b57', '#778899', '#483d8b', '#00ced1', '#4169e1']
  const urgentColors = ['#d9001b', '#b03060', '#ff4500', '#8b0000', '#dc143c', '#a52a2a', '#ff6347', '#c71585']

  const renderItem = (params, api) => {
    const idx = api.value(0)
    const start = api.coord([api.value(1), idx])
    const end = api.coord([api.value(2), idx])
    const h = api.size([0, 1])[1] * 0.6
    return {
      type: 'rect',
      shape: echarts.graphic.clipRectByRect(
        { x: start[0], y: start[1] - h / 2, width: end[0] - start[0], height: h },
        { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height },
      ),
      style: { ...api.style(), borderRadius: 2 },
    }
  }

  const highlightSet = new Set((store.highlightJobNames || []).map((n) => String(n).trim()))
  const alerts = materialAlertStatsForAlgo.value.all
  const alertJobs = shortageJobIdSet(alerts)
  const markPoints = buildShortageMarkPoints(data, alerts)

  const seriesList = jobIds.map((jid) => {
    const firstItem = data.find((d) => d.job_id === jid)
    const priority = firstItem ? Number(firstItem.priority || 10) : 10
    const isUrgent = priority > 10
    const jName = (firstItem && firstItem.job_name) ? firstItem.job_name : `工单 ${jid}`
    const displayName = isUrgent ? `🔥 ${jName}` : jName
    const isHighlighted = highlightSet.has(jName) || highlightSet.has(displayName)
    const hasAlert = alertJobs.has(Number(jid))
    const alertLevel = alerts.find((a) => Number(a.job_id) === Number(jid))?.level
    const baseColor = isUrgent ? urgentColors[jid % urgentColors.length] : normalColors[jid % normalColors.length]
    return {
      name: displayName,
      type: 'custom',
      renderItem,
      itemStyle: {
        color: baseColor,
        opacity: isHighlighted ? 1 : 0.9,
        borderColor: isHighlighted
          ? '#ffd700'
          : (hasAlert ? (alertLevel === 'shortage' ? '#f56c6c' : '#e6a23c') : 'transparent'),
        borderWidth: isHighlighted ? 3 : (hasAlert ? 2 : 0),
        shadowBlur: isHighlighted ? 14 : 0,
        shadowColor: isHighlighted ? 'rgba(255, 215, 0, 0.95)' : 'transparent',
      },
      encode: { x: [1, 2], y: 0 },
      data: data
        .filter((d) => d.job_id === jid)
        .map((d) => ({ value: [machines.indexOf(d.machine_id), d.start, d.end, d.job_id, d.machine_id, d.operation_name, d.job_name || `工单 ${d.job_id}`] })),
    }
  })

  if (markPoints.length) {
    seriesList.push({
      name: '缺料预警',
      type: 'scatter',
      symbol: 'pin',
      symbolSize: 24,
      z: 100,
      data: markPoints.map((p) => {
        const alert = alerts.find(
          (a) => Number(a.job_id) === Number(p.job_id) && Number(a.time) === Number(p.time),
        )
        const level = alert?.level || (Number(p.stock_left) < 0 ? 'shortage' : 'warning')
        return {
          value: p.value,
          job_name: p.job_name,
          material_name: p.material_name,
          time: p.time,
          stock_left: p.stock_left,
          safe_level: p.safe_level,
          level,
          itemStyle: { color: level === 'shortage' ? '#f56c6c' : '#e6a23c' },
        }
      }),
      tooltip: {
        formatter: (p) => {
          const d = p.data || {}
          const label = d.level === 'shortage' ? '缺料' : '预警'
          const safeLine =
            d.level === 'warning' && d.safe_level != null
              ? `<br>安全线: ${d.safe_level}`
              : ''
          return `<b>${label}</b><br>工单: ${d.job_name || '-'}<br>物料: ${d.material_name || '-'}<br>时刻: ${d.time ?? '-'}<br>剩余库存: ${d.stock_left ?? '-'}${safeLine}`
        },
      },
    })
  }

  const legendRows = Math.ceil(seriesList.length / 8)
  const bottomSpace = 30 + legendRows * 25

  const layers = store.impactReport?.gantt_layers
  const markAreas = []
  const bw = layers?.breakdown_window || (
    store.impactReport?.breakdown_start != null
      ? {
          machine_id: store.impactReport.machine_id,
          start: store.impactReport.breakdown_start,
          end: store.impactReport.breakdown_end,
        }
      : null
  )
  if (bw && bw.machine_id != null) {
    const yIdx = machines.indexOf(Number(bw.machine_id))
    if (yIdx >= 0) {
      markAreas.push([
        { xAxis: bw.start, yAxis: yIdx - 0.4, itemStyle: { color: 'rgba(245,108,108,0.35)' } },
        { xAxis: bw.end, yAxis: yIdx + 0.4 },
      ])
    }
  }
  const freezeT = layers?.freeze_time ?? store.impactReport?.freeze_time
  if (freezeT != null && Number(freezeT) > 0) {
    markAreas.push([
      { xAxis: 0, yAxis: -0.5, itemStyle: { color: 'rgba(144,147,153,0.18)' } },
      { xAxis: freezeT, yAxis: machines.length - 0.5 },
    ])
  }
  if (markAreas.length) {
    seriesList.push({
      name: '_layers',
      type: 'line',
      data: [],
      markArea: { silent: true, data: markAreas },
    })
  }

  ganttChart.setOption({
    tooltip: { formatter: (p) => `<b>${p.value[6]} - ${p.value[5]}</b><br>设备: M-${p.value[4]}<br>时间: ${p.value[1]} -> ${p.value[2]}` },
    legend: { type: 'plain', bottom: 0, left: 'center', width: '95%', itemGap: 15, itemWidth: 15, itemHeight: 10, textStyle: { fontSize: 11 } },
    grid: { top: 30, left: 50, right: 30, bottom: bottomSpace },
    xAxis: { min: 0, scale: true, splitLine: { show: true }, axisLabel: { color: '#909399' } },
    yAxis: { type: 'category', data: machines.map((m) => `M-${m}`), splitLine: { show: true }, axisLabel: { fontWeight: 'bold' } },
    series: seriesList,
  })
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

function syncWorkContextFromReport() {
  if (!hasReportData.value || !store.currentPlanInput?.length) return
  workContext.setFromPlan({
    planId: store.currentPlanId || '',
    planName: store.currentPlanName || '分析报表计划',
    jobs: (store.currentPlanInput || []).map((j) => normalizeJob(j)),
    source: 'reports',
  })
}

function openGlobalAssistant() {
  syncWorkContextFromReport()
  assistantStore.open()
}

async function saveResultToDB() {
  if (!selectedAlgoId.value || !store.results?.[selectedAlgoId.value]) {
    ElMessage.warning('请先选择一个算法结果')
    return
  }
  if (!store.currentPlanInput || !Array.isArray(store.currentPlanInput) || !store.currentPlanInput.length) {
    ElMessage.warning('当前无工单输入数据，无法保存')
    return
  }

  const result = store.results[selectedAlgoId.value]
  let planName = store.currentPlanName
  if (!planName) {
    planName = `排程结果-[${result.name}]-${new Date().toLocaleString()}`
  }

  try {
    await ElMessageBox.confirm(`确定将计划 "${planName}" 保存到数据库吗？`, '保存确认', { type: 'warning' })
  } catch {
    return
  }

  const chartBase64 = ganttChart
    ? ganttChart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
    : null

  const payload = {
    plan_name: planName,
    jobs: store.currentPlanInput,
    schedule_result: {
      algorithm: result.name,
      makespan: result.best_score,
      score: result.score,
      metrics: result.metrics || {},
      gantt_data: result.gantt_data || [],
      saved_at: new Date().toISOString(),
    },
    chart_image: chartBase64,
    status: 'done',
  }

  try {
    const { data } = await api.post('/api/db/save', payload)
    if (data?.status === 'success') {
      store.currentPlanId = data.id
      store.currentPlanName = planName
      ElMessage.success('保存成功')
    } else {
      ElMessage.error(`保存失败: ${data?.message || '未知错误'}`)
    }
  } catch (e) {
    ElMessage.error(`保存失败: ${e}`)
  }
}

watch(
  () => store.results,
  async (val, oldVal) => {
    if (val && val !== oldVal) {
      sortKey.value = DEFAULT_REPORT_SORT_KEY
    }
    ensureDefaultAlgo()
    await nextTick()
    if (activeTab.value === 'gantt') renderGantt()
    if (activeTab.value === 'convergence') renderConvergence()
  },
)

watch(activeTab, async (tab) => {
  await nextTick()
  if (tab === 'gantt') {
    ensureDefaultAlgo()
    renderGantt()
  } else if (tab === 'convergence') {
    renderConvergence()
  }
})

watch(selectedAlgoId, () => {
  if (activeTab.value === 'gantt') renderGantt()
})

async function hydrateReportsOnEnter() {
  if (consumeReportsScheduleFromSession(store)) {
    await nextTick()
    ensureDefaultAlgo()
    if (activeTab.value === 'gantt') renderGantt()
    if (activeTab.value === 'convergence') renderConvergence()
    return true
  }
  if (isValidScheduleResults(store.results)) {
    await nextTick()
    ensureDefaultAlgo()
    if (activeTab.value === 'gantt') renderGantt()
    return true
  }
  return tryLoadScheduleFromBoundPlan()
}

async function tryLoadScheduleFromBoundPlan() {
  if (isValidScheduleResults(store.results)) return true
  const planId = store.currentPlanId || workContext.planId
  if (!planId) return false
  try {
    const { data: order } = await api.get(`/api/db/get/${planId}`)
    if (hydrateResultsStoreFromPlan(order, store)) {
      ElMessage.info(`已加载计划「${order.plan_name || planId}」的排程快照`)
      return true
    }
  } catch (e) {
    console.warn('load plan schedule', e)
  }
  return false
}

onMounted(async () => {
  await hydrateReportsOnEnter()
  ensureDefaultAlgo()
  await nextTick()
  if (activeTab.value === 'gantt') renderGantt()
})

watch(
  () => route.path,
  async (path) => {
    if (path !== '/reports') return
    const ok = await hydrateReportsOnEnter()
    if (ok) {
      await nextTick()
      ensureDefaultAlgo()
      if (activeTab.value === 'gantt') renderGantt()
      if (activeTab.value === 'convergence') renderConvergence()
    }
  },
)

onUnmounted(() => {
  if (highlightTimer) clearTimeout(highlightTimer)
  if (ganttChart) ganttChart.dispose()
  if (convChart) convChart.dispose()
})
</script>

<style scoped>
.row { display:flex; align-items:center; gap: 12px; }
.h { font-weight: 700; }
.spacer { flex: 1; }
.chart-wrap { margin-top: 8px; }
.chart { width: 100%; height: 560px; border: 1px solid #ebeef5; border-radius: 6px; }
.small-title { font-size: 12px; color: #909399; }
.alert-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.mb12 { margin-bottom: 12px; }
.hint { font-size: 12px; color: #909399; }
</style>

