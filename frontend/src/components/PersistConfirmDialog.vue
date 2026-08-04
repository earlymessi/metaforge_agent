<template>
  <el-dialog
    :model-value="modelValue"
    title="确认落库（Human-in-the-Loop）"
    width="680px"
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-empty v-if="!preview" description="无预览数据" />
    <template v-else>
      <el-alert
        v-if="summaryZh"
        type="info"
        :closable="false"
        show-icon
        :title="summaryZh"
        style="margin-bottom: 12px"
      />
      <el-alert
        v-if="preview.has_existing_schedule"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="该计划已有排程，确认后将覆盖原有排程与工单数据。"
      />

      <!-- 异常重排：R0 / R1 / R2 三场景对比（核心） -->
      <div v-if="showImpactCompare" class="compare-block">
        <div class="compare-title">重排效果对比（完工时间，越低越好）</div>
        <el-table :data="impactRows" size="small" stripe border class="compare-table">
          <el-table-column prop="label" label="场景" min-width="160" />
          <el-table-column prop="makespan" label="完工时间" width="120" align="right">
            <template #default="{ row }">
              <span :class="row.tone">{{ formatNum(row.makespan) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="说明" min-width="200" />
        </el-table>
        <p v-if="improvementHint" class="compare-hint">{{ improvementHint }}</p>
      </div>

      <el-descriptions v-if="preview.has_existing_schedule" :column="2" border size="small" style="margin-bottom: 12px">
        <el-descriptions-item label="操作类型">
          {{ preview.action_zh || '覆盖已有排程' }}
        </el-descriptions-item>
        <el-descriptions-item label="库中原算法">
          {{ preview.previous_best_solver || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="库中原 Makespan">
          {{ formatNum(preview.previous_makespan) }}
        </el-descriptions-item>
        <el-descriptions-item label="将写入 Makespan">
          {{ formatNum(preview.makespan ?? preview.r2_makespan) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="preview.jobs_update_count != null" label="工单数" :span="2">
          {{ preview.jobs_update_count }} 个（含插单/改交期）
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="计划名称" :span="2">
          {{ preview.plan_name || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="计划 ID">
          <span class="mono">{{ preview.plan_id || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item :label="solverRoleLabel">
          {{ preview.best_solver || preview.rescheduled_solver || '—' }}
          <el-tag v-if="preview.is_reschedule" size="small" type="info" class="solver-tip-tag">
            沿用执行基准算法，非多算法竞选
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Makespan">
          {{ formatNum(preview.makespan ?? preview.r2_makespan) }}
        </el-descriptions-item>
        <el-descriptions-item label="综合得分">
          {{ formatNum(preview.best_score) }}
        </el-descriptions-item>
        <el-descriptions-item label="交期结论">
          <el-tag size="small" :type="deliveryTagType(preview.delivery_overall)">
            {{ deliveryLabel(preview.delivery_overall) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="高风险工单">
          {{ preview.high_risk_count ?? (preview.high_risk_jobs || []).length }} 个
        </el-descriptions-item>
        <el-descriptions-item v-if="expiresAt" label="确认截止" :span="2">
          {{ formatExpires(expiresAt) }}
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="highRiskRows.length" class="risk-block">
        <div class="risk-title">高风险工单明细</div>
        <el-table :data="highRiskRows" size="small" stripe max-height="220">
          <el-table-column prop="job_name" label="工单" min-width="120" />
          <el-table-column prop="risk_level" label="风险" width="90">
            <template #default="{ row }">
              <el-tag type="danger" size="small">{{ row.risk_level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="predicted_completion" label="预测完工" width="110" align="right" />
          <el-table-column prop="due_date" label="交期" width="90" align="right" />
        </el-table>
      </div>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px"
        title="确认后将把排程结果写入数据库；取消可保留当前会话结果，稍后可重新发起。"
      />
    </template>

    <template #footer>
      <el-button @click="onCancel" :disabled="confirming">取消</el-button>
      <el-button type="primary" :loading="confirming" :disabled="!confirmToken" @click="onConfirm">
        {{ preview?.has_existing_schedule ? '确认覆盖写入' : '确认写入数据库' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmPersistSave } from '../api/client'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  confirmToken: { type: String, default: '' },
  preview: { type: Object, default: null },
  expiresAt: { type: String, default: '' },
  summaryZh: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'confirmed', 'cancelled'])

const confirming = ref(false)

const highRiskRows = computed(() => props.preview?.high_risk_jobs || [])

const showImpactCompare = computed(() => {
  const p = props.preview
  if (!p?.is_reschedule) return false
  return p.r0_makespan != null || p.r1_makespan != null || p.r2_makespan != null
})

const impactRows = computed(() => {
  const p = props.preview || {}
  const rows = [
    {
      key: 'r0',
      label: p.r0_label || '原计划 R0',
      makespan: p.r0_makespan,
      note: '故障前基准排程',
      tone: '',
    },
    {
      key: 'r1',
      label: p.r1_label || '不重排 R1',
      makespan: p.r1_makespan,
      note: '故障后只推延工序、不调用求解器',
      tone: 'tone-warn',
    },
    {
      key: 'r2',
      label: p.r2_label || '重排 R2',
      makespan: p.r2_makespan ?? p.makespan,
      note: `本次将写入库的结果（算法 ${p.rescheduled_solver || p.best_solver || '—'}）`,
      tone: 'tone-ok',
    },
  ]
  return rows.filter((r) => r.makespan != null && r.makespan !== '')
})

const improvementHint = computed(() => {
  const d = props.preview?.improvement_vs_r1?.makespan_delta
  if (d == null || d === '') return ''
  const n = Number(d)
  if (!Number.isFinite(n)) return ''
  if (n < -1e-6) return `相对不重排(R1)，重排后完工缩短 ${Math.abs(n).toFixed(2)} h。`
  if (n > 1e-6) return `相对不重排(R1)，重排后完工反而增加 ${n.toFixed(2)} h，请谨慎覆盖。`
  return '相对不重排(R1)，重排后完工时间基本持平。'
})

const solverRoleLabel = computed(
  () => props.preview?.solver_role_zh || (props.preview?.is_reschedule ? '本次重排算法' : '推荐算法'),
)

function formatNum(v) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : String(v)
}

function formatExpires(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function deliveryLabel(overall) {
  const map = {
    met: '可满足',
    partially_met: '部分满足',
    partial: '部分满足',
    not_met: '难以满足',
    unknown: '未知',
  }
  return map[overall] || overall || '—'
}

function deliveryTagType(overall) {
  if (overall === 'met') return 'success'
  if (overall === 'not_met') return 'danger'
  if (overall === 'partial' || overall === 'partially_met') return 'warning'
  return 'info'
}

function onCancel() {
  emit('update:modelValue', false)
  emit('cancelled')
}

async function onConfirm() {
  if (!props.confirmToken) {
    ElMessage.warning('缺少确认令牌')
    return
  }
  confirming.value = true
  try {
    const { data } = await confirmPersistSave(props.confirmToken)
    if (data?.error) throw new Error(data.error)
    ElMessage.success(
      props.preview?.has_existing_schedule ? '已覆盖更新计划排程与工单' : '排程结果已写入数据库'
    )
    emit('confirmed', data)
    emit('update:modelValue', false)
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElMessage.error(`落库失败: ${detail || e?.message || e}`)
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  word-break: break-all;
}
.risk-block {
  margin-top: 14px;
}
.risk-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}
.compare-block {
  margin-bottom: 14px;
}
.compare-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}
.compare-table {
  width: 100%;
}
.compare-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #606266;
}
.tone-warn {
  color: #e6a23c;
  font-weight: 600;
}
.tone-ok {
  color: #67c23a;
  font-weight: 600;
}
.solver-tip-tag {
  margin-left: 6px;
  vertical-align: middle;
}
</style>
