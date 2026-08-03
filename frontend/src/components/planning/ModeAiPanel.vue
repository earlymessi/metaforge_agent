<template>
  <div class="mode-ai-panel">
    <el-form label-position="top" class="mode-form">
      <el-form-item label="自然语言目标">
        <el-input
          v-model="userGoal"
          type="textarea"
          :rows="3"
          :disabled="disabled"
          placeholder="例如：交付优先，保证工单A按期，减少换型"
        />
      </el-form-item>

      <el-button
        type="primary"
        style="width: 100%"
        :disabled="disabled || !userGoal.trim()"
        @click="onRun"
      >
        AI 协同排产运行
      </el-button>

      <el-collapse
        v-if="hasAnalyses"
        v-model="analysisOpen"
        class="analysis-collapse"
      >
        <el-collapse-item title="三分析摘要（订单 / 约束 / 资源）" name="analyses">
          <div v-if="analyses?.order_analysis" class="analysis-row">
            <span class="analysis-k">订单</span>
            <span>{{ orderSummary }}</span>
          </div>
          <div v-if="analyses?.constraint_analysis" class="analysis-row">
            <span class="analysis-k">约束</span>
            <span>{{ constraintSummary }}</span>
          </div>
          <div v-if="analyses?.resource_analysis" class="analysis-row">
            <span class="analysis-k">资源</span>
            <span>{{ resourceSummary }}</span>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-form>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  analyses: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['run'])

const userGoal = ref('')
const analysisOpen = ref(['analyses'])

const hasAnalyses = computed(() => {
  const a = props.analyses
  if (!a || typeof a !== 'object') return false
  return !!(a.order_analysis || a.constraint_analysis || a.resource_analysis)
})

const orderSummary = computed(() => {
  const oa = props.analyses?.order_analysis
  if (!oa) return '—'
  if (oa.summary) return oa.summary
  const ids = oa.critical_orders || []
  return ids.length ? `关键订单：${ids.join('、')}` : '无关键订单'
})

const constraintSummary = computed(() => {
  const ca = props.analyses?.constraint_analysis
  if (!ca) return '—'
  if (ca.summary) return ca.summary
  const hard = (ca.hard_constraints || []).map((c) => c.type).filter(Boolean)
  const soft = (ca.soft_constraints || []).map((c) => c.type).filter(Boolean)
  const parts = []
  if (hard.length) parts.push(`硬：${hard.join(',')}`)
  if (soft.length) parts.push(`软：${soft.join(',')}`)
  return parts.join('；') || '无约束候选'
})

const resourceSummary = computed(() => {
  const ra = props.analyses?.resource_analysis
  if (!ra) return '—'
  if (ra.summary) return ra.summary
  const bn = ra.bottleneck_machines || []
  return bn.length ? `瓶颈设备：${bn.join('、')}` : '无瓶颈标记'
})

function onRun() {
  const goal = userGoal.value.trim()
  if (!goal) return
  emit('run', {
    user_goal: goal,
    skip_strategy_hitl: false,
  })
}
</script>

<style scoped>
.mode-ai-panel {
  width: 100%;
}

.mode-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.analysis-collapse {
  margin-top: 12px;
}

.analysis-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  margin: 4px 0;
  color: var(--el-text-color-regular);
}

.analysis-k {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--el-text-color-primary);
  min-width: 2.5em;
}
</style>
