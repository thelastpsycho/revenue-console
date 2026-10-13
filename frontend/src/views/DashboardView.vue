<template>
  <div class="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6 lg:px-10">
    <!-- Header (inlined minimal — isolated from the shared neumorphic PageHeader) -->
    <header class="flex flex-col gap-5 border-b border-slate-200 pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div class="min-w-0">
        <p class="text-xs font-medium uppercase tracking-widest text-slate-400">Revenue Console</p>
        <h1 class="mt-2 text-2xl font-semibold tracking-tight text-slate-900">Dashboard</h1>
        <p class="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500">
          Live status for the automated pipeline, booking data and stop sale — jump into any report below.
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
      <h2 class="text-xs font-medium uppercase tracking-widest text-slate-400">Status</h2>
      <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <router-link
          to="/fast-api-pipeline"
          class="group neu-card flex flex-col gap-3 p-5 transition-colors hover:border-slate-300"
        >
          <div class="flex items-center justify-between">
            <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-colors group-hover:bg-slate-900 group-hover:text-white">
              <BoltIcon class="h-4.5 w-4.5" />
            </span>
            <span v-if="!pipeline.loading" :class="['pill', pipelineTone.pill]">{{ pipelineTone.label }}</span>
          </div>
          <div>
            <p class="text-sm font-semibold text-slate-900">Automation</p>
            <p class="mt-0.5 text-xs leading-relaxed text-slate-500">
              {{ pipeline.loading ? "Loading…" : pipelineDetail }}
            </p>
          </div>
        </router-link>

        <router-link
          to="/rms"
          class="group neu-card flex flex-col gap-3 p-5 transition-colors hover:border-slate-300"
        >
          <div class="flex items-center justify-between">
            <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-colors group-hover:bg-slate-900 group-hover:text-white">
              <CircleStackIcon class="h-4.5 w-4.5" />
            </span>
            <span v-if="!sync.loading" :class="['pill', syncTone.pill]">{{ syncTone.label }}</span>
          </div>
          <div>
            <p class="text-sm font-semibold text-slate-900">Booking data</p>
            <p class="mt-0.5 text-xs leading-relaxed text-slate-500">
              {{ sync.loading ? "Loading…" : syncDetail }}
            </p>
          </div>
        </router-link>

        <router-link
          to="/stop-sale"
          class="group neu-card flex flex-col gap-3 p-5 transition-colors hover:border-slate-300"
        >
          <div class="flex items-center justify-between">
            <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-colors group-hover:bg-slate-900 group-hover:text-white">
              <EnvelopeIcon class="h-4.5 w-4.5" />
            </span>
            <span v-if="!stopSale.loading" :class="['pill', stopSaleTone.pill]">{{ stopSaleTone.label }}</span>
          </div>
          <div>
            <p class="text-sm font-semibold text-slate-900">Stop sale</p>
            <p class="mt-0.5 text-xs leading-relaxed text-slate-500">
              {{ stopSale.loading ? "Loading…" : stopSaleDetail }}
            </p>
          </div>
        </router-link>
      </div>
    </section>

    <!-- Reports and tools -->
    <section class="mt-10">
      <h2 class="text-xs font-medium uppercase tracking-widest text-slate-400">Reports &amp; tools</h2>
      <div class="mt-5 grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-4">
        <router-link
          v-for="link in links"
          :key="link.title"
          :to="link.href"
          class="group flex flex-col bg-white p-6 transition-colors hover:bg-slate-50 cursor-pointer"
        >
          <component :is="link.icon" class="h-5 w-5 text-slate-400 transition-colors group-hover:text-slate-900" />
          <h3 class="mt-6 text-sm font-medium text-slate-900">{{ link.title }}</h3>
          <p class="mt-1.5 flex-1 text-xs leading-relaxed text-slate-500">{{ link.description }}</p>
          <span class="mt-4 inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors group-hover:text-slate-900">
            Open
            <ArrowRightIcon class="h-3.5 w-3.5" />
          </span>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from "vue";
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

const links = [
  { title: "RMS", description: "Daily pace, forecast, production and booking behaviour.", href: "/rms", icon: PresentationChartLineIcon },
  { title: "Online segment", description: "Source mix, pace and Santika Online's direct vs OTA share.", href: "/rms/online", icon: GlobeAltIcon },
  { title: "Fast API Pipeline", description: "Run or schedule the full scrape-to-BAR automation.", href: "/fast-api-pipeline", icon: BoltIcon },
  { title: "Pipeline History", description: "Past automated runs and their logs.", href: "/fast-pipeline-history", icon: ClockIcon },
  { title: "Stop Sale", description: "Review closures from current inventory and send the email.", href: "/stop-sale", icon: EnvelopeIcon },
  { title: "BAR Calculator", description: "One-off BAR level calculations.", href: "/bar-calculator", icon: ReceiptPercentIcon },
  { title: "Data", description: "Raw and processed PMS/CM/combined inventory tables.", href: "/data", icon: CircleStackIcon },
  { title: "Yielder", description: "Manual yield run with full threshold control.", href: "/yielder", icon: ChartBarIcon },
];

