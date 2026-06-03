import { defineStore } from 'pinia'

/** 跨页面共享：当前计划 / 工单，供智能助手与异常重排自动带入 */
export const useWorkContextStore = defineStore('workContext', {
  state: () => ({
    planId: '',
    planName: '',
    customJobs: null,
    source: '',
  }),
  getters: {
    hasJobs: (s) => Array.isArray(s.customJobs) && s.customJobs.length > 0,
    summaryLabel(state) {
      if (!state.hasJobs) return '未绑定工单计划'
      const name = state.planName || '当前工单'
      const n = state.customJobs.length
      const src = { aps: '排程中心', reports: '分析报表', database: '数据中心', manual: '手动选择' }[
        state.source
      ] || ''
      return `${name}（${n} 个工单${src ? ` · 来自${src}` : ''}）`
    },
  },
  actions: {
    setFromPlan({ planId = '', planName = '', jobs = null, source = '' }) {
      this.planId = planId || ''
      this.planName = planName || ''
      this.customJobs = Array.isArray(jobs) ? jobs : null
      this.source = source || ''
    },
    clear() {
      this.planId = ''
      this.planName = ''
      this.customJobs = null
      this.source = ''
    },
  },
})
