import { createRouter, createWebHistory } from 'vue-router'

import Layout from '../views/Layout.vue'
import DashboardView from '../views/DashboardView.vue'
import APSView from '../views/APSView.vue'
import AnalysisView from '../views/AnalysisView.vue'
import EnergyView from '../views/EnergyView.vue'
import DataCenterView from '../views/DataCenterView.vue'
import LogisticsView from '../views/LogisticsView.vue'
import StaffingView from '../views/StaffingView.vue'
import MaterialsView from '../views/MaterialsView.vue'
import HealthView from '../views/HealthView.vue'
import AgentChatView from '../views/AgentChatView.vue'
import CompareView from '../views/CompareView.vue'

export default createRouter({
  history: createWebHistory('/new-ui'),
  routes: [
    {
      path: '/',
      component: Layout,
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', component: DashboardView },
        { path: 'database', component: DataCenterView },
        { path: 'aps', component: APSView },
        { path: 'assistant', component: AgentChatView },
        { path: 'reports', component: AnalysisView },
        { path: 'compare', component: CompareView },
        { path: 'energy', component: EnergyView },
        { path: 'health', component: HealthView },
        { path: 'logistics', component: LogisticsView },
        { path: 'staffing', component: StaffingView },
        { path: 'materials', component: MaterialsView },
      ],
    },
  ],
})

