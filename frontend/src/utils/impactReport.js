/** 解析/补全影响评估报告（兼容 Agent 的 impact_summary 嵌套结构）。 */

import { deferInsertToTailGantt } from './ganttInsertDefer.js'
import { propagateBreakdownOnGantt } from './ganttPropagate.js'

export const DUAL_GANTT_EVENT_TYPES = ['insert_order', 'machine_breakdown', 'due_date_change']

export function impactHasPayload(obj) {
  if (!obj || typeof obj !== 'object') return false
  return !!(
    obj.r1_gantt?.length ||
    obj.r2_gantt?.length ||
    obj.r0_gantt?.length ||
    obj.delay_details?.length ||
    obj.commitment_changes?.length ||
    obj.scenarios
  )
}

/** Agent / MES 落库常为多层 { impact_report: { impact_report: {…} } } */
export function unwrapImpactReport(raw) {
  if (!raw || typeof raw !== 'object') return null

  let cur = raw
  for (let depth = 0; depth < 6; depth += 1) {
    const nested = cur.impact_report
    if (!nested || typeof nested !== 'object') break
    if (impactHasPayload(nested) && !impactHasPayload(cur)) {
      cur = {
        ...nested,
        summary_zh: cur.summary_zh ?? nested.summary_zh,
        rescheduled_at: cur.rescheduled_at ?? nested.rescheduled_at,
      }
      continue
    }
    if (impactHasPayload(nested)) {
      cur = {
        ...nested,
        summary_zh: cur.summary_zh ?? nested.summary_zh,
        rescheduled_at: cur.rescheduled_at ?? nested.rescheduled_at,
      }
      break
    }
    if (!cur.event_type && !cur.r1_gantt && !cur.r2_gantt) {
      cur = nested
      continue
    }
    break
  }
  return cur
}

/** 合并顶层 impact_gantt 或嵌套字段，避免大数组在传输/落库时丢失 */
export function mergeImpactGanttFields(impact, rawBundle) {
  if (!impact || typeof impact !== 'object') return null
  const out = { ...impact }
  const ig = rawBundle?.impact_gantt || rawBundle?.impactGantt
  if (ig) {
    if (!out.r0_gantt?.length && ig.r0?.length) out.r0_gantt = ig.r0
    if (!out.r1_gantt?.length && ig.r1?.length) out.r1_gantt = ig.r1
    if (!out.r2_gantt?.length && ig.r2?.length) out.r2_gantt = ig.r2
  }
  return out
}

export function hydrateImpactFromSources(rawImpact, extras = {}) {
  const unwrapped = unwrapImpactReport(rawImpact)
  return mergeImpactGanttFields(unwrapped, extras) || unwrapped
}

/** Pinia 中 impactReport 与 lastRescheduleImpact 可能不一致，取数据更完整的一份 */
export function pickActiveImpactReport(primary, fallback) {
  const a = hydrateImpactFromSources(primary)
  const b = hydrateImpactFromSources(fallback)
  const aOk = impactHasPayload(a)
  const bOk = impactHasPayload(b)
  if (aOk && !bOk) return a
  if (bOk && !aOk) return b
  if (aOk && bOk) {
    const aGantt = (a.r1_gantt?.length || 0) + (a.r2_gantt?.length || 0)
    const bGantt = (b.r1_gantt?.length || 0) + (b.r2_gantt?.length || 0)
    if (bGantt > aGantt) return b
    if (aGantt > bGantt) return a
  }
  return a || b || null
}

export function normalizeEventResultBundle(body) {
  const bundle = body?.data ?? body ?? {}
  const rawImpact =
    bundle.impact_report ?? body?.impact_report ?? bundle.impact_summary
  const impact = hydrateImpactFromSources(rawImpact, {
    impact_report: rawImpact,
    impact_gantt: bundle.impact_gantt ?? body?.impact_gantt,
  })
  return {
    results: bundle.results ?? body?.schedule_results ?? null,
    impact_report: impact,
    updated_jobs: bundle.updated_jobs,
    production_execution: bundle.production_execution,
    impact_gantt: bundle.impact_gantt ?? body?.impact_gantt,
  }
}

