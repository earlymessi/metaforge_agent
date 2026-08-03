<template>
  <div class="mode-parameter-panel">
    <el-form label-position="top" class="mode-form">
      <div class="section-title">目标权重（越小越好）</div>
      <div class="weights-grid">
        <el-form-item label="Makespan">
          <el-input-number
            v-model="objectives.makespan"
            :step="0.1"
            :min="0"
            controls-position="right"
            style="width: 100%"
            :disabled="disabled"
          />
        </el-form-item>
        <el-form-item label="加权交期违约">
          <el-input-number
            v-model="objectives.weighted_tardiness_total"
            :step="0.1"
            :min="0"
            controls-position="right"
            style="width: 100%"
            :disabled="disabled"
          />
        </el-form-item>
        <el-form-item label="能耗成本">
          <el-input-number
            v-model="objectives.energy_cost"
            :step="0.01"
            :min="0"
            controls-position="right"
            style="width: 100%"
            :disabled="disabled"
          />
        </el-form-item>
        <el-form-item label="负载均衡 CV">
          <el-input-number
            v-model="objectives.machine_busy_cv"
            :step="0.5"
            :min="0"
            controls-position="right"
            style="width: 100%"
            :disabled="disabled"
          />
        </el-form-item>
      </div>

      <el-form-item label="关键订单 critical_orders">
        <el-select
          v-model="criticalOrders"
          multiple
          filterable
          clearable
          placeholder="从当前工单多选"
          style="width: 100%"
          :disabled="disabled"
        >
          <el-option
            v-for="id in jobIds"
            :key="id"
            :label="id"
            :value="id"
          />
        </el-select>
      </el-form-item>

      <div class="section-title">硬 / 软约束</div>
      <ConstraintEditor v-model="constraints" :catalog="catalog" />

      <el-collapse v-model="jsonOpen" class="json-collapse">
        <el-collapse-item title="Strategy JSON（可选编辑）" name="json">
          <el-input
            v-model="strategyJson"
            type="textarea"
            :rows="8"
            :disabled="disabled"
            class="strategy-json-input"
            placeholder="可粘贴完整 strategy JSON；应用后覆盖上方表单"
          />
          <div class="json-actions">
            <el-button size="small" :disabled="disabled" @click="syncJsonFromForm">
              从表单刷新 JSON
            </el-button>
            <el-button size="small" type="primary" plain :disabled="disabled" @click="applyJsonToForm">
              从 JSON 应用到表单
            </el-button>
          </div>
          <el-alert
            v-if="jsonError"
            type="error"
            :closable="false"
            :title="jsonError"
            class="mode-alert"
          />
        </el-collapse-item>
      </el-collapse>

      <el-alert
        v-if="catalogError"
        type="error"
        :closable="false"
        :title="catalogError"
        class="mode-alert"
      />

      <div class="ops-btns">
        <el-button
          type="primary"
          plain
          :disabled="disabled || catalogLoading"
          :loading="catalogLoading"
          @click="onValidate"
        >
          校验策略
        </el-button>
        <el-button
          type="success"
          :disabled="disabled || catalogLoading"
          @click="onRun"
        >
          运行（需 HITL）
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../api/client'
import ConstraintEditor from './ConstraintEditor.vue'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  jobIds: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['validate', 'run'])

const objectives = reactive({
  makespan: 1.0,
  weighted_tardiness_total: 0.5,
  energy_cost: 0.05,
  machine_busy_cv: 10.0,
})

const criticalOrders = ref([])
const constraints = ref({
  hard_constraints: [],
  soft_constraints: [],
})
const catalog = ref([])
const catalogLoading = ref(false)
const catalogError = ref('')
const strategyJson = ref('')
const jsonOpen = ref([])
const jsonError = ref('')

function buildStrategy() {
  return {
    objectives: { ...objectives },
    critical_orders: [...criticalOrders.value],
    hard_constraints: (constraints.value.hard_constraints || []).map((c) => ({ ...c })),
    soft_constraints: (constraints.value.soft_constraints || []).map((c) => ({ ...c })),
    generated_by: 'user',
  }
}

function syncJsonFromForm() {
  jsonError.value = ''
  strategyJson.value = JSON.stringify(buildStrategy(), null, 2)
}

function applyJsonToForm() {
  jsonError.value = ''
  try {
    const parsed = JSON.parse(strategyJson.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('JSON 必须是对象')
    }
    const objs = parsed.objectives || {}
    objectives.makespan = Number(objs.makespan ?? objectives.makespan)
    objectives.weighted_tardiness_total = Number(
      objs.weighted_tardiness_total ?? objectives.weighted_tardiness_total,
    )
    objectives.energy_cost = Number(objs.energy_cost ?? objectives.energy_cost)
    objectives.machine_busy_cv = Number(objs.machine_busy_cv ?? objectives.machine_busy_cv)
    criticalOrders.value = Array.isArray(parsed.critical_orders)
      ? parsed.critical_orders.map(String)
      : []
    constraints.value = {
      hard_constraints: Array.isArray(parsed.hard_constraints)
        ? parsed.hard_constraints.map((c) => ({ ...c }))
        : [],
      soft_constraints: Array.isArray(parsed.soft_constraints)
        ? parsed.soft_constraints.map((c) => ({ ...c }))
        : [],
    }
  } catch (e) {
    jsonError.value = e?.message || 'JSON 解析失败'
  }
}

function onValidate() {
  const strategy = buildStrategy()
  syncJsonFromForm()
  emit('validate', { strategy })
}

function onRun() {
  const strategy = buildStrategy()
  syncJsonFromForm()
  emit('run', {
    strategy,
    skip_strategy_hitl: false,
  })
}

async function loadCatalog() {
  catalogLoading.value = true
  catalogError.value = ''
  try {
    const { data } = await api.get('/api/planning/constraints/catalog')
    catalog.value = Array.isArray(data?.catalog)
      ? data.catalog
      : Array.isArray(data)
        ? data
        : []
  } catch (e) {
    catalogError.value = e?.message || '加载约束 catalog 失败'
    catalog.value = []
  } finally {
    catalogLoading.value = false
  }
}

watch(
  () => props.jobIds,
  (ids) => {
    const allowed = new Set((ids || []).map(String))
    criticalOrders.value = criticalOrders.value.filter((id) => allowed.has(String(id)))
  },
)

onMounted(() => {
  loadCatalog()
  syncJsonFromForm()
})
</script>

<style scoped>
.mode-parameter-panel {
  width: 100%;
}

.mode-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  margin: 4px 0;
  color: var(--el-text-color-primary);
}

.weights-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 8px;
}

.json-collapse {
  margin: 8px 0;
}

.json-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.strategy-json-input {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.ops-btns {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.mode-alert {
  margin-top: 8px;
}
</style>
