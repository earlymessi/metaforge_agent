import { api } from '../api/client'
import { useResultsStore } from '../stores/useResultsStore'
import {
  buildImpactSummaryPayload,
  hydrateImpactFromSources,
  unwrapImpactReport,
} from './impactReport'

/** 从编排器 artifacts 取出多算法 results（兼容 { results: {...} } 包装） */
export function normalizeScheduleResults(raw) {
  if (!raw || typeof raw !== 'object') return null
  if (raw.results && typeof raw.results === 'object' && !raw.spt && !raw.edd && !raw.ts) {
    return raw.results
  }
  const keys = Object.keys(raw)
  if (!keys.length) return null
  return raw
}

export function scheduleResultsFromArtifacts(artifacts) {
  return normalizeScheduleResults(artifacts?.schedule_results)
}

/** 从计划文档还原多算法 results（供分析报表 Pinia） */
export function scheduleResultsFromPlan(order) {
  if (!order) return null
  if (order.schedule_results && typeof order.schedule_results === 'object') {
    const keys = Object.keys(order.schedule_results)
    if (keys.length) return order.schedule_results
  }
  if (order.schedule_result && typeof order.schedule_result === 'object') {
    const sr = order.schedule_result
    const id = sr.id || sr.algorithm || 'saved'
    return {
      [id]: {
        ...sr,
        id,
        name: sr.name || sr.algorithm || id,
        best_score: sr.best_score ?? sr.makespan,
      },
    }
  }
  return null
}

export function hasPlanSchedule(order) {
  return !!scheduleResultsFromPlan(order)
}

/** 从计划文档列出可选基准算法 ID（ts / spt / ga …，而非 gantt_data 等字段名） */
export function listSolverIdsFromPlan(order) {
  const results = scheduleResultsFromPlan(order)
  if (!results) return []
  return Object.keys(results).filter((k) => {
    const v = results[k]
    return (
      v &&
      typeof v === 'object' &&
      !v.error &&
      !v.summary_zh &&
      (Array.isArray(v.gantt_data) || v.best_score != null || v.makespan != null)
    )
  })
}

export function solverDisplayName(order, solverId, results = null) {
  const map = results || scheduleResultsFromPlan(order)
  const entry = map?.[solverId]
  if (!entry) return solverId
  return entry.name || entry.algorithm || solverId
}

/** 写入 Pinia（可选 impact / material） */
export function hydrateResultsStoreFromPlan(order, store = useResultsStore()) {
  const results = scheduleResultsFromPlan(order)
  if (!results) return false
  store.setResults(results)
  store.currentPlanId = order.id || order._id || ''
  store.currentPlanName = order.plan_name || ''
  store.currentPlanInput = Array.isArray(order.jobs) ? order.jobs : []
  if (order.interpretation?.strategy_id) {
    store.setSchedulingStrategy(
      order.interpretation.strategy_id,
      order.interpretation.strategy_name || ''
    )
  }
  if (order.impact_summary) {
    store.impactPlanId = order.id || order._id || ''
    const impact = hydrateImpactFromSources(order.impact_summary, {
      impact_report: order.impact_summary,
    })
    store.setImpactReport(impact)
    store.setRescheduleSnapshot(results, impact)
  }
  return true
}

/** 拉取当前 MES 执行态（running/paused 时含 last_impact_summary） */
export async function fetchExecutionState() {
  try {
    const { data } = await api.get('/api/execution/state')
    if (data?.status && data.status !== 'idle') return data
  } catch (e) {
    console.warn('fetch execution state', e)
  }
  return null
}

/**
 * 从 MES 执行态或计划库加载最新影响评估（避免 Pinia 残留上一次重排）。
 * 优先级：execution.last_impact_summary > plan.impact_summary
 */
