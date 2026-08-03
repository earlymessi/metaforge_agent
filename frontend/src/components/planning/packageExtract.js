/**
 * Normalize planning run / collab response into fields for PackageResultPanel.
 * Accepts evaluation / candidate_schedules / strategy at top level or inside package.
 */
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
  const candidates =
    candidatesFromSchedules ||
    (Array.isArray(evaluation.candidates) && evaluation.candidates) ||
    (Array.isArray(evaluation.ranking) && evaluation.ranking) ||
    []

  const recommended =
    candidates.find(
      (c) => (c.schedule_id || c.solver) === recommended_schedule_id,
    ) || null
  const metrics = recommended?.metrics && typeof recommended.metrics === 'object'
    ? { ...recommended.metrics }
    : {}

  return {
    recommended_schedule_id,
    hard_violations,
    recommendation_reason,
    simulated_fields,
    candidates,
    metrics,
    hasRecommendation: recommended_schedule_id != null && recommended_schedule_id !== '',
  }
}
