<template>
  <div class="mx-auto w-full max-w-screen-2xl space-y-4 p-4 sm:p-6">
    <PageHeader
      title="Pickup by stay month"
      subtitle="Whole hotel. Net pickup over the selected window, rolled up by stay month, with where occupancy currently stands."
      compact
    />

    <form class="filter-bar neu-card flex flex-wrap items-end gap-2 p-3" @submit.prevent="apply">
      <label>
        <span class="field-label">Pickup window</span>
        <select v-model.number="filters.pickupDays" class="neu-input">
          <option v-for="d in [1, 3, 7, 14, 30]" :key="d" :value="d">
            {{ d }} {{ d === 1 ? "day" : "days" }}
          </option>
        </select>
      </label>
      <button :class="['btn-primary px-3 py-1.5 text-xs', dirty && 'ring-2 ring-amber-300']">
        {{ dirty ? "Apply changes" : "Apply" }}
      </button>
    </form>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>

    <RmsCard
      title="Pickup by stay month"
      :description="`Net pickup over the last ${loaded?.pickupDays ?? filters.pickupDays} days = new − cancelled + amendments, in room nights. OTB occupancy and revenue reflect what's currently on the books.`"
    >
      <RmsSkeleton v-if="loading" variant="table" :count="12" :columns="4" />
      <table v-else-if="months.length" class="data-table">
        <thead>
          <tr>
            <th>Month</th>
            <th class="num">Pickup room nights</th>
            <th class="num">Pickup room revenue</th>
            <th class="num">OTB occupancy</th>
            <th class="num">OTB revenue</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in months" :key="m.month">
            <td class="whitespace-nowrap font-semibold text-slate-900">
              {{ monthLabel(m.month) }}
            </td>
            <td :class="['num', signClass(m.pickupRooms)]">
              {{ signed(m.pickupRooms) }}
            </td>
            <td class="num" :title="money(m.pickupRevenue)">
              {{ m.pickupRevenue == null ? EMPTY : signedMoney(m.pickupRevenue) }}
            </td>
            <td class="num">{{ percent(m.occupancy) }}</td>
            <td class="num" :title="money(m.otbRevenue)">
              {{ m.otbRevenue == null ? EMPTY : moneyShort(m.otbRevenue) }}
            </td>
          </tr>
        </tbody>
      </table>
      <template v-if="!loading && !months.length" #empty>
        Apply a pickup window to load data.
      </template>
    </RmsCard>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import axios from "../plugins/axios";
import PageHeader from "../components/PageHeader.vue";
import RmsCard from "../components/RmsCard.vue";
import RmsSkeleton from "../components/RmsSkeleton.vue";
import {
  EMPTY,
  money,
  moneyShort,
  percent,
  signed,
  signClass,
  sumKnown,
  ratio,
  currentRooms,
  hotelToday,
  loadStoredFilters,
  saveStoredFilters,
  type PaceRow,
  type Forecast,
} from "../utils/rms";

const today = hotelToday(),
  route = useRoute(),
  router = useRouter();

const STORAGE_KEY = "rms-pickup";
const stored = loadStoredFilters(STORAGE_KEY) || {};
const query = (k: string, f = "") =>
  typeof route.query[k] === "string" ? String(route.query[k]) : (stored[k] ?? f);

interface PickupFilters {
  pickupDays: number;
}
const filters = reactive<PickupFilters>({
  pickupDays: Number(query("pickupDays", "7")) || 7,
});
const loaded = ref<PickupFilters | null>(null);
const dirty = computed(
  () => loaded.value && JSON.stringify(filters) !== JSON.stringify(loaded.value),
);
const error = ref("");
const loading = ref(false);

const paceRows = ref<PaceRow[]>([]);
const forecast = ref<Forecast | null>(null);
const forecastBusy = computed(() =>
  Object.values(forecast.value?.sections || {}).some((s) => s.refreshing),
);

