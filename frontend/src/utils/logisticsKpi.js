/** 从任务列表或 KPI API 响应计算展示用指标 */
export function formatKpiPercent(ratio) {
  if (ratio == null || Number.isNaN(ratio)) return '—'
  return `${(ratio * 100).toFixed(1)}%`
}

export function summarizeTasksKpi(tasks = []) {
  const total = tasks.length
  const scored = tasks.filter((t) => t.score != null && t.score !== '')
  const onTime = scored.filter((t) => {
    const p = t.score_breakdown?.order_penalty
    return p == null || Number(p) <= 0
  })
  const seamless = tasks.filter((t) => t.is_seamless)
  const emptyCosts = scored
    .map((t) => t.score_breakdown?.empty_cost)
    .filter((v) => v != null && !Number.isNaN(Number(v)))
  const avgEmpty =
    emptyCosts.length > 0
      ? emptyCosts.reduce((a, b) => a + Number(b), 0) / emptyCosts.length
      : null
  const status = { pending: 0, dispatched: 0, done: 0 }
  for (const t of tasks) {
    const s = t.dispatch_status || (t.dispatched ? 'dispatched' : 'pending')
    if (status[s] != null) status[s] += 1
    else status.pending += 1
  }
  return {
    total,
    scored_count: scored.length,
    on_time_rate: scored.length ? onTime.length / scored.length : null,
    seamless_rate: total ? seamless.length / total : null,
    avg_empty_cost: avgEmpty,
    status,
  }
}
