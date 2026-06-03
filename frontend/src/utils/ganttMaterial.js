/**
 * 将排程缺料事件映射到甘特图坐标（机台 + 时刻）。
 */
export function buildShortageMarkPoints(ganttData, shortages) {
  if (!Array.isArray(ganttData) || !Array.isArray(shortages) || !shortages.length) {
    return []
  }

  const machines = [...new Set(ganttData.map((d) => d.machine_id))].sort((a, b) => a - b)
  const points = []

  for (const s of shortages) {
    const jid = Number(s.job_id)
    const t = Number(s.time)
    if (Number.isNaN(t)) continue

    let op = ganttData.find(
      (d) => Number(d.job_id) === jid && Number(d.start) <= t && t < Number(d.end),
    )
    if (!op) {
      const jobOps = ganttData
        .filter((d) => Number(d.job_id) === jid)
        .sort((a, b) => Number(a.start) - Number(b.start))
      op = jobOps.find((d) => Math.abs(Number(d.start) - t) < 1e-6) || jobOps[0]
    }
    if (!op) continue

    const mid = Number(op.machine_id)
    const yIdx = machines.indexOf(mid)
    if (yIdx < 0) continue

    points.push({
      value: [t + 0.35, yIdx],
      machine_id: mid,
      time: t,
      job_id: jid,
      job_name: s.job_name || op.job_name || `Job-${jid}`,
      material_id: s.mat_id,
      material_name: s.name || s.mat_id,
      stock_left: s.left,
      safe_level: s.safe_level ?? s.limit,
      event_type: s.event_type,
    })
  }

  return points
}

/**
 * 有缺料的工单 job_id 集合，用于甘特条加红框。
 */
export function shortageJobIdSet(shortages) {
  const set = new Set()
  for (const s of shortages || []) {
    if (s.job_id != null) set.add(Number(s.job_id))
  }
  return set
}
