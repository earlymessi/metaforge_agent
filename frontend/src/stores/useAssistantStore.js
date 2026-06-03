import { defineStore } from 'pinia'

/** 全局顶栏智能助手抽屉 */
export const useAssistantStore = defineStore('assistant', {
  state: () => ({
    visible: false,
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
  },
})
