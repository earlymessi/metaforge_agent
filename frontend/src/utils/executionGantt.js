/**
 * 构建 MES 执行看板甘特图 ECharts option（随 sim_time 高亮已完成/进行中/未开始）。
 */

import * as echarts from 'echarts'

const NORMAL_COLORS = ['#305680', '#008b8b', '#4682b4', '#6b8e23', '#5f9ea0', '#708090', '#2e8b57', '#778899', '#483d8b', '#00ced1', '#4169e1']
const URGENT_COLORS = ['#d9001b', '#b03060', '#ff4500', '#8b0000', '#dc143c', '#a52a2a', '#ff6347', '#c71585']

function opPhase(start, end, simTime) {
  const s = Number(start)
  const e = Number(end)
  const t = Number(simTime)
  if (e <= t + 1e-9) return 'done'
  if (s >= t - 1e-9) return 'pending'
  if (s < t && t < e) return 'running'
  return 'pending'
}

export function buildExecutionGanttOption(ganttData, simTime = 0, opts = {}) {
  const data = Array.isArray(ganttData) ? ganttData : []
  const sim = Math.max(0, Number(simTime) || 0)
  const showNowLine = opts.showNowLine !== false && sim > 0

  if (!data.length) {
    return {
      title: { text: opts.emptyText || '暂无甘特数据', left: 'center', top: 'middle', textStyle: { color: '#909399', fontSize: 14 } },
    }
  }

  const machines = [...new Set(data.map((d) => d.machine_id))].sort((a, b) => a - b)
  const jobIds = [...new Set(data.map((d) => d.job_id))].sort((a, b) => a - b)

  const renderItem = (params, api) => {
    const idx = api.value(0)
    const start = api.coord([api.value(1), idx])
    const end = api.coord([api.value(2), idx])
    const h = api.size([0, 1])[1] * 0.6
    return {
      type: 'rect',
      shape: echarts.graphic.clipRectByRect(
        { x: start[0], y: start[1] - h / 2, width: Math.max(end[0] - start[0], 2), height: h },
        { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height },
      ),
      style: { ...api.style(), borderRadius: 2 },
    }
  }

  const seriesList = jobIds.map((jid) => {
    const firstItem = data.find((d) => d.job_id === jid)
    const priority = firstItem ? Number(firstItem.priority || 10) : 10
    const isUrgent = priority > 10
    const jName = firstItem?.job_name ? firstItem.job_name : `工单 ${jid}`
    const displayName = isUrgent ? `🔥 ${jName}` : jName
    const baseColor = isUrgent ? URGENT_COLORS[jid % URGENT_COLORS.length] : NORMAL_COLORS[jid % NORMAL_COLORS.length]

    return {
      name: displayName,
      type: 'custom',
      renderItem,
      encode: { x: [1, 2], y: 0 },
      data: data
        .filter((d) => d.job_id === jid)
        .map((d) => {
          const phase = opPhase(d.start, d.end, sim)
          let opacity = 0.32
          let borderColor = 'transparent'
          let borderWidth = 0
          let shadowBlur = 0
          if (phase === 'done') {
            opacity = 0.55
          } else if (phase === 'running') {
            opacity = 1
            borderColor = '#ffd04b'
            borderWidth = 2
            shadowBlur = 8
          } else if (phase === 'pending') {
            opacity = 0.95
          }
          return {
            value: [machines.indexOf(d.machine_id), d.start, d.end, d.job_id, d.machine_id, d.operation_name, jName, phase],
            itemStyle: {
              color: baseColor,
              opacity,
              borderColor,
              borderWidth,
              shadowBlur,
              shadowColor: phase === 'running' ? 'rgba(255, 208, 75, 0.8)' : 'transparent',
            },
          }
        }),
    }
  })

  const legendRows = Math.ceil(seriesList.length / 8)
  const bottomSpace = 28 + legendRows * 22
  const makespan = opts.makespan != null ? Number(opts.makespan) : Math.max(...data.map((d) => Number(d.end) || 0), sim)

  const option = {
    animation: true,
    animationDurationUpdate: 400,
    tooltip: {
      formatter: (p) => {
        const v = p.value || []
        const phaseMap = { done: '已完成', running: '进行中', pending: '未开始' }
        return `<b>${v[6] || ''} · ${v[5] || ''}</b><br>机台 M-${v[4]}<br>${v[1]} → ${v[2]} h<br>状态: ${phaseMap[v[7]] || '-'}`
      },
    },
    legend: {
      type: 'plain',
      bottom: 0,
      left: 'center',
      width: '95%',
      itemGap: 12,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: { fontSize: 11 },
    },
    grid: { top: 36, left: 56, right: 24, bottom: bottomSpace },
    xAxis: {
      min: 0,
      max: makespan > 0 ? makespan * 1.02 : undefined,
      scale: true,
      name: '排程时间 (h)',
      nameLocation: 'middle',
      nameGap: 28,
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#ebeef5' } },
      axisLabel: { color: '#606266' },
    },
    yAxis: {
      type: 'category',
      data: machines.map((m) => `M-${m}`),
      splitLine: { show: true, lineStyle: { color: '#f0f2f5' } },
      axisLabel: { fontWeight: 'bold', color: '#303133' },
    },
    series: seriesList,
  }

  if (showNowLine) {
    option.series.push({
      name: '_now',
      type: 'line',
      data: [],
      markLine: {
        silent: false,
        symbol: 'none',
        lineStyle: { color: '#f56c6c', width: 2, type: 'solid' },
        label: {
          formatter: `当前 ${sim.toFixed(1)} h`,
          position: 'insideEndTop',
          color: '#f56c6c',
          fontWeight: 'bold',
        },
        data: [{ xAxis: sim }],
      },
      z: 200,
    })
  }

  const breakdownWindows = Array.isArray(opts.breakdownWindows) ? opts.breakdownWindows : []
  const markAreas = []
  for (const bw of breakdownWindows) {
    if (bw?.machine_id == null) continue
    const yIdx = machines.indexOf(Number(bw.machine_id))
    if (yIdx < 0) continue
    markAreas.push([
      { xAxis: bw.start, yAxis: yIdx - 0.4, itemStyle: { color: 'rgba(245, 108, 108, 0.4)' } },
      { xAxis: bw.end, yAxis: yIdx + 0.4 },
    ])
  }
  if (markAreas.length) {
    option.series.push({
      name: '_breakdown',
      type: 'line',
      data: [],
      markArea: { silent: true, data: markAreas },
      z: 50,
    })
  }

  return option
}

