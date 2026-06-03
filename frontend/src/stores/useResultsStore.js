import { defineStore } from 'pinia'
import {
  hydrateImpactFromSources,
  pickActiveImpactReport,
} from '../utils/impactReport'

export const useResultsStore = defineStore('results', {
  state: () => ({
    computing: false,
    results: null,
    impactReport: null,
    lastPayload: null,
    currentPlanInput: null,
    currentPlanName: '',
    currentPlanId: '',
    /** 最近一次排程使用的策略模板（报表默认排序依据） */
    lastStrategyId: '',
    lastStrategyName: '',
    /** 甘特图高亮工单名（插单后短暂显示） */
    highlightJobNames: [],
    materialCheck: null,
    /** 影响评估所属计划（与 impactReport 同步刷新） */
    impactPlanId: '',
    /** 最近一次事件重排完整结果（与 impactPlanId 绑定，切换计划时清空） */
    lastRescheduleImpact: null,
    lastRescheduleResults: null,
  }),
  getters: {
    resultsArray: (s) => (s.results ? Object.values(s.results) : []),
    /** 影响评估展示用：避免空的 lastRescheduleImpact 盖住完整的 impactReport */
    activeImpactReport: (s) =>
      pickActiveImpactReport(s.impactReport, s.lastRescheduleImpact),
    activeRescheduleResults: (s) => s.lastRescheduleResults || s.results,
  },
  actions: {
    setResults(data) {
      this.results = data
    },
    setSchedulingStrategy(strategyId, strategyName) {
      this.lastStrategyId = strategyId || ''
      this.lastStrategyName = strategyName || ''
    },
    setImpactReport(data, extras = {}) {
      this.impactReport = data ? hydrateImpactFromSources(data, extras) : null
    },
    setRescheduleSnapshot(results, impact, extras = {}) {
      if (results) this.lastRescheduleResults = JSON.parse(JSON.stringify(results))
      if (impact) {
        const hydrated = hydrateImpactFromSources(impact, extras)
        this.lastRescheduleImpact = JSON.parse(JSON.stringify(hydrated))
      }
    },
    clearRescheduleSnapshot() {
      this.lastRescheduleImpact = null
      this.lastRescheduleResults = null
    },
    clearImpactAssessment() {
      this.impactReport = null
      this.impactPlanId = ''
      this.clearRescheduleSnapshot()
    },
    setMaterialCheck(data) {
      this.materialCheck = data
    },
    setHighlightJobNames(names) {
      this.highlightJobNames = Array.isArray(names) ? names.filter(Boolean) : []
    },
    clearHighlightJobNames() {
      this.highlightJobNames = []
    },
  },
})

