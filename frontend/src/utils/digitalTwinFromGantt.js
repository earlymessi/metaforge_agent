/** 与执行甘特同一时刻计算机台孪生状态 */
export function buildMachinesFromGantt(gantt, simTime, layoutMachines = []) {
  const t = Number(simTime) || 0
  const list = Array.isArray(layoutMachines) ? layoutMachines : []
  return list.map((m) => {
    const mid = Number(m.id)
    let status = 'idle'
    let current_job = ''
    for (const task of gantt || []) {
      if (Number(task.machine_id) !== mid) continue
      const start = Number(task.start) || 0
      const end = Number(task.end) || 0
      if (start <= t && t <= end) {
        status = 'running'
        current_job = String(task.job_name || '')
        break
      }
    }
    return {
      id: mid,
      x: Number(m.x),
      z: Number(m.z),
      status,
      current_job,
    }
  })
}