export async function loadImpactAssessmentForPlan(
  planId,
  { executionDoc } = {},
  store = useResultsStore()
) {
  if (!planId) {
    store.clearImpactAssessment()
    return false
  }

  let exec = executionDoc
  if (!exec?.last_impact_summary) {
    const remote = await fetchExecutionState()
    if (remote?.plan_id === planId) exec = remote
  }

  let impactRaw = null
  let results = null

  if (
    exec?.plan_id === planId &&
    exec?.last_impact_summary &&
    typeof exec.last_impact_summary === 'object'
  ) {
    impactRaw = exec.last_impact_summary
    results = exec.last_reschedule_results || null
  }

  if (!impactRaw) {
    try {
      const { data: order } = await api.get(`/api/db/get/${planId}`)
      if (order?.impact_summary) {
        impactRaw = order.impact_summary
        results = scheduleResultsFromPlan(order)
      }
    } catch (e) {
      console.warn('load impact from plan', e)
    }
  }

  if (!impactRaw) {
    if (store.impactPlanId && store.impactPlanId !== planId) {
      store.clearImpactAssessment()
    }
    return false
  }

  const impactGantt =
    (exec?.plan_id === planId && exec?.last_impact_gantt) ||
    impactRaw?.impact_gantt
  const impact = hydrateImpactFromSources(impactRaw, {
    impact_report: impactRaw,
    impact_gantt: impactGantt,
  })
  store.impactPlanId = planId
  store.setImpactReport(impact, { impact_gantt: impactGantt })
  store.setRescheduleSnapshot(results || store.results, impact, { impact_gantt: impactGantt })
  return true
}

/** 将当前排程结果保存到 MongoDB 计划（强制写入，不经 HITL） */
export async function persistScheduleToPlan(planId, results, extras = {}) {
  if (!planId || !results || !Object.keys(results).length) return null
  const { data } = await api.put(`/api/db/schedule/${planId}`, {
    schedule_results: results,
    ...extras,
  })
  return data
}

/**
 * HITL 落库：计划尚无排程则直接写入；已有排程则返回 pending_action 待确认。
 * @returns {{ kind: 'skipped'|'saved'|'pending', plan?, pending_action? }}
 */
export async function persistScheduleWithHitl(planId, results, extras = {}) {
  if (!planId || !results || !Object.keys(results).length) {
    return { kind: 'skipped' }
  }
  const { data } = await api.post('/api/db/propose_schedule', {
    plan_id: planId,
    schedule_results: results,
    ...extras,
  })
  if (data?.status === 'pending_confirm' && data?.pending_action) {
    return { kind: 'pending', pending_action: data.pending_action }
  }
  return { kind: 'saved', plan: data }
}

/** localStorage 键：从数据中心导入时携带排程快照 */
export function stashPlanLoadPayload(order) {
  localStorage.setItem('aps_load_data', JSON.stringify(order.jobs || []))
  localStorage.setItem('aps_load_id', order.id || '')
  localStorage.setItem('aps_load_plan_name', order.plan_name || '')
  localStorage.setItem('aps_load_force_custom', '1')
  const results = scheduleResultsFromPlan(order)
  if (results) {
    localStorage.setItem('aps_load_schedule_results', JSON.stringify(results))
    if (order.interpretation) {
      localStorage.setItem('aps_load_interpretation', JSON.stringify(order.interpretation))
    }
  } else {
    localStorage.removeItem('aps_load_schedule_results')
    localStorage.removeItem('aps_load_interpretation')
  }
}

export function consumeApsLoadSchedule(store = useResultsStore()) {
  const raw = localStorage.getItem('aps_load_schedule_results')
  if (!raw) return false
  try {
    const results = JSON.parse(raw)
    if (results && typeof results === 'object' && Object.keys(results).length) {
      store.setResults(results)
      const interpRaw = localStorage.getItem('aps_load_interpretation')
      if (interpRaw) {
        const interp = JSON.parse(interpRaw)
        if (interp?.strategy_id) {
          store.setSchedulingStrategy(interp.strategy_id, interp.strategy_name || '')
        }
      }
      return true
    }
  } catch {
    /* ignore */
  }
  return false
}

export function clearApsLoadScheduleKeys() {
  localStorage.removeItem('aps_load_schedule_results')
  localStorage.removeItem('aps_load_interpretation')
}

/** 是否像多算法排程结果（而非 interpretation 等） */
export function isValidScheduleResults(results) {
  if (!results || typeof results !== 'object') return false
  return Object.values(results).some(
    (v) =>
      v &&
      typeof v === 'object' &&
      !v.summary_zh &&
      (Array.isArray(v.gantt_data) ||
        v.best_score != null ||
        v.id ||
        v.name)
  )
}

const REPORTS_SESSION_KEY = 'metaforge_reports_payload'

/** 跳转分析报表前写入 sessionStorage，避免 Pinia 时序或旧 dist 丢数据 */
export function stashScheduleResultsForReports(payload) {
  const results = normalizeScheduleResults(payload?.schedule_results || payload?.results)
  if (!isValidScheduleResults(results)) return false
  try {
    sessionStorage.setItem(
      REPORTS_SESSION_KEY,
      JSON.stringify({
        schedule_results: results,
        plan_id: payload.plan_id || '',
        plan_name: payload.plan_name || '',
        jobs: payload.jobs || [],
        interpretation: payload.interpretation || null,
        ts: Date.now(),
      })
    )
    return true
  } catch {
    return false
  }
}