interface MonthRow {
  month: string;
  pickupRooms: number | null;
  pickupRevenue: number | null;
  otbRevenue: number | null;
  occupancy: number | null;
}
// Gross OTB revenue for a stay date, gated the same way currentRooms() gates
// rooms - null while that date's pace data is still "unavailable" quality.
const currentRevenue = (r: PaceRow) => (currentRooms(r) == null ? null : r.revenue);
const months = computed<MonthRow[]>(() => {
  const capacities: Record<string, number> = {};
  for (const h of forecast.value?.hotel || []) {
    if (h.roomCount != null) capacities[h.date] = h.roomCount;
  }
  const byMonth = new Map<string, PaceRow[]>();
  for (const r of paceRows.value) {
    const key = r.date.slice(0, 7);
    byMonth.set(key, [...(byMonth.get(key) || []), r]);
  }
  return [...byMonth].map(([month, rs]) => {
    const otbRooms = sumKnown(rs.map(currentRooms)),
      capacity = sumKnown(rs.map((r) => capacities[r.date] ?? null)),
      occ = ratio(otbRooms, capacity);
    return {
      month,
      pickupRooms: sumKnown(rs.map((r) => r.pickupRooms)),
      pickupRevenue: sumKnown(rs.map((r) => r.pickupRevenue)),
      otbRevenue: sumKnown(rs.map(currentRevenue)),
      occupancy: occ == null ? null : occ * 100,
    };
  });
});

function monthLabel(month: string) {
  return new Date(`${month}-01T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    month: "long",
    year: "numeric",
  });
}
const signedMoney = (v: number) => `${v > 0 ? "+" : ""}${moneyShort(v)}`;

// Rolling 12 months: this stay month plus the next 11. A 12-calendar-month
// span never exceeds 366 days, matching the forecast API's cap - also used
// for the forecast request so occupancy covers the same months pace does.
function stayRange() {
  const start = `${today.slice(0, 7)}-01`;
  const d = new Date(`${start}T00:00:00Z`);
  const endDate = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 12, 0));
  const days = Math.round((endDate.getTime() - d.getTime()) / 86400000) + 1;
  return { start, end: endDate.toISOString().slice(0, 10), days };
}

function saveUrl() {
  const f = loaded.value || filters;
  router.replace({ query: { pickupDays: String(f.pickupDays) } });
  saveStoredFilters(STORAGE_KEY, { pickupDays: String(f.pickupDays) });
}

let requestId = 0;
let forecastTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;

// Forecast capacity is cached and refreshed server-side on its own schedule,
// so a cold/stale cache means an empty hotel[] at first - poll like the Pace
// tab does until sections stop refreshing, rather than leaving occupancy blank.
async function loadForecast(id: number) {
  clearTimeout(forecastTimer);
  try {
    const { start, days } = stayRange();
    const r = await axios.get<{ status: string } & Forecast>("/api/rms/forecast", {
      // Occupancy only needs room capacity, which lives in the "hotel"
      // section - skip the segments/roomTypes/availability reports this
      // page never reads.
      params: { start, days, sections: "hotel" },
    });
    if (disposed || id !== requestId) return;
    forecast.value = r.data;
    if (forecastBusy.value) forecastTimer = setTimeout(() => loadForecast(id), 2000);
  } catch {
    // Occupancy just stays blank; the pickup figures below don't depend on it.
  }
}

async function apply() {
  if (disposed) return;
  const id = ++requestId;
  error.value = "";
  loading.value = true;
  loaded.value = { ...filters };
  saveUrl();
  void loadForecast(id);
  try {
    const { start, end } = stayRange();
    const r = await axios.get("/api/rms/pace", {
      params: { start, end, pickupDays: filters.pickupDays },
    });
    if (disposed || id !== requestId) return;
    paceRows.value = r.data.rows;
  } catch (e: any) {
    if (id === requestId) {
      error.value = e?.response?.data?.message || "Could not load pickup data";
      paceRows.value = [];
    }
  } finally {
    if (id === requestId) loading.value = false;
  }
}

onMounted(apply);
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(forecastTimer);
});
</script>
