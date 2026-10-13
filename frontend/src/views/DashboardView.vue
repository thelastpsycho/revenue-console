<template>
  <div class="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6 lg:px-10">
    <!-- Header (inlined minimal — isolated from the shared neumorphic PageHeader) -->
    <header
      class="flex flex-col gap-5 border-b border-slate-200 pb-8 sm:flex-row sm:items-end sm:justify-between"
    >
      <div class="min-w-0">
        <p class="text-xs font-medium uppercase tracking-widest text-slate-400">
          Revenue Console
        </p>
        <h1 class="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
          Dashboard
        </h1>
        <p class="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500">
          Live status for the automated pipeline, booking data and stop sale —
          jump into any report below.
        </p>
      </div>
      <router-link
        to="/fast-api-pipeline"
        class="inline-flex flex-shrink-0 items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700 cursor-pointer"
      >
        <BoltIcon class="h-4 w-4" />
        Open Fast API Pipeline
      </router-link>
    </header>

    <!-- Live status -->
    <section class="mt-10">
      <div class="flex items-center justify-between">
        <h2
          class="text-xs font-medium uppercase tracking-widest text-slate-400"
        >
          Status
        </h2>
        <button type="button" class="text-xs underline" @click="refresh()">
          Refresh status
        </button>
      </div>
      <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <article
          class="group neu-card flex flex-col gap-3 p-5 transition-colors hover:border-slate-300"
        >
          <div class="flex items-center justify-between">
            <span
              class="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-colors group-hover:bg-slate-900 group-hover:text-white"
            >
              <BoltIcon class="h-4.5 w-4.5" />
            </span>
            <span
              v-if="!pipeline.loading"
              :class="['pill', pipelineTone.pill]"
              >{{ pipelineTone.label }}</span
            >
          </div>
          <div>
            <router-link
              to="/fast-api-pipeline"
              class="text-sm font-semibold text-slate-900 underline"
              >Automation</router-link
            >
            <p class="mt-0.5 text-xs leading-relaxed text-slate-500">
              {{ pipeline.loading ? "Loading…" : pipelineDetail }}
            </p>
            <p class="mt-2 text-xs text-slate-500">
              Last successful check: {{ timestamp(pipeline.checkedAt) }}
            </p>
            <button
              v-if="pipeline.error"
              type="button"
              class="mt-2 text-xs font-semibold underline"
              :disabled="pipeline.loading"
              @click="refresh('pipeline')"
            >
              Retry automation
            </button>
            <div v-if="pipeline.lastRun" class="mt-2 space-y-1">
              <span :class="['pill', lastRunTone.pill]">{{
                lastRunTone.label
              }}</span>
              <p class="text-xs text-slate-500">
                {{
                  timestamp(
                    pipeline.lastRun.finished_at || pipeline.lastRun.started_at,
                  )
                }}
              </p>
              <router-link
                :to="{
                  path: '/fast-pipeline-history',
                  query: { runId: pipeline.lastRun.id },
                }"
                class="text-xs underline"
                >View run logs</router-link
              >
            </div>
          </div>
        </article>

        <article
          class="group neu-card flex flex-col gap-3 p-5 transition-colors hover:border-slate-300"
        >
          <div class="flex items-center justify-between">
            <span
              class="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-colors group-hover:bg-slate-900 group-hover:text-white"
            >
              <CircleStackIcon class="h-4.5 w-4.5" />
            </span>
            <span v-if="!sync.loading" :class="['pill', syncTone.pill]">{{
              syncTone.label
            }}</span>
          </div>
          <div>
            <router-link
              to="/rms"
              class="text-sm font-semibold text-slate-900 underline"
              >Booking data</router-link
            >
            <p class="mt-0.5 text-xs leading-relaxed text-slate-500">
              {{ sync.loading ? "Loading…" : syncDetail }}
            </p>
            <p class="mt-2 text-xs text-slate-500">
              Last successful check: {{ timestamp(sync.checkedAt) }}
            </p>
            <button
              v-if="sync.error"
              type="button"
              class="mt-2 text-xs font-semibold underline"
              :disabled="sync.loading"
              @click="refresh('sync')"
            >
              Retry booking data
            </button>
          </div>
        </article>

        <article
          class="group neu-card flex flex-col gap-3 p-5 transition-colors hover:border-slate-300"
        >
          <div class="flex items-center justify-between">
            <span
              class="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-colors group-hover:bg-slate-900 group-hover:text-white"
            >
              <EnvelopeIcon class="h-4.5 w-4.5" />
            </span>
            <span
              v-if="!stopSale.loading"
              :class="['pill', stopSaleTone.pill]"
              >{{ stopSaleTone.label }}</span
            >
          </div>
          <div>
            <router-link
              to="/stop-sale"
              class="text-sm font-semibold text-slate-900 underline"
              >Stop sale</router-link
            >
            <p class="mt-0.5 text-xs leading-relaxed text-slate-500">
              {{ stopSale.loading ? "Loading…" : stopSaleDetail }}
            </p>
            <p class="mt-2 text-xs text-slate-500">
              Last successful check: {{ timestamp(stopSale.checkedAt) }}
            </p>
            <button
              v-if="stopSale.error"
              type="button"
              class="mt-2 text-xs font-semibold underline"
              :disabled="stopSale.loading"
              @click="refresh('stopSale')"
            >
              Retry stop sale
            </button>
            <p class="mt-2 text-xs text-slate-500">
              Inventory updated: {{ timestamp(stopSale.updatedAt) }}. Stale
              after {{ thresholdMinutes }} min.
            </p>
          </div>
        </article>
      </div>
    </section>

    <!-- Reports and tools -->
    <section class="mt-10">
      <h2 class="text-xs font-medium uppercase tracking-widest text-slate-400">
        Reports &amp; tools
      </h2>
      <div
        class="mt-5 grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-4"
      >
        <router-link
          v-for="link in links"
          :key="link.title"
          :to="link.href"
          class="group flex flex-col bg-white p-6 transition-colors hover:bg-slate-50 cursor-pointer"
        >
          <component
            :is="link.icon"
            class="h-5 w-5 text-slate-400 transition-colors group-hover:text-slate-900"
          />
          <h3 class="mt-6 text-sm font-medium text-slate-900">
            {{ link.title }}
          </h3>
          <p class="mt-1.5 flex-1 text-xs leading-relaxed text-slate-500">
            {{ link.description }}
          </p>
          <span
            class="mt-4 inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors group-hover:text-slate-900"
          >
            Open
            <ArrowRightIcon class="h-3.5 w-3.5" />
          </span>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from "vue";
