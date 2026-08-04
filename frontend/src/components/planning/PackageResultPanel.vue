<template>
  <div class="pkg-panel">
    <div class="pkg-header">
      <span class="pkg-label">推荐方案</span>
      <template v-if="result?.hasRecommendation">
        <el-tag type="success" size="small">{{ result.recommended_label || result.recommended_schedule_id }}</el-tag>
        <el-tag type="info" size="small" effect="plain">代号 {{ result.recommended_schedule_id }}</el-tag>
      </template>
      <el-tag v-else type="warning" size="small">无合法推荐</el-tag>
    </div>

    <div v-if="metricEntries.length" class="pkg-section">
      <div class="pkg-label">推荐方案 KPI</div>
      <div class="pkg-metrics">
        <el-tag
          v-for="[key, val] in metricEntries"
          :key="key"
          class="pkg-metric-tag"
          type="info"
          effect="plain"
        >
          {{ metricLabel(key) }}: {{ formatValue(val) }}
        </el-tag>
      </div>
    </div>

    <div class="pkg-section">
      <div class="pkg-label">硬约束违反</div>
      <el-alert
        v-if="!violations.length"
        type="success"
        :closable="false"
        title="无硬约束违反"
        class="pkg-alert"
      />
      <ul v-else class="pkg-violations">
        <li v-for="(v, i) in violations" :key="i" class="pkg-violation-item">
          {{ formatViolation(v) }}
        </li>
      </ul>
      <p v-if="hiddenViolationCount > 0" class="pkg-muted">
        另有 {{ hiddenViolationCount }} 条未展示
      </p>
    </div>

    <div class="pkg-section">
      <div class="pkg-label">推荐理由</div>
      <p class="pkg-reason">{{ result?.recommendation_reason || '—' }}</p>
      <p class="pkg-muted">综合得分越低越好（硬约束通过的前提下）。</p>
    </div>

    <div class="pkg-section">
      <div class="pkg-label">候选对比</div>
      <el-table
        :data="candidates"
        size="small"
        stripe
        empty-text="暂无候选"
        class="pkg-candidates"
        :row-class-name="rowClassName"
      >
        <el-table-column label="排名" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_recommended" type="success" size="small" effect="dark">荐</el-tag>
            <span v-else>{{ row.rank ?? '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="算法" min-width="120">
          <template #default="{ row }">
            <div class="algo-cell">
              <strong>{{ row.solver_label || solverLabel(row.solver || row.schedule_id) }}</strong>
              <span class="algo-code">{{ row.schedule_id || row.solver }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="综合得分" width="100" align="right">
          <template #default="{ row }">
            {{ formatValue(row.score) }}
          </template>
        </el-table-column>
        <el-table-column label="硬约束" width="88" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.hard_ok === true" type="success" size="small">通过</el-tag>
            <el-tag v-else-if="row.hard_ok === false" type="danger" size="small">未过</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="完工时间" width="90" align="right">
          <template #default="{ row }">
            {{ formatValue(row.metrics?.makespan) }}
          </template>
        </el-table-column>
        <el-table-column label="拖期" width="90" align="right">
          <template #default="{ row }">
            {{ formatValue(row.metrics?.tardiness ?? row.metrics?.weighted_tardiness_total) }}
          </template>
        </el-table-column>
        <el-table-column label="对比结论" min-width="160">
          <template #default="{ row }">
            <span :class="compareClass(row)">{{ row.compare_hint || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pkg-section">
      <div class="pkg-label">策略推演字段</div>
      <div v-if="simulatedFields.length" class="pkg-sim-fields">
        <el-tag
          v-for="field in simulatedFields"
          :key="field"
          size="small"
          class="pkg-sim-tag"
        >
          {{ field }}
        </el-tag>
      </div>
      <p v-else class="pkg-muted">无</p>
    </div>

    <div class="pkg-actions">
      <el-button
        type="primary"
        :disabled="!result?.hasRecommendation || sending"
        :loading="sending"
        @click="emit('send-to-sim')"
      >
        送入执行仿真
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { metricLabel, solverLabel } from './packageExtract.js'

const props = defineProps({
  result: {
    type: Object,
    default: null,
  },
  sending: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['send-to-sim'])

const MAX_VIOLATIONS = 8

const metricEntries = computed(() => {
  const m = props.result?.metrics
  if (!m || typeof m !== 'object') return []
  return Object.entries(m)
})

const violations = computed(() => {
  const list = props.result?.hard_violations
  if (!Array.isArray(list)) return []
  return list.slice(0, MAX_VIOLATIONS)
})

const hiddenViolationCount = computed(() => {
  const list = props.result?.hard_violations
  if (!Array.isArray(list)) return 0
  return Math.max(0, list.length - MAX_VIOLATIONS)
})

const candidates = computed(() =>
  Array.isArray(props.result?.candidates) ? props.result.candidates : [],
)

const simulatedFields = computed(() =>
  Array.isArray(props.result?.simulated_fields) ? props.result.simulated_fields : [],
)

function formatValue(val) {
  if (val == null || val === '') return '—'
  if (typeof val === 'number') return Number.isInteger(val) ? String(val) : val.toFixed(2)
  return String(val)
}

function formatViolation(v) {
  if (v == null) return '—'
  if (typeof v === 'string') return v
  const parts = []
  if (v.schedule_id) parts.push(v.schedule_id)
  if (v.type) parts.push(v.type)
  if (v.message) parts.push(v.message)
  if (parts.length) return parts.join(' · ')
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function rowClassName({ row }) {
  if (row?.is_recommended) return 'pkg-row-recommended'
  if (row?.hard_ok === false) return 'pkg-row-illegal'
  return ''
}

function compareClass(row) {
  if (row?.is_recommended) return 'cmp-best'
  if (row?.hard_ok === false) return 'cmp-bad'
  if (String(row?.compare_hint || '').includes('较差')) return 'cmp-worse'
  if (String(row?.compare_hint || '').includes('更好')) return 'cmp-better'
  return ''
}
</script>

<style scoped>
.pkg-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pkg-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pkg-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pkg-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.pkg-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pkg-metric-tag {
  margin: 0;
}

.pkg-alert {
  padding: 8px 12px;
}

.pkg-violations {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--el-color-danger);
}

.pkg-violation-item {
  margin: 2px 0;
}

.pkg-reason {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.pkg-candidates {
  width: 100%;
}

.pkg-candidates :deep(.pkg-row-recommended) {
  --el-table-tr-bg-color: var(--el-color-success-light-9);
}

.pkg-candidates :deep(.pkg-row-illegal) {
  --el-table-tr-bg-color: var(--el-color-danger-light-9);
}

.algo-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.2;
}

.algo-code {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.cmp-best {
  color: var(--el-color-success);
  font-weight: 600;
}

.cmp-worse {
  color: var(--el-color-warning);
}

.cmp-better {
  color: var(--el-color-success);
}

.cmp-bad {
  color: var(--el-color-danger);
}

.pkg-sim-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pkg-sim-tag {
  margin: 0;
}

.pkg-muted {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.pkg-actions {
  margin-top: 4px;
}
</style>
