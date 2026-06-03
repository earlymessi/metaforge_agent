<template>
  <el-dialog
    :model-value="modelValue"
    title="物料预检明细"
    width="820px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-empty v-if="!report" description="暂无预检数据" />
    <template v-else>
      <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
        <el-descriptions-item label="静态库存">
          <el-tag :type="staticFeasible ? 'success' : 'danger'" size="small">
            {{ staticFeasible ? '总量充足' : '总量不足' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="缺料预警">
          <el-tag :type="alertStats.total ? (alertStats.hasShortage ? 'danger' : 'warning') : 'success'" size="small">
            {{ alertSummaryText }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="总体结论">
          <el-tag :type="overallTagType" size="small">{{ overallLabel }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="库存汇总" name="summary">
          <el-table :data="summaryRows" size="small" stripe max-height="360" empty-text="无 BOM 需求">
            <el-table-column prop="material_name" label="物料" min-width="120" />
            <el-table-column prop="material_id" label="ID" width="110" />
            <el-table-column prop="required_total" label="总需求" width="100" align="right" />
            <el-table-column prop="available" label="库存" width="100" align="right" />
            <el-table-column prop="shortage" label="缺口" width="100" align="right">
              <template #default="{ row }">
                <span :style="{ color: row.shortage > 0 ? '#f56c6c' : '#67c23a', fontWeight: 600 }">
                  {{ row.shortage }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.feasible ? 'success' : 'danger'" size="small">
                  {{ row.feasible ? '充足' : '不足' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="按工单" name="jobs">
          <el-table :data="perJobRows" size="small" stripe max-height="360" empty-text="无工单 BOM">
            <el-table-column prop="job_name" label="工单" min-width="120" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.feasible ? 'success' : 'warning'" size="small">
                  {{ row.feasible ? 'OK' : '风险' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="明细" min-width="280">
              <template #default="{ row }">
                <span v-if="!row.lines?.length" class="muted">未配置 BOM</span>
                <span v-else>{{ formatJobLines(row.lines) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane v-if="alertStats.total" :label="`缺料预警 (${alertStats.total})`" name="alerts">
          <p class="hint">
            按甘特时刻仿真扣料：<b>缺料</b>表示库存为负；<b>预警</b>表示仍为正但低于安全库存线。
          </p>
          <el-table :data="materialAlerts" size="small" stripe max-height="320">
            <el-table-column label="类型" width="72" align="center">
              <template #default="{ row }">
                <el-tag :type="levelTagType(row.level)" size="small">{{ row.level_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="time" label="时刻 T" width="80" align="right" />
            <el-table-column prop="job_name" label="工单" min-width="120" />
            <el-table-column prop="name" label="物料" min-width="100" />
            <el-table-column prop="left" label="剩余库存" width="96" align="right">
              <template #default="{ row }">
                <span :class="row.level === 'shortage' ? 'num-danger' : 'num-warning'">{{ row.left }}</span>
              </template>
            </el-table-column>
            <el-table-column label="安全线" width="80" align="right">
              <template #default="{ row }">
                {{ row.level === 'warning' ? (row.safe_level ?? row.limit ?? '-') : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="consume_mode" label="扣料" width="80">
              <template #default="{ row }">
                {{ row.consume_mode === 'per_hour' ? '按小时' : '开工扣' }}
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </template>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { levelTagType, materialAlertStats } from '../utils/materialAlerts'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  report: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue'])

const activeTab = ref('summary')

const staticCheck = computed(() => {
  if (!props.report) return null
  if (props.report.static_check) return props.report.static_check
  if (props.report.summary || props.report.per_job) return props.report
  return null
})

const summaryRows = computed(() => staticCheck.value?.summary || [])
const perJobRows = computed(() => staticCheck.value?.per_job || [])
const staticFeasible = computed(() => staticCheck.value?.feasible !== false)

const alertStats = computed(() => materialAlertStats(props.report?.simulation))
const materialAlerts = computed(() => alertStats.value.all)

const alertSummaryText = computed(() => {
  const { total, shortageCount, warningCount } = alertStats.value
  if (!total) return '无'
  const parts = []
  if (shortageCount) parts.push(`缺料 ${shortageCount}`)
  if (warningCount) parts.push(`预警 ${warningCount}`)
  return `${total} 条（${parts.join('，')}）`
})

const overallLabel = computed(() => {
  if (alertStats.value.hasShortage) return '存在缺料'
  if (alertStats.value.hasWarning) return '有库存预警'
  if (!staticFeasible.value) return '静态库存不足'
  return '通过'
})

const overallTagType = computed(() => {
  if (alertStats.value.hasShortage || !staticFeasible.value) return 'danger'
  if (alertStats.value.hasWarning) return 'warning'
  return 'success'
})

watch(
  () => props.modelValue,
  (open) => {
    if (open) activeTab.value = alertStats.value.total ? 'alerts' : 'summary'
  },
)

function formatJobLines(lines) {
  return (lines || [])
    .map((l) => `${l.material_name || l.material_id}: 需${l.required} / 有${l.available}`)
    .join('；')
}
</script>

<style scoped>
.muted { color: #909399; font-size: 12px; }
.hint { color: #909399; font-size: 12px; margin: 0 0 8px; }
.num-danger { color: #f56c6c; font-weight: 600; }
.num-warning { color: #e6a23c; font-weight: 600; }
</style>
