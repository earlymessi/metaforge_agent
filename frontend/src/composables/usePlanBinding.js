import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useWorkContextStore } from '../stores/useWorkContextStore'
import { findPlanByQuery, parsePlanNlCommand } from '../utils/planNlCommands'
import { stashPlanLoadPayload } from '../utils/planScheduleSync'

export function usePlanBinding() {
  const router = useRouter()
  const workStore = useWorkContextStore()
  const planList = ref([])
  const plansLoading = ref(false)
  const selectedPlanId = ref('')

  const planOptions = computed(() =>
    (planList.value || []).map((o) => ({
      id: o.id || '',
      label: `${o.plan_name || '未命名'}（${(o.jobs || []).length} 工单）`,
      order: o,
    }))
  )

  function bindOrder(order) {
    if (!order) return false
    const jobs = order.jobs || []
    workStore.setFromPlan({
      planId: order.id || '',
      planName: order.plan_name || '未命名计划',
      jobs: jobs.length ? jobs : null,
      source: 'manual',
    })
    selectedPlanId.value = order.id || ''
    return true
  }

  function clearBinding() {
    workStore.clear()
    selectedPlanId.value = ''
  }

  /** 与数据中心「导入排程」一致 */
  function goToAps(order) {
    stashPlanLoadPayload(order || { jobs: [] })
    bindOrder(order)
    router.push('/aps')
  }

  async function fetchPlans() {
    plansLoading.value = true
    try {
      const { data } = await api.get('/api/db/list')
      planList.value = Array.isArray(data) ? data : []
      if (workStore.planId && !selectedPlanId.value) {
        selectedPlanId.value = workStore.planId
      }
    } catch (e) {
      ElMessage.error(`加载计划列表失败：${e?.message || e}`)
    } finally {
      plansLoading.value = false
    }
  }

  async function createPlan(name, { navigateAps = false } = {}) {
    let planName = (name || '').trim()
    if (!planName) {
      try {
        const { value } = await ElMessageBox.prompt('请输入新计划名称', '新建计划', {
          confirmButtonText: '创建',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '名称不能为空',
        })
        planName = value.trim()
      } catch {
        return { ok: false, cancelled: true }
      }
    }
    try {
      const { data } = await api.post('/api/db/save', {
        plan_name: planName,
        jobs: [],
        status: 'pending',
      })
      if (data?.status !== 'success' && !data?.id) {
        throw new Error(data?.message || '保存未返回计划 ID')
      }
      await fetchPlans()
      const created = planList.value.find((o) => o.id === data?.id) || {
        id: data?.id,
        plan_name: planName,
        jobs: [],
      }
      bindOrder(created)
      ElMessage.success(`已创建并绑定计划「${planName}」`)
      const reply =
        `已创建计划「${planName}」并写入数据库。` +
        (navigateAps ? '正在打开排程中心，可添加工单并排程。' : '可在排程中心编辑工单，或继续用自然语言下达调度指令。')
      if (navigateAps) goToAps(created)
      return { ok: true, plan: created, reply, navigateAps }
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || String(e)
      ElMessage.error(`创建失败：${msg}`)
      return { ok: false, error: msg }
    }
  }

  async function selectPlanByQuery(query, { navigateAps = false } = {}) {
    await fetchPlans()
    const found = findPlanByQuery(planList.value, query)
    if (!found) {
      return { ok: false, reply: `未找到匹配「${query}」的计划，请检查名称或先说「刷新计划列表」。` }
    }
    if (found.ambiguous) {
      const names = found.matches.slice(0, 5).map((o) => o.plan_name).join('、')
      return { ok: false, reply: `匹配到多个计划：${names}… 请说得更具体一些。` }
    }
    bindOrder(found)
    const n = (found.jobs || []).length
    ElMessage.success(`已绑定：${found.plan_name}`)
    if (navigateAps) goToAps(found)
    return {
      ok: true,
      reply: `已绑定计划「${found.plan_name}」（${n} 个工单）。${navigateAps ? '已打开排程中心。' : n ? '可直接描述故障重排、齐套等需求。' : '该计划暂无工单，已可去排程中心编辑。'}`,
      navigateAps,
    }
  }

  async function deletePlanByQuery(query) {
    await fetchPlans()
    const found = findPlanByQuery(planList.value, query)
    if (!found) {
      return { ok: false, reply: `未找到要删除的计划「${query}」。` }
    }
    if (found.ambiguous) {
      const names = found.matches.slice(0, 5).map((o) => o.plan_name).join('、')
      return { ok: false, reply: `匹配到多个计划：${names}… 请指定更具体的名称。` }
    }
    try {
      await ElMessageBox.confirm(`确定删除计划「${found.plan_name}」？此操作不可恢复。`, '删除确认', {
        type: 'warning',
      })
    } catch {
      return { ok: false, reply: '已取消删除。' }
    }
    try {
      await api.delete(`/api/db/delete/${found.id}`)
      if (workStore.planId === found.id) clearBinding()
      await fetchPlans()
      ElMessage.success('已删除')
      return { ok: true, reply: `已删除计划「${found.plan_name}」。` }
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || String(e)
      return { ok: false, reply: `删除失败：${msg}` }
    }
  }

  function formatPlanListReply() {
    if (!planList.value.length) {
      return '数据库中暂无计划。可说「新建计划叫 XXX」创建。'
    }
    const lines = planList.value.slice(0, 12).map((o) => {
      const n = (o.jobs || []).length
      return `· ${o.plan_name || '未命名'}（${n} 工单）`
    })
    const more = planList.value.length > 12 ? `\n… 共 ${planList.value.length} 条，完整列表见「数据中心」。` : ''
    return `当前计划列表：\n${lines.join('\n')}${more}`
  }

  /** @returns {{ handled: boolean, reply?: string }} */
  async function tryHandlePlanNl(text) {
    const cmd = parsePlanNlCommand(text)
    if (!cmd) return { handled: false }

    if (cmd.type === 'clear') {
      clearBinding()
      return { handled: true, reply: '已解除计划绑定。' }
    }
    if (cmd.type === 'list') {
      await fetchPlans()
      return { handled: true, reply: formatPlanListReply() }
    }
    if (cmd.type === 'goto_aps') {
      if (workStore.planId) {
        const row = planList.value.find((o) => o.id === workStore.planId) || {
          id: workStore.planId,
          plan_name: workStore.planName,
          jobs: workStore.customJobs || [],
        }
        goToAps(row)
        return { handled: true, reply: '已打开排程中心。' }
      }
      router.push('/aps')
      return { handled: true, reply: '已打开排程中心；请先新建或加载计划。' }
    }
    if (cmd.type === 'create') {
      const r = await createPlan(cmd.name, { navigateAps: true })
      if (r.cancelled) return { handled: true, reply: '已取消新建。' }
      if (r.ok) return { handled: true, reply: r.reply }
      return { handled: true, reply: `新建失败：${r.error}（请确认 MongoDB 已启动且后端 tests/main.py 在运行）` }
    }
    if (cmd.type === 'select') {
      const r = await selectPlanByQuery(cmd.query, { navigateAps: false })
      return { handled: true, reply: r.reply }
    }
    if (cmd.type === 'delete') {
      const r = await deletePlanByQuery(cmd.query)
      return { handled: true, reply: r.reply }
    }
    return { handled: false }
  }

  function onPlanSelectChange(id) {
    if (!id) {
      clearBinding()
      return
    }
    const row = planList.value.find((o) => o.id === id)
    if (row) bindOrder(row)
  }

  function syncSelectedFromStore() {
    selectedPlanId.value = workStore.planId || ''
  }

  return {
    planList,
    planOptions,
    plansLoading,
    selectedPlanId,
    fetchPlans,
    bindOrder,
    clearBinding,
    createPlan,
    selectPlanByQuery,
    deletePlanByQuery,
    goToAps,
    tryHandlePlanNl,
    onPlanSelectChange,
    syncSelectedFromStore,
  }
}
