import { createRouter, createWebHistory } from "vue-router";
const DashboardView = () => import("./views/DashboardView.vue");
const InventoryCollectionView = () =>
  import("./views/InventoryCollectionView.vue");
const YieldManagementView = () => import("./views/YieldManagementView.vue");
const InventoryDataView = () => import("./views/InventoryDataView.vue");
const AllotmentManagementView = () =>
  import("./views/AllotmentManagementView.vue");
const BarPricingView = () => import("./views/BarPricingView.vue");
const AutomationPipelineView = () =>
  import("./views/AutomationPipelineView.vue");
const PmsApiTestView = () => import("./views/PmsApiTestView.vue");
const FastApiPipelineView = () => import("./views/FastApiPipelineView.vue");
const FastPipelineHistoryView = () =>
  import("./views/FastPipelineHistoryView.vue");
const StopSaleView = () => import("./views/StopSaleView.vue");
const RmsView = () => import("./views/RmsView.vue");
const RmsOnlineView = () => import("./views/RmsOnlineView.vue");
const RmsPickupView = () => import("./views/RmsPickupView.vue");

const AdministrationView = () => import("./views/AdministrationView.vue");

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/administration",
      name: "administration",
      component: AdministrationView,
    },
    {
      path: "/",
      name: "home",
      component: DashboardView,
    },
    {
      path: "/scraping",
      name: "scraping",
      component: InventoryCollectionView,
    },
    {
      path: "/yielder",
      name: "yielder",
      component: YieldManagementView,
    },
    {
      path: "/data",
      name: "data",
      component: InventoryDataView,
    },
    {
      path: "/allotment",
      name: "allotment",
      component: AllotmentManagementView,
    },
    {
      path: "/bar-calculator",
      name: "bar-calculator",
      component: BarPricingView,
    },
    {
      path: "/pipeline",
      name: "pipeline",
      component: AutomationPipelineView,
    },
    {
      path: "/pms-api-test",
      name: "pms-api-test",
      component: PmsApiTestView,
    },
    {
      path: "/fast-api-pipeline",
      name: "fast-api-pipeline",
      component: FastApiPipelineView,
    },
    {
      path: "/fast-pipeline-history",
      name: "fast-pipeline-history",
      component: FastPipelineHistoryView,
    },
    {
      path: "/stop-sale",
      name: "stop-sale",
      component: StopSaleView,
    },
    {
      path: "/rms",
      name: "rms",
      component: RmsView,
    },
    {
      path: "/rms/online",
      name: "rms-online",
      component: RmsOnlineView,
    },
    {
      path: "/rms/pick-up",
      name: "rms-pickup",
      component: RmsPickupView,
    },
  ],
});

export default router;
