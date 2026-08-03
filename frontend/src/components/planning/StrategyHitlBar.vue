<template>
  <div class="pkg-hitl-bar">
    <el-button
      type="success"
      :loading="loading"
      :disabled="!runId || loading"
      @click="$emit('approve')"
    >
      批准
    </el-button>
    <el-button
      type="danger"
      :loading="loading"
      :disabled="!runId || loading"
      @click="$emit('reject')"
    >
      拒绝
    </el-button>
    <el-button
      type="primary"
      plain
      :loading="loading"
      :disabled="!runId || loading"
      @click="$emit('edit-approve')"
    >
      编辑后批准
    </el-button>
  </div>
</template>

<script setup>
defineProps({
  runId: {
    type: String,
    default: '',
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['approve', 'reject', 'edit-approve'])
</script>

<style scoped>
.pkg-hitl-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