function opKey(d) {
  return `${d.job_id}:${d.operation_id ?? d.id ?? 0}`
}

/** 影响评估静态甘特（R1 不重排 / R2 重排对比） */
export function buildImpactGanttOption(ganttData, opts = {}) {
  const data = Array.isArray(ganttData) ? ganttData : []
  const highlightSet = new Set(opts.highlightKeys || [])
  const layers = opts.layers || {}

  if (!data.length) {
    return {
      title: { text: opts.emptyText || '暂无甘特数据', left: 'center', top: 'middle', textStyle: { color: '#909399', fontSize: 13 } },
    }
  }

  const machines = [...new Set(data.map((d) => d.machine_id))].sort((a, b) => a - b)
  const jobIds = [...new Set(data.map((d) => d.job_id))].sort((a, b) => a - b)

  const renderItem = (params, api) => {
    const idx = api.value(0)
    const start = api.coord([api.value(1), idx])
    const end = api.coord([api.value(2), idx])
    const h = api.size([0, 1])[1] * 0.6
    return {
      type: 'rect',
      shape: echarts.graphic.clipRectByRect(
        { x: start[0], y: start[1] - h / 2, width: Math.max(end[0] - start[0], 2), height: h },
        { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height },
      ),
      style: { ...api.style(), borderRadius: 2 },
    }
  }

  const seriesList = jobIds.map((jid) => {
    const firstItem = data.find((d) => d.job_id === jid)
    const priority = firstItem ? Number(firstItem.priority || 10) : 10
    const isUrgent = priority > 10
    const jName = firstItem?.job_name ? firstItem.job_name : `工单 ${jid}`
    const displayName = isUrgent ? `🔥 ${jName}` : jName
    const baseColor = isUrgent ? URGENT_COLORS[jid % URGENT_COLORS.length] : NORMAL_COLORS[jid % NORMAL_COLORS.length]

    return {
      name: displayName,
      type: 'custom',
      renderItem,
      encode: { x: [1, 2], y: 0 },
      data: data
        .filter((d) => d.job_id === jid)
        .map((d) => {
          const hi = highlightSet.has(opKey(d))
          return {
            value: [machines.indexOf(d.machine_id), d.start, d.end, d.job_id, d.machine_id, d.operation_name, jName],
            itemStyle: {
              color: baseColor,
              opacity: 0.92,
              borderColor: hi ? '#409eff' : 'transparent',
              borderWidth: hi ? 2 : 0,
            },
          }
        }),
    }
  })

  const makespan = opts.makespan != null
    ? Number(opts.makespan)
    : Math.max(...data.map((d) => Number(d.end) || 0), 0)

  const markAreas = []
  const bw = layers.breakdown_window
  if (bw && bw.machine_id != null) {
    const yIdx = machines.indexOf(Number(bw.machine_id))
    if (yIdx >= 0) {
      markAreas.push([
        { xAxis: bw.start, yAxis: yIdx - 0.4, itemStyle: { color: 'rgba(245, 108, 108, 0.35)' } },
        { xAxis: bw.end, yAxis: yIdx + 0.4 },
      ])
    }
  }
  const freezeT = layers.freeze_time
  if (opts.showFreezeZone && freezeT != null && Number(freezeT) > 0) {
    markAreas.push([
      { xAxis: 0, yAxis: -0.5, itemStyle: { color: 'rgba(144, 147, 153, 0.12)' } },
      { xAxis: freezeT, yAxis: machines.length - 0.5 },
    ])
  }
  if (markAreas.length) {
    seriesList.push({
      name: '_layers',
      type: 'line',
      data: [],
      markArea: { silent: true, data: markAreas },
      z: 1,
    })
  }

  const legendRows = Math.ceil(seriesList.length / 6)
  const bottomSpace = 24 + legendRows * 20

  return {
    title: opts.title
      ? { text: opts.title, left: 'center', top: 4, textStyle: { fontSize: 13, fontWeight: 600, color: '#303133' } }
      : undefined,
    animation: false,
    tooltip: {
      formatter: (p) => {
        const v = p.value || []
        return `<b>${v[6] || ''} · ${v[5] || ''}</b><br>机台 M-${v[4]}<br>${v[1]} → ${v[2]} h`
      },
    },
    legend: {
      show: seriesList.length <= 8,
      type: 'plain',
      bottom: 0,
      left: 'center',
      itemWidth: 12,
      itemHeight: 6,
      textStyle: { fontSize: 10 },
    },
    grid: { top: opts.title ? 32 : 16, left: 48, right: 16, bottom: bottomSpace },
    xAxis: {
      min: 0,
      max: makespan > 0 ? makespan * 1.02 : undefined,
      scale: true,
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#ebeef5' } },
      axisLabel: { fontSize: 10, color: '#606266' },
    },
    yAxis: {
      type: 'category',
      data: machines.map((m) => `M-${m}`),
      axisLabel: { fontSize: 10, fontWeight: 'bold' },
    },
    series: seriesList,
  }
}
