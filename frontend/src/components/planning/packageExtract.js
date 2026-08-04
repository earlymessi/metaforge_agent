/**
 * Normalize planning run / collab response into fields for PackageResultPanel.
 * Accepts evaluation / candidate_schedules / strategy at top level or inside package.
 */

export const SOLVER_LABELS = {
  ts: '禁忌搜索 TS',
  ga: '遗传算法 GA',
  sa: '模拟退火 SA',
  aco: '蚁群 ACO',
  edd: '最早交期 EDD',
  spt: '最短加工 SPT',
  mwkr: '剩余最多 MWKR',
  fifo: '先进先出 FIFO',
}

export const METRIC_LABELS = {
  makespan: '完工时间',
  tardiness: '拖期',
  weighted_tardiness_total: '加权拖期',
  energy_cost: '能耗成本',
  machine_busy_cv: '负载不均',
  setup_count: '换型次数',
  composite_score: '综合得分',
}

export function solverLabel(id) {
  if (id == null || id === '') return '—'
  const key = String(id)
  return SOLVER_LABELS[key] || SOLVER_LABELS[key.toLowerCase()] || key.toUpperCase()
}

export function metricLabel(key) {
  return METRIC_LABELS[key] || key
}

function candidateKey(c) {
  return c?.schedule_id || c?.solver || c?.id || ''
}

function mergeRankingIntoCandidates(candidates, ranking, recommendedId) {
  const rankById = new Map()
  ;(Array.isArray(ranking) ? ranking : []).forEach((row, idx) => {
    const id = row.schedule_id || row.solver || ''
    if (!id) return
    rankById.set(id, {
      rank: idx + 1,
      score: row.score,
      hard_ok: row.hard_ok,
      metrics: row.metrics && typeof row.metrics === 'object' ? row.metrics : undefined,
    })
  })

  const bestScore = (Array.isArray(ranking) && ranking.length)
    ? ranking.find((r) => r.hard_ok)?.score
    : null

  return (candidates || []).map((c) => {
    const id = candidateKey(c)
    const ranked = rankById.get(id) || {}
    const metrics = {
      ...(ranked.metrics || {}),
      ...(c.metrics && typeof c.metrics === 'object' ? c.metrics : {}),
    }
    const score = ranked.score ?? c.score ?? c.composite_score ?? null
    const hardOk = ranked.hard_ok ?? c.hard_ok
    const isRecommended = recommendedId != null && id === recommendedId
    let compareHint = ''
    if (hardOk === false) {
      compareHint = '硬约束未过'
    } else if (isRecommended) {
      compareHint = '推荐 · 综合最优'
    } else if (bestScore != null && score != null && Number.isFinite(Number(score))) {
      const delta = Number(score) - Number(bestScore)
      if (Math.abs(delta) < 1e-9) compareHint = '与推荐并列'
      else if (delta > 0) compareHint = `综合得分 +${delta.toFixed(2)}（较差）`
      else compareHint = `综合得分 ${delta.toFixed(2)}（更好）`
    }
    return {
      ...c,
      schedule_id: id || c.schedule_id,
      solver: c.solver || id,
      solver_label: solverLabel(c.solver || id),
      metrics,
      score,
      hard_ok: hardOk,
      rank: ranked.rank ?? null,
      is_recommended: isRecommended,
      compare_hint: compareHint,
    }
  }).sort((a, b) => {
    if (a.rank != null && b.rank != null) return a.rank - b.rank
    if (a.rank != null) return -1
    if (b.rank != null) return 1
    return 0
  })
}

export function extractPackageView(data) {
  const pkg = data?.package || {}
  const evaluation = data?.evaluation || pkg.evaluation || {}
  const strategy =
    data?.strategy_approved ||
    data?.strategy_draft ||
    pkg.strategy ||
    {}

  const recommended_schedule_id =
    evaluation.recommended_schedule_id ?? pkg.recommended_schedule_id ?? null

  const hard_violations = evaluation.hard_violations || []
  const recommendation_reason = evaluation.recommendation_reason || ''

  const simulated = strategy?.provenance?.simulated_fields
  const simulated_fields = Array.isArray(simulated) ? simulated : []

  const candidatesFromSchedules =
    (Array.isArray(data?.candidate_schedules) && data.candidate_schedules) ||
    (Array.isArray(pkg.candidate_schedules) && pkg.candidate_schedules) ||
    null
  // Prefer schedules with gantt_data; evaluation.ranking/candidates usually lack gantt.
  const rawCandidates =
    candidatesFromSchedules ||
    (Array.isArray(evaluation.candidates) && evaluation.candidates) ||
    (Array.isArray(evaluation.ranking) && evaluation.ranking) ||
    []

  const ranking = Array.isArray(evaluation.ranking) ? evaluation.ranking : []
  const candidates = mergeRankingIntoCandidates(
    rawCandidates,
    ranking,
    recommended_schedule_id,
  )

  const recommended =
    candidates.find((c) => candidateKey(c) === recommended_schedule_id) || null
  const metrics = recommended?.metrics && typeof recommended.metrics === 'object'
    ? { ...recommended.metrics }
    : {}
  if (recommended?.score != null && metrics.composite_score == null) {
    metrics.composite_score = recommended.score
  }

  const package_code =
    data?.package_code ||
    pkg.package_code ||
    (recommended_schedule_id
      ? `PKG-${String(recommended_schedule_id).toUpperCase()}`
      : null)

  return {
    recommended_schedule_id,
    recommended_label: recommended
      ? recommended.solver_label || solverLabel(recommended_schedule_id)
      : solverLabel(recommended_schedule_id),
    package_code,
    hard_violations,
    recommendation_reason,
    simulated_fields,
    candidates,
    metrics,
    hasRecommendation: recommended_schedule_id != null && recommended_schedule_id !== '',
    run_id: data?.run_id || null,
  }
}

