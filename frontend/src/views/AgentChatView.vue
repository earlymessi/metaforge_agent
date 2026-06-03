<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistantStore } from '../stores/useAssistantStore'

const router = useRouter()
const assistantStore = useAssistantStore()

/** 旧链接 /assistant：打开顶栏全局助手并回到看板 */
onMounted(() => {
  assistantStore.open()
  router.replace('/dashboard')
})
</script>

<template>
  <div />
</template>
