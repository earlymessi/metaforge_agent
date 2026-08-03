<template>
  <div class="pkg-panel">
    <div class="pkg-header">
      <span class="pkg-label">推荐方案</span>
      <el-tag v-if="result?.hasRecommendation" type="success" size="small">
        {{ result.recommended_schedule_id }}
      </el-tag>
      <el-tag v-else type="warning" size="small">无合法推荐</el-tag>
    </div>

    <div v-if="metricEntries.length" class="pkg-section">
      <div class="pkg-label">KPI / Metrics</div>
      <div class="pkg-metrics">
        <el-tag
          v-for="[key, val] in metricEntries"
          :key="key"
          class="pkg-metric-tag"
          type="info"
          effect="plain"
        >
          {{ key }}: {{ formatValue(val) }}
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
    </div>

    <div class="pkg-section">
      <div class="pkg-label">候选对比</div>
      <el-table
        :data="candidates"
        size="small"
        stripe
        empty-text="暂无候选"
        class="pkg-candidates"
      >
        <el-table-column prop="schedule_id" label="schedule_id" min-width="100" />
        <el-table-column prop="solver" label="solver" min-width="100" />
        <el-table-column label="makespan" width="100">
          <template #default="{ row }">
            {{ formatValue(row.metrics?.makespan) }}
          </template>
        </el-table-column>
        <el-table-column label="tardiness" width="100">
          <template #default="{ row }">
            {{ formatValue(row.metrics?.tardiness) }}
          </template>
        </el-table-column>
        <el-table-column label="其它指标" min-width="140">
          <template #default="{ row }">
            {{ formatOtherMetrics(row.metrics) }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pkg-section">
      <div class="pkg-label">simulated_fields</div>
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

function formatOtherMetrics(metrics) {
  if (!metrics || typeof metrics !== 'object') return '—'
  const skip = new Set(['makespan', 'tardiness'])
  const entries = Object.entries(metrics).filter(([k]) => !skip.has(k))
  if (!entries.length) return '—'
  return entries.map(([k, v]) => `${k}=${formatValue(v)}`).join(', ')
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