function ganttMakespan(gantt) {
  if (!Array.isArray(gantt) || !gantt.length) return 0
  let max = 0
  for (const t of gantt) {
    const end = Number(t?.end)
    if (Number.isFinite(end) && end > max) max = end
  }
  return max
}

/**
 * 将 AI/模板/参数排产的 candidate_schedules 转为 Pinia `store.results`
 *（与「开始排程计算」返回的多算法字典同形，供分析报表/物料/能耗等消费）。
 */
export function candidatesToScheduleResults(candidates) {
  const out = {}
  for (const c of Array.isArray(candidates) ? candidates : []) {
    const id = String(c?.schedule_id || c?.solver || c?.id || '').trim()
    if (!id) continue
    const gantt = Array.isArray(c.gantt_data) ? c.gantt_data : []
    const metrics =
      c.metrics && typeof c.metrics === 'object' ? { ...c.metrics } : {}
    const makespan =
      Number(
        metrics.makespan ??
          c.best_score ??
          c.makespan ??
          ganttMakespan(gantt),
      ) || 0
    if (makespan && metrics.makespan == null) metrics.makespan = makespan
    const composite =
      c.score ?? c.composite_score ?? metrics.composite_score ?? makespan
    out[id] = {
      id,
      solver_id: id,
      name: c.solver_label || solverLabel(c.solver || id),
      algorithm: c.solver || id,
      best_score: makespan,
      score: Number(composite) || 0,
      metrics,
      gantt_data: gantt,
      history: Array.isArray(c.history) ? c.history : [],
      material_report: c.material_report || null,
      bottleneck_report: c.bottleneck_report || null,
      delivery_predictions: c.delivery_predictions || null,
      hard_ok: c.hard_ok,
      rank: c.rank ?? null,
      is_recommended: !!c.is_recommended,
    }
  }
  return Object.keys(out).length ? out : null
}

/** 从 planning COMPLETED 载荷提取可写入报表的 schedule_results */
export function scheduleResultsFromPlanningRun(data, packageView = null) {
  const view = packageView || extractPackageView(data || {})
  const fromRun = Array.isArray(data?.candidate_schedules)
    ? data.candidate_schedules
    : null
  const fromPkg = Array.isArray(data?.package?.candidate_schedules)
    ? data.package.candidate_schedules
    : null
  const fromView = Array.isArray(view?.candidates) ? view.candidates : null
  const pickWithGantt = (list) =>
    (Array.isArray(list) ? list : []).filter(
      (c) => Array.isArray(c?.gantt_data) && c.gantt_data.length,
    )
  const candidates =
    (pickWithGantt(fromRun).length ? fromRun : null) ||
    (pickWithGantt(fromPkg).length ? fromPkg : null) ||
    (pickWithGantt(fromView).length ? fromView : null) ||
    fromRun ||
    fromPkg ||
    fromView ||
    []
  // Prefer ranked/enriched view candidates when they already carry gantt
  const enriched =
    pickWithGantt(fromView).length >= pickWithGantt(candidates).length
      ? fromView
      : candidates
  return candidatesToScheduleResults(
    mergeRankingIntoCandidates(
      enriched,
      Array.isArray(data?.evaluation?.ranking)
        ? data.evaluation.ranking
        : data?.package?.evaluation?.ranking || [],
      view?.recommended_schedule_id,
    ),
  )
}

/** 送入仿真时的计划代号与显示名 */
export function buildPackagePlanIdentity(packageView, { runId } = {}) {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`
  const solver = String(packageView?.recommended_schedule_id || 'NA').toUpperCase()
  const code = `PKG-${stamp}-${solver}`
  const algo = packageView?.recommended_label || solverLabel(packageView?.recommended_schedule_id)
  const shortRun = runId ? String(runId).slice(0, 8) : ''
  const plan_name = shortRun
    ? `${code} · ${algo}（run ${shortRun}）`
    : `${code} · ${algo}`
  return { package_code: code, plan_name, solver_id: packageView?.recommended_schedule_id || null }
}
