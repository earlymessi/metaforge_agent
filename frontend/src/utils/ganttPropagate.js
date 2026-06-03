/** R1：故障下沿用原计划 — 序不变，故障机台工序右移（与后端 gantt_propagate 对齐） */

function opDuration(op) {
  const s = Number(op.start ?? 0)
  const e = Number(op.end ?? 0)
  if (e > s) return e - s
  return Math.max(1, Number(op.duration ?? 1) || 1)
}

function overlapsBreakdown(start, end, b0, b1) {
  return start < b1 && end > b0
}

export function propagateBreakdownOnGantt(
  gantt,
  { machineId, breakdownStart, breakdownDuration },
) {
  if (!Array.isArray(gantt) || !gantt.length) return []

  const b0 = Number(breakdownStart)
  const b1 = b0 + Number(breakdownDuration)
  const midFault = Number(machineId)

  const ordered = [...gantt]
    .map((op) => ({ ...op }))
    .sort((a, b) => {
      const ds = Number(a.start ?? 0) - Number(b.start ?? 0)
      if (ds !== 0) return ds
      const dj = Number(a.job_id ?? 0) - Number(b.job_id ?? 0)
      if (dj !== 0) return dj
      return Number(a.operation_id ?? a.id ?? 0) - Number(b.operation_id ?? b.id ?? 0)
    })

  const machineAvailable = {}
  const jobReady = {}
  const out = []

  for (const op of ordered) {
    const jid = Number(op.job_id ?? 0)
    const mid = Number(op.machine_id ?? op.machine ?? 0)
    const dur = opDuration(op)
    const origStart = Number(op.start ?? 0)

    let start = Math.max(origStart, jobReady[jid] ?? 0, machineAvailable[mid] ?? 0)
    let end = start + dur

    if (mid === midFault && overlapsBreakdown(start, end, b0, b1)) {
      start = b1
      end = start + dur
    }

    op.start = start
    op.end = end
    machineAvailable[mid] = end
    jobReady[jid] = end
    out.push(op)
  }

  return out.sort((a, b) => {
    const ds = Number(a.start ?? 0) - Number(b.start ?? 0)
    if (ds !== 0) return ds
    const dj = Number(a.job_id ?? 0) - Number(b.job_id ?? 0)
    if (dj !== 0) return dj
    return Number(a.operation_id ?? a.id ?? 0) - Number(b.operation_id ?? b.id ?? 0)
  })
}
