<template>
  <div v-if="visible" class="agent-result-cards">
    <!-- 交期承诺 -->
    <el-card v-if="commitmentCard" shadow="never" class="result-card">
      <template #header>
        <span>交期评估</span>
        <el-tag :type="commitmentCard.overallTag" size="small" style="margin-left: 8px">
          {{ commitmentCard.overallLabel }}
        </el-tag>
      </template>
      <p v-if="commitmentCard.summary" class="muted">{{ commitmentCard.summary }}</p>
      <el-table
        v-if="commitmentCard.highRisk.length"
        :data="commitmentCard.highRisk"
        size="small"
        stripe
        max-height="200"
      >
        <el-table-column prop="job_name" label="工单" min-width="100" />
        <el-table-column prop="risk_level" label="风险" width="80">
          <template #default="{ row }">
            <el-tag type="danger" size="small">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="predicted_completion" label="预测完工" width="90" />
        <el-table-column prop="due_date" label="交期" width="80" />
        <el-table-column prop="verdict_zh" label="结论" min-width="120" />
      </el-table>
      <p v-else class="muted">暂无高风险工单。</p>
    </el-card>

    <!-- 方案对比 -->
    <el-card v-if="whatifCard" shadow="never" class="result-card">
      <template #header>
        <span>方案对比</span>
        <el-tag v-if="whatifCard.winner" type="success" size="small" style="margin-left: 8px">
          推荐：{{ whatifCard.winner }}
        </el-tag>
      </template>
      <p v-if="whatifCard.reason" class="muted">{{ whatifCard.reason }}</p>
      <el-table :data="whatifCard.rows" size="small" stripe>
        <el-table-column prop="label" label="方案" min-width="120" />
        <el-table-column prop="metric" label="指标值" width="100" />
        <el-table-column prop="solver" label="算法" width="100" />
        <el-table-column prop="note" label="备注" min-width="100" />
      </el-table>
    </el-card>

    <!-- 齐套（简要） -->
    <el-card v-if="kittingCard" shadow="never" class="result-card">
      <template #header>齐套摘要</template>
      <p>{{ kittingCard.recommendation }}</p>
      <el-tag v-if="kittingCard.can_start != null" :type="kittingCard.can_start ? 'success' : 'warning'" size="small">
        {{ kittingCard.can_start ? '可开工' : '暂不可开工' }}
      </el-tag>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  agentId: { type: String, default: '' },
  artifacts: { type: Object, default: null },
})

const visible = computed(() => !!(commitmentCard.value || whatifCard.value || kittingCard.value))

const commitmentCard = computed(() => {
  if (props.agentId !== 'commitment') return null
  const da = props.artifacts?.delivery_assessment
  if (!da) return null
  const overall = da.overall || 'unknown'
  const map = {
    met: { label: '可满足', tag: 'success' },
    partial: { label: '部分可满足', tag: 'warning' },
    not_met: { label: '难以满足', tag: 'danger' },
    unknown: { label: '待评估', tag: 'info' },
  }
  const o = map[overall] || map.unknown
  const jobs = da.jobs || []
  const highRisk = jobs.filter((j) => ['high', 'critical', 'medium'].includes(j.risk_level))
  return {
    overallLabel: o.label,
    overallTag: o.tag,
    summary: da.summary_zh || '',
    highRisk: highRisk.slice(0, 10),
  }
})

const whatifCard = computed(() => {
  if (props.agentId !== 'whatif') return null
  const wi = props.artifacts?.what_if
  if (!wi?.variants?.length) return null
  const src = wi.ranking?.length ? wi.ranking : wi.variants
  const rows = src.map((v) => ({
    label: v.label || v.variant_id,
    metric:
      v.best_score != null
        ? Number(v.best_score).toFixed(2)
        : v.makespan != null
          ? Number(v.makespan).toFixed(2)
          : '—',
    solver: v.best_solver || v.solver_id || '—',
    note: v.error || '',
  }))
  const winner = wi.recommended_label || wi.recommendation || null
  return {
    winner,
    reason: wi.recommendation_reason_zh || '',
    rows,
  }
})

const kittingCard = computed(() => {
  if (props.agentId !== 'kitting') return null
  const kr = props.artifacts?.kitting_report
  if (!kr) return null
  return {
    recommendation: kr.recommendation_zh || kr.summary_zh || '齐套检查已完成',
    can_start: kr.can_start,
  }
})
</script>

<style scoped>
.agent-result-cards {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.result-card :deep(.el-card__header) {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 8px;
}
</style>
