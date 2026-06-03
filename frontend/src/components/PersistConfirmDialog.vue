<template>
  <el-dialog
    :model-value="modelValue"
    title="确认落库（Human-in-the-Loop）"
    width="640px"
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
      <el-descriptions v-if="preview.has_existing_schedule" :column="2" border size="small" style="margin-bottom: 12px">
        <el-descriptions-item label="操作类型">
          {{ preview.action_zh || '覆盖已有排程' }}
        </el-descriptions-item>
        <el-descriptions-item label="原 Makespan">
          {{ formatNum(preview.previous_makespan) }}
        </el-descriptions-item>
        <el-descriptions-item label="原算法">
          {{ preview.previous_best_solver || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="新 Makespan">
          {{ formatNum(preview.makespan) }}
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
        <el-descriptions-item label="推荐算法">
          {{ preview.best_solver || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="Makespan">
          {{ formatNum(preview.makespan) }}
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
</style>
