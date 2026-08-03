<template>
  <div class="constraint-editor">
    <el-collapse v-model="openPanels">
      <el-collapse-item title="硬约束" name="hard">
        <div
          v-for="(row, index) in hardList"
          :key="'hard-' + index"
          class="constraint-row"
        >
          <el-select
            :model-value="row.type"
            placeholder="类型"
            filterable
            class="constraint-type"
            @update:model-value="(v) => setType('hard', index, v)"
          >
            <el-option
              v-for="opt in hardCatalog"
              :key="opt.type"
              :label="opt.type"
              :value="opt.type"
            />
          </el-select>
          <el-input
            :model-value="paramStr(row, 'job_id')"
            placeholder="job_id"
            clearable
            class="constraint-field"
            @update:model-value="(v) => setParam('hard', index, 'job_id', v)"
          />
          <el-input
            :model-value="paramStr(row, 'due')"
            placeholder="due"
            clearable
            class="constraint-field"
            @update:model-value="(v) => setParam('hard', index, 'due', v)"
          />
          <el-input
            :model-value="paramsJson(row)"
            placeholder='params JSON，如 {"job_id":"A"}'
            class="constraint-json"
            @update:model-value="(v) => setParamsJson('hard', index, v)"
          />
          <el-button
            type="danger"
            text
            size="small"
            @click="removeRow('hard', index)"
          >
            删除
          </el-button>
        </div>
        <el-button size="small" type="primary" plain @click="addRow('hard')">
          添加硬约束
        </el-button>
      </el-collapse-item>

      <el-collapse-item title="软约束" name="soft">
        <div
          v-for="(row, index) in softList"
          :key="'soft-' + index"
          class="constraint-row"
        >
          <el-select
            :model-value="row.type"
            placeholder="类型"
            filterable
            class="constraint-type"
            @update:model-value="(v) => setType('soft', index, v)"
          >
            <el-option
              v-for="opt in softCatalog"
              :key="opt.type"
              :label="opt.type"
              :value="opt.type"
            />
          </el-select>
          <el-input
            :model-value="paramStr(row, 'job_id')"
            placeholder="job_id"
            clearable
            class="constraint-field"
            @update:model-value="(v) => setParam('soft', index, 'job_id', v)"
          />
          <el-input
            :model-value="paramStr(row, 'due')"
            placeholder="due"
            clearable
            class="constraint-field"
            @update:model-value="(v) => setParam('soft', index, 'due', v)"
          />
          <el-input
            :model-value="paramsJson(row)"
            placeholder='params JSON，如 {"penalty":1}'
            class="constraint-json"
            @update:model-value="(v) => setParamsJson('soft', index, v)"
          />
          <el-button
            type="danger"
            text
            size="small"
            @click="removeRow('soft', index)"
          >
            删除
          </el-button>
        </div>
        <el-button size="small" type="primary" plain @click="addRow('soft')">
          添加软约束
        </el-button>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({ hard_constraints: [], soft_constraints: [] }),
  },
  catalog: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:modelValue'])

const openPanels = ref(['hard', 'soft'])

const hardList = computed(() =>
  Array.isArray(props.modelValue?.hard_constraints)
    ? props.modelValue.hard_constraints
    : [],
)

const softList = computed(() =>
  Array.isArray(props.modelValue?.soft_constraints)
    ? props.modelValue.soft_constraints
    : [],
)

const hardCatalog = computed(() =>
  (props.catalog || []).filter((c) => c?.kind === 'hard' && c?.type),
)

const softCatalog = computed(() =>
  (props.catalog || []).filter((c) => c?.kind === 'soft' && c?.type),
)

function cloneValue() {
  return {
    hard_constraints: hardList.value.map((r) => ({ ...r })),
    soft_constraints: softList.value.map((r) => ({ ...r })),
  }
}

function emitValue(next) {
  emit('update:modelValue', next)
}

function listKey(kind) {
  return kind === 'hard' ? 'hard_constraints' : 'soft_constraints'
}

function catalogFor(kind) {
  return kind === 'hard' ? hardCatalog.value : softCatalog.value
}

function addRow(kind) {
  const opts = catalogFor(kind)
  if (!opts.length) return
  const next = cloneValue()
  next[listKey(kind)].push({ type: opts[0].type })
  emitValue(next)
}

function removeRow(kind, index) {
  const next = cloneValue()
  next[listKey(kind)].splice(index, 1)
  emitValue(next)
}

function setType(kind, index, type) {
  const allowed = new Set(catalogFor(kind).map((c) => c.type))
  if (!allowed.has(type)) return
  const next = cloneValue()
  next[listKey(kind)][index] = { ...next[listKey(kind)][index], type }
  emitValue(next)
}

function paramStr(row, key) {
  const v = row?.[key]
  return v == null ? '' : String(v)
}

function setParam(kind, index, key, raw) {
  const next = cloneValue()
  const row = { ...next[listKey(kind)][index] }
  const trimmed = typeof raw === 'string' ? raw.trim() : raw
  if (trimmed === '' || trimmed == null) {
    delete row[key]
  } else if (key === 'due' && !Number.isNaN(Number(trimmed)) && trimmed !== '') {
    row[key] = Number(trimmed)
  } else {
    row[key] = trimmed
  }
  next[listKey(kind)][index] = row
  emitValue(next)
}

function paramsJson(row) {
  if (!row || typeof row !== 'object') return '{}'
  const params = { ...row }
  delete params.type
  try {
    return JSON.stringify(params)
  } catch {
    return '{}'
  }
}

function setParamsJson(kind, index, raw) {
  const text = (raw || '').trim()
  let parsed = {}
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      return
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return
  }
  const next = cloneValue()
  const type = next[listKey(kind)][index]?.type
  next[listKey(kind)][index] = { type, ...parsed }
  emitValue(next)
}
</script>

<style scoped>
.constraint-editor {
  width: 100%;
}

.constraint-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}

.constraint-type {
  width: 180px;
}

.constraint-field {
  width: 110px;
}

.constraint-json {
  flex: 1;
  min-width: 160px;
}
</style>
