<template>
  <div class="fab-lab">
    <div class="lab-head">
      <div>
        <div class="lab-title">FAB 研究台</div>
        <div class="lab-sub">
          导入场景默认配置 → 在建模页自定义修改 → 选择 FAB 方法求解（与通用 APS 隔离）
        </div>
      </div>
      <el-tag type="warning" effect="plain">一期：无真训练 · 训练步已预留</el-tag>
    </div>

    <el-steps :active="stageIndex" finish-status="success" align-center class="lab-steps">
      <el-step
        v-for="(s, i) in stages"
        :key="s.id"
        :title="s.title"
        :description="s.desc"
        @click="goStage(i)"
        class="lab-step-click"
      />
    </el-steps>

    <!-- 业务 -->
    <el-card v-show="stage === 'business'" shadow="never" class="lab-card">
      <template #header><div class="card-h">1. 业务场景（导入默认配置）</div></template>
      <el-form inline>
        <el-form-item label="场景包">
          <el-select v-model="selectedId" placeholder="选择 Mini-Fab 场景" style="width: 320px" :loading="loadingList">
            <el-option
              v-for="s in scenarios"
              :key="s.scenario_id"
              :label="`${s.title || s.scenario_id}（${s.area}）`"
              :value="s.scenario_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loadingLoad" @click="loadScenario">载入默认配置 → 建模</el-button>
        </el-form-item>
      </el-form>

      <template v-if="defaults">
        <el-descriptions :column="2" border size="small" class="mb">
          <el-descriptions-item label="scenario_id">{{ defaults.scenario_id }}</el-descriptions-item>
          <el-descriptions-item label="工区">{{ defaults.fab_meta?.area }}</el-descriptions-item>
        </el-descriptions>
        <el-alert :title="failureModeText" type="info" :closable="false" show-icon class="mb" />
        <div class="section-label">物理依据</div>
        <ul class="ref-list">
          <li v-for="(r, i) in (defaults.fab_meta?.physics_refs || [])" :key="i">{{ r }}</li>
        </ul>
        <div class="section-label">明确不建模</div>
        <ul class="ref-list warn">
          <li v-for="(r, i) in (defaults.fab_meta?.out_of_scope || [])" :key="i">{{ r }}</li>
        </ul>
      </template>
      <el-empty v-else description="选择场景包载入默认配置（后续可在建模页改）" />
    </el-card>

    <!-- 建模（可编辑） -->
    <el-card v-show="stage === 'model'" shadow="never" class="lab-card">
      <template #header>
        <div class="card-h row-between">
          <span>2. 形式化建模（可编辑）</span>
          <div class="head-actions">
            <el-tag v-if="modelDirty" type="warning" size="small">已修改</el-tag>
            <el-tag v-else type="info" size="small">默认配置</el-tag>
            <el-button size="small" @click="resetModel">恢复默认</el-button>
          </div>
        </div>
      </template>
      <template v-if="model">
        <el-alert
          class="mb"
          type="success"
          :closable="false"
          show-icon
          title="流程：场景包只提供初始默认值。下面各表可直接改；进入求解时使用当前草稿，不会写回 YAML。"
        />

        <el-tabs v-model="modelTab">
          <el-tab-pane label="机台" name="machines">
            <div class="tab-toolbar">
              <el-button size="small" @click="addMachine">添加机台</el-button>
            </div>
            <el-table :data="model.machines" size="small" border>
              <el-table-column label="id" min-width="100">
                <template #default="{ row }">
                  <el-input v-model="row.id" size="small" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="type" min-width="120">
                <template #default="{ row }">
                  <el-input v-model="row.type" size="small" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="index" width="100">
                <template #default="{ row }">
                  <el-input-number v-model="row.machine_index" size="small" :min="0" controls-position="right" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="max_batch" width="120">
                <template #default="{ row }">
                  <el-input-number v-model="row.max_batch_size" size="small" :min="1" controls-position="right" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="removeMachine($index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="Lots / 工序" name="lots">
            <div class="tab-toolbar">
              <el-button size="small" @click="addLot">添加 Lot</el-button>
            </div>
            <el-collapse v-model="openLots">
              <el-collapse-item v-for="(job, jIdx) in model.jobs" :key="jIdx" :name="String(jIdx)">
                <template #title>
                  <div class="lot-title">
                    <span>{{ job.job_id || job.name || `Lot-${jIdx}` }}</span>
                    <el-tag size="small" type="info">family={{ job.family_id || '—' }}</el-tag>
                    <el-tag size="small">{{ (job.tasks || []).length }} ops</el-tag>
                  </div>
                </template>
                <el-form label-width="90px" size="small" class="lot-form">
                  <el-row :gutter="8">
                    <el-col :span="6">
                      <el-form-item label="job_id">
                        <el-input v-model="job.job_id" @change="syncJobName(job); markDirty()" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="6">
                      <el-form-item label="family_id">
                        <el-input v-model="job.family_id" @change="markDirty" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="6">
                      <el-form-item label="priority">
                        <el-input-number v-model="job.priority" :min="1" controls-position="right" @change="markDirty" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="6">
                      <el-form-item label="release">
                        <el-input-number v-model="job.material_arrival" :min="0" :step="0.5" controls-position="right" @change="markDirty" />
                      </el-form-item>
                    </el-col>
                  </el-row>
                </el-form>
                <div class="tab-toolbar">
                  <el-button size="small" @click="addTask(job)">添加工序</el-button>
                  <el-button size="small" type="danger" plain @click="removeLot(jIdx)">删除 Lot</el-button>
                </div>
                <el-table :data="job.tasks || []" size="small" border>
                  <el-table-column label="工序名" min-width="110">
                    <template #default="{ row }">
                      <el-input v-model="row.name" size="small" @change="markDirty" />
                    </template>
                  </el-table-column>
                  <el-table-column label="process_area" width="120">
                    <template #default="{ row }">
                      <el-input v-model="row.process_area" size="small" @change="markDirty" />
                    </template>
                  </el-table-column>
                  <el-table-column label="layer" width="80">
                    <template #default="{ row }">
                      <el-input-number v-model="row.layer_index" size="small" :min="1" controls-position="right" @change="markDirty" />
                    </template>
                  </el-table-column>
                  <el-table-column label="粘机标记" width="90">
                    <template #default="{ row }">
                      <el-switch v-model="row.is_dedication_mark" @change="markDirty" />
                    </template>
                  </el-table-column>
                  <el-table-column label="machine_id" width="110">
                    <template #default="{ row }">
                      <el-input-number v-model="row.machine_id" size="small" :min="0" controls-position="right" @change="markDirty" />
                    </template>
                  </el-table-column>
                  <el-table-column label="options(逗号)" min-width="120">
                    <template #default="{ row }">
                      <el-input
                        :model-value="(row.machine_options || []).join(',')"
                        size="small"
                        @update:model-value="(v) => setOptions(row, v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="duration" width="100">
                    <template #default="{ row }">
                      <el-input-number v-model="row.duration" size="small" :min="1" controls-position="right" @change="markDirty" />
                    </template>
                  </el-table-column>
                  <el-table-column label="" width="60">
                    <template #default="{ $index }">
                      <el-button link type="danger" size="small" @click="removeTask(job, $index)">删</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </el-tab-pane>

          <el-tab-pane label="硬约束" name="hard">
            <div class="tab-toolbar">
              <el-select v-model="newHardType" placeholder="约束类型" size="small" style="width: 220px">
                <el-option v-for="t in fabHardTypes" :key="t" :label="t" :value="t" />
              </el-select>
              <el-button size="small" type="primary" @click="addHard">添加</el-button>
            </div>
            <el-table :data="model.strategy_defaults.hard_constraints" size="small" border>
              <el-table-column label="type" min-width="180">
                <template #default="{ row }">
                  <el-select v-model="row.type" size="small" @change="markDirty">
                    <el-option v-for="t in fabHardTypes" :key="t" :label="t" :value="t" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="from_op" width="140">
                <template #default="{ row }">
                  <el-input v-model="row.from_op" size="small" :disabled="row.type !== 'max_lag_between_ops'" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="to_op" width="140">
                <template #default="{ row }">
                  <el-input v-model="row.to_op" size="small" :disabled="row.type !== 'max_lag_between_ops'" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="max_lag" width="110">
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.max_lag"
                    size="small"
                    :min="0"
                    :step="0.5"
                    :disabled="row.type !== 'max_lag_between_ops'"
                    controls-position="right"
                    @change="markDirty"
                  />
                </template>
              </el-table-column>
              <el-table-column label="" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="removeHard($index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="Timelinks" name="timelinks">
            <div class="tab-toolbar">
              <el-button size="small" @click="addTimelink">添加时间窗</el-button>
            </div>
            <el-table :data="model.fab_meta.timelinks" size="small" border>
              <el-table-column label="from_op" min-width="140">
                <template #default="{ row }">
                  <el-input v-model="row.from_op" size="small" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="to_op" min-width="140">
                <template #default="{ row }">
                  <el-input v-model="row.to_op" size="small" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="max_lag" width="120">
                <template #default="{ row }">
                  <el-input-number v-model="row.max_lag" size="small" :min="0" :step="0.5" controls-position="right" @change="markDirty" />
                </template>
              </el-table-column>
              <el-table-column label="" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="removeTimelink($index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-alert
              class="mb"
              style="margin-top: 10px"
              type="info"
              :closable="false"
              title="光刻/扩散场景可留空；刻蚀时间窗场景在此改 Q。求解评价会读 fab_meta.timelinks。"
            />
          </el-tab-pane>
        </el-tabs>

        <div class="stage-actions">
          <el-button @click="stage = 'business'">上一步</el-button>
          <el-button type="primary" @click="enterSolve">用当前模型进入求解</el-button>
        </div>
      </template>
      <el-empty v-else description="请先在「业务」载入默认配置" />
    </el-card>

    <!-- 求解 -->
    <el-card v-show="stage === 'solve'" shadow="never" class="lab-card">
      <template #header><div class="card-h">3. 选择算法 / 方法</div></template>
      <template v-if="model">
        <el-alert class="mb" type="warning" :closable="false" show-icon>
          <template #title>
            不是通用 GA/TS 勾选。请按工区选一张方法卡：先看「推荐」，再看「何时用」。
            当前工区：<b>{{ model.fab_meta?.area }}</b>
            · 模型：{{ modelDirty ? '已自定义' : '默认配置' }}
          </template>
        </el-alert>

        <el-radio-group v-model="selectedMethod" class="method-radio">
          <div
            v-for="m in methods"
            :key="m.id"
            class="method-card"
            :class="{ active: selectedMethod === m.id }"
            @click="selectedMethod = m.id"
          >
            <div class="method-top">
              <el-radio :label="m.id">{{ m.title }}</el-radio>
              <el-tag v-if="m.recommended" type="success" size="small">推荐</el-tag>
            </div>
            <div class="method-id">{{ m.id }}</div>
            <div class="method-sum">{{ m.summary }}</div>
            <div class="method-when"><b>何时选：</b>{{ m.when_to_use || '—' }}</div>
          </div>
        </el-radio-group>

        <el-table :data="methods" size="small" border class="mb" style="margin-top: 8px">
          <el-table-column prop="title" label="方法" min-width="140" />
          <el-table-column label="推荐" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.recommended" type="success" size="small">是</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="when_to_use" label="何时选用" min-width="220" />
        </el-table>

        <div class="stage-actions">
          <el-button @click="stage = 'model'">回建模改参数</el-button>
          <el-button type="primary" :loading="solving" :disabled="!selectedMethod" @click="runSolve">
            用「{{ selectedMethodLabel }}」运行实验
          </el-button>
        </div>
      </template>
      <el-empty v-else description="请先载入并完成建模" />
    </el-card>

    <!-- 结果 -->
    <el-card v-show="stage === 'results'" shadow="never" class="lab-card">
      <template #header>
        <div class="card-h row-between">
          <span>4. 结果与约束解释</span>
          <el-tag v-if="solveResult" :type="solveResult.schedule?.fab_hard_ok ? 'success' : 'danger'">
            hard_ok={{ solveResult.schedule?.fab_hard_ok }}
          </el-tag>
        </div>
      </template>
      <template v-if="solveResult">
        <div class="section-label">method_trace</div>
        <el-timeline class="mb">
          <el-timeline-item v-for="(t, i) in solveResult.method_trace || []" :key="i" :timestamp="t.step">
            {{ t.detail }}
          </el-timeline-item>
        </el-timeline>
        <el-descriptions :column="3" size="small" border class="mb">
          <el-descriptions-item label="method">{{ solveResult.method }}</el-descriptions-item>
          <el-descriptions-item label="makespan">{{ solveResult.schedule?.metrics?.makespan ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="violations">{{ (solveResult.fab_evaluation?.hard_violations || []).length }}</el-descriptions-item>
        </el-descriptions>
        <div class="section-label">硬约束违反</div>
        <el-table
          v-if="(solveResult.fab_evaluation?.hard_violations || []).length"
          :data="solveResult.fab_evaluation.hard_violations"
          size="small"
          border
          class="mb"
        >
          <el-table-column prop="type" label="约束" width="200" />
          <el-table-column prop="message" label="解释" min-width="320" />
        </el-table>
        <el-alert v-else title="无硬约束违反" type="success" :closable="false" class="mb" />
        <div class="section-label">甘特（简化）</div>
        <div class="mini-gantt">
          <div v-for="(op, i) in ganttRows" :key="i" class="gantt-row">
            <div class="gantt-label">{{ op.label }}</div>
            <div class="gantt-track">
              <div class="gantt-bar" :style="{ left: op.left + '%', width: Math.max(op.width, 1.5) + '%' }" :title="op.title" />
            </div>
          </div>
        </div>
        <div class="stage-actions">
          <el-button @click="stage = 'solve'">换方法</el-button>
          <el-button @click="stage = 'model'">改模型再跑</el-button>
          <el-button type="primary" @click="stage = 'train'">训练占位</el-button>
        </div>
      </template>
      <el-empty v-else description="请先运行实验" />
    </el-card>

    <el-card v-show="stage === 'train'" shadow="never" class="lab-card">
      <template #header><div class="card-h">5. 训练（二期预留）</div></template>
      <el-result icon="info" title="一期不做真训练" sub-title="POST /api/fab/research/train 已占位。">
        <template #extra>
          <el-button type="primary" disabled>开始训练</el-button>
          <el-button @click="probeTrain">探测占位接口</el-button>
        </template>
      </el-result>
      <el-alert v-if="trainProbe" :title="trainProbe" type="warning" :closable="false" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const stages = [
  { id: 'business', title: '业务', desc: '导入默认' },
  { id: 'model', title: '建模', desc: '可编辑' },
  { id: 'solve', title: '求解', desc: '选方法' },
  { id: 'results', title: '结果', desc: '可解释' },
  { id: 'train', title: '训练', desc: '二期' },
]

const fabHardTypes = [
  'photo_machine_dedication',
  'max_lag_between_ops',
  'batch_same_family',
  'batch_capacity',
  'batch_synchronized',
]

const stage = ref('business')
const stageIndex = computed(() => Math.max(0, stages.findIndex((s) => s.id === stage.value)))

const scenarios = ref([])
const selectedId = ref('')
const loadingList = ref(false)
const loadingLoad = ref(false)
const defaults = ref(null)
const model = ref(null)
const modelDirty = ref(false)
const modelTab = ref('lots')
const openLots = ref(['0'])
const newHardType = ref('photo_machine_dedication')
const methods = ref([])
const selectedMethod = ref('')
const solving = ref(false)
const solveResult = ref(null)
const trainProbe = ref('')

const FAILURE = {
  photolithography: '失效模式：natural bias → overlay → 硬约束 photo_machine_dedication。',
  etch_timelink: '失效模式：表面时效 → 硬约束 max_lag_between_ops。',
  diffusion_furnace: '失效模式：混炉污染 + 热同步 → 同族批/容量/同步。',
}

const failureModeText = computed(() => FAILURE[defaults.value?.fab_meta?.area] || '请载入场景。')
const selectedMethodLabel = computed(() => {
  const m = methods.value.find((x) => x.id === selectedMethod.value)
  return m?.title || selectedMethod.value || '—'
})

const ganttRows = computed(() => {
  const gantt = solveResult.value?.schedule?.gantt_data || []
  if (!gantt.length) return []
  const maxEnd = Math.max(...gantt.map((o) => Number(o.end || 0)), 1)
  return gantt.map((o) => {
    const start = Number(o.start || 0)
    const end = Number(o.end || start)
    const label = `${o.job_name || o.job_id} / ${o.operation_name || 'op'} @M${o.machine_id}`
    return {
      label,
      left: (start / maxEnd) * 100,
      width: ((end - start) / maxEnd) * 100,
      title: `${label} [${start}, ${end}]`,
    }
  })
})

function clone(obj) {
  return JSON.parse(JSON.stringify(obj))
}

function markDirty() {
  modelDirty.value = true
}

function normalizeDraft(data) {
  const d = clone(data)
  d.jobs = (d.jobs || []).map((j) => ({
    ...j,
    job_id: j.job_id || j.name,
    name: j.name || j.job_id,
    priority: j.priority ?? 10,
    family_id: j.family_id ?? '',
    material_arrival: j.material_arrival ?? 0,
    tasks: (j.tasks || []).map((t) => ({
      ...t,
      machine_options: Array.isArray(t.machine_options)
        ? t.machine_options
        : t.machine_id != null
          ? [t.machine_id]
          : [0],
      is_dedication_mark: !!t.is_dedication_mark,
      duration: t.duration ?? 1,
    })),
  }))
  d.machines = d.machines || []
  d.strategy_defaults = d.strategy_defaults || { hard_constraints: [], soft_constraints: [], objectives: {} }
  d.strategy_defaults.hard_constraints = d.strategy_defaults.hard_constraints || []
  d.fab_meta = d.fab_meta || {}
  d.fab_meta.timelinks = d.fab_meta.timelinks || []
  return d
}

function resetModel() {
  if (!defaults.value) return
  model.value = normalizeDraft(defaults.value)
  modelDirty.value = false
  ElMessage.success('已恢复为场景默认配置')
}

function syncJobName(job) {
  job.name = job.job_id
}

function setOptions(row, text) {
  row.machine_options = String(text || '')
    .split(',')
    .map((x) => Number(String(x).trim()))
    .filter((n) => Number.isInteger(n) && n >= 0)
  markDirty()
}

function addMachine() {
  const idx = (model.value.machines || []).length
  model.value.machines.push({ id: `M${idx}`, type: 'generic', machine_index: idx })
  markDirty()
}
function removeMachine(i) {
  model.value.machines.splice(i, 1)
  markDirty()
}
function addLot() {
  const n = (model.value.jobs || []).length + 1
  model.value.jobs.push({
    job_id: `L${n}`,
    name: `L${n}`,
    priority: 10,
    family_id: '',
    material_arrival: 0,
    tasks: [{ name: 'op1', process_area: '', duration: 1, machine_id: 0, machine_options: [0] }],
  })
  openLots.value = [...openLots.value, String(model.value.jobs.length - 1)]
  markDirty()
}
function removeLot(i) {
  model.value.jobs.splice(i, 1)
  markDirty()
}
function addTask(job) {
  if (!job.tasks) job.tasks = []
  job.tasks.push({ name: `op${job.tasks.length + 1}`, process_area: '', duration: 1, machine_id: 0, machine_options: [0] })
  markDirty()
}
function removeTask(job, i) {
  job.tasks.splice(i, 1)
  markDirty()
}
function addHard() {
  const t = newHardType.value || 'photo_machine_dedication'
  const row = { type: t }
  if (t === 'max_lag_between_ops') {
    row.from_op = 'wet_clean'
    row.to_op = 'diffusion'
    row.max_lag = 1.5
  }
  model.value.strategy_defaults.hard_constraints.push(row)
  markDirty()
}
function removeHard(i) {
  model.value.strategy_defaults.hard_constraints.splice(i, 1)
  markDirty()
}
function addTimelink() {
  model.value.fab_meta.timelinks.push({ from_op: '', to_op: '', max_lag: 1.5 })
  markDirty()
}
function removeTimelink(i) {
  model.value.fab_meta.timelinks.splice(i, 1)
  markDirty()
}

function goStage(i) {
  if (!defaults.value && i > 0) return ElMessage.warning('请先载入默认配置')
  if (stages[i].id === 'results' && !solveResult.value) return ElMessage.warning('请先运行实验')
  stage.value = stages[i].id
}

async function fetchScenarios() {
  loadingList.value = true
  try {
    const { data } = await api.get('/api/fab/scenarios')
    scenarios.value = data.scenarios || []
    if (!selectedId.value && scenarios.value.length) selectedId.value = scenarios.value[0].scenario_id
  } catch (e) {
    ElMessage.error(`场景列表失败: ${e?.response?.data?.detail || e.message || e}`)
  } finally {
    loadingList.value = false
  }
}

async function loadScenario() {
  if (!selectedId.value) return ElMessage.warning('请选择场景')
  loadingLoad.value = true
  try {
    const { data } = await api.post(`/api/fab/scenarios/${selectedId.value}/load`)
    defaults.value = data
    model.value = normalizeDraft(data)
    modelDirty.value = false
    openLots.value = model.value.jobs.map((_, i) => String(i))
    solveResult.value = null
    const area = data.fab_meta?.area
    const { data: md } = await api.get('/api/fab/research/methods', { params: { area } })
    methods.value = md.methods || []
    const rec = methods.value.find((m) => m.recommended) || methods.value[0]
    selectedMethod.value = rec?.id || ''
    stage.value = 'model'
    modelTab.value = 'lots'
    ElMessage.success(`已导入默认配置 ${data.scenario_id}，可在建模页修改`)
  } catch (e) {
    ElMessage.error(`载入失败: ${e?.response?.data?.detail || e.message || e}`)
  } finally {
    loadingLoad.value = false
  }
}

async function enterSolve() {
  stage.value = 'solve'
  const area = model.value?.fab_meta?.area
  if (area) {
    const { data: md } = await api.get('/api/fab/research/methods', { params: { area } })
    methods.value = md.methods || []
    if (!methods.value.find((m) => m.id === selectedMethod.value)) {
      selectedMethod.value = (methods.value.find((m) => m.recommended) || methods.value[0])?.id || ''
    }
  }
}

function buildModelPayload() {
  const m = model.value
  return {
    jobs: m.jobs,
    machines: m.machines,
    strategy_defaults: m.strategy_defaults,
    fab_meta: m.fab_meta,
  }
}

async function runSolve() {
  if (!selectedMethod.value || !model.value) return
  solving.value = true
  try {
    const { data } = await api.post('/api/fab/research/solve', {
      scenario_id: model.value.scenario_id || defaults.value.scenario_id,
      method: selectedMethod.value,
      model: buildModelPayload(),
    })
    solveResult.value = data
    stage.value = 'results'
    ElMessage.success('实验完成（已使用当前建模草稿）')
  } catch (e) {
    ElMessage.error(`求解失败: ${e?.response?.data?.detail || e.message || e}`)
  } finally {
    solving.value = false
  }
}

async function probeTrain() {
  try {
    const { data } = await api.post('/api/fab/research/train', {
      scenario_id: defaults.value?.scenario_id || selectedId.value,
      algo: 'dqn',
      epochs: 10,
    })
    trainProbe.value = `${data.status}: ${data.message}`
  } catch (e) {
    trainProbe.value = String(e?.response?.data?.detail || e.message || e)
  }
}

onMounted(fetchScenarios)
</script>

<style scoped>
.fab-lab { padding: 4px 2px 24px; }
.lab-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
.lab-title { font-size: 20px; font-weight: 700; }
.lab-sub { color: #606266; font-size: 13px; margin-top: 4px; max-width: 760px; }
.lab-steps { margin: 8px 0 20px; }
.lab-step-click { cursor: pointer; }
.lab-card { margin-bottom: 12px; }
.card-h { font-weight: 700; }
.row-between { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.head-actions { display: flex; align-items: center; gap: 8px; }
.section-label { font-weight: 600; font-size: 13px; margin: 8px 0 6px; }
.ref-list { margin: 0 0 12px 18px; color: #606266; font-size: 13px; }
.ref-list.warn { color: #b88230; }
.mb { margin-bottom: 12px; }
.tab-toolbar { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.lot-title { display: flex; gap: 8px; align-items: center; font-weight: 600; }
.lot-form { margin-bottom: 8px; }
.method-radio { display: block; width: 100%; }
.method-card {
  border: 1px solid #dcdfe6; border-radius: 8px; padding: 12px; margin-bottom: 10px;
  cursor: pointer; background: #fff;
}
.method-card:hover { border-color: #409eff; }
.method-card.active { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64,158,255,.15); }
.method-top { display: flex; justify-content: space-between; align-items: center; }
.method-id { font-size: 12px; color: #909399; margin: 4px 0 6px; }
.method-sum { font-size: 13px; color: #606266; }
.method-when { font-size: 12px; color: #303133; margin-top: 8px; }
.stage-actions { margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap; }
.mini-gantt { border: 1px solid #ebeef5; border-radius: 6px; padding: 8px; background: #fafafa; }
.gantt-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.gantt-label { width: 220px; font-size: 12px; color: #606266; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gantt-track { flex: 1; height: 18px; background: #eef1f6; border-radius: 4px; position: relative; }
.gantt-bar {
  position: absolute; top: 2px; height: 14px; border-radius: 3px;
  background: linear-gradient(90deg, #409eff, #79bbff);
}
</style>
