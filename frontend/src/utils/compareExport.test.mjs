/**
 * Plain node test (no vitest): node frontend/src/utils/compareExport.test.mjs
 */
import assert from 'node:assert/strict'
import { buildCompareJson, extractCompareMetrics } from './compareExport.js'

const impact = {
  event_type: 'machine_breakdown',
  summary_zh: 'demo',
  r0_gantt: [{ Job: 'A', start: 0, end: 2 }],
  r1_gantt: [{ Job: 'A', start: 0, end: 3 }],
  r2_gantt: [{ Job: 'A', start: 0, end: 4 }],
  scenarios: {
    r0: { label: 'R0', makespan: 2 },
    r1: { label: 'R1', makespan: 3 },
    r2: { label: 'R2', makespan: 4 },
  },
}

const out = buildCompareJson(impact)
assert.equal(out.gantt.r0.length, 1)
assert.equal(out.gantt.r1.length, 1)
assert.equal(out.gantt.r2.length, 1)
assert.equal(out.scenarios.r0.makespan, 2)
assert.deepEqual(
  out.metrics.rows.map((r) => r.key),
  ['r0', 'r1', 'r2'],
)

const m = extractCompareMetrics({})
assert.equal(m.rows.length, 3)

console.log('compareExport.test.mjs: ok')
