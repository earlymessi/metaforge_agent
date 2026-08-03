import assert from 'node:assert/strict'
import { extractPackageView } from './packageExtract.js'

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

console.log('packageExtract ok')
