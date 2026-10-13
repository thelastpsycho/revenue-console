<template>
  <section class="mt-8 space-y-4" aria-labelledby="briefing-title">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="briefing-title" class="text-lg font-semibold text-slate-900">
          Daily revenue briefing
        </h2>
        <p class="text-xs text-slate-500">
          Today onward · Bali time · 7-day net pickup · same-calendar-date
          comparison
        </p>
      </div>
      <button
        class="text-xs font-semibold underline"
        :disabled="loading"
        @click="load"
      >
        {{ loading ? "Refreshing…" : "Refresh briefing" }}
      </button>
    </div>
    <p
      v-if="error"
      role="alert"
      class="rounded-lg bg-rose-50 p-3 text-sm text-rose-800"
    >
      {{ error }}
    </p>
    <p v-if="!data && loading" role="status" class="text-sm text-slate-500">
      Loading booking position…
    </p>
    <template v-if="data">
      <p
        v-for="warning in data.warnings"
        :key="warning"
        class="rounded-lg bg-amber-50 p-3 text-xs text-amber-900"
      >
        {{ warning }}
      </p>
      <div class="space-y-3">
        <article
          v-for="p in data.periods"
          :key="p.days"
          class="neu-card overflow-hidden"
        >
          <header
            class="flex flex-wrap justify-between gap-2 border-b border-slate-200 p-4"
          >
            <h3 class="text-sm font-semibold">
              Next {{ p.days }} days
              <span class="font-normal text-slate-500"
                >{{ p.start }}–{{ p.end }}</span
              >
            </h3>
            <router-link
              :to="reportLink(p, 'overview')"
              class="text-xs underline"
              >Open period report</router-link
            >
          </header>
          <dl
            class="grid grid-cols-2 gap-px bg-slate-200 sm:grid-cols-3 lg:grid-cols-6"
          >
            <router-link
              v-for="m in metrics(p)"
              :key="m.label"
              :to="m.link"
              class="bg-white p-4 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-700"
              ><dt class="text-xs text-slate-500">{{ m.label }}</dt>
              <dd class="mt-1 text-base font-semibold tabular-nums">
                {{ m.value }}
              </dd></router-link
            >
          </dl>
          <p class="px-4 py-2 text-xs text-slate-500">
            {{ p.comparisonQuality }} comparison · IDR ADR coverage:
            {{ pct(p.idrCoveragePct) }}. Budget is the imported daily gross IDR
            target for this date range.
          </p>
        </article>
      </div>
      <p class="text-xs text-slate-500">
        {{ data.basis }}. Booking source: {{ timestamp(data.bookingSync) }}.
        Capacity source: {{ timestamp(data.capacityState.fetchedAt)
        }}{{ data.capacityState.stale ? " (stale/loading)" : "" }}. These are
        on-the-books positions, not audited actual revenue.
      </p>
      <div class="neu-card overflow-hidden">
        <h3 class="p-4 text-sm font-semibold">Dates needing attention</h3>
        <p
          v-if="!data.attention.length"
          class="px-4 pb-4 text-xs text-slate-500"
        >
          {{
            data.warnings.length
              ? "No demand flags in the available data; resolve the data warnings above before treating this as clear."
              : "No demand flags in the next 30 days using your current thresholds."
          }}
        </p>
        <div v-else class="max-h-80 overflow-auto">
          <table class="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>OTB occupancy</th>
                <th>7-day pickup</th>
                <th>Reason</th>
                <th>Comparison</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in data.attention" :key="r.date">
                <td>
                  <router-link
                    :to="reportLink({ start: r.date, end: r.date }, 'overview')"
                    class="font-semibold underline"
                    >{{ r.date }}</router-link
                  >
                </td>
                <td>{{ pct(r.occupancy) }}</td>
                <td>{{ signed(r.pickupRooms) }}</td>
                <td>{{ r.reasons.join(" · ") }}</td>
                <td>{{ r.comparisonQuality }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import axios from "../plugins/axios";
import { timestamp } from "../utils/rms";
import { briefingReportLink as reportLink } from "../utils/briefing";
interface Period {
  days: number;
  start: string;
  end: string;
  rooms: number | null;
  occupancy: number | null;
  revenue: number | null;
  adr: number | null;
  pickupRooms: number | null;
  budgetRevenue: number | null;
  budgetGap: number | null;
  idrCoveragePct: number | null;
  comparisonQuality: string;
}
interface Briefing {
  basis: string;
  periods: Period[];
  attention: {
    date: string;
    rooms: number;
    occupancy: number | null;
    pickupRooms: number | null;
    reasons: string[];
    comparisonQuality: string;
  }[];
  warnings: string[];
  bookingSync: string | null;
  capacityState: {
    stale: boolean;
    refreshing: boolean;
    fetchedAt: string | null;
    error: string | null;
  };
}
const data = ref<Briefing | null>(null),
  loading = ref(false),
  error = ref("");
let timer: ReturnType<typeof setTimeout> | undefined,
  disposed = false;
const number = (v: number | null) =>
  v == null
    ? "Unavailable"
    : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const pct = (v: number | null) =>
  v == null ? "Unavailable" : `${v.toFixed(1)}%`;
const money = (v: number | null) =>
  v == null ? "Unavailable" : `IDR ${Math.round(v).toLocaleString("en-US")}`;
const signed = (v: number | null) =>
  v == null ? "Unavailable" : `${v > 0 ? "+" : ""}${number(v)}`;
function metrics(p: Period) {
  return [
    {
      label: "OTB occupancy",
      value: pct(p.occupancy),
      link: reportLink(p, "rooms"),
    },
    { label: "IDR ADR", value: money(p.adr), link: reportLink(p, "pace") },
    {
      label: "IDR room revenue",
      value: money(p.revenue),
      link: reportLink(p, "pace"),
    },
    {
      label: "Net pickup (room nights)",
      value: signed(p.pickupRooms),
      link: reportLink(p, "pace"),
    },
    {
      label: "Budget revenue gap",
      value: money(p.budgetGap),
      link: reportLink(p, "pace", "budget"),
    },
    {
      label: "OTB room nights",
      value: number(p.rooms),
      link: reportLink(p, "business"),
    },
  ];
}
async function load() {
  if (disposed || loading.value || document.visibilityState === "hidden")
    return;
  clearTimeout(timer);
  loading.value = true;
  error.value = "";
  try {
    const r = await axios.get("/api/rms/briefing", { timeout: 15000 });
    if (!disposed) data.value = r.data;
  } catch {
    if (!disposed)
      error.value =
        "Briefing could not be refreshed. Retained figures below may be outdated.";
  } finally {
    if (!disposed) {
      loading.value = false;
      timer = setTimeout(
        load,
        data.value?.capacityState.refreshing ? 3000 : 60000,
      );
    }
  }
}
function wake() {
  if (document.visibilityState === "visible") void load();
  else clearTimeout(timer);
}
onMounted(() => {
  void load();
  document.addEventListener("visibilitychange", wake);
  window.addEventListener("focus", wake);
});
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  document.removeEventListener("visibilitychange", wake);
  window.removeEventListener("focus", wake);
});
</script>
