/**
 * Build comparable R0/R1/R2 payload for CompareView / export.
 */

import {
  effectiveR1Gantt,
  effectiveR2Gantt,
  hydrateImpactFromSources,
} from './impactReport.js'

export const IMPACT_STORAGE_KEY = 'metaforge_last_impact'

export function effectiveR0Gantt(impact, opts = {}) {
  const ir = impact || {}
  if (Array.isArray(ir.r0_gantt) && ir.r0_gantt.length) return ir.r0_gantt
  if (Array.isArray(opts?.baselineGantt) && opts.baselineGantt.length) return opts.baselineGantt
  return []
}

export function extractCompareMetrics(impact) {
  const ir = hydrateImpactFromSources(impact) || {}
  const sc = ir.scenarios || {}
  const rows = ['r0', 'r1', 'r2'].map((key) => {
    const s = sc[key] || {}
    return {
      key,
      label: s.label || key.toUpperCase(),
      makespan: s.makespan ?? null,
      delayed_jobs: s.delayed_jobs ?? s.delay_jobs ?? null,
      affected_ops: s.affected_ops ?? s.rescheduled_ops ?? null,
    }
  })
  return {
    event_type: ir.event_type || null,
    summary_zh: ir.summary_zh || '',
    rows,
    delay_count: Array.isArray(ir.delay_details) ? ir.delay_details.length : 0,
    commitment_count: Array.isArray(ir.commitment_changes) ? ir.commitment_changes.length : 0,
  }
}

export function buildCompareJson(impact, extras = {}) {
  const ir = hydrateImpactFromSources(impact) || {}
  const r0 = effectiveR0Gantt(ir, extras)
  const r1 = effectiveR1Gantt(ir, extras)
  const r2 = effectiveR2Gantt(ir, extras.results, extras.snapshotResults)
  const metrics = extractCompareMetrics(ir)
  return {
    exported_at: new Date().toISOString(),
    event_type: ir.event_type || null,
    summary_zh: ir.summary_zh || '',
    metrics,
    scenarios: ir.scenarios || {
      r0: { label: 'R0', makespan: null },
      r1: { label: 'R1', makespan: null },
      r2: { label: 'R2', makespan: null },
    },
    gantt: {
      r0,
      r1,
      r2,
    },
    impact: ir,
  }
}

export function loadImpactFromSession() {
  try {
    const raw = sessionStorage.getItem(IMPACT_STORAGE_KEY)
    if (!raw) return null
    return hydrateImpactFromSources(JSON.parse(raw))
  } catch {
    return null
  }
}

export async function exportComparePdf(comparePayload) {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const metrics = comparePayload.metrics || extractCompareMetrics(comparePayload.impact)
  let y = 48
  doc.setFontSize(16)
  doc.text('MetaForge R0/R1/R2 Compare', 40, y)
  y += 24
  doc.setFontSize(11)
  doc.text(`Exported: ${comparePayload.exported_at || ''}`, 40, y)
  y += 18
  doc.text(`Event: ${metrics.event_type || '-'}`, 40, y)
  y += 18
  if (metrics.summary_zh) {
    const lines = doc.splitTextToSize(String(metrics.summary_zh), 500)
    doc.text(lines, 40, y)
    y += 16 * lines.length + 8
  }
  doc.text('Metrics', 40, y)
  y += 16
  for (const row of metrics.rows || []) {
    const line = `${row.label}: makespan=${row.makespan ?? '-'} delayed=${row.delayed_jobs ?? '-'} affected_ops=${row.affected_ops ?? '-'}`
    doc.text(line, 48, y)
    y += 14
  }
  doc.text(`delay_details=${metrics.delay_count} commitment_changes=${metrics.commitment_count}`, 40, y + 8)
  doc.save(`metaforge-compare-${Date.now()}.pdf`)
}