import {
  CircleStackIcon,
  ChartBarIcon,
  ArrowRightIcon,
  BoltIcon,
  ReceiptPercentIcon,
  EnvelopeIcon,
  ClockIcon,
  PresentationChartLineIcon,
  GlobeAltIcon,
} from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import { timestamp } from "../utils/rms";
import {
  scheduleTone,
  runTone,
  inventoryTone,
  refreshController,
  type Schedule,
  type Run,
  type Coverage,
} from "../utils/dashboardStatus";

const links = [
  {
    title: "RMS",
    description: "Daily pace, forecast, production and booking behaviour.",
    href: "/rms",
    icon: PresentationChartLineIcon,
  },
  {
    title: "Online segment",
    description: "Source mix, pace and Santika Online's direct vs OTA share.",
    href: "/rms/online",
    icon: GlobeAltIcon,
  },
  {
    title: "Fast API Pipeline",
    description: "Run or schedule the full scrape-to-BAR automation.",
    href: "/fast-api-pipeline",
    icon: BoltIcon,
  },
  {
    title: "Pipeline History",
    description: "Past automated runs and their logs.",
    href: "/fast-pipeline-history",
    icon: ClockIcon,
  },
  {
    title: "Stop Sale",
    description: "Review closures from current inventory and send the email.",
    href: "/stop-sale",
    icon: EnvelopeIcon,
  },
  {
    title: "BAR Calculator",
    description: "One-off BAR level calculations.",
    href: "/bar-calculator",
    icon: ReceiptPercentIcon,
  },
  {
    title: "Data",
    description: "Raw and processed PMS/CM/combined inventory tables.",
    href: "/data",
    icon: CircleStackIcon,
  },
  {
    title: "Yielder",
    description: "Manual yield run with full threshold control.",
    href: "/yielder",
    icon: ChartBarIcon,
  },
];

