import assert from 'node:assert/strict'
import {
  extractPackageView,
  candidatesToScheduleResults,
  scheduleResultsFromPlanningRun,
} from './packageExtract.js'

// Package-nested evaluation (primary shape from pipeline)
{
  const view = extractPackageView({
    status: 'COMPLETED',
    package: {
      recommended_schedule_id: 'edd',
      strategy: { provenance: { simulated_fields: ['skill'] } },
      evaluation: {
        recommended_schedule_id: 'edd',
        recommendation_reason: 'ok',
        hard_violations: [],
        candidates: [{ schedule_id: 'edd', solver: 'edd', metrics: { makespan: 10 } }],
      },
    },
  })
  assert.equal(view.recommended_schedule_id, 'edd')
  assert.equal(view.hasRecommendation, true)
  assert.equal(view.recommendation_reason, 'ok')
  assert.deepEqual(view.hard_violations, [])
  assert.deepEqual(view.simulated_fields, ['skill'])
  assert.equal(view.candidates.length, 1)
  assert.deepEqual(view.metrics, { makespan: 10 })
}

// Top-level evaluation + candidate_schedules + strategy_approved
{
  const view = extractPackageView({
    status: 'COMPLETED',
    evaluation: {
      recommended_schedule_id: 'ts',
      recommendation_reason: 'best score',
      hard_violations: [{ schedule_id: 'ga', type: 'due_date' }],
    },
    candidate_schedules: [
      { schedule_id: 'ts', solver: 'tabu_search', metrics: { makespan: 12, tardiness: 0 } },
      { schedule_id: 'ga', solver: 'genetic', metrics: { makespan: 20, tardiness: 5 } },
    ],
    strategy_approved: { provenance: { simulated_fields: ['setup'] } },
    package: { recommended_schedule_id: 'ts' },
  })
  assert.equal(view.recommended_schedule_id, 'ts')
  assert.equal(view.hasRecommendation, true)
  assert.equal(view.recommendation_reason, 'best score')
  assert.equal(view.hard_violations.length, 1)
  assert.deepEqual(view.simulated_fields, ['setup'])
  assert.equal(view.candidates.length, 2)
  assert.deepEqual(view.metrics, { makespan: 12, tardiness: 0 })
}

// No recommendation: strategy_draft simulated_fields, empty candidates
{
  const view = extractPackageView({
    status: 'COMPLETED',
    package: {
      recommended_schedule_id: null,
      evaluation: {
        recommended_schedule_id: null,
        recommendation_reason: '无合法推荐',
        hard_violations: [{ schedule_id: 'edd', type: 'due_date' }],
        candidates: [],
      },
    },
    strategy_draft: { provenance: { simulated_fields: [] } },
  })
  assert.equal(view.recommended_schedule_id, null)
  assert.equal(view.hasRecommendation, false)
  assert.equal(view.recommendation_reason, '无合法推荐')
  assert.equal(view.hard_violations.length, 1)
  assert.deepEqual(view.simulated_fields, [])
  assert.deepEqual(view.candidates, [])
  assert.deepEqual(view.metrics, {})
}

// candidates → store.results shape for reports / materials / energy
{
  const results = candidatesToScheduleResults([
    {
      schedule_id: 'ts',
      solver: 'ts',
      solver_label: '禁忌搜索 TS',
      metrics: { makespan: 55, tardiness: 2 },
      score: 12.5,
      gantt_data: [
        { machine_id: 0, start: 0, end: 30, job_id: 1 },
        { machine_id: 1, start: 30, end: 55, job_id: 1 },
      ],
      is_recommended: true,
      rank: 1,
    },
    {
      schedule_id: 'ga',
      solver: 'ga',
      metrics: {},
      gantt_data: [{ machine_id: 0, start: 0, end: 70, job_id: 1 }],
      rank: 2,
    },
  ])
  assert.ok(results.ts)
  assert.equal(results.ts.best_score, 55)
  assert.equal(results.ts.score, 12.5)
  assert.equal(results.ts.name, '禁忌搜索 TS')
  assert.equal(results.ts.gantt_data.length, 2)
  assert.equal(results.ga.best_score, 70)
  assert.equal(results.ga.metrics.makespan, 70)
}

{
  const data = {
    status: 'COMPLETED',
    evaluation: {
      recommended_schedule_id: 'spt',
      ranking: [{ schedule_id: 'spt', score: 1, hard_ok: true }],
    },
    candidate_schedules: [
      {
        schedule_id: 'spt',
        solver: 'spt',
        metrics: { makespan: 40 },
        gantt_data: [{ machine_id: 0, start: 0, end: 40, job_id: 1 }],
      },
    ],
  }
  const results = scheduleResultsFromPlanningRun(data)
  assert.ok(results.spt)
  assert.equal(results.spt.best_score, 40)
  assert.equal(results.spt.is_recommended, true)
}

console.log('packageExtract ok')