interface FastPipelineSchedule {
  enabled: boolean;
  live: boolean;
  intervalMinutes: number;
  nextRunAt: string | null;
  schedulerOnline: boolean;
}
interface LastRun {
  started_at: string;
  finished_at: string | null;
  status: string;
  error: string | null;
}
const pipeline = reactive<{
  loading: boolean;
  schedule: FastPipelineSchedule | null;
  lastRun: LastRun | null;
  active: boolean;
}>({ loading: true, schedule: null, lastRun: null, active: false });

const sync = reactive<{
  loading: boolean;
  lastSuccessfulSync: string | null;
  stale: boolean;
  bookings: number;
  coverageFrom: string | null;
}>({ loading: true, lastSuccessfulSync: null, stale: true, bookings: 0, coverageFrom: null });

const stopSale = reactive<{ loading: boolean; count: number | null; available: boolean }>({
  loading: true,
  count: null,
  available: true,
});

const PILL_TONE = {
  ok: "pill-ok",
  warn: "pill-warn",
  bad: "pill-bad",
  muted: "pill-muted",
};

const pipelineTone = computed(() => {
  const s = pipeline.schedule;
  if (pipeline.lastRun?.status === "running" || pipeline.active)
    return { label: "Running", pill: PILL_TONE.warn };
  if (!s?.enabled) return { label: "Off", pill: PILL_TONE.muted };
  if (!s.schedulerOnline) return { label: "Scheduler offline", pill: PILL_TONE.warn };
  return s.live ? { label: "Live", pill: PILL_TONE.bad } : { label: "Preview", pill: PILL_TONE.ok };
});
const pipelineDetail = computed(() => {
  const s = pipeline.schedule,
    r = pipeline.lastRun;
  if (!s?.enabled) return r ? `Last run ${timestamp(r.finished_at || r.started_at)}` : "Not scheduled";
  const every = s.intervalMinutes % 60 === 0 ? `${s.intervalMinutes / 60}h` : `${s.intervalMinutes}min`;
  const next = s.nextRunAt ? timestamp(s.nextRunAt) : "soon";
  return `Every ${every} · next ${next}`;
});

const syncTone = computed(() =>
  sync.stale ? { label: "Stale", pill: PILL_TONE.warn } : { label: "Synced", pill: PILL_TONE.ok },
);
const syncDetail = computed(
  () => `${sync.bookings.toLocaleString("en-US")} bookings · last synced ${timestamp(sync.lastSuccessfulSync)}`,
);

const stopSaleTone = computed(() => {
  if (!stopSale.available) return { label: "No data", pill: PILL_TONE.muted };
  if (!stopSale.count) return { label: "Clear", pill: PILL_TONE.ok };
  return { label: `${stopSale.count} date${stopSale.count === 1 ? "" : "s"}`, pill: PILL_TONE.warn };
});
const stopSaleDetail = computed(() => {
  if (!stopSale.available) return "Run the pipeline to combine inventory first.";
  if (!stopSale.count) return "No upcoming dates need a stop sale right now.";
  return `${stopSale.count} upcoming date${stopSale.count === 1 ? "" : "s"} are over threshold.`;
});

onMounted(() => {
  axios
    .get("/api/fast-pipeline/schedule")
    .then((r) => {
      pipeline.schedule = r.data.schedule;
      pipeline.lastRun = r.data.lastScheduledRun;
      pipeline.active = !!r.data.pipelineActive;
    })
    .catch(() => {
      // Card falls back to its loading-skeleton-free default (all null/false).
    })
    .finally(() => (pipeline.loading = false));

  axios
    .get("/api/rms/sync")
    .then((r) => {
      sync.lastSuccessfulSync = r.data.lastSuccessfulSync;
      sync.stale = r.data.stale;
      sync.bookings = r.data.bookings || 0;
      sync.coverageFrom = r.data.coverageFrom;
    })
    .catch(() => {})
    .finally(() => (sync.loading = false));

  axios
    .get("/api/stop-sale/preview")
    .then((r) => {
      stopSale.count = (r.data.closures || []).length;
      stopSale.available = true;
    })
    .catch(() => {
      stopSale.available = false;
    })
    .finally(() => (stopSale.loading = false));
});
</script>
