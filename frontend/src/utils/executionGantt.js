/**
 * 构建 MES 执行看板甘特图 ECharts option（随 sim_time 高亮已完成/进行中/未开始）。
 */

import * as echarts from 'echarts'

const NORMAL_COLORS = ['#305680', '#008b8b', '#4682b4', '#6b8e23', '#5f9ea0', '#708090', '#2e8b57', '#778899', '#483d8b', '#00ced1', '#4169e1']
const URGENT_COLORS = ['#d9001b', '#b03060', '#ff4500', '#8b0000', '#dc143c', '#a52a2a', '#ff6347', '#c71585']

/** 机台轴：并入故障窗机台，避免空闲机台时红区画不出来 */
function collectMachines(data, extraIds = []) {
  const set = new Set((data || []).map((d) => Number(d.machine_id)))
  for (const id of extraIds) {
    if (id == null || id === '') continue
    const n = Number(id)
    if (Number.isFinite(n)) set.add(n)
  }
  return [...set].sort((a, b) => a - b)
}

function normalizeBreakdownWindow(bw) {
  if (!bw || bw.machine_id == null) return null
  const mid = Number(bw.machine_id)
  const start = Number(bw.start)
  let end = Number(bw.end)
  if (!Number.isFinite(end) && bw.duration != null) {
    end = start + Number(bw.duration)
  }
  if (!Number.isFinite(mid) || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    return null
  }
  return { machine_id: mid, start, end }
}

/**
 * 故障/停机窗：用 custom series 画在甘特同一坐标系（比 markArea 更稳）。
 */
function buildWindowCustomSeries(machines, bw, opts = {}) {
  const win = normalizeBreakdownWindow(bw)
  if (!win) return null
  const yIdx = machines.indexOf(win.machine_id)
  if (yIdx < 0) return null
  const label = String(opts.label || bw?.label || '故障')
  const seriesName = String(opts.seriesName || (label.includes('停') ? '停机窗口' : '故障窗口'))
  const fill = opts.fill || 'rgba(245, 108, 108, 0.38)'
  const stroke = opts.stroke || '#f56c6c'

  const renderWindow = (params, api) => {
    const idx = api.value(0)
    const p0 = api.coord([api.value(1), idx])
    const p1 = api.coord([api.value(2), idx])
    const bandH = api.size([0, 1])[1] * 0.88
    const shape = echarts.graphic.clipRectByRect(
      {
        x: p0[0],
        y: p0[1] - bandH / 2,
        width: Math.max(p1[0] - p0[0], 3),
        height: bandH,
      },
      {
        x: params.coordSys.x,
        y: params.coordSys.y,
        width: params.coordSys.width,
        height: params.coordSys.height,
      },
    )
    if (!shape) return null
    const children = [
      {
        type: 'rect',
        shape,
        style: {
          fill,
          stroke,
          lineWidth: 1.5,
          lineDash: [5, 3],
        },
        z2: 1,
      },
    ]
    if (shape.width >= 36) {
      children.push({
        type: 'text',
        style: {
          text: label.slice(0, 4),
          x: shape.x + shape.width / 2,
          y: shape.y + shape.height / 2,
          fill: '#b33b3b',
          font: 'bold 11px sans-serif',
          align: 'center',
          verticalAlign: 'middle',
        },
        z2: 2,
      })
    }
    return { type: 'group', children }
  }

  return {
    name: seriesName,
    type: 'custom',
    renderItem: renderWindow,
    encode: { x: [1, 2], y: 0 },
    data: [
      {
        value: [yIdx, win.start, win.end, -1, win.machine_id, label, seriesName],
        itemStyle: { color: fill },
      },
    ],
    z: 5,
    clip: true,
  }
}

function buildBreakdownCustomSeries(machines, bw) {
  return buildWindowCustomSeries(machines, bw, {
    label: bw?.label || '故障',
    seriesName: '故障窗口',
  })
}

function collectOverlayWindows(layers) {
  const out = []
  const seen = new Set()
  const push = (bw, fallbackLabel) => {
    const win = normalizeBreakdownWindow(bw)
    if (!win) return
    const key = `${win.machine_id}:${win.start}:${win.end}`
    if (seen.has(key)) return
    seen.add(key)
    out.push({ ...win, label: bw?.label || fallbackLabel })
  }
  for (const w of layers?.downtime_windows || []) push(w, '停机')
  if (layers?.breakdown_window) {
    push(layers.breakdown_window, layers.breakdown_window.label || '故障')
  }
  return out
}

