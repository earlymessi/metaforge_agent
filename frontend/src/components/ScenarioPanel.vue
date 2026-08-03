<template>
  <div class="scenario-panel">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="mb"
      title="运行剧本前请先在上方开始 MES 执行；步骤 event_type 须与现网事件一致（machine_breakdown / insert_order / due_date_change 等）。"
    />
    <div class="row">
      <el-select
        v-model="selectedPresetId"
        placeholder="加载预设剧本"
        clearable
        style="width: 200px"
        @change="onPresetChange"
      >
        <el-option
          v-for="p in presets"
          :key="p.id"
          :label="p.name"
          :value="p.id"
        />
      </el-select>
      <el-select
        v-model="selectedId"
        placeholder="已保存剧本"
        clearable
        style="width: 200px"
        @change="onSavedChange"
      >
        <el-option
          v-for="s in saved"
          :key="s.id"
          :label="s.name"
          :value="s.id"
        />
      </el-select>
      <el-input v-model="name" placeholder="剧本名称" style="width: 180px" />
      <el-button :loading="saving" @click="saveScenario">保存</el-button>
      <el-button type="primary" :loading="running" :disabled="!canRun" @click="runScenario">
        运行剧本
      </el-button>
      <el-button
        v-if="lastImpact"
        type="success"
        plain
        @click="openCompare"
      >
        打开对比
      </el-button>
    </div>

    <div class="field-label mt">Steps JSON</div>
    <el-input
      v-model="stepsJson"
      type="textarea"
      :rows="8"
      placeholder='[{"event_type":"machine_breakdown","params":{...}}]'
      class="json-input"
    />

    <div v-if="timeline.length" class="mt">
      <div class="field-label">运行时间线</div>
      <el-timeline>
        <el-timeline-item
          v-for="item in timeline"
          :key="item.index"
          :type="item.status === 'ok' ? 'success' : 'danger'"
          :timestamp="`#${item.index} ${item.event_type || '-'}`"
        >
          {{ item.status }}{{ item.error ? ` · ${item.error}` : '' }}
        </el-timeline-item>
      </el-timeline>
      <el-tag :type="runStatus === 'completed' ? 'success' : 'danger'" size="small">
        {{ runStatus || '—' }}
      </el-tag>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const IMPACT_KEY = 'metaforge_last_impact'

const emit = defineEmits(['ran'])

const router = useRouter()
const presets = ref([])
const saved = ref([])
const selectedPresetId = ref('')
const selectedId = ref('')
const name = ref('')
const stepsJson = ref('[]')
const saving = ref(false)
const running = ref(false)
const timeline = ref([])
const runStatus = ref('')
const lastImpact = ref(null)

const canRun = computed(() => {
  try {
    const steps = JSON.parse(stepsJson.value || '[]')
    return Array.isArray(steps) && steps.length > 0
  } catch {
    return false
  }
})

async function refreshList() {
  const [p, s] = await Promise.all([
    api.get('/api/scenarios/presets'),
    api.get('/api/scenarios'),
  ])
  presets.value = p.data?.items || []
  saved.value = s.data?.items || []
}

function applyScenario(sc) {
  if (!sc) return
  name.value = sc.name || ''
  stepsJson.value = JSON.stringify(sc.steps || [], null, 2)
}

function onPresetChange(id) {
  const sc = presets.value.find((x) => x.id === id)
  if (sc) {
    selectedId.value = ''
    applyScenario({ ...sc, name: `${sc.name}（副本）` })
  }
}

function onSavedChange(id) {
  const sc = saved.value.find((x) => x.id === id)
  if (sc) {
    selectedPresetId.value = ''
    applyScenario(sc)
  }
}

function parseSteps() {
  let steps
  try {
    steps = JSON.parse(stepsJson.value || '[]')
  } catch {
    throw new Error('Steps JSON 非法')
  }
  if (!Array.isArray(steps)) throw new Error('steps 必须是数组')
  for (const s of steps) {
    if (!s?.event_type) throw new Error('每步需要 event_type')
  }
  return steps
}

async function saveScenario() {
  saving.value = true
  try {
    const steps = parseSteps()
    const payload = { name: name.value || '未命名剧本', steps }
    let data
    if (selectedId.value) {
      const res = await api.put(`/api/scenarios/${selectedId.value}`, payload)
      data = res.data
    } else {
      const res = await api.post('/api/scenarios', payload)
      data = res.data
      selectedId.value = data.id
    }
    ElMessage.success('剧本已保存')
    await refreshList()
  } catch (e) {
    ElMessage.error(`保存失败: ${e?.response?.data?.detail || e.message || e}`)
  } finally {
    saving.value = false
  }
}

async function ensureSavedId() {
  if (selectedId.value) return selectedId.value
  const steps = parseSteps()
  const { data } = await api.post('/api/scenarios', {
    name: name.value || '未命名剧本',
    steps,
  })
  selectedId.value = data.id
  await refreshList()
  return data.id
}

async function runScenario() {
  running.value = true
  timeline.value = []
  runStatus.value = ''
  lastImpact.value = null
  try {
    const sid = await ensureSavedId()
    const { data } = await api.post(`/api/scenarios/${sid}/run`, {})
    timeline.value = data.timeline || []
    runStatus.value = data.status || ''
    lastImpact.value = data.impact || null
    if (data.impact) {
      sessionStorage.setItem(IMPACT_KEY, JSON.stringify(data.impact))
    }
    if (data.status === 'completed') {
      ElMessage.success('剧本运行完成')
    } else {
      ElMessage.warning('剧本中途失败，已停止后续步骤')
    }
    emit('ran', data)
  } catch (e) {
    ElMessage.error(`运行失败: ${e?.response?.data?.detail || e.message || e}`)
  } finally {
    running.value = false
  }
}

function openCompare() {
  if (lastImpact.value) {
    sessionStorage.setItem(IMPACT_KEY, JSON.stringify(lastImpact.value))
  }
  router.push({ path: '/compare' })
}

onMounted(async () => {
  try {
    await refreshList()
    if (presets.value.length) {
      selectedPresetId.value = presets.value[0].id
      onPresetChange(selectedPresetId.value)
    }
  } catch (e) {
    ElMessage.error(`加载剧本失败: ${e?.message || e}`)
  }
})
</script>

<style scoped>
.scenario-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mb {
  margin-bottom: 4px;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.field-label {
  font-size: 12px;
  color: #909399;
}
.mt {
  margin-top: 8px;
}
.json-input :deep(textarea) {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}
</style>