export function consumeReportsScheduleFromSession(store = useResultsStore()) {
  try {
    const raw = sessionStorage.getItem(REPORTS_SESSION_KEY)
    if (!raw) return false
    const payload = JSON.parse(raw)
    const results = normalizeScheduleResults(payload?.schedule_results)
    if (!isValidScheduleResults(results)) return false
    store.setResults(results)
    if (payload.plan_id) store.currentPlanId = payload.plan_id
    if (payload.plan_name) store.currentPlanName = payload.plan_name
    if (Array.isArray(payload.jobs) && payload.jobs.length) {
      store.currentPlanInput = payload.jobs
    }
    if (payload.interpretation?.strategy_id) {
      store.setSchedulingStrategy(
        payload.interpretation.strategy_id,
        payload.interpretation.strategy_name || ''
      )
    }
    sessionStorage.removeItem(REPORTS_SESSION_KEY)
    return true
  } catch {
    return false
  }
}
/** 将编排器/助手返回写入 results store；返回是否写入有效排程数据 */
export function applyScheduleToResultsStore(data, store = useResultsStore(), workStore = null) {
  let results =
    normalizeScheduleResults(data?.schedule_results) ||
    scheduleResultsFromArtifacts(data?.artifacts)
  if (!results && data?.schedule_saved_to_plan_id) {
    return { results: null, needFetchPlanId: data.schedule_saved_to_plan_id, applied: false }
  }
  if (!isValidScheduleResults(results)) {
    return { results: null, needFetchPlanId: null, applied: false }
  }

  store.setResults(results)
  const jobs = workStore?.customJobs || []
  if (jobs.length) store.currentPlanInput = jobs
  store.currentPlanId = data.schedule_saved_to_plan_id || workStore?.planId || store.currentPlanId || ''
  store.currentPlanName = workStore?.planName || store.currentPlanName || ''
  const interp = data?.artifacts?.interpretation || data?.interpretation
  if (interp?.strategy_id) {
    store.setSchedulingStrategy(interp.strategy_id, interp.strategy_name || '')
  }
  return { results, needFetchPlanId: null, applied: true }
}

export async function fetchPlanScheduleIntoStore(planId, store = useResultsStore()) {
  if (!planId) return false
  const { data: order } = await api.get(`/api/db/get/${planId}`)
  return hydrateResultsStoreFromPlan(order, store)
}

/** 从编排 done 载荷 + 会话 artifacts 兜底恢复排程结果 */
export async function hydrateFromOrchestratorDone(data, sessionId, store = useResultsStore(), workStore = null) {
  if (!data) return false

  let results =
    normalizeScheduleResults(data.schedule_results) ||
    scheduleResultsFromArtifacts(data.artifacts)

  if (!isValidScheduleResults(results) && sessionId) {
    try {
      const { data: sess } = await api.get(`/api/orchestrator/session/${sessionId}/artifacts`)
      results =
        normalizeScheduleResults(sess?.schedule_results) ||
        scheduleResultsFromArtifacts(sess?.artifacts)
    } catch (e) {
      console.warn('fetch session artifacts', e)
    }
  }

  if (!isValidScheduleResults(results) && data.schedule_saved_to_plan_id) {
    return fetchPlanScheduleIntoStore(data.schedule_saved_to_plan_id, store)
  }

  if (!isValidScheduleResults(results)) return false

  store.setResults(results)
  const jobs = workStore?.customJobs || []
  if (jobs.length) store.currentPlanInput = jobs
  store.currentPlanId =
    data.schedule_saved_to_plan_id || workStore?.planId || store.currentPlanId || ''
  store.currentPlanName = workStore?.planName || store.currentPlanName || ''
  const interp = data?.artifacts?.interpretation || data?.interpretation
  if (interp?.strategy_id) {
    store.setSchedulingStrategy(interp.strategy_id, interp.strategy_name || '')
  }

  stashScheduleResultsForReports({
    schedule_results: results,
    plan_id: store.currentPlanId,
    plan_name: store.currentPlanName,
    jobs: store.currentPlanInput || jobs,
    interpretation: interp,
  })
  return true
}
