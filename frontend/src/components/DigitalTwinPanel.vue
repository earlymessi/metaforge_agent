<template>
  <div class="twin-panel">
    <div class="toolbar">
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button value="3d">3D 车间</el-radio-button>
        <el-radio-button value="2d">平面</el-radio-button>
      </el-radio-group>
    </div>
    <DigitalTwinScene3D
      v-if="viewMode === '3d'"
      :machines="machines"
      :agvs="agvs"
      :staff="staff"
    />
    <DigitalTwinMap
      v-else
      :machines="machines"
      :agvs="agvs"
      :staff="staff"
    />
    <div v-if="machines.length" class="legend">
      <span><i class="dot run" />运行中</span>
      <span><i class="dot idle" />空闲</span>
      <span><i class="dot agv" />AGV</span>
      <span><i class="dot staff" />人员</span>
    </div>
  </div>
</template>

<script setup>
import { defineAsyncComponent, ref } from 'vue'
import DigitalTwinMap from './DigitalTwinMap.vue'

const DigitalTwinScene3D = defineAsyncComponent(() => import('./DigitalTwinScene3D.vue'))

defineProps({
  machines: { type: Array, default: () => [] },
  agvs: { type: Array, default: () => [] },
  staff: { type: Array, default: () => [] },
})

const viewMode = ref('3d')
</script>

<style scoped>
.twin-panel {
  width: 100%;
}
.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 10px;
  font-size: 12px;
  color: #606266;
}
.dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 4px;
  vertical-align: middle;
  border-radius: 2px;
}
.dot.run { background: #00c9a7; }
.dot.idle { background: #3d4f63; }
.dot.agv { background: #e6a23c; border-radius: 50%; }
.dot.staff { background: #f56c6c; border-radius: 50%; }
</style>
