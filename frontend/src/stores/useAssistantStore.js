import { defineStore } from 'pinia'

/** 全局顶栏智能助手抽屉 */
export const useAssistantStore = defineStore('assistant', {
  state: () => ({
    visible: false,
    /** 系统推送（如预约动态事件自动重排），由 AgentChatPanel 消费为助手消息 */
    systemNotices: [],
  }),
  actions: {
    open() {
      this.visible = true
    },
    close() {
      this.visible = false
    },
    toggle() {
      this.visible = !this.visible
    },
    /** @param {{ text: string, openDrawer?: boolean }} payload */
    pushSystemNotice(payload) {
      const text = (payload?.text || '').trim()
      if (!text) return
      this.systemNotices.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        text,
        ts: Date.now(),
      })
      if (payload?.openDrawer !== false) this.visible = true
    },
    shiftSystemNotice() {
      return this.systemNotices.shift() || null
    },
  },
})
