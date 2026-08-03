<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="row">
          <div class="h">R0 / R1 / R2 对比</div>
          <div class="spacer" />
          <el-button :disabled="!payload" @click="downloadJson">导出 JSON</el-button>
          <el-button type="primary" :disabled="!payload" :loading="pdfLoading" @click="downloadPdf">
            导出 PDF
          </el-button>
          <el-button @click="router.push('/dashboard')">返回看板</el-button>
        </div>
      </template>

      <el-alert
        v-if="!impact"
        type="info"
        show-icon
        :closable="false"
        title="暂无对比数据。请先在看板完成异常重排或运行扰动剧本，再打开本页。"
      />

      <template v-else>
        <div class="metrics">
          <el-tag type="info">事件：{{ metrics.event_type || '—' }}</el-tag>
          <el-tag
            v-for="row in metrics.rows"
            :key="row.key"
            effect="plain"
          >
            {{ row.label }} · MS {{ formatNum(row.makespan) }}
          </el-tag>
          <el-tag effect="plain">延期明细 {{ metrics.delay_count }}</el-tag>
          <el-tag effect="plain">承诺变更 {{ metrics.commitment_count }}</el-tag>
        </div>
        <p v-if="metrics.summary_zh" class="summary">{{ metrics.summary_zh }}</p>

        <ImpactTripleGantt
          class="mt"
          :r0-gantt="payload.gantt.r0"
          :r1-gantt="payload.gantt.r1"
          :r2-gantt="payload.gantt.r2"
          :scenarios="payload.scenarios"
          :event-type="payload.event_type || ''"
          :rescheduled-keys="rescheduledKeys"
          :layers="layers"
        />
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ImpactTripleGantt from '../components/ImpactTripleGantt.vue'
import {
  buildCompareJson,
  exportComparePdf,
  extractCompareMetrics,
  loadImpactFromSession,
} from '../utils/compareExport'

const router = useRouter()
const impact = ref(loadImpactFromSession())
const pdfLoading = ref(false)

const payload = computed(() => (impact.value ? buildCompareJson(impact.value) : null))
const metrics = computed(() => extractCompareMetrics(impact.value || {}))
const rescheduledKeys = computed(() => impact.value?.rescheduled_op_keys || [])
const layers = computed(() => impact.value?.layers || {})

function formatNum(v) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(1) : String(v)
}

function downloadJson() {
  if (!payload.value) return
  const blob = new Blob([JSON.stringify(payload.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `metaforge-compare-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 JSON')
}

async function downloadPdf() {
  if (!payload.value) return
  pdfLoading.value = true
  try {
    await exportComparePdf(payload.value)
    ElMessage.success('已导出 PDF')
  } catch (e) {
    ElMessage.error(`PDF 导出失败: ${e?.message || e}（仍可导出 JSON）`)
  } finally {
    pdfLoading.value = false
  }
}
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.spacer {
  flex: 1;
}
.h {
  font-weight: 700;
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.summary {
  margin: 0 0 8px;
  font-size: 13px;
  color: #606266;
  white-space: pre-wrap;
}
.mt {
  margin-top: 12px;
}
</style>