/** category 轴 markArea 作底色加强（custom 条带为主） */
function appendBreakdownMarkArea(markAreas, machines, bw, color = 'rgba(245, 108, 108, 0.18)') {
  const win = normalizeBreakdownWindow(bw)
  if (!win || !machines.includes(win.machine_id)) return
  const y = `M-${win.machine_id}`
  markAreas.push([
    { xAxis: win.start, yAxis: y, itemStyle: { color } },
    { xAxis: win.end, yAxis: y },
  ])
}

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

  const breakdownWindowsEarly = Array.isArray(opts.breakdownWindows) ? opts.breakdownWindows : []
  const machines = collectMachines(
    data,
    breakdownWindowsEarly.map((bw) => bw?.machine_id),
  )
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

  const markAreas = []
  for (const bw of breakdownWindowsEarly) {
    appendBreakdownMarkArea(markAreas, machines, bw)
    const faultSeries = buildBreakdownCustomSeries(machines, bw)
    if (faultSeries) option.series.push(faultSeries)
  }
  if (markAreas.length) {
    option.series.push({
      name: '_breakdown_bg',
      type: 'line',
      data: [],
      markArea: { silent: true, data: markAreas, z: 0 },
      tooltip: { show: false },
      legendHoverLink: false,
      z: 0,
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

  const overlayWindows = collectOverlayWindows({
    ...layers,
    breakdown_window:
      layers.breakdown_window
      || (layers.machine_id != null && layers.breakdown_start != null
        ? {
            machine_id: layers.machine_id,
            start: layers.breakdown_start,
            end: layers.breakdown_end,
            duration: layers.breakdown_duration,
            label: '故障',
          }
        : null),
  })
  const machines = collectMachines(
    data,
    overlayWindows.map((w) => w.machine_id),
  )
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
            value: [machines.indexOf(Number(d.machine_id)), d.start, d.end, d.job_id, d.machine_id, d.operation_name, jName],
            itemStyle: {
              color: baseColor,
              opacity: 0.92,
              borderColor: hi ? '#409eff' : 'transparent',
              borderWidth: hi ? 2 : 0,
            },
          }
        }),
      z: 10,
    }
  })

  for (const win of overlayWindows) {
    const raw = String(win.label || '')
    const isDown = /停|downtime|maint|planned/i.test(raw)
    const series = buildWindowCustomSeries(machines, win, {
      label: isDown ? '停机' : (raw || '故障'),
      seriesName: isDown ? '停机窗口' : '故障窗口',
      fill: isDown ? 'rgba(230, 162, 60, 0.35)' : 'rgba(245, 108, 108, 0.38)',
      stroke: isDown ? '#e6a23c' : '#f56c6c',
    })
    if (series) seriesList.unshift(series)
  }

  const makespan = opts.makespan != null
    ? Number(opts.makespan)
    : Math.max(
      ...data.map((d) => Number(d.end) || 0),
      ...overlayWindows.map((w) => Number(w.end) || 0),
      0,
    )

  const markAreas = []
  for (const win of overlayWindows) appendBreakdownMarkArea(markAreas, machines, win)
  const freezeT = layers.freeze_time
  if (opts.showFreezeZone && freezeT != null && Number(freezeT) > 0 && machines.length) {
    const y0 = `M-${machines[0]}`
    const y1 = `M-${machines[machines.length - 1]}`
    markAreas.push([
      { xAxis: 0, yAxis: y0, itemStyle: { color: 'rgba(144, 147, 153, 0.12)' } },
      { xAxis: Number(freezeT), yAxis: y1 },
    ])
  }
  if (markAreas.length) {
    seriesList.push({
      name: '_layers',
      type: 'line',
      data: [],
      markArea: { silent: true, data: markAreas, z: 0 },
      tooltip: { show: false },
      legendHoverLink: false,
      z: 0,
    })
  }

  const legendData = seriesList.filter((s) => !String(s.name).startsWith('_')).map((s) => s.name)
  const legendRows = Math.ceil(Math.max(legendData.length, 1) / 6)
  const bottomSpace = 24 + legendRows * 20

  return {
    title: opts.title
      ? { text: opts.title, left: 'center', top: 4, textStyle: { fontSize: 13, fontWeight: 600, color: '#303133' } }
      : undefined,
    animation: false,
    tooltip: {
      formatter: (p) => {
        const v = p.value || []
        if (p.seriesName === '故障窗口' || p.seriesName === '停机窗口' || v[3] === -1) {
          return `<b>${p.seriesName || v[6] || '窗口'}</b><br>机台 M-${v[4]}<br>${Number(v[1]).toFixed(2)} → ${Number(v[2]).toFixed(2)} h`
        }
        return `<b>${v[6] || ''} · ${v[5] || ''}</b><br>机台 M-${v[4]}<br>${v[1]} → ${v[2]} h`
      },
    },
    legend: {
      show: legendData.length <= 8,
      type: 'plain',
      bottom: 0,
      left: 'center',
      itemWidth: 12,
      itemHeight: 6,
      textStyle: { fontSize: 10 },
      data: legendData,
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
