<template>
  <el-card shadow="never">
    <template #header>
      <div class="row">
        <div class="h">历史工单管理</div>
        <div class="spacer" />
        <el-button @click="fetchOrders" :loading="loading">刷新列表</el-button>
      </div>
    </template>

    <el-table :data="orders" stripe v-loading="loading">
      <el-table-column prop="plan_name" label="计划名称" min-width="180" />
      <el-table-column label="结果预览" width="110">
        <template #default="{ row }">
          <el-button v-if="row.chart_image" text type="primary" @click="showImage(row.chart_image)">查看</el-button>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="工单数量" width="100" align="right">
        <template #default="{ row }">{{ row.jobs ? row.jobs.length : 0 }}</template>
      </el-table-column>
      <el-table-column label="工序总数" width="100" align="right">
        <template #default="{ row }">{{ countOps(row) }}</template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="hasSchedule(row)" type="success" effect="plain">已排程</el-tag>
          <el-tag v-else :type="row.status === 'pending' ? 'warning' : 'info'">
            {{ row.status === 'pending' ? '待排程' : '无排程快照' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="loadToAPS(row)">导入排程</el-button>
          <el-button v-if="hasSchedule(row)" size="small" plain @click="openReports(row)">分析报表</el-button>
          <el-button size="small" type="success" plain @click="openAssistant(row)">智能助手</el-button>
          <el-button size="small" type="danger" plain @click="deleteOrder(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="imageDialogVisible" title="排程快照预览" width="75%">
    <div class="img-wrap">
      <img v-if="imageBase64" :src="imageBase64" class="snapshot" alt="schedule snapshot" />
    </div>
  </el-dialog>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useWorkContextStore } from '../stores/useWorkContextStore'
import { useAssistantStore } from '../stores/useAssistantStore'
import { useResultsStore } from '../stores/useResultsStore'
import {
  hasPlanSchedule,
  hydrateResultsStoreFromPlan,
  stashPlanLoadPayload,
} from '../utils/planScheduleSync'

const router = useRouter()
const workContext = useWorkContextStore()
const assistantStore = useAssistantStore()
const resultsStore = useResultsStore()

function hasSchedule(row) {
  return hasPlanSchedule(row)
}
const orders = ref([])
const loading = ref(false)
const imageDialogVisible = ref(false)
const imageBase64 = ref('')

async function fetchOrders() {
  loading.value = true
  try {
    const { data } = await api.get('/api/db/list')
    orders.value = Array.isArray(data) ? data : []
  } catch (e) {
    ElMessage.error(`加载历史工单失败: ${e}`)
  } finally {
    loading.value = false
  }
}

async function deleteOrder(id) {
  try {
    await ElMessageBox.confirm('确定删除该记录吗？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/db/delete/${id}`)
    ElMessage.success('删除成功')
    fetchOrders()
  } catch (e) {
    ElMessage.error(`删除失败: ${e}`)
  }
}

function loadToAPS(order) {
  stashPlanLoadPayload(order)
  workContext.setFromPlan({
    planId: order.id || '',
    planName: order.plan_name || '',
    jobs: order.jobs || [],
    source: 'database',
  })
  if (hydrateResultsStoreFromPlan(order, resultsStore)) {
    ElMessage.success('已导入工单与排程结果到排程中心')
  } else {
    ElMessage.success('已导入工单到排程中心（该计划尚无排程快照）')
  }
  router.push('/aps')
}

function openReports(order) {
  workContext.setFromPlan({
    planId: order.id || '',
    planName: order.plan_name || '',
    jobs: order.jobs || [],
    source: 'database',
  })
  if (!hydrateResultsStoreFromPlan(order, resultsStore)) {
    ElMessage.warning('该计划暂无排程结果，请先在排程中心或智能助手执行排程')
    return
  }
  router.push('/reports')
}

function openAssistant(order) {
  workContext.setFromPlan({
    planId: order.id || '',
    planName: order.plan_name || '历史计划',
    jobs: order.jobs || [],
    source: 'database',
  })
  assistantStore.open()
}

function countOps(order) {
  if (!order || !order.jobs) return 0
  return order.jobs.reduce((acc, job) => acc + (job.tasks ? job.tasks.length : 0), 0)
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString()
}

function showImage(base64) {
  imageBase64.value = base64
  imageDialogVisible.value = true
}

onMounted(fetchOrders)
</script>

<style scoped>
.row { display:flex; align-items:center; gap: 12px; }
.h { font-weight: 700; }
.spacer { flex: 1; }
.muted { color: #909399; }
.img-wrap { display:flex; justify-content:center; background:#f5f7fa; padding: 12px; }
.snapshot { max-width: 100%; border-radius: 6px; }
</style>

