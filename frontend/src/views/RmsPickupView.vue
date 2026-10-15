<template>
  <div class="mx-auto w-full max-w-screen-2xl space-y-4 p-4 sm:p-6">
    <PageHeader
      title="Pickup by stay month"
      subtitle="Whole hotel. Net pickup over the selected window, rolled up by stay month, with where occupancy currently stands."
      compact
    />

    <form class="filter-bar neu-card flex flex-wrap items-end gap-2 p-3" @submit.prevent="apply">
      <div ref="dateMenuRef" class="relative">
        <span class="field-label">Pickup window</span>
        <button
          type="button"
          class="neu-input flex items-center gap-1.5 whitespace-nowrap"
          :aria-expanded="dateMenuOpen"
          @click="dateMenuOpen = !dateMenuOpen"
        >
          <CalendarDaysIcon class="h-3.5 w-3.5 text-slate-400" />
          {{ shortDayYear(filters.pickupStart) }} – {{ shortDayYear(filters.pickupEnd) }}
          ({{ pickupDaysLabel }})
        </button>
        <div
          v-if="dateMenuOpen"
          class="neu-card absolute left-0 top-full z-30 mt-1 w-64 space-y-3 p-3 shadow-lg"
        >
          <div class="grid grid-cols-2 gap-1.5">
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="presetYesterday">
              Yesterday
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="presetThisWeek">
              This week
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="presetThisMonth">
              This month
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="presetLastWeek">
              Last week
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="presetLastMonth">
              Last month
            </button>
          </div>
          <div class="border-t border-slate-200 pt-3">
            <span class="field-label">Custom range</span>
            <div class="flex items-center gap-1.5">
              <input
                v-model="filters.pickupStart"
                type="date"
                :max="filters.pickupEnd"
                class="neu-input w-full"
              />
              <span class="text-slate-400">–</span>
              <input
                v-model="filters.pickupEnd"
                type="date"
                :min="filters.pickupStart"
                :max="maxPickupEnd"
                class="neu-input w-full"
              />
            </div>
            <div class="mt-2 flex justify-end">
              <button
                type="button"
                class="btn-primary px-3 py-1 text-xs"
                @click="dateMenuOpen = false"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      </div>
      <label>
        <span class="field-label">Revenue basis</span>
        <select v-model="basis" class="neu-input">
          <option value="gross">Gross IDR</option>
          <option value="net">Estimated net IDR</option>
        </select>
      </label>
      <button :class="['btn-primary px-3 py-1.5 text-xs', dirty && 'ring-2 ring-amber-300']">
        {{ dirty ? "Apply changes" : "Apply" }}
      </button>
    </form>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>

    <RmsSkeleton v-if="loading" variant="tiles" :count="2" />
    <dl v-else class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div class="stat-tile">
        <dt>Total room nights pickup</dt>
        <dd :class="signClass(totalPickupRooms)">{{ signed(totalPickupRooms) }}</dd>
      </div>
      <div class="stat-tile">
        <dt>Total revenue pickup</dt>
        <dd :title="money(totalPickupRevenue)">
          {{ totalPickupRevenue == null ? EMPTY : signedMoney(totalPickupRevenue) }}
        </dd>
      </div>
    </dl>

    <RmsCard
      title="Pickup by stay month"
      :description="`Net pickup ${loadedPickupLabel} = new − cancelled + amendments, in room nights. OTB occupancy and revenue reflect what's currently on the books.`"
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
        Apply a pickup start date to load data.
      </template>
    </RmsCard>

    <div class="grid gap-4 lg:grid-cols-2">
      <RmsCard
        title="Pickup by segment"
        :description="`Net pickup ${loadedPickupLabel}, by market segment.`"
      >
        <RmsSkeleton v-if="loading" variant="table" :count="6" :columns="3" />
        <table v-else-if="segmentRows.length" class="data-table">
          <thead>
            <tr>
              <th>Segment</th>
              <th class="num">Current rooms</th>
              <th class="num">Pickup rooms</th>
              <th class="num">Pickup revenue</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in segmentRows" :key="s.id">
              <td class="whitespace-nowrap font-semibold text-slate-900">{{ s.name }}</td>
              <td class="num">{{ num(s.rooms) }}</td>
              <td :class="['num', signClass(s.pickupRooms)]">{{ signed(s.pickupRooms) }}</td>
              <td class="num" :title="money(groupPickupRevenueFor(s, basis))">
                {{ signedMoney(groupPickupRevenueFor(s, basis)) }}
              </td>
            </tr>
          </tbody>
        </table>
        <template v-if="!loading && !segmentRows.length" #empty>No segment data yet.</template>
      </RmsCard>

      <RmsCard
        title="Top 10 company pickup"
        :description="`Net pickup ${loadedPickupLabel}, by booking company.`"
      >
        <RmsSkeleton v-if="loading" variant="table" :count="10" :columns="3" />
        <table v-else-if="companyRows.length" class="data-table">
          <thead>
            <tr>
              <th>Company</th>
              <th class="num">Current rooms</th>
              <th class="num">Pickup rooms</th>
              <th class="num">Pickup revenue</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in companyRows" :key="c.id">
              <td class="whitespace-nowrap font-semibold text-slate-900">{{ c.name }}</td>
              <td class="num">{{ num(c.rooms) }}</td>
              <td :class="['num', signClass(c.pickupRooms)]">{{ signed(c.pickupRooms) }}</td>
              <td class="num" :title="money(groupPickupRevenueFor(c, basis))">
                {{ signedMoney(groupPickupRevenueFor(c, basis)) }}
              </td>
            </tr>
          </tbody>
        </table>
        <template v-if="!loading && !companyRows.length" #empty>No company data yet.</template>
      </RmsCard>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { CalendarDaysIcon } from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import PageHeader from "../components/PageHeader.vue";
