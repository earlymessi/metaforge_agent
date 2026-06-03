/** Agent 异常重排结果与生产看板 MesReschedulePanel 对齐的 store 写入 */

import { normalizeEventResultBundle } from './impactReport'

/**
 * 将编排器/Agent 返回的 artifacts 转为看板同款 bundle 并写入 results store。
 * @returns {{ bundle: object|null, applied: boolean }}
 */
export function applyMesEventArtifactsToStore(data, store) {
  if (!data || !store) return { bundle: null, applied: false }
  const artifacts = data.artifacts || {}
  const impact =
    artifacts.impact_report ||
    artifacts.impact_summary?.impact_report ||
    data.impact_report
  const results = artifacts.schedule_results || data.schedule_results
  if (!impact && !results) return { bundle: null, applied: false }

  const impactGantt = artifacts.impact_gantt || data.impact_gantt
  const bundle = normalizeEventResultBundle({
    data: {
      results,
      impact_report: impact,
      updated_jobs: artifacts.updated_jobs,
      production_execution: artifacts.production_execution || data.production_execution,
      impact_gantt: impactGantt,
    },
    impact_gantt: impactGantt,
    impact_report: data.impact_report,
  })
  store.setResults(bundle.results || null)
  store.setImpactReport(bundle.impact_report || null, { impact_gantt: impactGantt })
  store.setRescheduleSnapshot(bundle.results, bundle.impact_report, { impact_gantt: impactGantt })
  if (Array.isArray(bundle.updated_jobs) && bundle.updated_jobs.length) {
    store.currentPlanInput = bundle.updated_jobs
  }
  const insName = bundle.impact_report?.insert_job_name
  if (insName) store.setHighlightJobNames([insName])
  return { bundle, applied: true }
}
