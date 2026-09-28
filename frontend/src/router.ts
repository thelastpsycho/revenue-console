import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'
import InventoryCollectionView from './views/InventoryCollectionView.vue'
import YieldManagementView from './views/YieldManagementView.vue'
import InventoryDataView from './views/InventoryDataView.vue'
import AllotmentManagementView from './views/AllotmentManagementView.vue'
import BarPricingView from './views/BarPricingView.vue'
import AutomationPipelineView from './views/AutomationPipelineView.vue'
import PmsApiTestView from './views/PmsApiTestView.vue'
import FastApiPipelineView from './views/FastApiPipelineView.vue'
import FastPipelineHistoryView from './views/FastPipelineHistoryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: DashboardView
    },
    {
      path: '/scraping',
      name: 'scraping',
      component: InventoryCollectionView
    },
    {
      path: '/yielder',
      name: 'yielder',
      component: YieldManagementView
    },
    {
      path: '/data',
      name: 'data',
      component: InventoryDataView
    },
    {
      path: '/allotment',
      name: 'allotment',
      component: AllotmentManagementView
    },
    {
      path: '/bar-calculator',
      name: 'bar-calculator',
      component: BarPricingView
    },
    {
      path: '/pipeline',
      name: 'pipeline',
      component: AutomationPipelineView
    },
    {
      path: '/pms-api-test',
      name: 'pms-api-test',
      component: PmsApiTestView
    },
    {
      path: '/fast-api-pipeline',
      name: 'fast-api-pipeline',
      component: FastApiPipelineView
    },
    {
      path: '/fast-pipeline-history',
      name: 'fast-pipeline-history',
      component: FastPipelineHistoryView
    }
  ]
})

export default router 