import RmsCard from "../components/RmsCard.vue";
import RmsSkeleton from "../components/RmsSkeleton.vue";
import {
  EMPTY,
  money,
  moneyShort,
  num,
  percent,
  signed,
  signClass,
  sumKnown,
  ratio,
  currentRooms,
  revenueFor,
  pickupRevenueFor,
  groupPickupRevenueFor,
  hotelToday,
  addDays,
  shortDayYear,
  loadStoredFilters,
  saveStoredFilters,
  type PaceRow,
  type Forecast,
  type GroupPickupRow,
} from "../utils/rms";

const today = hotelToday(),
  route = useRoute(),
  router = useRouter();

// Pickup compares OTB "as of" two dates - normally today vs pickupStart,
// but asOf can be pinned to any past date too (e.g. "last week"), not just
// today. Clamped to the pace API's 90-day pickup limit.
const MAX_PICKUP_DAYS = 90;
const maxPickupEnd = today;
const mondayOf = (iso: string) =>
  addDays(iso, -((new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7));

const STORAGE_KEY = "rms-pickup";
const stored = loadStoredFilters(STORAGE_KEY) || {};
const query = (k: string, f = "") =>
  typeof route.query[k] === "string" ? String(route.query[k]) : (stored[k] ?? f);

interface PickupFilters {
  pickupStart: string;
  pickupEnd: string;
}
function daysBetween(startIso: string, endIso: string) {
  const days = Math.round((Date.parse(endIso) - Date.parse(startIso)) / 86400000);
  return Math.max(1, Math.min(MAX_PICKUP_DAYS, days));
}
const filters = reactive<PickupFilters>({
  pickupStart: query("pickupStart", addDays(today, -7)) || addDays(today, -7),
  pickupEnd: query("pickupEnd", today) || today,
});
const basis = ref<"gross" | "net">(query("basis") === "net" ? "net" : "gross");
const pickupDays = computed(() => daysBetween(filters.pickupStart, filters.pickupEnd));
const pickupDaysLabel = computed(
  () => `${pickupDays.value} ${pickupDays.value === 1 ? "day" : "days"}`,
);
const loaded = ref<PickupFilters | null>(null);
const loadedPickupLabel = computed(() => {
  const f = loaded.value ?? filters;
  const days = daysBetween(f.pickupStart, f.pickupEnd);
  return `from ${shortDayYear(f.pickupStart)} to ${shortDayYear(f.pickupEnd)} (${days} ${days === 1 ? "day" : "days"})`;
});
const dirty = computed(
  () => loaded.value && JSON.stringify(filters) !== JSON.stringify(loaded.value),
);
const error = ref("");
const loading = ref(false);

const dateMenuOpen = ref(false),
  dateMenuRef = ref<HTMLElement | null>(null);
function onDateMenuClickOutside(e: MouseEvent) {
  if (
    dateMenuOpen.value &&
    dateMenuRef.value &&
    !dateMenuRef.value.contains(e.target as Node)
  )
    dateMenuOpen.value = false;
}
function presetYesterday() {
  filters.pickupStart = addDays(today, -1);
  filters.pickupEnd = today;
  dateMenuOpen.value = false;
}
function presetThisWeek() {
  filters.pickupStart = mondayOf(today);
  filters.pickupEnd = today;
  dateMenuOpen.value = false;
}
function presetThisMonth() {
  filters.pickupStart = `${today.slice(0, 7)}-01`;
  filters.pickupEnd = today;
  dateMenuOpen.value = false;
}
function presetLastWeek() {
  const end = addDays(mondayOf(today), -1);
  filters.pickupStart = addDays(end, -6);
  filters.pickupEnd = end;
  dateMenuOpen.value = false;
}
function presetLastMonth() {
  const end = addDays(`${today.slice(0, 7)}-01`, -1);
  filters.pickupStart = `${end.slice(0, 7)}-01`;
  filters.pickupEnd = end;
  dateMenuOpen.value = false;
}
onMounted(() => document.addEventListener("mousedown", onDateMenuClickOutside));
onBeforeUnmount(() =>
  document.removeEventListener("mousedown", onDateMenuClickOutside),
);

const paceRows = ref<PaceRow[]>([]);
const segmentRows = ref<GroupPickupRow[]>([]);
const companyRows = ref<GroupPickupRow[]>([]);
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
// OTB revenue for a stay date in the selected basis, gated the same way
// currentRooms() gates rooms - null while that date's pace data is still
// "unavailable" quality.
const currentRevenue = (r: PaceRow) => (currentRooms(r) == null ? null : revenueFor(r, basis.value));
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
      pickupRevenue: sumKnown(rs.map((r) => pickupRevenueFor(r, basis.value))),
      otbRevenue: sumKnown(rs.map(currentRevenue)),
      occupancy: occ == null ? null : occ * 100,
    };
  });
});
const totalPickupRooms = computed(() => sumKnown(months.value.map((m) => m.pickupRooms)));
const totalPickupRevenue = computed(() => sumKnown(months.value.map((m) => m.pickupRevenue)));

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
  const q = { pickupStart: f.pickupStart, pickupEnd: f.pickupEnd, basis: basis.value };
  router.replace({ query: q });
  saveStoredFilters(STORAGE_KEY, q);
}
watch(basis, saveUrl);

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
    const common = {
      start,
      end,
      pickupDays: daysBetween(filters.pickupStart, filters.pickupEnd),
      asOf: filters.pickupEnd,
    };
    const [pace, segments, companies] = await Promise.all([
      axios.get("/api/rms/pace", { params: common }),
      axios.get("/api/rms/pace/pickup-groups", { params: { ...common, dimension: "market" } }),
      axios.get("/api/rms/pace/pickup-groups", {
        params: { ...common, dimension: "company", limit: 10 },
      }),
    ]);
    if (disposed || id !== requestId) return;
    paceRows.value = pace.data.rows;
    segmentRows.value = segments.data.rows;
    companyRows.value = companies.data.rows;
  } catch (e: any) {
    if (id === requestId) {
      error.value = e?.response?.data?.message || "Could not load pickup data";
      paceRows.value = [];
      segmentRows.value = [];
      companyRows.value = [];
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
