<template>
  <el-row :gutter="12">
    <el-col :lg="16" :md="24">
      <el-card shadow="never">
        <template #header>
          <div class="row">
            <div class="h">工单池（优先级管理）</div>
            <div class="spacer" />
            <el-radio-group v-model="inputMode" size="small">
              <el-radio-button label="file">算例库</el-radio-button>
              <el-radio-button label="custom">自定义/数据库</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="inputMode === 'custom'" class="plan-bar">
            <span class="plan-bar-label">当前计划</span>
            <el-select
              v-model="selectedPlanId"
              filterable
              clearable
              placeholder="从数据库选择计划"
              size="small"
              class="plan-bar-select"
              :loading="plansLoading"
              @change="onApsPlanSelect"
            >
              <el-option v-for="p in planOptions" :key="p.id" :label="p.label" :value="p.id" />
            </el-select>
            <el-input
              v-model="planName"
              size="small"
              class="plan-bar-name"
              placeholder="计划名称（可编辑）"
              clearable
              @blur="onPlanNameBlur"
            />
            <el-button size="small" :loading="plansLoading" @click="refreshPlanList">刷新</el-button>
            <el-button size="small" type="success" :loading="savingPlan" @click="savePlanToDb">保存计划</el-button>
            <el-tag v-if="currentPlanId" size="small" type="info">已入库</el-tag>
            <el-tag v-else size="small" type="warning">未保存</el-tag>
          </div>
        </template>

        <div v-if="inputMode === 'file'">
          <el-form label-width="100px">
            <el-form-item label="基准算例">
              <el-select v-model="selectedBenchmark" placeholder="请选择文件" style="width:100%">
                <el-option v-for="f in benchmarks" :key="f" :label="f" :value="f" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>

        <div v-else>
          <div class="toolbar toolbar-lite">
            <el-button size="small" @click="loadTemplate">加载示例</el-button>
            <el-button size="small" type="primary" plain @click="addJob">添加工单</el-button>
          </div>

          <el-alert
            v-if="currentPlanId || planName"
            :title="planPoolBanner"
            type="success"
            :closable="false"
            show-icon
            class="plan-pool-banner"
          />

          <el-empty
            v-if="customJobs.length === 0"
            description="该计划暂无工单，点击「添加工单」编辑工序与工艺"
            class="plan-empty-hint"
          />

          <el-space v-else direction="vertical" fill style="width:100%">
            <el-card v-for="(job, jIndex) in customJobs" :key="jIndex" shadow="never" class="job-card">
              <template #header>
                <div class="job-head-grid">
                  <div class="job-field job-field-name">
                    <span class="field-label">工单名称</span>
                    <el-input v-model="job.name" placeholder="请输入工单名称" size="small" />
                  </div>
                  <div class="job-field job-field-prio">
                    <span class="field-label">优先级</span>
                    <div class="field-inline">
                      <el-tag :type="job.priority > 10 ? 'danger' : 'info'" size="small">
                        {{ job.priority > 10 ? '急单' : '普通单' }}
                      </el-tag>
                      <el-button size="small" link @click="togglePriority(jIndex)">切换优先级</el-button>
                    </div>
                  </div>
                  <div class="job-field job-field-due">
                    <span class="field-label">交期</span>
                    <el-input-number
                      v-model="job.due_date"
                      :min="0"
                      :step="1"
                      size="small"
                      controls-position="right"
                      placeholder="自动"
                      class="field-full"
                    />
                  </div>
                  <div class="job-field job-field-qty">
                    <span class="field-label">数量</span>
                    <el-input-number
                      v-model="job.quantity"
                      :min="1"
                      :step="1"
                      size="small"
                      controls-position="right"
                      placeholder="可选"
                      class="field-full"
                      @change="syncJobTaskDurations(job)"
                    />
                  </div>
                  <div class="job-field job-field-act">
                    <el-button type="danger" plain size="small" @click="removeJob(jIndex)">删除工单</el-button>
                  </div>
                </div>
              </template>

              <div class="task-block">
                <div class="section-bar">
                  <span class="section-title">工序路线</span>
                  <el-button size="small" type="primary" plain @click="addTask(jIndex)">+ 添加工序</el-button>
                </div>

                <div class="data-table task-list">
                  <div class="data-row data-row-head task-row-cols">
                    <span class="cell-name">工序名称</span>
                    <span class="cell-mach">首选机台</span>
                    <span class="cell-alt">候选机台</span>
                    <span class="cell-dur">加工时长</span>
                    <span class="cell-act">操作</span>
                  </div>
                  <div v-for="(row, tIndex) in job.tasks" :key="tIndex" class="task-item">
                    <div class="data-row data-row-body task-row-cols">
                      <div class="cell-name">
                        <el-input v-model="row.name" placeholder="如：卷料冲压" size="small" />
                      </div>
                      <div class="cell-mach">
                        <el-input-number
                          v-model="row.machine_id"
                          :min="0"
                          size="small"
                          controls-position="right"
                          class="field-full"
                        />
                      </div>
                      <div class="cell-alt">
                        <el-input
                          v-model="row.machine_options_text"
                          placeholder="多台用逗号，如 1,3"
                          size="small"
                        />
                      </div>
                      <div class="cell-dur">
                        <div class="duration-inline">
                          <el-input-number
                            v-model="row.duration"
                            :min="1"
                            size="small"
                            controls-position="right"
                            class="field-full"
                            :disabled="isDurationAuto(row, job)"
                          />
                          <el-tag v-if="isDurationAuto(row, job)" type="success" size="small" effect="plain">自动计算</el-tag>
                        </div>
                      </div>
                      <div class="cell-act">
                        <el-button type="danger" link size="small" @click="removeTask(jIndex, tIndex)">删除</el-button>
                      </div>
                    </div>
                    <div v-if="showTaskAdvanced" class="task-adv-row">
                      <div class="adv-field">
                        <span class="adv-label">准备时间</span>
                        <el-input-number
                          v-model="row.setup_time"
                          :min="0"
                          :step="0.5"
                          size="small"
                          controls-position="right"
                          class="field-full"
                          @change="onTaskTimingChange(row, job)"
                        />
                      </div>
                      <div class="adv-field">
                        <span class="adv-label">单件工时</span>
                        <el-input-number
                          v-model="row.unit_time"
                          :min="0"
                          :step="0.5"
                          size="small"
                          controls-position="right"
                          class="field-full"
                          @change="onTaskTimingChange(row, job)"
                        />
                      </div>
                      <div class="adv-field">
                        <span class="adv-label">加工数量</span>
                        <el-input-number
                          v-model="row.quantity"
                          :min="1"
                          :step="1"
                          size="small"
                          controls-position="right"
                          class="field-full"
                          @change="onTaskTimingChange(row, job)"
                        />
                      </div>
                      <div class="adv-field">
                        <span class="adv-label">设备组（仅标注）</span>
                        <el-input v-model="row.machine_group" placeholder="如 CNC-A" size="small" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="bom-block">
                <div class="section-bar">
                  <span class="section-title">物料清单 BOM</span>
                  <div class="section-actions">
                    <el-dropdown trigger="click" @command="(cmd) => applyBomTemplate(jIndex, cmd)">
                      <el-button size="small" type="primary" plain>套用模板</el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item v-for="t in bomTemplates" :key="t.id" :command="t.id">
                            {{ t.name }}
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                    <el-button size="small" plain @click="addBomLine(jIndex)">+ 添加物料</el-button>
                  </div>
                </div>
                <div v-if="!(job.bom || []).length" class="bom-empty">未配置 BOM，可在右侧「批量BOM」或此处添加</div>
                <div v-else class="data-table bom-list">
                  <div class="data-row data-row-head bom-row-cols">
                    <span class="cell-bom-mat">物料名称</span>
                    <span class="cell-bom-qty">单件用量</span>
                    <span class="cell-bom-mode">消耗方式</span>
                    <span class="cell-bom-act">操作</span>
                  </div>
                  <div v-for="(brow, bIndex) in job.bom" :key="bIndex" class="data-row data-row-body bom-row-cols">
                    <div class="cell-bom-mat">
                      <el-select v-model="brow.material_id" filterable placeholder="选择物料" size="small">
                        <el-option
                          v-for="m in materialCatalog"
                          :key="m.id"
                          :label="`${m.name}（${m.id}）`"
                          :value="m.id"
                        />
                      </el-select>
                    </div>
                    <div class="cell-bom-qty">
                      <el-input-number v-model="brow.quantity_per_unit" :min="0" :step="0.1" size="small" controls-position="right" class="field-full" />
                    </div>
                    <div class="cell-bom-mode">
                      <el-select v-model="brow.consume_mode" size="small">
                        <el-option label="开工扣料" value="job_start" />
                        <el-option label="按小时扣料" value="per_hour" />
                      </el-select>
                    </div>
                    <div class="cell-bom-act">
                      <el-button type="danger" link size="small" @click="(job.bom || []).splice(bIndex, 1)">删除</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-card>
          </el-space>
        </div>
      </el-card>
    </el-col>

    <el-col :lg="8" :md="24">
      <el-card shadow="never" class="side-card">
        <template #header>
          <div class="row">
            <div class="h">策略与运行</div>
            <div class="spacer" />
            <el-checkbox :model-value="isAllSelected" @change="toggleSelectAll">全选</el-checkbox>
          </div>
        </template>

        <div v-if="inputMode === 'custom'" class="ops-panel">
          <div class="ops-title">工单操作</div>

          <div class="ops-group">
            <div class="ops-label">工艺路线</div>
            <el-select v-model="selectedRoutingId" placeholder="选择模板" clearable size="small" style="width:100%">
              <el-option v-for="r in routingTemplates" :key="r.id" :label="r.name" :value="r.id" />
            </el-select>
            <div class="ops-btns">
              <el-button size="small" :disabled="!selectedRoutingId" @click="applyRoutingTemplate">套用</el-button>
              <el-button size="small" @click="saveRoutingTemplate">保存模板</el-button>
            </div>
          </div>

          <div class="ops-group">
            <div class="ops-label">物料 / BOM</div>
            <div class="ops-btns">
              <el-button size="small" type="warning" plain @click="checkMaterials">物料预检</el-button>
              <el-dropdown trigger="click" @command="applyBomTemplateToAll">
                <el-button size="small" type="primary" plain>批量BOM</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="t in bomTemplates" :key="t.id" :command="t.id">
                      {{ t.name }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button v-if="store.materialCheck" size="small" type="warning" link @click="materialCheckDialogVisible = true">预检明细</el-button>
            </div>
          </div>

          <div class="ops-group">
            <div class="ops-label">工序编辑</div>
            <el-checkbox v-model="showTaskAdvanced" size="small">显示工艺参数（准备/单件/数量）</el-checkbox>
            <div class="ops-tip">时长可直接填；工艺参数齐全时自动计算</div>
          </div>

          <div class="ops-group">
            <div class="ops-label">计划数据</div>
            <div class="ops-btns">
              <el-button size="small" @click="exportJSON">导出</el-button>
              <el-upload :show-file-list="false" accept=".json" :auto-upload="false" :on-change="handleFileUpload">
                <el-button size="small">导入</el-button>
              </el-upload>
            </div>
            <el-button size="small" type="success" style="width:100%;margin-top:6px" @click="savePlanToDb">保存计划与工单</el-button>
            <el-button
              size="small"
              type="warning"
              plain
              style="width:100%;margin-top:6px"
              :loading="pipelineRunning"
              :disabled="customJobs.length === 0"
              @click="runPipelineWithHitl"
            >
              排程并待确认落库
            </el-button>
            <div v-if="currentPlanId" class="ops-tip">计划 ID：{{ currentPlanId }}</div>
            <el-button
              size="small"
              type="primary"
              plain
              style="width:100%;margin-top:8px"
              :disabled="customJobs.length === 0"
              @click="openGlobalAssistant"
            >
              车间助手（故障/齐套/交期）
            </el-button>
          </div>
        </div>

        <div class="planning-panel">
          <div class="ops-title">协同排产（Collab + 策略 V1）</div>
          <el-form-item label="自然语言目标" label-width="auto" style="margin-bottom: 8px">
            <el-input
              v-model="planningGoal"
              type="textarea"
              :rows="2"
              placeholder="例如：交付优先，保证工单A按期，减少换型"
            />
          </el-form-item>
          <div class="ops-btns" style="margin-bottom: 8px">
            <el-button
              size="small"
              type="primary"
              plain
              :loading="planningGenerating"
              :disabled="!planningGoal?.trim()"
              @click="generatePlanningStrategy"
            >
              AI 生成策略
            </el-button>
            <el-button
              size="small"
              type="success"
              :loading="planningRunning"
              :disabled="!planningGoal?.trim() || planningJobsDisabled"
              @click="runSmartPlanning"
            >
              智能排产运行
            </el-button>
          </div>
          <el-collapse v-if="strategyDraftJson" v-model="strategyPreviewOpen" class="strategy-preview-collapse">
            <el-collapse-item title="Strategy JSON 预览" name="preview">
              <el-input
                v-model="strategyDraftJson"
                type="textarea"
                :rows="8"
                class="strategy-json-input"
              />
            </el-collapse-item>
          </el-collapse>
          <el-collapse v-if="collabAnalyses" v-model="collabAnalysisOpen" class="strategy-preview-collapse">
            <el-collapse-item title="三分析摘要（订单 / 约束 / 资源）" name="analyses">
              <div v-if="collabAnalyses.order_analysis" class="planning-result-row">
                <span class="planning-result-k">订单</span>
                <span>{{ collabAnalyses.order_analysis.summary || formatCriticalOrders(collabAnalyses.order_analysis) }}</span>
              </div>
              <div v-if="collabAnalyses.constraint_analysis" class="planning-result-row">
                <span class="planning-result-k">约束</span>
                <span>{{ collabAnalyses.constraint_analysis.summary || formatConstraintBrief(collabAnalyses.constraint_analysis) }}</span>
              </div>
              <div v-if="collabAnalyses.resource_analysis" class="planning-result-row">
                <span class="planning-result-k">资源</span>
                <span>{{ collabAnalyses.resource_analysis.summary || formatResourceBrief(collabAnalyses.resource_analysis) }}</span>
              </div>
            </el-collapse-item>
          </el-collapse>
          <div v-if="planningRunId && planningRunStatus === 'WAITING_APPROVAL'" class="planning-hitl">
            <div class="ops-label">策略确认（HITL）</div>
            <div class="ops-btns">
              <el-button size="small" type="success" :loading="planningHitlLoading" @click="approvePlanningStrategy">
                批准
              </el-button>
              <el-button size="small" type="danger" plain :loading="planningHitlLoading" @click="rejectPlanningStrategy">
                拒绝
              </el-button>
              <el-button size="small" type="warning" plain :loading="planningHitlLoading" @click="editApprovePlanningStrategy">
                编辑后批准
              </el-button>
            </div>
            <div v-if="planningRunId" class="ops-tip">Run ID：{{ planningRunId }}</div>
          </div>
          <div v-if="planningResult" class="planning-result">
            <div class="ops-label">排产结果</div>
            <div class="planning-result-row">
              <span class="planning-result-k">推荐方案</span>
              <span>{{ planningResult.recommended_schedule_id || '—' }}</span>
            </div>
            <div v-if="planningResult.recommendation_reason" class="planning-result-reason">
              {{ planningResult.recommendation_reason }}
            </div>
            <div v-if="planningResult.simulated_fields?.length" class="planning-result-row">
              <span class="planning-result-k">模拟字段</span>
              <span>{{ planningResult.simulated_fields.join('、') }}</span>
            </div>
            <div v-if="planningResult.hard_violations?.length" class="planning-violations">
              <div class="ops-label">硬约束违反（{{ planningResult.hard_violations.length }}）</div>
              <ul class="planning-violation-list">
                <li v-for="(v, i) in planningResult.hard_violations.slice(0, 5)" :key="i">
                  {{ v.schedule_id || '—' }}：{{ v.message || v.type || JSON.stringify(v) }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div class="weights-panel">
          <el-form-item label="自然语言排程（可选）" label-width="auto" style="margin-bottom: 8px">
            <el-input
              v-model="scheduleMessage"
              type="textarea"
              :rows="2"
              placeholder="例如：交付优先，对比禁忌搜索和 SPT"
            />
          </el-form-item>
          <div class="ops-btns" style="margin-bottom: 12px">
            <el-button size="small" :disabled="!scheduleMessage?.trim()" @click="previewScheduleIntent">
              预览解析
            </el-button>
            <span v-if="lastPlanner" class="ops-tip">上次解析：{{ lastPlanner }}</span>
          </div>
          <div class="row" style="margin-bottom: 10px">
            <span class="weights-title" style="margin: 0">策略模板</span>
            <div class="spacer" />
            <el-select
              v-model="selectedStrategyId"
              placeholder="一键套用权重"
              clearable
              style="width: 100%"
              @change="applyStrategyTemplate"
            >
              <el-option v-for="s in strategyTemplates" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </div>
          <el-form-item label="随机种子（可选，复现）" label-width="auto" style="margin-bottom: 10px">
            <el-input-number v-model="randomSeed" :min="0" :step="1" controls-position="right" style="width: 100%" clearable />
          </el-form-item>
          <div class="weights-title">多目标权重（越小越好）</div>
          <el-form label-position="top" class="weights-form">
            <div class="weights-grid">
              <el-form-item>
                <template #label>
                  <div class="wlabel">完工时间（Makespan）</div>
                </template>
                <el-input-number v-model="weights.makespan" :step="0.1" :min="0" controls-position="right" style="width: 100%" />
                <div class="wdesc">最大完工时间</div>
              </el-form-item>

              <el-form-item>
                <template #label>
                  <div class="wlabel">交期违约（加权 Tardiness）</div>
                </template>
                <el-input-number v-model="weights.weighted_tardiness_total" :step="0.1" :min="0" controls-position="right" style="width: 100%" />
                <div class="wdesc">逾期时间按优先级加权</div>
              </el-form-item>

              <el-form-item>
                <template #label>
                  <div class="wlabel">能耗成本（Energy Cost）</div>
                </template>
                <el-input-number v-model="weights.energy_cost" :step="0.01" :min="0" controls-position="right" style="width: 100%" />
                <div class="wdesc">功率 × 分时电价 × 时长</div>
              </el-form-item>

              <el-form-item>
                <template #label>
                  <div class="wlabel">负载均衡（机器忙碌度 CV）</div>
                </template>
                <el-input-number v-model="weights.machine_busy_cv" :step="0.5" :min="0" controls-position="right" style="width: 100%" />
                <div class="wdesc">各机器忙碌度离散程度</div>
              </el-form-item>
            </div>
          </el-form>
          <el-alert
            class="whelp"
            type="info"
            :closable="false"
            show-icon
            title="综合评分 = w1·makespan + w2·加权交期违约 + w3·能耗成本 + w4·负载CV"
          />
        </div>

        <el-space direction="vertical" fill style="width:100%">
          <div v-for="group in solverGroups" :key="group.title">
            <div class="group-title">{{ group.title }}</div>
            <el-checkbox-group v-model="selectedSolvers" class="solver-list">
              <el-checkbox v-for="s in group.items" :key="s.id" :label="s.id">
                <span>{{ s.name }}</span>
                <el-tag v-if="s.supports_weights_in_search" size="small" type="success" class="solver-tag">多目标搜索</el-tag>
                <el-tag v-else-if="s.optimization_mode === 'rule_construct'" size="small" type="info" class="solver-tag">规则构造</el-tag>
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </el-space>

        <div style="margin-top:16px">
          <el-checkbox v-model="useAsyncRun" style="margin-bottom: 8px">异步计算（大规模算例推荐，避免页面超时）</el-checkbox>
          <el-checkbox v-model="enforceMaterial" style="margin-bottom: 8px">启用物料约束（按优先级推迟缺料工单开工）</el-checkbox>
          <el-button type="primary" :loading="store.computing" :disabled="runDisabled" style="width:100%" @click="run">开始排程计算</el-button>
        </div>
      </el-card>
    </el-col>
  </el-row>

  <MaterialCheckDialog v-model="materialCheckDialogVisible" :report="store.materialCheck" />

  <PersistConfirmDialog
    v-model="persistDialogVisible"
    :confirm-token="persistPending.confirmToken"
    :preview="persistPending.preview"
    :expires-at="persistPending.expiresAt"
    :summary-zh="persistPending.summaryZh"
    @confirmed="onPersistConfirmed"
  />

</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'
import MaterialCheckDialog from '../components/MaterialCheckDialog.vue'
import PersistConfirmDialog from '../components/PersistConfirmDialog.vue'
import { runPipelineAgent } from '../api/client'
import { useWorkContextStore } from '../stores/useWorkContextStore'
import { useAssistantStore } from '../stores/useAssistantStore'
import { usePlanBinding } from '../composables/usePlanBinding'
import {
  clearApsLoadScheduleKeys,
  consumeApsLoadSchedule,
  hydrateResultsStoreFromPlan,
  persistScheduleToPlan,
} from '../utils/planScheduleSync'

const router = useRouter()
const store = useResultsStore()
const workContext = useWorkContextStore()
const assistantStore = useAssistantStore()
const {
  planOptions,
  planList,
  plansLoading,
  selectedPlanId,
  fetchPlans,
} = usePlanBinding()

const savingPlan = ref(false)
const planPoolBanner = computed(() => {
  const name = planName.value?.trim() || '未命名计划'
  const n = customJobs.value.length
  return `正在编辑计划「${name}」${currentPlanId.value ? '' : '（请先保存入库）'} · ${n} 个工单`
})

const inputMode = ref('file')
const benchmarks = ref([])
const selectedBenchmark = ref('ft06.txt')

const planName = ref('')
const currentPlanId = ref('')
const customJobs = ref([
  {
    name: '工单A',
    priority: 10,
    due_date: null,
    quantity: null,
    bom: [
      { material_id: 'MAT_STEEL', quantity_per_unit: 2, consume_mode: 'job_start' },
      { material_id: 'MAT_SCREW', quantity_per_unit: 6, consume_mode: 'job_start' },
    ],
    tasks: [
      { name: 'Cut', machine_id: 0, machine_options_text: '0', machine_group: 'CUT', duration: 6, setup_time: null, unit_time: null, quantity: null },
      { name: 'Drill', machine_id: 1, machine_options_text: '1,2', machine_group: 'DRILL', duration: 4, setup_time: null, unit_time: null, quantity: null },
    ],
  },
])

const strategyTemplates = ref([])
const selectedStrategyId = ref('')
const routingTemplates = ref([])
const selectedRoutingId = ref('')
const randomSeed = ref(null)
const useAsyncRun = ref(true)
const enforceMaterial = ref(true)
const materialCatalog = ref([])
const scheduleMessage = ref('')
const lastPlanner = ref('')
const materialCheckDialogVisible = ref(false)
const persistDialogVisible = ref(false)
const pipelineRunning = ref(false)
const persistPending = ref({
  confirmToken: '',
  expiresAt: '',
  preview: null,
  summaryZh: '',
})
const showTaskAdvanced = ref(false)

const planningGoal = ref('')
const strategyDraftJson = ref('')
const strategyPreviewOpen = ref(['preview'])
const planningRunId = ref('')
const planningRunStatus = ref('')
const planningGenerating = ref(false)
const planningRunning = ref(false)
const planningHitlLoading = ref(false)
const planningResult = ref(null)
const collabAnalyses = ref(null)
const collabAnalysisOpen = ref(['analyses'])

const planningJobsDisabled = computed(() => {
  if (inputMode.value === 'custom') return customJobs.value.length === 0
  return !selectedBenchmark.value
})

const bomTemplates = [
  {
    id: 'machining',
    name: '机加工 · 钢材+螺栓',
    lines: [
      { material_id: 'MAT_STEEL', quantity_per_unit: 2.5, consume_mode: 'job_start' },
      { material_id: 'MAT_SCREW', quantity_per_unit: 4, consume_mode: 'job_start' },
    ],
  },
  {
    id: 'sheet_metal',
    name: '钣金 · 铝材',
    lines: [{ material_id: 'MAT_ALUM', quantity_per_unit: 1.5, consume_mode: 'job_start' }],
  },
  {
    id: 'injection',
    name: '注塑 · 塑料',
    lines: [{ material_id: 'MAT_PLASTIC', quantity_per_unit: 0.6, consume_mode: 'job_start' }],
  },
  {
    id: 'continuous',
    name: '连续加工 · 按小时耗钢',
    lines: [{ material_id: 'MAT_STEEL', quantity_per_unit: 3, consume_mode: 'per_hour' }],
  },
  {
    id: 'mixed',
    name: '综合装配 · 四种主料',
    lines: [
      { material_id: 'MAT_STEEL', quantity_per_unit: 1, consume_mode: 'job_start' },
      { material_id: 'MAT_ALUM', quantity_per_unit: 0.5, consume_mode: 'job_start' },
      { material_id: 'MAT_PLASTIC', quantity_per_unit: 0.3, consume_mode: 'job_start' },
      { material_id: 'MAT_SCREW', quantity_per_unit: 8, consume_mode: 'job_start' },
    ],
  },
]

const solverGroups = ref([])
const catalogLoading = ref(false)

const selectedSolvers = ref(['spt', 'ts'])
const allSolverIds = computed(() =>
  solverGroups.value.flatMap((g) => g.items.map((x) => x.id)),
)

const weights = reactive({
  makespan: 1.0,
  weighted_tardiness_total: 0.5,
  energy_cost: 0.05,
  machine_busy_cv: 10.0,
})

const isAllSelected = computed(() =>
  allSolverIds.value.length > 0 && selectedSolvers.value.length === allSolverIds.value.length,
)
const runDisabled = computed(() => {
  if (selectedSolvers.value.length === 0) return true
  if (inputMode.value === 'file' && !selectedBenchmark.value) return true
  if (inputMode.value === 'custom' && customJobs.value.length === 0) return true
  return false
})

function toggleSelectAll(checked) { selectedSolvers.value = checked ? [...allSolverIds.value] : [] }

function buildSolverGroupsFromCatalog(solvers, families) {
  const familyOrder = ['rule', 'metaheuristic', 'rl']
  const byFamily = {}
  for (const s of solvers || []) {
    if (!byFamily[s.family]) byFamily[s.family] = []
    byFamily[s.family].push({
      id: s.id,
      name: s.name_zh || s.name_en,
      supports_weights_in_search: s.supports_weights_in_search,
      optimization_mode: s.optimization_mode,
    })
  }
  return familyOrder
    .filter((f) => byFamily[f]?.length)
    .map((f) => ({ title: families?.[f] || f, items: byFamily[f] }))
}
function addJob() {
  customJobs.value.push({
    name: `工单${customJobs.value.length + 1}`,
    priority: 10,
    due_date: null,
    quantity: null,
    bom: [],
    tasks: [{ name: 'Op-1', machine_id: 0, machine_options_text: '0', machine_group: '', duration: 5, setup_time: null, unit_time: null, quantity: null }],
  })
}

function addBomLine(jobIdx) {
  const job = customJobs.value[jobIdx]
  if (!job.bom) job.bom = []
  const defaultMat = materialCatalog.value[0]?.id || 'MAT_STEEL'
  job.bom.push({ material_id: defaultMat, quantity_per_unit: 1, consume_mode: 'job_start' })
}

function resolveMaterialId(id) {
  const cat = materialCatalog.value
  if (!cat.length) return id
  if (cat.some((m) => m.id === id)) return id
  return cat[0].id
}

function cloneBomLines(template) {
  return (template.lines || []).map((line) => ({
    material_id: resolveMaterialId(line.material_id),
    quantity_per_unit: Number(line.quantity_per_unit ?? 1),
    consume_mode: line.consume_mode || 'job_start',
  }))
}

function applyBomTemplate(jobIdx, templateId) {
  const tpl = bomTemplates.find((t) => t.id === templateId)
  if (!tpl) return
  const job = customJobs.value[jobIdx]
  if (!job) return
  job.bom = cloneBomLines(tpl)
  ElMessage.success(`已为「${job.name}」套用：${tpl.name}`)
}

function applyBomTemplateToAll(templateId) {
  if (inputMode.value !== 'custom' || !customJobs.value.length) {
    return ElMessage.warning('请使用自定义工单模式并至少添加一条工单')
  }
  const tpl = bomTemplates.find((t) => t.id === templateId)
  if (!tpl) return
  customJobs.value.forEach((job) => {
    job.bom = cloneBomLines(tpl)
  })
  ElMessage.success(`已为 ${customJobs.value.length} 个工单套用：${tpl.name}`)
}

async function fetchMaterialCatalog() {
  try {
    const { data } = await api.get('/api/materials/list')
    materialCatalog.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.warn('materials list', e)
  }
}

async function checkMaterials() {
  if (inputMode.value !== 'custom' || !customJobs.value.length) {
    return ElMessage.warning('请使用自定义工单模式并至少添加一条工单')
  }
  try {
    const { data } = await api.post('/api/materials/check_jobs', {
      jobs: customJobs.value.map((j) => mapJobPayload(j)),
    })
    if (data?.error) throw new Error(data.error)
    const report = data.report || {}
    store.setMaterialCheck(report)
    materialCheckDialogVisible.value = true
    if (report.feasible) {
      ElMessage.success('物料预检通过：当前库存可覆盖 BOM 总需求')
    } else {
      const bad = (report.summary || []).filter((x) => !x.feasible).map((x) => x.material_name).join('、')
      ElMessage.warning(`物料不足：${bad || '请查看预检明细'}`)
    }
  } catch (e) {
    ElMessage.error(`物料预检失败: ${e}`)
  }
}
function removeJob(idx) { customJobs.value.splice(idx, 1) }

function taskEffectiveQty(row, job) {
  if (row.quantity != null && row.quantity !== '') return Number(row.quantity)
  if (job?.quantity != null && job.quantity !== '') return Number(job.quantity)
  return null
}

function canAutoDuration(row, job) {
  const qty = taskEffectiveQty(row, job)
  return (
    row.setup_time != null && row.setup_time !== ''
    && row.unit_time != null && row.unit_time !== ''
    && qty != null && qty > 0
  )
}

function calcTaskDuration(row, job) {
  if (!canAutoDuration(row, job)) return null
  const qty = taskEffectiveQty(row, job)
  return Math.max(1, Math.round(Number(row.setup_time) + Number(row.unit_time) * qty))
}

function isDurationAuto(row, job) {
  return canAutoDuration(row, job)
}

function syncTaskDuration(row, job) {
  const d = calcTaskDuration(row, job)
  if (d != null) row.duration = d
}

function onTaskTimingChange(row, job) {
  syncTaskDuration(row, job)
}

function syncJobTaskDurations(job) {
  for (const t of job.tasks || []) syncTaskDuration(t, job)
}

function addTask(jobIdx) {
  const j = customJobs.value[jobIdx]
  j.tasks.push({ name: `Op-${j.tasks.length + 1}`, machine_id: 0, machine_options_text: '0', machine_group: '', duration: 5, setup_time: null, unit_time: null, quantity: null })
}

function syncStrategyToStore(id) {
  if (!id) {
    store.setSchedulingStrategy('', '')
    return
  }
  const t = strategyTemplates.value.find((x) => x.id === id)
  store.setSchedulingStrategy(id, t?.name || id)
}

function applyStrategyTemplate(id) {
  if (!id) return
  const t = strategyTemplates.value.find((x) => x.id === id)
  if (!t?.weights) return
  Object.assign(weights, t.weights)
  syncStrategyToStore(id)
  ElMessage.success(`已套用策略：${t.name}`)
}

function mapTaskPayload(t, job) {
  const machineOptions = parseMachineOptions(t.machine_options_text, t.machine_id)
  const payload = {
    name: t.name,
    duration: Number(t.duration || 1),
    machine_id: Number.isInteger(t.machine_id) ? t.machine_id : (machineOptions[0] ?? 0),
    machine_options: machineOptions,
    machine_group: t.machine_group || null,
  }
  const qty = t.quantity ?? job?.quantity
  if (qty != null && qty !== '') payload.quantity = Number(qty)
  if (t.setup_time != null && t.setup_time !== '') payload.setup_time = Number(t.setup_time)
  if (t.unit_time != null && t.unit_time !== '') payload.unit_time = Number(t.unit_time)
  return payload
}

function buildPlanningJobs() {
  if (inputMode.value === 'custom') {
    return customJobs.value.map((j) => {
      const payload = mapJobPayload(j)
      payload.job_id = j.job_id || j.name
      return payload
    })
  }
  return []
}

function buildPlanningMachines() {
  const ids = new Set()
  for (const job of customJobs.value) {
    for (const t of job.tasks || []) {
      if (Number.isInteger(t.machine_id) && t.machine_id >= 0) ids.add(String(t.machine_id))
      for (const mid of parseMachineOptions(t.machine_options_text, t.machine_id)) {
        ids.add(String(mid))
      }
    }
  }
  return [...ids].map((id) => ({ machine_id: id, id }))
}

function extractPlanningResult(data) {
  const pkg = data?.package || {}
  const ev = data?.evaluation || pkg.evaluation || {}
  const strategy = data?.strategy_approved || data?.strategy_draft || pkg.strategy || {}
  const simulated = strategy?.provenance?.simulated_fields
  return {
    recommended_schedule_id: ev.recommended_schedule_id ?? pkg.recommended_schedule_id ?? null,
    hard_violations: ev.hard_violations || [],
    recommendation_reason: ev.recommendation_reason || '',
    simulated_fields: Array.isArray(simulated) ? simulated : [],
  }
}

function formatCriticalOrders(orderAnalysis) {
  const ids = orderAnalysis?.critical_orders || []
  return ids.length ? `关键订单：${ids.join('、')}` : '无关键订单'
}

function formatConstraintBrief(constraintAnalysis) {
  const hard = (constraintAnalysis?.hard_constraints || []).map((c) => c.type).filter(Boolean)
  const soft = (constraintAnalysis?.soft_constraints || []).map((c) => c.type).filter(Boolean)
  const parts = []
  if (hard.length) parts.push(`硬：${hard.join(',')}`)
  if (soft.length) parts.push(`软：${soft.join(',')}`)
  return parts.join('；') || '无约束候选'
}

function formatResourceBrief(resourceAnalysis) {
  const bn = resourceAnalysis?.bottleneck_machines || []
  return bn.length ? `瓶颈设备：${bn.join('、')}` : '无瓶颈标记'
}

function handlePlanningRunResponse(data) {
  if (!data) return
  planningRunId.value = data.run_id || planningRunId.value
  planningRunStatus.value = data.status || ''
  if (data.artifacts) {
    collabAnalyses.value = {
      order_analysis: data.artifacts.order_analysis || null,
      constraint_analysis: data.artifacts.constraint_analysis || null,
      resource_analysis: data.artifacts.resource_analysis || null,
    }
  }
  if (data.strategy_draft) {
    strategyDraftJson.value = JSON.stringify(data.strategy_draft, null, 2)
  }
  if (data.status === 'COMPLETED') {
    planningResult.value = extractPlanningResult(data)
    ElMessage.success('智能排产完成')
  } else if (data.status === 'WAITING_APPROVAL') {
    planningResult.value = null
    ElMessage.info('策略已生成，请确认后批准')
  } else if (data.validation_errors?.length) {
    ElMessage.warning(`策略校验未通过（${data.validation_errors.length} 项）`)
  } else if (data.status === 'CANCELLED') {
    planningResult.value = null
  }
}

async function ensurePlanningRun() {
  if (planningRunId.value) return planningRunId.value
  const goal = planningGoal.value?.trim()
  if (!goal) throw new Error('请先输入自然语言目标')
  const jobs = buildPlanningJobs()
  if (!jobs.length) throw new Error('请先配置工单数据（自定义模式）')
  const { data } = await api.post('/api/planning/collab/run', {
    user_goal: goal,
    jobs,
    machines: buildPlanningMachines(),
    skip_strategy_hitl: false,
  })
  handlePlanningRunResponse(data)
  if (!data?.run_id) throw new Error('未返回 run_id')
  return data.run_id
}

async function generatePlanningStrategy() {
  const goal = planningGoal.value?.trim()
  if (!goal) return ElMessage.warning('请先输入自然语言目标')
  if (inputMode.value !== 'custom') {
    return ElMessage.warning('参数化策略请在「自定义/数据库」模式下使用')
  }
  if (!customJobs.value.length) return ElMessage.warning('请先添加工单')
  planningGenerating.value = true
  try {
    const { data } = await api.post('/api/planning/strategy/generate', {
      user_goal: goal,
      jobs: buildPlanningJobs(),
      machines: buildPlanningMachines(),
    })
    strategyDraftJson.value = JSON.stringify(data.strategy, null, 2)
    planningRunId.value = ''
    planningRunStatus.value = ''
    planningResult.value = null
    ElMessage.success(`策略已生成（${data.meta?.generated_by || data.meta?.source || 'ok'}）`)
  } catch (e) {
    ElMessage.error(`生成失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    planningGenerating.value = false
  }
}

async function runSmartPlanning() {
  const goal = planningGoal.value?.trim()
  if (!goal) return ElMessage.warning('请先输入自然语言目标')
  if (inputMode.value !== 'custom') {
    return ElMessage.warning('智能排产请在「自定义/数据库」模式下使用')
  }
  if (!customJobs.value.length) return ElMessage.warning('请先添加工单')
  planningRunning.value = true
  planningResult.value = null
  collabAnalyses.value = null
  try {
    const { data } = await api.post('/api/planning/collab/run', {
      user_goal: goal,
      jobs: buildPlanningJobs(),
      machines: buildPlanningMachines(),
      skip_strategy_hitl: false,
    })
    handlePlanningRunResponse(data)
  } catch (e) {
    ElMessage.error(`运行失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    planningRunning.value = false
  }
}

async function approvePlanningStrategy() {
  planningHitlLoading.value = true
  try {
    await ensurePlanningRun()
    const { data } = await api.post(`/api/planning/runs/${planningRunId.value}/strategy/approve`, {})
    handlePlanningRunResponse(data)
  } catch (e) {
    ElMessage.error(`批准失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    planningHitlLoading.value = false
  }
}

async function rejectPlanningStrategy() {
  planningHitlLoading.value = true
  try {
    await ensurePlanningRun()
    const { data } = await api.post(`/api/planning/runs/${planningRunId.value}/strategy/reject`, {
      reason: '用户拒绝',
    })
    handlePlanningRunResponse(data)
    ElMessage.info('已拒绝策略')
  } catch (e) {
    ElMessage.error(`拒绝失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    planningHitlLoading.value = false
  }
}

async function editApprovePlanningStrategy() {
  if (!strategyDraftJson.value?.trim()) {
    return ElMessage.warning('请先填写 Strategy JSON')
  }
  let strategy
  try {
    strategy = JSON.parse(strategyDraftJson.value)
  } catch {
    return ElMessage.error('Strategy JSON 格式无效')
  }
  planningHitlLoading.value = true
  try {
    await ensurePlanningRun()
    const { data } = await api.post(
      `/api/planning/runs/${planningRunId.value}/strategy/edit_and_approve`,
      {
        strategy,
        jobs: buildPlanningJobs(),
        machines: buildPlanningMachines(),
      },
    )
    handlePlanningRunResponse(data)
  } catch (e) {
    ElMessage.error(`编辑批准失败: ${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    planningHitlLoading.value = false
  }
}

function mapJobPayload(j) {
  const job = {
    name: j.name,
    priority: j.priority || 10,
    due_date: j.due_date ?? null,
    tasks: (j.tasks || []).map((t) => mapTaskPayload(t, j)),
  }
  if (j.quantity != null && j.quantity !== '') job.quantity = Number(j.quantity)
  if (j.material_arrival != null && j.material_arrival !== '') job.material_arrival = Number(j.material_arrival)
  if (Array.isArray(j.bom) && j.bom.length) {
    job.bom = j.bom.map((b) => ({
      material_id: b.material_id,
      quantity_per_unit: Number(b.quantity_per_unit ?? 1),
      consume_mode: b.consume_mode || 'job_start',
    }))
  }
  return job
}

async function fetchRoutingTemplates() {
  try {
    const { data } = await api.get('/api/routing/list')
    routingTemplates.value = data.items || []
  } catch (e) {
    console.warn('routing list', e)
  }
}

async function saveRoutingTemplate() {
  if (!customJobs.value.length) return ElMessage.warning('请先添加工单')
  try {
    const { value: name } = await ElMessageBox.prompt('请输入工艺路线模板名称', '保存路线', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    if (!name) return
    const first = customJobs.value[0]
    const tasks = (first.tasks || []).map((t) => mapTaskPayload(t, first))
    const { data } = await api.post('/api/routing/save', { name, description: `来自工单 ${first.name}`, tasks })
    if (data?.status === 'success') {
      ElMessage.success('路线模板已保存')
      await fetchRoutingTemplates()
      selectedRoutingId.value = data.id
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(`保存失败: ${e}`)
  }
}

function applyRoutingTemplate() {
  const tpl = routingTemplates.value.find((r) => r.id === selectedRoutingId.value)
  if (!tpl?.tasks?.length) return ElMessage.warning('请选择有效模板')
  const tasks = tpl.tasks.map((t, idx) => {
    const machineOptions = Array.isArray(t.machine_options) ? t.machine_options : [t.machine_id ?? 0]
    const machineId = Number.isInteger(t.machine_id) ? t.machine_id : machineOptions[0]
    return {
      name: t.name || `Op-${idx + 1}`,
      machine_id: machineId,
      machine_options_text: machineOptions.join(','),
      machine_group: t.machine_group || '',
      duration: Number(t.duration || 1),
      setup_time: t.setup_time ?? null,
      unit_time: t.unit_time ?? null,
      quantity: t.quantity ?? null,
    }
  })
  customJobs.value.push({
    name: `${tpl.name}-工单`,
    priority: 10,
    due_date: null,
    quantity: null,
    tasks,
  })
  ElMessage.success('已套用工艺路线到新工单')
}
function removeTask(jobIdx, taskIdx) { customJobs.value[jobIdx].tasks.splice(taskIdx, 1) }
function togglePriority(idx) { customJobs.value[idx].priority = customJobs.value[idx].priority > 10 ? 10 : 100 }

function parseMachineOptions(text, fallbackMachineId) {
  const nums = String(text || '')
    .split(',')
    .map((x) => Number(String(x).trim()))
    .filter((n) => Number.isInteger(n) && n >= 0)
  if (!nums.length && Number.isInteger(fallbackMachineId) && fallbackMachineId >= 0) return [fallbackMachineId]
  return [...new Set(nums)]
}

function normalizeJobs(rawJobs) {
  return (rawJobs || []).map((job) => ({
    ...job,
    priority: Number(job.priority || 10),
    due_date: job.due_date === null || job.due_date === undefined || job.due_date === ''
      ? null
      : Number(job.due_date),
    quantity: job.quantity ?? null,
    bom: (job.bom || []).map((b) => ({
      material_id: b.material_id,
      quantity_per_unit: Number(b.quantity_per_unit ?? 1),
      consume_mode: b.consume_mode || 'job_start',
    })),
    tasks: (job.tasks || []).map((t, idx) => {
      const machineOptions = Array.isArray(t.machine_options) ? t.machine_options : null
      const machineId = Number.isInteger(t.machine_id) ? t.machine_id : (Array.isArray(machineOptions) && machineOptions.length ? Number(machineOptions[0]) : 0)
      const optionsText = machineOptions && machineOptions.length ? machineOptions.join(',') : String(machineId)
      return {
        name: t.name || `Op-${idx + 1}`,
        machine_id: machineId,
        machine_options_text: optionsText,
        machine_group: t.machine_group || '',
        duration: Number(t.duration || 1),
        setup_time: t.setup_time ?? null,
        unit_time: t.unit_time ?? null,
        quantity: t.quantity ?? null,
      }
    }),
  }))
}

function loadTemplate() {
  customJobs.value = normalizeJobs([
    {
      name: '模板工单-1',
      priority: 100,
      bom: [
        { material_id: 'MAT_STEEL', quantity_per_unit: 2.5, consume_mode: 'job_start' },
        { material_id: 'MAT_SCREW', quantity_per_unit: 4, consume_mode: 'job_start' },
      ],
      tasks: [
        { name: 'Cut', machine_id: 0, machine_options: [0, 4], machine_group: 'CUT', duration: 8 },
        { name: 'Weld', machine_id: 2, machine_options: [2], machine_group: 'WELD', duration: 6 },
      ],
    },
    {
      name: '模板工单-2',
      priority: 10,
      bom: [
        { material_id: 'MAT_ALUM', quantity_per_unit: 1.5, consume_mode: 'job_start' },
        { material_id: 'MAT_PLASTIC', quantity_per_unit: 0.5, consume_mode: 'per_hour' },
      ],
      tasks: [
        { name: 'Mill', machine_id: 1, machine_options: [1, 5], machine_group: 'MILL', duration: 7 },
        { name: 'Assemble', machine_id: 3, machine_options: [3], machine_group: 'ASM', duration: 5 },
      ],
    },
  ])
  ElMessage.success('已加载示例工单（含 BOM）')
}

function exportJSON() {
  const clean = customJobs.value.map((j) => mapJobPayload(j))
  const blob = new Blob([JSON.stringify(clean, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'custom_jobs.json'
  a.click()
  URL.revokeObjectURL(url)
}

function handleFileUpload(file) {
  const f = file.raw
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const parsed = JSON.parse(String(e.target?.result || '[]'))
      if (!Array.isArray(parsed)) throw new Error('格式错误')
      customJobs.value = normalizeJobs(parsed)
      ElMessage.success('导入成功')
    } catch (err) {
      ElMessage.error(`导入失败: ${err}`)
    }
  }
  reader.readAsText(f, 'utf-8')
}

function applyPlanFromOrder(order) {
  if (!order) return
  inputMode.value = 'custom'
  currentPlanId.value = order.id || ''
  planName.value = order.plan_name || ''
  selectedPlanId.value = order.id || ''
  const jobs = order.jobs || []
  customJobs.value = jobs.length ? normalizeJobs(jobs) : []
  syncWorkContextToStore()
  hydrateResultsStoreFromPlan(order, store)
}

async function saveScheduleSnapshotToPlan(results, extras = {}) {
  if (!currentPlanId.value || !results || !Object.keys(results).length) return
  try {
    await persistScheduleToPlan(currentPlanId.value, results, extras)
  } catch (e) {
    console.warn('save schedule to plan', e)
    ElMessage.warning('排程结果未能写入计划库，分析报表可能无法恢复')
  }
}

function syncWorkContextToStore() {
  workContext.setFromPlan({
    planId: currentPlanId.value,
    planName: planName.value || '当前计划',
    jobs: customJobs.value.map((j) => mapJobPayload(j)),
    source: 'aps',
  })
}

function onApsPlanSelect(id) {
  if (!id) {
    currentPlanId.value = ''
    planName.value = ''
    customJobs.value = []
    workContext.clear()
    return
  }
  const row = planList.value.find((o) => o.id === id)
  if (row) applyPlanFromOrder(row)
}

async function refreshPlanList() {
  await fetchPlans()
  if (currentPlanId.value) selectedPlanId.value = currentPlanId.value
  ElMessage.success('计划列表已刷新')
}

async function onPlanNameBlur() {
  const name = planName.value?.trim()
  if (!currentPlanId.value || !name) return
  if (name === planList.value.find((o) => o.id === currentPlanId.value)?.plan_name) return
  try {
    await api.put(`/api/db/update/${currentPlanId.value}`, { plan_name: name })
    await fetchPlans()
    syncWorkContextToStore()
    ElMessage.success('计划名称已更新')
  } catch (e) {
    ElMessage.error(`更名失败：${e?.response?.data?.detail || e.message || e}`)
  }
}

function openGlobalAssistant() {
  syncWorkContextToStore()
  assistantStore.open()
}

async function savePlanToDb() {
  const name = (planName.value || '').trim() || `计划-${new Date().toLocaleString()}`
  planName.value = name
  const jobs = customJobs.value.map((j) => mapJobPayload(j))
  savingPlan.value = true
  try {
    if (currentPlanId.value) {
      const { data } = await api.put(`/api/db/update/${currentPlanId.value}`, {
        plan_name: name,
        jobs,
      })
      if (data?.status !== 'success') throw new Error(data?.message || '更新失败')
      selectedPlanId.value = currentPlanId.value
    } else {
      const { data } = await api.post('/api/db/save', {
        plan_name: name,
        jobs,
        status: 'pending',
      })
      if (data?.status !== 'success' && !data?.id) throw new Error(data?.message || '保存失败')
      currentPlanId.value = data.id
      selectedPlanId.value = data.id
    }
    await fetchPlans()
    syncWorkContextToStore()
    ElMessage.success('计划已保存')
    return currentPlanId.value
  } catch (e) {
    ElMessage.error(`保存失败：${e?.response?.data?.detail || e.message || e}`)
    return null
  } finally {
    savingPlan.value = false
  }
}

/** @deprecated 兼容旧调用 */
async function saveToDB() {
  return savePlanToDb()
}

function openPersistDialog(pendingAction, summaryZh) {
  persistPending.value = {
    confirmToken: pendingAction?.confirm_token || '',
    expiresAt: pendingAction?.expires_at || '',
    preview: pendingAction?.preview || null,
    summaryZh: summaryZh || '',
  }
  persistDialogVisible.value = true
}

function onPersistConfirmed() {
  persistPending.value = { confirmToken: '', expiresAt: '', preview: null, summaryZh: '' }
  if (store.results && Object.keys(store.results).length) {
    router.push('/reports')
  }
}

async function runPipelineWithHitl() {
  if (inputMode.value !== 'custom') {
    return ElMessage.warning('请切换到「自定义/数据库」模式')
  }
  if (customJobs.value.length === 0) {
    return ElMessage.warning('请先添加工单')
  }
  if (selectedSolvers.value.length === 0) {
    return ElMessage.warning('请至少选择一个算法')
  }

  pipelineRunning.value = true
  store.computing = true
  try {
    let planId = currentPlanId.value
    if (!planId) {
      ElMessage.info('尚未保存计划，将先写入数据库…')
      planId = await saveToDB()
      if (!planId) return
    }

    const { data } = await runPipelineAgent({
      plan_id: planId,
      custom_data: customJobs.value.map((j) => mapJobPayload(j)),
      params: {
        solvers: selectedSolvers.value,
      },
    })

    if (data?.status === 'pending_confirm' && data?.pending_action?.confirm_token) {
      if (data.artifacts?.schedule_results) {
        store.setResults(data.artifacts.schedule_results)
        store.setImpactReport(null)
        await saveScheduleSnapshotToPlan(data.artifacts.schedule_results, {
          delivery_assessment: data.artifacts?.delivery_assessment,
        })
      }
      openPersistDialog(data.pending_action, data.summary_zh)
      ElMessage.success('排程完成，请确认是否落库')
      return
    }

    if (data?.status === 'success') {
      ElMessage.success(data.summary_zh || '流水线执行成功')
      if (data.artifacts?.schedule_results) {
        store.setResults(data.artifacts.schedule_results)
        await saveScheduleSnapshotToPlan(data.artifacts.schedule_results, {
          delivery_assessment: data.artifacts?.delivery_assessment,
        })
      }
      router.push('/reports')
      return
    }

    ElMessage.error(data?.error || data?.summary_zh || '流水线执行失败')
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElMessage.error(`流水线失败: ${detail || e?.message || e}`)
  } finally {
    pipelineRunning.value = false
    store.computing = false
  }
}

async function fetchBenchmarks() {
  try {
    const { data } = await api.get('/api/benchmarks')
    benchmarks.value = data.files || []
    if (!selectedBenchmark.value && benchmarks.value.length) selectedBenchmark.value = benchmarks.value[0]
  } catch (e) {
    ElMessage.error(`加载算例失败: ${e}`)
  }
}

async function pollAsyncRun(taskId) {
  for (let i = 0; i < 600; i += 1) {
    if (i > 0) await new Promise((r) => setTimeout(r, 1000))
    let statusData
    try {
      const res = await api.get(`/api/run/status/${taskId}`)
      statusData = res.data
    } catch (e) {
      if (e?.response?.status === 404) {
        throw new Error('异步任务不存在或后端未重启，请关闭「异步计算」后重试，或重启后端服务')
      }
      throw e
    }
    if (statusData?.status === 'failed') throw new Error(statusData.error || '异步排程失败')
    if (statusData?.status === 'completed') {
      const { data: resultData } = await api.get(`/api/run/result/${taskId}`)
      if (resultData?.error) throw new Error(resultData.error)
      return resultData
    }
  }
  throw new Error('异步排程超时，请稍后重试')
}

async function postRun(payload) {
  const { data } = await api.post('/api/run', payload)
  if (data?.error) throw new Error(data.error)
  return data
}

async function postRunMaybeAsync(payload) {
  if (!useAsyncRun.value) {
    return postRun(payload)
  }
  try {
    const { data: accepted } = await api.post('/api/run/async', payload)
    if (accepted?.error) throw new Error(accepted.error)
    if (!accepted?.task_id) throw new Error('未返回 task_id')
    ElMessage.info('已提交异步任务，正在计算…')
    return pollAsyncRun(accepted.task_id)
  } catch (e) {
    const status = e?.response?.status
    if (status === 404 || status === 405) {
      ElMessage.warning('当前后端不支持异步排程，已自动改为同步计算（请重启 tests/main.py 以启用异步 API）')
      return postRun(payload)
    }
    throw e
  }
}

async function previewScheduleIntent() {
  const msg = scheduleMessage.value?.trim()
  if (!msg) return ElMessage.warning('请先输入自然语言描述')
  if (inputMode.value !== 'custom') {
    return ElMessage.warning('自然语言排程请在「自定义/数据库」模式下使用')
  }
  if (!customJobs.value.length) return ElMessage.warning('请先添加工单')
  try {
    const { data } = await api.post('/api/agent/schedule', {
      message: msg,
      custom_data: customJobs.value.map((j) => mapJobPayload(j)),
      solvers: selectedSolvers.value,
      weights: { ...weights },
      enforce_material: enforceMaterial.value,
      parse_only: true,
    })
    const interp = data.interpretation || {}
    lastPlanner.value = data.planner || interp.planner || ''
    const lines = [
      interp.summary_zh || '',
      '',
      `解析方式：${lastPlanner.value || '—'}`,
      `策略：${interp.strategy_name || interp.strategy_id || '—'}`,
      `算法：${(interp.solvers || []).join(', ') || '—'}`,
    ]
    await ElMessageBox.alert(lines.join('\n'), '排程意图预览', { confirmButtonText: '知道了' })
  } catch (e) {
    ElMessage.error(`预览失败: ${e?.response?.data?.detail || e?.message || e}`)
  }
}

async function run() {
  store.computing = true
  try {
    const nlMsg = scheduleMessage.value?.trim()
    if (nlMsg && inputMode.value === 'custom' && customJobs.value.length) {
      const agentPayload = {
        message: nlMsg,
        custom_data: customJobs.value.map((j) => mapJobPayload(j)),
        solvers: selectedSolvers.value,
        weights: { ...weights },
        enforce_material: enforceMaterial.value,
      }
      if (randomSeed.value != null && randomSeed.value !== '') {
        agentPayload.random_seed = Number(randomSeed.value)
      }
      if (useAsyncRun.value) {
        agentPayload.async_run = true
      }
      const { data } = await api.post('/api/agent/schedule', agentPayload)
      if (data?.error) throw new Error(data.error)
      if (data.status === 'need_data') {
        throw new Error(data.message_zh || '缺少工单数据')
      }
      if (data.status === 'submitted' && data.task_id) {
        ElMessage.info('已提交异步任务，正在计算…')
        const resultPayload = await pollAsyncRun(data.task_id)
        const sid = data.interpretation?.strategy_id || selectedStrategyId.value
        if (sid) selectedStrategyId.value = sid
        syncStrategyToStore(sid)
        store.lastPayload = {
          ...agentPayload,
          strategy_id: sid || undefined,
          strategy_name: data.interpretation?.strategy_name,
        }
        store.setResults(resultPayload.data)
        store.setMaterialCheck(resultPayload.material_check || null)
        lastPlanner.value = data.planner || data.interpretation?.planner || ''
        if (currentPlanId.value) {
          await saveScheduleSnapshotToPlan(resultPayload.data, {
            interpretation: data.interpretation || undefined,
          })
        }
        router.push('/reports')
        return
      }
      if (data.status !== 'success') {
        throw new Error(data.error || data.status || '排程失败')
      }
      lastPlanner.value = data.planner || data.interpretation?.planner || ''
      const sid = data.interpretation?.strategy_id || selectedStrategyId.value
      if (sid) selectedStrategyId.value = sid
      syncStrategyToStore(sid)
      store.lastPayload = {
        ...agentPayload,
        strategy_id: sid || undefined,
        strategy_name: data.interpretation?.strategy_name,
      }
      store.currentPlanInput = customJobs.value
      store.currentPlanName = planName.value
      store.currentPlanId = currentPlanId.value
      store.setResults(data.data)
      store.setImpactReport(null)
      store.setMaterialCheck(data.material_check || null)
      if (data.material_check && !data.material_check.feasible) {
        materialCheckDialogVisible.value = true
        ElMessage.warning('排程完成，但物料静态预检显示库存不足')
      }
      if (currentPlanId.value) {
        await saveScheduleSnapshotToPlan(data.data, {
          interpretation: data.interpretation || undefined,
        })
      }
      router.push('/reports')
      return
    }

    const payload = {
      solvers: selectedSolvers.value,
      weights: { ...weights },
      strategy_id: selectedStrategyId.value || undefined,
    }
    if (selectedStrategyId.value) {
      const t = strategyTemplates.value.find((x) => x.id === selectedStrategyId.value)
      if (t?.name) payload.strategy_name = t.name
    }
    syncStrategyToStore(selectedStrategyId.value)
    if (randomSeed.value != null && randomSeed.value !== '') payload.random_seed = Number(randomSeed.value)
    if (inputMode.value === 'file') payload.benchmark_file = selectedBenchmark.value
    else {
      payload.custom_data = customJobs.value.map((j) => mapJobPayload(j))
      payload.enforce_material = enforceMaterial.value
    }

    store.lastPayload = payload
    store.currentPlanInput = customJobs.value
    store.currentPlanName = planName.value
    store.currentPlanId = currentPlanId.value

    let resultPayload = await postRunMaybeAsync(payload)
    if (resultPayload?.error) throw new Error(resultPayload.error)
    store.setResults(resultPayload.data)
    store.setImpactReport(null)
    store.setMaterialCheck(resultPayload.material_check || null)
    if (resultPayload.material_check) {
      materialCheckDialogVisible.value = !resultPayload.material_check.feasible
    }
    if (resultPayload.material_check && !resultPayload.material_check.feasible) {
      ElMessage.warning('排程完成，但物料静态预检显示库存不足，请在报表/物料页查看缺料')
    }

    if (currentPlanId.value && inputMode.value === 'custom') {
      await saveScheduleSnapshotToPlan(resultPayload.data, {
        interpretation: resultPayload.interpretation || undefined,
      })
    }
    router.push('/reports')
  } catch (e) {
    const status = e?.response?.status
    const detail = e?.response?.data?.detail
    const hint = status === 404
      ? '（接口不存在，请确认已用最新代码启动 tests/main.py 并 Ctrl+F5 刷新页面）'
      : ''
    ElMessage.error(`计算失败: ${detail || e?.message || e}${hint}`)
  } finally {
    store.computing = false
  }
}

async function fetchSolverCatalog() {
  catalogLoading.value = true
  try {
    const { data } = await api.get('/api/solvers/catalog')
    solverGroups.value = buildSolverGroupsFromCatalog(data.solvers, data.families)
    const ids = allSolverIds.value
    if (ids.length) {
      selectedSolvers.value = selectedSolvers.value.filter((id) => ids.includes(id))
      if (selectedSolvers.value.length === 0) {
        selectedSolvers.value = ids.includes('spt') && ids.includes('ts') ? ['spt', 'ts'] : ids.slice(0, 2)
      }
    }
  } catch (e) {
    console.warn('solver catalog', e)
    ElMessage.warning('算法目录加载失败，将使用默认选项')
    solverGroups.value = [
      { title: '规则启发式', items: [{ id: 'spt', name: 'SPT' }, { id: 'ts', name: 'Tabu Search' }] },
    ]
  } finally {
    catalogLoading.value = false
  }
}

async function fetchStrategyTemplates() {
  try {
    const { data } = await api.get('/api/strategy/templates')
    strategyTemplates.value = data.templates || []
  } catch (e) {
    console.warn('strategy templates', e)
  }
}

function hydratePlanFromStorage() {
  try {
    const raw = localStorage.getItem('aps_load_data')
    const planId = localStorage.getItem('aps_load_id') || ''
    const pName = localStorage.getItem('aps_load_plan_name') || ''
    const forceCustom = localStorage.getItem('aps_load_force_custom') === '1'
    let jobs = []
    if (raw != null && raw !== '') {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) jobs = parsed
    }
    if (forceCustom || planId || pName || jobs.length) {
      inputMode.value = 'custom'
      currentPlanId.value = planId
      planName.value = pName || planName.value
      selectedPlanId.value = planId
      customJobs.value = jobs.length ? normalizeJobs(jobs) : []
      syncWorkContextToStore()
      consumeApsLoadSchedule(store)
    }
    localStorage.removeItem('aps_load_data')
    localStorage.removeItem('aps_load_id')
    localStorage.removeItem('aps_load_plan_name')
    localStorage.removeItem('aps_load_force_custom')
    clearApsLoadScheduleKeys()
  } catch {
    // ignore invalid local storage payload
  }
}

watch(
  () => workContext.planId,
  (id) => {
    if (!id || id === currentPlanId.value) return
    const row = planList.value.find((o) => o.id === id) || {
      id,
      plan_name: workContext.planName,
      jobs: workContext.customJobs || [],
    }
    applyPlanFromOrder(row)
  }
)

onMounted(async () => {
  fetchBenchmarks()
  fetchSolverCatalog()
  fetchStrategyTemplates()
  fetchRoutingTemplates()
  fetchMaterialCatalog()
  await fetchPlans()
  hydratePlanFromStorage()
  if (!currentPlanId.value && workContext.planId) {
    const row = planList.value.find((o) => o.id === workContext.planId) || {
      id: workContext.planId,
      plan_name: workContext.planName,
      jobs: workContext.customJobs || [],
    }
    applyPlanFromOrder(row)
  }
  if (currentPlanId.value && inputMode.value === 'custom') {
    inputMode.value = 'custom'
  }
})
</script>

<style scoped>
.row { display:flex; align-items:center; gap: 12px; }
.h { font-weight: 700; }
.spacer { flex: 1; }
.plan-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
}
.plan-bar-label { font-size: 12px; color: #606266; font-weight: 600; white-space: nowrap; }
.plan-bar-select { width: min(280px, 100%); }
.plan-bar-name { width: min(200px, 100%); }
.plan-pool-banner { margin-bottom: 10px; }
.plan-empty-hint { margin: 16px 0; }
.toolbar { margin-bottom: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-lite { margin-bottom: 8px; }
.job-card :deep(.el-card__header) { padding: 10px 14px; }
.job-card :deep(.el-card__body) { padding: 10px 14px; overflow: hidden; }
.side-card :deep(.el-card__body) { overflow: hidden; }
.ops-panel {
  padding: 10px 12px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fdfefe;
}
.ops-title { font-size: 13px; font-weight: 700; color: #303133; margin-bottom: 10px; }
.ops-group { margin-bottom: 10px; }
.ops-group:last-child { margin-bottom: 0; }
.ops-label { font-size: 11px; color: #909399; margin-bottom: 4px; font-weight: 600; }
.ops-btns { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ops-tip { font-size: 11px; color: #909399; margin-top: 4px; line-height: 1.3; }
.planning-panel {
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #f6ffed;
}
.planning-hitl { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #dcdfe6; }
.planning-result { margin-top: 10px; padding-top: 8px; border-top: 1px solid #ebeef5; }
.planning-result-row { font-size: 12px; color: #303133; margin-bottom: 4px; }
.planning-result-k { color: #909399; margin-right: 8px; }
.planning-result-reason { font-size: 12px; color: #606266; line-height: 1.4; margin: 6px 0; }
.planning-violations { margin-top: 6px; }
.planning-violation-list { margin: 4px 0 0; padding-left: 18px; font-size: 11px; color: #f56c6c; }
.strategy-preview-collapse { margin-bottom: 8px; border: none; }
.strategy-preview-collapse :deep(.el-collapse-item__header) { font-size: 12px; height: 36px; }
.strategy-json-input :deep(textarea) { font-family: Consolas, Monaco, monospace; font-size: 11px; }
.weights-panel { padding: 12px; border: 1px solid #ebeef5; border-radius: 8px; background: #fafcff; margin-bottom: 12px; }
.weights-title { font-size: 13px; font-weight: 700; color: #303133; margin-bottom: 8px; }
.weights-form :deep(.el-form-item) { margin-bottom: 10px; }
.weights-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 10px; }
.job-card :deep(.el-card__header) { padding: 12px 16px; background: #fafbfc; border-bottom: 1px solid #ebeef5; }
.job-card :deep(.el-card__body) { padding: 14px 16px; }
.job-card { border: 1px solid #e4e7ed; margin-bottom: 4px; }
.job-head-grid {
  display: grid;
  grid-template-columns: minmax(160px, 2fr) minmax(180px, 1.4fr) 110px 100px auto;
  gap: 12px 16px;
  align-items: end;
}
.job-field { min-width: 0; }
.job-field-act { display: flex; align-items: flex-end; justify-content: flex-end; }
.field-label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
  line-height: 1.2;
}
.field-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-height: 24px; }
.field-full { width: 100% !important; }
.section-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.section-title { font-size: 14px; font-weight: 700; color: #303133; }
.section-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.data-table {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}
.data-row {
  display: grid;
  align-items: center;
  column-gap: 12px;
  padding: 8px 12px;
  min-width: 0;
}
.data-row-head {
  background: #f5f7fa;
  font-size: 13px;
  color: #606266;
  font-weight: 600;
  border-bottom: 1px solid #dcdfe6;
  min-height: 38px;
}
.data-row-body {
  border-bottom: 1px solid #f0f2f5;
}
.data-row-body:last-child { border-bottom: none; }
.task-item:nth-child(even) .data-row-body { background: #fcfcfd; }
.task-item:last-child .data-row-body { border-bottom: none; }
.task-row-cols {
  grid-template-columns: minmax(0, 1.6fr) 88px minmax(0, 1fr) 108px 72px;
}
.bom-row-cols {
  grid-template-columns: minmax(0, 2fr) 108px 128px 72px;
}
.cell-name, .cell-mach, .cell-alt, .cell-dur, .cell-act,
.cell-bom-mat, .cell-bom-qty, .cell-bom-mode, .cell-bom-act {
  min-width: 0;
}
.cell-act, .cell-bom-act { text-align: center; }
.cell-name :deep(.el-input),
.cell-alt :deep(.el-input),
.cell-bom-mat :deep(.el-select) { width: 100%; }
.duration-inline {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
}
.task-adv-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 10px 12px 12px;
  background: #f8f9fb;
  border-top: 1px dashed #e4e7ed;
  border-bottom: 1px solid #f0f2f5;
}
.adv-field { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.adv-label { font-size: 12px; color: #909399; }
.bom-block { margin-top: 16px; }
.bom-empty {
  font-size: 13px;
  color: #909399;
  padding: 12px 14px;
  background: #f5f7fa;
  border-radius: 6px;
  border: 1px dashed #dcdfe6;
}
.task-block { margin-bottom: 4px; }
.wlabel { font-weight: 700; color:#303133; font-size: 12px; line-height: 1.3; }
.wdesc { font-size: 11px; color: #909399; margin-top: 4px; line-height: 1.2; }
.whelp { margin-top: 2px; }
.due-label { font-size: 11px; color: #909399; }
.group-title { font-size: 12px; color: #909399; margin-bottom: 6px; font-weight: 700; }
.solver-list { display: grid; grid-template-columns: 1fr 1fr; row-gap: 6px; }
.solver-tag { margin-left: 6px; vertical-align: middle; }
@media (max-width: 1280px) {
  .weights-grid { grid-template-columns: 1fr; }
  .job-head-grid {
    grid-template-columns: 1fr 1fr;
  }
  .job-field-act {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
  .task-row-cols {
    grid-template-columns: minmax(0, 1.2fr) 76px minmax(0, 0.9fr) 96px 68px;
  }
  .bom-row-cols {
    grid-template-columns: minmax(0, 1.5fr) 96px 120px 68px;
  }
}
</style>

