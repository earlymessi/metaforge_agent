<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="row">
          <div class="h">设备健康管控中心</div>
          <div class="spacer" />
          <el-select v-model="selectedAlgo" style="width:260px" @change="analyze" :disabled="!hasResults">
            <el-option v-for="r in sortedResults" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
          <el-button @click="refreshAll" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-alert
        v-if="!hasResults"
        type="info"
        show-icon
        title="等待排程数据"
        description="系统需要先生成排程方案，才能分析设备磨损情况。"
      />

      <el-row v-else :gutter="12" class="mt">
        <el-col :lg="8" :md="24">
          <el-card shadow="never">
            <template #header><div class="h2">机器磨损阈值（Config）</div></template>
            <el-table :data="limitsTable" size="small" max-height="520">
              <el-table-column prop="mid" label="Machine" width="110" />
              <el-table-column prop="power" label="功率(kW)" width="100" align="right" />
              <el-table-column prop="limit" label="红线阈值(h)" width="110" align="right" />
            </el-table>
          </el-card>
        </el-col>

        <el-col :lg="16" :md="24">
          <el-card shadow="never">
            <template #header>
              <div class="row">
                <div class="h2">连续负荷预警分析</div>
                <div class="spacer" />
                <el-tag :type="warnings.length ? 'danger' : 'success'">
                  {{ warnings.length ? `检测到 ${warnings.length} 项风险` : '设备运行健康' }}
                </el-tag>
              </div>
            </template>

            <el-empty
              v-if="warnings.length === 0"
              description="当前排程下，无机器超过连续工作时长红线。"
            />

            <el-table v-else :data="warnings" size="small" max-height="520">
              <el-table-column prop="machine" label="机器" width="90">
                <template #default="{ row }">M-{{ row.machine }}</template>
              </el-table-column>
              <el-table-column label="时段(Start-End)" min-width="140">
                <template #default="{ row }">T{{ row.start }} → T{{ row.end }}</template>
              </el-table-column>
              <el-table-column label="连续工作(h)" width="110" align="right">
                <template #default="{ row }">{{ row.duration.toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="阈值(h)" width="90" align="right">
                <template #default="{ row }">{{ row.limit.toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="达到阈值时刻" width="120" align="right">
                <template #default="{ row }">T{{ (row.start + row.limit).toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="超标时长" width="100" align="right">
                <template #default="{ row }">+{{ (row.duration - row.limit).toFixed(1) }}h</template>
              </el-table-column>
              <el-table-column label="操作" width="140">
                <template #default="{ row }">
                  <el-button size="small" type="danger" plain @click="generatePDF(row)">
                    生成维保单(PDF)
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { jsPDF } from 'jspdf'
import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'

const store = useResultsStore()
const loading = ref(false)
const config = ref(null)
const warnings = ref([])
const selectedAlgo = ref('')

const hasResults = computed(() => !!(store.results && Object.keys(store.results).length))
const sortedResults = computed(() => (store.results ? Object.values(store.results).sort((a, b) => a.best_score - b.best_score) : []))

const limitsTable = computed(() => {
  const limits = config.value?.maintenance_limits || {}
  const powers = config.value?.machine_powers || {}
  return Object.keys(limits).map((mid) => ({
    mid: `M-${mid}`,
    power: powers[mid] ?? '-',
    limit: Number(limits[mid]),
  }))
})

async function loadConfig() {
  const { data } = await api.get('/api/resources/config')
  config.value = data
}

function analyze() {
  if (!selectedAlgo.value || !store.results || !config.value) return
  const data = store.results[selectedAlgo.value]?.gantt_data || []
  const limits = config.value.maintenance_limits || {}
  const list = []

  const machineTasks = {}
  for (const t of data) {
    const mid = String(t.machine_id)
    if (!machineTasks[mid]) machineTasks[mid] = []
    machineTasks[mid].push(t)
  }

  Object.keys(machineTasks).forEach((mid) => {
    const tasks = machineTasks[mid].slice().sort((a, b) => a.start - b.start)
    const limit = Number(limits[mid] ?? 10.0)

    let seqStart = -1
    let lastEnd = -1
    let currentDur = 0

    tasks.forEach((t, i) => {
      const dur = Number(t.end) - Number(t.start)
      // 按旧版逻辑：必须严格连续（start == lastEnd）
      if (lastEnd === -1 || Number(t.start) !== Number(lastEnd)) {
        if (currentDur > limit) list.push({ machine: mid, start: seqStart, end: lastEnd, duration: currentDur, limit })
        seqStart = Number(t.start)
        currentDur = dur
      } else {
        currentDur += dur
      }
      lastEnd = Number(t.end)
      if (i === tasks.length - 1 && currentDur > limit) list.push({ machine: mid, start: seqStart, end: lastEnd, duration: currentDur, limit })
    })
  })

  warnings.value = list
}

function generatePDF(w) {
  const overload = (w.duration - w.limit).toFixed(1)
  const reachTime = (w.start + w.limit).toFixed(1)
  const now = new Date().toLocaleString()

  const doc = new jsPDF()
  doc.setFontSize(22)
  doc.setTextColor(220, 53, 69)
  doc.text('MAINTENANCE ORDER', 105, 20, null, null, 'center')

  doc.setFontSize(14)
  doc.setTextColor(0, 0, 0)
  doc.text(`Severity: HIGH (Overload by ${overload}h)`, 20, 40)

  doc.setLineWidth(0.5)
  doc.line(20, 45, 190, 45)

  doc.setFontSize(12)
  doc.text(`Issue Date: ${now}`, 20, 55)
  doc.text(`Target Machine: M-${w.machine}`, 20, 65)
  doc.text(`Work Interval: T${w.start} to T${w.end}`, 20, 75)

  doc.line(20, 85, 190, 85)
  doc.text('WEAR & TEAR ANALYSIS:', 20, 95)
  doc.text(`- Safe Limit: ${w.limit} hours`, 20, 105)
  doc.setFont(undefined, 'bold')
  doc.text(`- Threshold Reached At: T${reachTime} (System Time)`, 20, 115)
  doc.setFont(undefined, 'normal')
  doc.text(`- Actual Runtime: ${w.duration.toFixed(1)} hours`, 20, 125)
  doc.setTextColor(220, 53, 69)
  doc.text(`- Threshold Exceeded By: ${overload} hours`, 20, 135)

  doc.setTextColor(150)
  doc.setFontSize(10)
  doc.text('Generated by MetaForge MES System', 105, 280, null, null, 'center')
  doc.save(`Maintenance_Order_M${w.machine}_${Date.now()}.pdf`)
}

async function refreshAll() {
  loading.value = true
  try {
    await loadConfig()
    if (hasResults.value && sortedResults.value.length > 0) {
      if (!selectedAlgo.value) selectedAlgo.value = sortedResults.value[0].id
      analyze()
    }
  } catch (e) {
    ElMessage.error(`加载失败: ${e}`)
  } finally {
    loading.value = false
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display:flex; align-items:center; gap: 12px; }
.h, .h2 { font-weight: 700; }
.spacer { flex: 1; }
.mt { margin-top: 12px; }
</style>

