/** 插单 R1：原计划不动，急单排到队尾（与后端 gantt_insert_defer 一致）。 */

function taskMachine(task) {
  if (task.machine_id != null) return Number(task.machine_id)
  const opts = task.machine_options || []
  return opts.length ? Number(opts[0]) : 0
}

function taskDuration(task) {
  return Math.max(1, Number(task.duration || 1))
}

export function deferInsertToTailGantt(baselineGantt, insertJob, insertJobId, freezeTime = 0, insertPriority = 100) {
  const out = (baselineGantt || []).map((op) => ({ ...op }))
  if (!insertJob?.tasks?.length) return out

  const freeze = Math.max(0, Number(freezeTime) || 0)
  const machineEnd = {}
  let globalEnd = freeze
  for (const op of baselineGantt || []) {
    const mid = Number(op.machine_id ?? 0)
    const e = Number(op.end) || 0
    machineEnd[mid] = Math.max(machineEnd[mid] || 0, e)
    globalEnd = Math.max(globalEnd, e)
  }

  const insName = insertJob.name || 'Insert'
  let jobReady = Math.max(globalEnd, freeze)
  ;(insertJob.tasks || []).forEach((task, i) => {
    const mid = taskMachine(task)
    const dur = taskDuration(task)
    const tname = task.name || `Op-${i + 1}`
    const start = Math.max(jobReady, machineEnd[mid] || 0, freeze)
    const end = start + dur
    out.push({
      job_id: Number(insertJobId),
      operation_id: i,
      machine_id: mid,
      start,
      end,
      job_name: insName,
      operation_name: tname,
      priority: insertPriority,
    })
    machineEnd[mid] = end
    jobReady = end
  })

  out.sort(
    (a, b) =>
      Number(a.start) - Number(b.start) ||
      Number(a.job_id) - Number(b.job_id) ||
      Number(a.operation_id ?? a.id ?? 0) - Number(b.operation_id ?? b.id ?? 0),
  )
  return out
}