function baselineGanttFrom(impact, opts) {
  if (Array.isArray(impact?.r0_gantt) && impact.r0_gantt.length) return impact.r0_gantt
  if (Array.isArray(impact?.r1_gantt) && impact.r1_gantt.length) return impact.r1_gantt
  if (Array.isArray(opts?.baselineGantt) && opts.baselineGantt.length) return opts.baselineGantt
  return []
}

function pickResultsGantt(results, solverRef) {
  if (!results || typeof results !== 'object') return []
  const sid = solverRef != null ? String(solverRef) : ''
  if (sid && results[sid]?.gantt_data?.length) return results[sid].gantt_data
  const lower = sid.toLowerCase()
  for (const [k, v] of Object.entries(results)) {
    if (String(k).toLowerCase() === lower && v?.gantt_data?.length) return v.gantt_data
  }
  const first = Object.values(results).find((r) => r?.gantt_data?.length)
  return first?.gantt_data || []
}

export function effectiveR2Gantt(impact, results, snapshotResults = null) {
  if (Array.isArray(impact?.r2_gantt) && impact.r2_gantt.length) return impact.r2_gantt
  const mergedResults = snapshotResults || results
  const sid = impact?.rescheduled_solver || impact?.baseline_solver
  const fromResults = pickResultsGantt(mergedResults, sid)
  if (fromResults.length) return fromResults
  return []
}

export function effectiveR1Gantt(impact, opts = {}) {
  const ir = impact || {}
  if (Array.isArray(ir.r1_gantt) && ir.r1_gantt.length) return ir.r1_gantt

  if (ir.event_type === 'due_date_change') {
    return baselineGanttFrom(ir, opts)
  }

  if (ir.event_type === 'insert_order') {
    const base = baselineGanttFrom(ir, opts)
    const snap = ir.insert_job_snapshot || opts.insertJobSnapshot
    if (!base?.length || !snap?.tasks?.length) return []
    const jid = Number(ir.insert_job_id ?? snap.job_id ?? base.length)
    const freeze = Number(ir.freeze_time ?? opts.freezeTime ?? 0)
    const pri = Number(snap.priority ?? 100)
    return deferInsertToTailGantt(base, snap, jid, freeze, pri)
  }

  if (ir.event_type === 'machine_breakdown') {
    // R1 必须由原计划 R0 推演；不可用 MES baseline_gantt（重排后已是 R2）
    const base = Array.isArray(ir.r0_gantt) && ir.r0_gantt.length ? ir.r0_gantt : []
    if (!base.length) return []
    if (ir.machine_id == null || ir.breakdown_start == null) return []
    const dur =
      ir.breakdown_duration != null
        ? Number(ir.breakdown_duration)
        : Number(ir.breakdown_end) - Number(ir.breakdown_start)
    if (!Number.isFinite(dur) || dur <= 0) return []
    return propagateBreakdownOnGantt(base, {
      machineId: ir.machine_id,
      breakdownStart: ir.breakdown_start,
      breakdownDuration: dur,
    })
  }

  return []
}

export function hasDualImpactGantt(impact, results, opts = {}, snapshotResults = null) {
  const r1 = effectiveR1Gantt(impact, opts)
  const r2 = effectiveR2Gantt(impact, results, snapshotResults)
  return r1.length > 0 && r2.length > 0
}

export function isDualGanttEvent(impact) {
  return DUAL_GANTT_EVENT_TYPES.includes(impact?.event_type)
}

/** 前端/API 落库用：包装完整 impact_report + 时间戳（避免重复嵌套） */
export function buildImpactSummaryPayload(impactReport, summaryZh = '') {
  const core = unwrapImpactReport(impactReport)
  if (!core || typeof core !== 'object') return null
  return {
    summary_zh: summaryZh || core.summary_zh || impactReport?.summary_zh || '',
    impact_report: core,
    event_type: core.event_type,
    rescheduled_at: new Date().toISOString(),
  }
}

export function firstImpactTab(impact, results, opts = {}, snapshotResults = null) {
  if (hasDualImpactGantt(impact, results, opts, snapshotResults)) return 'gantt'
  if (isDualGanttEvent(impact)) return 'gantt'
  if (impact?.scenarios && Object.keys(impact.scenarios).length) return 'recovery'
  return 'delay'
}
