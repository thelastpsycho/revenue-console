import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "./stores/auth";
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
const RmsCompanyAnalyticsView = () => import("./views/RmsCompanyAnalyticsView.vue");
const RmsNationalityAnalyticsView = () => import("./views/RmsNationalityAnalyticsView.vue");

const SeasonCalendarView = () => import("./views/SeasonCalendarView.vue");
const AllotmentRulesView = () => import("./views/AllotmentRulesView.vue");

const AdministrationView = () => import("./views/AdministrationView.vue");
const DocumentationView = () => import("./views/DocumentationView.vue");
const UsersManagementView = () => import("./views/UsersManagementView.vue");

declare module "vue-router" {
  interface RouteMeta {
    title: string;
    description: string;
    // Permission key required to enter the route; omitted = any logged-in user.
    permission?: string;
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/documentation",
      name: "documentation",
      component: DocumentationView,
      meta: {
        title: "Documentation",
        description:
          "What Revenue Console does, how data flows through the pipeline, and where every setting lives.",
      },
    },
    {
      path: "/administration",
      name: "administration",
      component: AdministrationView,
      meta: {
        title: "Administration",
        description: "Data health, mappings, settings and access.",
      },
    },
    {
      path: "/",
      name: "home",
      component: DashboardView,
      meta: {
        title: "Dashboard",
        description:
          "Live status for the automated pipeline, booking data and stop sale.",
      },
    },
    {
      path: "/scraping",
      name: "scraping",
      component: InventoryCollectionView,
      meta: {
        title: "Scraping",
        description:
          "Log into the PMS and capture room availability, then process and combine inventory.",
        permission: "run_pms_scrape",
      },
    },
    {
      path: "/yielder",
      name: "yielder",
      component: YieldManagementView,
      meta: {
        title: "Yield Management",
        description: "Run the demand matrix and tune allocation strategies.",
        permission: "run_yield",
      },
    },
    {
      path: "/data",
      name: "data",
      component: InventoryDataView,
      meta: {
        title: "Data Overview",
        description: "Browse and export the combined PMS/channel-manager inventory tables.",
      },
    },
    {
      path: "/allotment",
      name: "allotment",
      component: AllotmentManagementView,
      meta: {
        title: "Allotment",
        description: "Push the calculated allotment changes back into the PMS.",
        permission: "push_pms_allotment",
      },
    },
    {
      path: "/bar-calculator",
      name: "bar-calculator",
      component: BarPricingView,
      meta: {
        title: "BAR Calculator",
        description:
          "Pick a BAR level and a discount %, and see the resulting rate for every room type.",
        permission: "push_dedge_bar",
      },
    },
    {
      path: "/pipeline",
      name: "pipeline",
      component: AutomationPipelineView,
      meta: {
        title: "Pipeline",
        description: "Run the entire scrape-to-BAR-pricing pipeline end-to-end with one click.",
        permission: "run_pipeline",
      },
    },
    {
      path: "/pms-api-test",
      name: "pms-api-test",
      component: PmsApiTestView,
      meta: {
        title: "PMS API Test",
        description:
          "Try the Selenium-free PMS client side by side with the existing scraper.",
      },
    },
    {
      path: "/fast-api-pipeline",
      name: "fast-api-pipeline",
      component: FastApiPipelineView,
      meta: {
        title: "Fast API Pipeline",
        description:
          "Same scrape-to-BAR-pricing pipeline, but PMS steps call its JSON API directly.",
        permission: "run_pipeline",
      },
    },
    {
      path: "/fast-pipeline-history",
      name: "fast-pipeline-history",
      component: FastPipelineHistoryView,
      meta: {
        title: "Fast Pipeline History",
        description: "Every Fast API Pipeline run, persisted so past logs survive.",
      },
    },
    {
      path: "/stop-sale",
      name: "stop-sale",
      component: StopSaleView,
      meta: {
        title: "Stop Sale",
        description:
          "Email a stop sale on all static rates to partners when inventory shows the hotel or a room type is full.",
        permission: "manage_stop_sale",
      },
    },
    {
      path: "/season-calendar",
      name: "season-calendar",
      component: SeasonCalendarView,
      meta: {
        title: "Season Calendar",
        description:
          "Named date ranges (Nyepi, Lebaran, Lunar New Year, Easter, Australian school holidays, events) that set the yield engine's season tier.",
        permission: "manage_season_calendar",
      },
    },
    {
      path: "/allotment-rules",
      name: "allotment-rules",
      component: AllotmentRulesView,
      meta: {
        title: "Allotment Rules",
        description:
          "Release rules per room type, the Deluxe Suite borrow trigger, and suite upgrade routing/buffers/holds.",
        permission: "manage_allotment_rules",
      },
    },
    {
      path: "/users",
      name: "users",
      component: UsersManagementView,
      meta: {
        title: "Users",
        description: "Create and manage operator accounts and their permissions.",
        permission: "manage_users",
      },
    },
    {
      path: "/rms",
      name: "rms",
      component: RmsView,
      meta: {
        title: "Revenue Management",
        description: "Daily revenue decisions: forecast, pace and budget tracking.",
      },
    },
    {
      path: "/rms/online",
      name: "rms-online",
      component: RmsOnlineView,
      meta: {
        title: "Online Segment",
        description:
          "Source mix, pace, booking behaviour and direct vs OTA demand for the Online market segment.",
      },
    },
    {
      path: "/rms/pick-up",
      name: "rms-pickup",
      component: RmsPickupView,
      meta: {
        title: "Pickup by Stay Month",
        description:
          "Whole-hotel net pickup over a selected window, rolled up by stay month, with current occupancy.",
      },
    },
    {
      path: "/rms/company-analytics",
      name: "rms-company-analytics",
      component: RmsCompanyAnalyticsView,
      meta: {
        title: "Company Analytics",
        description:
          "Length of stay, nationality, booking behaviour, pace & pickups and production by company.",
      },
    },
    {
      path: "/rms/nationality-analytics",
      name: "rms-nationality-analytics",
      component: RmsNationalityAnalyticsView,
      meta: {
        title: "Nationality Analytics",
        description:
          "Length of stay, company, booking behaviour, pace & pickups and production by guest nationality.",
      },
    },
  ],
});

router.beforeEach((to) => {
  if (!to.meta.permission) return true;
  const auth = useAuthStore();
  // AuthGate blocks unauthenticated access app-wide; this only narrows which
  // pages a logged-in user without the page's permission can reach.
  if (!auth.authenticated || auth.hasPermission(to.meta.permission)) return true;
  return { name: "home" };
});

const DEFAULT_DESCRIPTION =
  "Revenue Console — hotel inventory and revenue automation: PMS/D-EDGE inventory sync, yield management, BAR pricing, and RMS forecast & pace.";

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · Revenue Console` : "Revenue Console";
  let tag = document.querySelector('meta[name="description"]');
  if (!tag) {
    tag = document.createElement("meta");
    tag.setAttribute("name", "description");
    document.head.appendChild(tag);
  }
  tag.setAttribute("content", to.meta.description || DEFAULT_DESCRIPTION);
});

export default router;