const pipeline = reactive({
  loading: true,
  error: false,
  checkedAt: null as string | null,
  schedule: null as Schedule | null,
  lastRun: null as Run | null,
  active: false,
});
const sync = reactive({
  loading: true,
  error: false,
  checkedAt: null as string | null,
  lastSuccessfulSync: null as string | null,
  stale: true,
  bookings: null as number | null,
  coverageFrom: null as string | null,
});
const stopSale = reactive({
  loading: true,
  error: false,
  checkedAt: null as string | null,
  count: null as number | null,
  updatedAt: null as string | null,
  coverage: null as Coverage | null,
});
const now = ref(Date.now());
const thresholdMinutes = computed(() =>
  Math.max(30, (pipeline.schedule?.intervalMinutes || 15) * 2),
);
const pipelineTone = computed(() =>
  scheduleTone(pipeline.schedule, pipeline.active, pipeline.error),
);
const lastRunTone = computed(() => runTone(pipeline.lastRun));
const pipelineDetail = computed(() => {
  if (pipeline.error)
    return "Status request failed. Retry to check automation.";
  const s = pipeline.schedule;
  if (!s) return "Schedule status unavailable";
  if (!s.enabled) return "Not scheduled";
  return `Every ${s.intervalMinutes} min · next ${timestamp(s.nextRunAt)}`;
});
const syncTone = computed(() => {
  if (sync.error) return { label: "Unable to load", pill: "pill-bad" };
  const stale =
    sync.stale ||
    !sync.lastSuccessfulSync ||
    now.value - Date.parse(sync.lastSuccessfulSync) > 36 * 3600000;
  return {
    label: stale ? "Stale" : "Synced",
    pill: stale ? "pill-warn" : "pill-ok",
  };
});
const syncDetail = computed(() =>
  sync.error
    ? "Status request failed. Retry to check booking data."
    : `${sync.bookings?.toLocaleString("en-US") ?? "Unknown"} bookings · last synced ${timestamp(sync.lastSuccessfulSync)}`,
);
const stopSaleTone = computed(() =>
  inventoryTone(
    stopSale.count,
    stopSale.updatedAt,
    stopSale.coverage,
    stopSale.error,
    now.value,
    thresholdMinutes.value,
  ),
);
const stopSaleDetail = computed(() => {
  if (stopSale.error)
    return "Preview request failed. Retry or open Stop Sale for details.";
  if (!stopSale.coverage?.days)
    return "No upcoming dates have inventory coverage.";
  return `${stopSale.count ?? "Unknown"} closure dates · checked ${stopSale.coverage.from}–${stopSale.coverage.to} (${stopSale.coverage.days} dates)`;
});
let disposed = false;
const cards = { pipeline, sync, stopSale };
const controller = refreshController(Object.keys(cards), async (key) => {
  const card = cards[key as keyof typeof cards];
  card.loading = true;
  try {
    const endpoint = {
      pipeline: "/api/fast-pipeline/schedule",
      sync: "/api/rms/sync",
      stopSale: "/api/stop-sale/preview",
    }[key as keyof typeof cards];
    const { data } = await axios.get(endpoint, { timeout: 10000 });
    if (disposed) return;
    if (key === "pipeline") {
      pipeline.schedule = data.schedule;
      pipeline.lastRun = data.lastScheduledRun;
      pipeline.active = !!data.pipelineActive;
    } else if (key === "sync") {
      sync.lastSuccessfulSync = data.lastSuccessfulSync;
      sync.stale = data.stale;
      sync.bookings = data.bookings ?? null;
      sync.coverageFrom = data.coverageFrom;
    } else {
      stopSale.count = Array.isArray(data.closures)
        ? data.closures.length
        : null;
      stopSale.updatedAt = data.updatedAt;
      stopSale.coverage = data.coverage ?? null;
    }
    card.error = false;
    card.checkedAt = new Date().toISOString();
  } catch {
    if (!disposed) card.error = true;
  } finally {
    if (!disposed) card.loading = false;
  }
});
function refresh(key?: string) {
  if (!disposed) {
    now.value = Date.now();
    void controller.refresh(key);
  }
}
function visibleRefresh() {
  if (document.visibilityState === "visible") refresh();
}
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  refresh();
  timer = setInterval(visibleRefresh, 15000);
  document.addEventListener("visibilitychange", visibleRefresh);
  window.addEventListener("focus", visibleRefresh);
});
onBeforeUnmount(() => {
  disposed = true;
  controller.stop();
  clearInterval(timer);
  document.removeEventListener("visibilitychange", visibleRefresh);
  window.removeEventListener("focus", visibleRefresh);
});
</script>
