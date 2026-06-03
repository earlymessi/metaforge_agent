/** 合并排程缺料与安全库存预警为统一「缺料预警」列表 */

export function mergeMaterialAlerts(simulation) {
  if (!simulation) return []

  const toShortage = (s) => ({
    ...s,
    level: 'shortage',
    level_label: '缺料',
  })
  const toWarning = (s) => ({
    ...s,
    level: 'warning',
    level_label: '预警',
  })

  if (Array.isArray(simulation.safe_warnings)) {
    const shortages = (simulation.shortages || []).map(toShortage)
    const warnings = simulation.safe_warnings.map(toWarning)
    return [...shortages, ...warnings].sort((a, b) => Number(a.time) - Number(b.time))
  }

  // 兼容旧数据：仅有 shortages 数组
  return (simulation.shortages || [])
    .map((s) => {
      const isWarning =
        Number(s.left) >= 0 && Number(s.limit || s.safe_level || 0) > 0
      return isWarning ? toWarning(s) : toShortage(s)
    })
    .sort((a, b) => Number(a.time) - Number(b.time))
}

export function materialAlertStats(simulation) {
  const all = mergeMaterialAlerts(simulation)
  const shortageCount = all.filter((a) => a.level === 'shortage').length
  const warningCount = all.filter((a) => a.level === 'warning').length
  return {
    all,
    total: all.length,
    shortageCount,
    warningCount,
    hasShortage: shortageCount > 0,
    hasWarning: warningCount > 0,
  }
}

export function levelTagType(level) {
  return level === 'shortage' ? 'danger' : 'warning'
}
