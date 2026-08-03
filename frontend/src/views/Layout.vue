<template>
  <el-container class="h">
    <el-aside width="240px" class="aside">
      <div class="brand">
        <div class="brand-text">
          <div class="brand-line">融合强化学习的车间</div>
          <div class="brand-line">智能排程与资源调度管控系统</div>
        </div>
      </div>

      <div class="nav-menu">
        <div class="nav-header">主控台</div>
        <el-menu :default-active="active" router class="menu" background-color="transparent" text-color="#bfcbd9" active-text-color="#ffffff">
          <el-menu-item index="/dashboard" class="nav-item">
            <el-icon><Monitor /></el-icon>
            <span>生产看板</span>
          </el-menu-item>
          <el-menu-item index="/database" class="nav-item">
            <el-icon><FolderOpened /></el-icon>
            <span>数据中心</span>
          </el-menu-item>

          <div class="nav-header">调度排程</div>
          <el-menu-item index="/aps" class="nav-item">
            <el-icon><Calendar /></el-icon>
            <span>智能排程</span>
          </el-menu-item>
          <el-menu-item index="/reports" class="nav-item">
            <el-icon><DataAnalysis /></el-icon>
            <span>分析报表</span>
          </el-menu-item>
          <el-menu-item index="/compare" class="nav-item">
            <el-icon><Histogram /></el-icon>
            <span>方案对比</span>
          </el-menu-item>

          <div class="nav-header">资源管控</div>
          <el-menu-item index="/energy" class="nav-item">
            <el-icon><Lightning /></el-icon>
            <span>能耗管控调度</span>
          </el-menu-item>
          <el-menu-item index="/health" class="nav-item">
            <el-icon><FirstAidKit /></el-icon>
            <span>设备健康管控</span>
          </el-menu-item>
          <el-menu-item index="/logistics" class="nav-item">
            <el-icon><Van /></el-icon>
            <span>AGV物流调度</span>
          </el-menu-item>
          <el-menu-item index="/staffing" class="nav-item">
            <el-icon><User /></el-icon>
            <span>人员负荷调度</span>
          </el-menu-item>
          <el-menu-item index="/materials" class="nav-item">
            <el-icon><Box /></el-icon>
            <span>加工物料调度</span>
          </el-menu-item>

        </el-menu>
      </div>

      <div class="aside-footer">
        数据库: <strong class="ok">已连接</strong><br />
        V2.2.0 (DB)
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-icon class="indent"><Fold /></el-icon>
          <div class="route-title">{{ routeTitle }}</div>
        </div>
        <div class="header-right">
          <div class="system-status">
            <span class="status-dot"></span>
            <span class="text-success">MongoDB Online</span>
          </div>
          <div class="system-time">
            <el-icon><Clock /></el-icon>
            <span>{{ currentTime }}</span>
          </div>
          <div class="user">
            <div class="avatar">OP</div>
            <div class="user-name">管理员</div>
          </div>
          <el-button type="primary" class="assistant-trigger" @click="assistantStore.open()">
            <el-icon><ChatDotRound /></el-icon>
            智能助手
          </el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <el-drawer
      v-model="assistantStore.visible"
      title="车间智能助手"
      size="520px"
      direction="rtl"
      class="global-assistant-drawer"
    >
      <AgentChatPanel compact :show-header="false" />
    </el-drawer>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis, Lightning, FolderOpened, Monitor, Van, User, Box, FirstAidKit, Fold, Clock, Calendar, ChatDotRound, Histogram } from '@element-plus/icons-vue'
import AgentChatPanel from '../components/AgentChatPanel.vue'
import { useAssistantStore } from '../stores/useAssistantStore'

const route = useRoute()
const assistantStore = useAssistantStore()
const active = computed(() => route.path)

const routeTitle = computed(() => {
  const map = {
    '/dashboard': '生产看板',
    '/database': '数据中心',
    '/aps': '智能排程',
    '/assistant': '智能助手',
    '/reports': '分析报表',
    '/compare': '方案对比',
    '/energy': '能耗管控调度',
    '/health': '设备健康管控',
    '/logistics': 'AGV物流调度',
    '/staffing': '人员负荷调度',
    '/materials': '加工物料调度',
  }
  return map[route.path] || '智能生产调度系统'
})

const currentTime = ref('')
let timer = null
function tick() {
  currentTime.value = new Date().toLocaleString()
}
onMounted(() => {
  tick()
  timer = setInterval(tick, 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.h { height: 100vh; }
.aside { background: #202d3d; color: #bfcbd9; }
.brand {
  min-height: 65px;
  padding: 12px 16px;
  display:flex;
  align-items:center;
  justify-content:center;
  text-align:center;
  background:#002140;
  color:#fff;
  border-bottom: 1px solid #2c3b4e;
}
.brand-text { line-height: 1.3; }
.brand-line { font-size: 14px; font-weight: 700; letter-spacing: 0.5px; }
.nav-menu { flex: 1; padding-top: 10px; overflow-y: auto; }
.nav-header { font-size: 12px; color: #758091; padding: 15px 20px 5px; font-weight: bold; }
.menu { border-right: none; background: transparent; }

/* Element Plus menu -> old nav-item look */
:deep(.el-menu) { border-right: none; }
:deep(.el-menu-item) {
  height: auto;
  line-height: normal;
  padding: 12px 20px;
  color: #bfcbd9;
  border-left: 4px solid transparent;
}
:deep(.el-menu-item:hover) {
  background: #263445 !important;
  color: #ffffff !important;
}
:deep(.el-menu-item.is-active) {
  background: #1890ff !important;
  color: #ffffff !important;
  border-left-color: #1890ff;
}
:deep(.el-menu-item .el-icon) { margin-right: 12px; font-size: 16px; width: 20px; }

.aside-footer {
  padding: 12px 16px;
  font-size: 12px;
  color: #909399;
  border-top: 1px solid #34495e;
}
.ok { color: #67c23a; }

.header {
  height: 55px;
  background: #ffffff;
  border-bottom: 1px solid #dcdfe6;
  display:flex;
  align-items:center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: 0 1px 4px rgba(0,21,41,0.08);
}
.header-left { display:flex; align-items:center; gap: 12px; }
.indent { color: #909399; font-size: 16px; }
.route-title { margin: 0; font-weight: 700; color: #303133; font-size: 15px; }
.header-right { display:flex; align-items:center; gap: 18px; color: #606266; font-size: 13px; }
.system-status { display:flex; align-items:center; gap: 8px; }
.status-dot { height: 8px; width: 8px; background-color: #67c23a; border-radius: 50%; display: inline-block; }
.system-time { display:flex; align-items:center; gap: 6px; color: #909399; }
.user { display:flex; align-items:center; gap: 8px; }
.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size: 12px;
}
.user-name { font-weight: 600; font-size: 13px; color: #606266; }
.assistant-trigger { margin-left: 4px; }
:deep(.global-assistant-drawer .el-drawer__body) {
  padding: 12px 16px 16px;
  display: flex;
  flex-direction: column;
  height: calc(100% - 56px);
}
:deep(.global-assistant-drawer .chat-panel) {
  flex: 1;
  min-height: 0;
}
:deep(.global-assistant-drawer .messages) {
  max-height: none;
  flex: 1;
}

.main { background: #f0f2f5; }
</style>

