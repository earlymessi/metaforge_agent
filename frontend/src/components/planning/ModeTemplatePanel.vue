<template>
  <div class="mode-template-panel">
    <el-form label-position="top" class="mode-form">
      <el-form-item label="策略模板">
        <el-select
          v-model="presetId"
          placeholder="选择 preset"
          filterable
          clearable
          :disabled="disabled || loading"
          style="width: 100%"
        >
          <el-option
            v-for="p in presets"
            :key="p.id"
            :label="presetLabel(p)"
            :value="p.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="自然语言目标（可选）">
        <el-input
          v-model="userGoal"
          type="textarea"
          :rows="2"
          :disabled="disabled"
          placeholder="例如：交付优先，保证关键订单按期"
        />
      </el-form-item>

      <el-form-item>
        <el-switch
          v-model="requireHitl"
          :disabled="disabled"
          active-text="运行前需确认（HITL）"
          inactive-text="一键跳过策略确认"
        />
      </el-form-item>

      <el-alert
        v-if="loadError"
        type="error"
        :closable="false"
        :title="loadError"
        class="mode-alert"
      />

      <el-button
        type="primary"
        :disabled="disabled || !presetId || loading"
        :loading="loading"
        style="width: 100%"
        @click="onRun"
      >
        一键运行模板
      </el-button>
    </el-form>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'

defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['run'])

const presets = ref([])
const presetId = ref('')
const userGoal = ref('')
const requireHitl = ref(false)
const loading = ref(false)
const loadError = ref('')

function presetLabel(p) {
  return p.name ? `${p.name} (${p.id})` : p.id
}

async function loadPresets() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/api/planning/strategy/presets')
    presets.value = Array.isArray(data?.presets) ? data.presets : []
  } catch (e) {
    loadError.value = e?.message || '加载 presets 失败'
    presets.value = []
  } finally {
    loading.value = false
  }
}

function onRun() {
  if (!presetId.value) return
  emit('run', {
    preset_id: presetId.value,
    skip_strategy_hitl: !requireHitl.value,
    user_goal: userGoal.value || '',
  })
}

onMounted(loadPresets)
</script>

<style scoped>
.mode-template-panel {
  width: 100%;
}

.mode-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mode-alert {
  margin-bottom: 8px;
}
</style>
