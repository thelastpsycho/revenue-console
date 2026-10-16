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
          class="neu-card absolute left-0 top-full z-30 mt-1 w-72 space-y-3 p-3 shadow-lg"
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
            <DateRangeCalendar
              v-model:start="filters.pickupStart"
              v-model:end="filters.pickupEnd"
              :max="maxPickupEnd"
            />
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
      <label>
        <span class="field-label">Compare with</span>
        <select v-model="filters.compare" class="neu-input">
          <option value="none">None</option>
          <option value="previous">Previous period</option>
          <option value="last_year">Same period last year</option>
        </select>
      </label>
      <button :class="['btn-primary px-3 py-1.5 text-xs', dirty && 'ring-2 ring-amber-300']">
        {{ dirty ? "Apply changes" : "Apply" }}
      </button>
    </form>
    <p v-if="loadedCompareWindow" class="text-xs text-slate-500">
      Comparing against {{ shortDayYear(loadedCompareWindow.start) }} –
      {{ shortDayYear(loadedCompareWindow.end) }}
    </p>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>

    <RmsSkeleton v-if="loading" variant="tiles" :count="2" />
    <dl v-else class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div class="stat-tile">
        <dt>Total room nights pickup</dt>
        <dd :class="signClass(totalPickupRooms)">{{ signed(totalPickupRooms) }}</dd>
        <p
          v-if="loadedCompare !== 'none'"
          :class="['mt-0.5 text-[11px] tabular-nums', roomsVsCompare.tone || 'text-slate-500']"
        >
          {{ roomsVsCompare.text }}
        </p>
      </div>
      <div class="stat-tile">
        <dt>Total revenue pickup</dt>
        <dd :title="money(totalPickupRevenue)">
          {{ totalPickupRevenue == null ? EMPTY : signedMoney(totalPickupRevenue) }}
        </dd>
        <p
          v-if="loadedCompare !== 'none'"
          :class="['mt-0.5 text-[11px] tabular-nums', revenueVsCompare.tone || 'text-slate-500']"
        >
          {{ revenueVsCompare.text }}
        </p>
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
            <th v-if="loadedCompare !== 'none'" class="num">
              {{ comparisonShortLabel }} room nights
            </th>
            <th v-if="loadedCompare !== 'none'" class="num">
              {{ comparisonShortLabel }} room revenue
            </th>
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
            <td v-if="loadedCompare !== 'none'" :class="['num', signClass(m.pickupRoomsCompare)]">
              {{ signed(m.pickupRoomsCompare) }}
            </td>
            <td v-if="loadedCompare !== 'none'" class="num" :title="money(m.pickupRevenueCompare)">
              {{ m.pickupRevenueCompare == null ? EMPTY : signedMoney(m.pickupRevenueCompare) }}
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
              <th v-if="loadedCompare !== 'none'" class="num">{{ comparisonShortLabel }} rooms</th>
              <th v-if="loadedCompare !== 'none'" class="num">{{ comparisonShortLabel }} revenue</th>
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
              <td
                v-if="loadedCompare !== 'none'"
                :class="['num', signClass(compareRoomsFor(segmentCompareById, s.id))]"
              >
                {{ signed(compareRoomsFor(segmentCompareById, s.id)) }}
              </td>
              <td v-if="loadedCompare !== 'none'" class="num">
                {{
                  compareRevenueFor(segmentCompareById, s.id, basis) == null
                    ? EMPTY
                    : signedMoney(compareRevenueFor(segmentCompareById, s.id, basis)!)
                }}
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
              <th v-if="loadedCompare !== 'none'" class="num">{{ comparisonShortLabel }} rooms</th>
              <th v-if="loadedCompare !== 'none'" class="num">{{ comparisonShortLabel }} revenue</th>
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
              <td
                v-if="loadedCompare !== 'none'"
                :class="['num', signClass(compareRoomsFor(companyCompareById, c.id))]"
              >
                {{ signed(compareRoomsFor(companyCompareById, c.id)) }}
              </td>
              <td v-if="loadedCompare !== 'none'" class="num">
                {{
                  compareRevenueFor(companyCompareById, c.id, basis) == null
                    ? EMPTY
                    : signedMoney(compareRevenueFor(companyCompareById, c.id, basis)!)
                }}
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
import DateRangeCalendar from "../components/DateRangeCalendar.vue";
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
  vsLy,
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

type CompareMode = "none" | "previous" | "last_year";
function validCompareMode(v: string): CompareMode {
  return v === "previous" || v === "last_year" ? v : "none";
}
interface PickupFilters {
  pickupStart: string;
  pickupEnd: string;
  compare: CompareMode;
}
function daysBetween(startIso: string, endIso: string) {
  const days = Math.round((Date.parse(endIso) - Date.parse(startIso)) / 86400000);
  return Math.max(1, Math.min(MAX_PICKUP_DAYS, days));
}
// "Previous period" shifts the pickup window back by its own length and
// keeps looking at the same forward-looking stay dates (it's about recent
// booking momentum). "Last year" shifts both the pickup window *and* the
// stay-date range back 364 days (weekday-aligned, matching the LY convention
// booking_events.comparison_date uses elsewhere) - without shifting the stay
// range too, "last year" would mean "bookings captured a year ago for stay
// dates that, back then, were over a year away" - always ~zero, since no one
// books that far ahead. shiftDays carries that stay-range offset so callers
// can shift the stay range and later realign comparison rows back onto the
// current calendar.
function comparisonWindow(mode: CompareMode, start: string, end: string) {
  if (mode === "previous") {
    const len = daysBetween(start, end);
    const cmpEnd = addDays(start, -1);
    return { start: addDays(cmpEnd, -(len - 1)), end: cmpEnd, shiftDays: 0 };
  }
  if (mode === "last_year") {
    return { start: addDays(start, -364), end: addDays(end, -364), shiftDays: 364 };
  }
  return null;
}
const filters = reactive<PickupFilters>({
  pickupStart: query("pickupStart", addDays(today, -7)) || addDays(today, -7),
  pickupEnd: query("pickupEnd", today) || today,
  compare: validCompareMode(query("compare")),
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
const paceRowsCompare = ref<PaceRow[]>([]);
const segmentCompareById = ref<Map<string, GroupPickupRow>>(new Map());
const companyCompareById = ref<Map<string, GroupPickupRow>>(new Map());
const loadedCompareWindow = ref<{ start: string; end: string } | null>(null);
// How far back the comparison's stay-date range was shifted (0 for
// "previous period", 364 for "last year") - needed to realign comparison
// pace rows, whose dates are themselves shifted, back onto the current
// calendar's month buckets.
const loadedCompareShiftDays = ref(0);
const loadedCompare = computed(() => loaded.value?.compare ?? "none");
const comparisonLabel = computed(() =>
  loadedCompare.value === "previous" ? "vs previous period" : "vs last year",
);
const comparisonShortLabel = computed(() =>
  loadedCompare.value === "previous" ? "Previous period" : "Last year",
);
function compareRoomsFor(map: Map<string, GroupPickupRow>, id: string) {
  return map.get(id)?.pickupRooms ?? null;
}
function compareRevenueFor(map: Map<string, GroupPickupRow>, id: string, basis: "gross" | "net") {
  const row = map.get(id);
  return row ? groupPickupRevenueFor(row, basis) : null;
}
const forecast = ref<Forecast | null>(null);
const forecastBusy = computed(() =>
  Object.values(forecast.value?.sections || {}).some((s) => s.refreshing),
);

interface MonthRow {
  month: string;
  pickupRooms: number | null;
  pickupRevenue: number | null;
  pickupRoomsCompare: number | null;
  pickupRevenueCompare: number | null;
  otbRevenue: number | null;
  occupancy: number | null;
}
// OTB revenue for a stay date in the selected basis, gated the same way
// currentRooms() gates rooms - null while that date's pace data is still
// "unavailable" quality.
const currentRevenue = (r: PaceRow) => (currentRooms(r) == null ? null : revenueFor(r, basis.value));
// For "last year", the comparison's stay-date range is itself shifted back
// 364 days, so its pace rows land on dates 364 days earlier than the
// primary rows they correspond to - look up a primary date's match by
// applying that same shift, rather than a literal date match.
const compareByDate = computed(() => {
  const m = new Map<string, PaceRow>();
  for (const r of paceRowsCompare.value) m.set(r.date, r);
  return m;
});
function compareRowFor(date: string) {
  const key = loadedCompareShiftDays.value ? addDays(date, -loadedCompareShiftDays.value) : date;
  return compareByDate.value.get(key);
}
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
    const cmpRs = rs.map((r) => compareRowFor(r.date)).filter((r): r is PaceRow => !!r);
    return {
      month,
      pickupRooms: sumKnown(rs.map((r) => r.pickupRooms)),
      pickupRevenue: sumKnown(rs.map((r) => pickupRevenueFor(r, basis.value))),
      pickupRoomsCompare: cmpRs.length ? sumKnown(cmpRs.map((r) => r.pickupRooms)) : null,
      pickupRevenueCompare: cmpRs.length
        ? sumKnown(cmpRs.map((r) => pickupRevenueFor(r, basis.value)))
        : null,
      otbRevenue: sumKnown(rs.map(currentRevenue)),
      occupancy: occ == null ? null : occ * 100,
    };
  });
});
const totalPickupRooms = computed(() => sumKnown(months.value.map((m) => m.pickupRooms)));
const totalPickupRevenue = computed(() => sumKnown(months.value.map((m) => m.pickupRevenue)));
const totalPickupRoomsCompare = computed(() =>
  sumKnown(months.value.map((m) => m.pickupRoomsCompare)),
);
const totalPickupRevenueCompare = computed(() =>
  sumKnown(months.value.map((m) => m.pickupRevenueCompare)),
);
const roomsVsCompare = computed(() =>
  vsLy(totalPickupRooms.value, totalPickupRoomsCompare.value, signed, comparisonLabel.value),
);
const revenueVsCompare = computed(() =>
  vsLy(
    totalPickupRevenue.value,
    totalPickupRevenueCompare.value,
    (v) => (v == null ? EMPTY : signedMoney(v)),
    comparisonLabel.value,
  ),
);

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
  const q = {
    pickupStart: f.pickupStart,
    pickupEnd: f.pickupEnd,
    basis: basis.value,
    compare: f.compare,
  };
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
    const cmp = comparisonWindow(filters.compare, filters.pickupStart, filters.pickupEnd);
    const cmpCommon = cmp
      ? {
          start: cmp.shiftDays ? addDays(start, -cmp.shiftDays) : start,
          end: cmp.shiftDays ? addDays(end, -cmp.shiftDays) : end,
          pickupDays: daysBetween(cmp.start, cmp.end),
          asOf: cmp.end,
        }
      : null;
    loadedCompareWindow.value = cmp;
    loadedCompareShiftDays.value = cmp?.shiftDays ?? 0;
    const requests = [
      axios.get("/api/rms/pace", { params: common }),
      axios.get("/api/rms/pace/pickup-groups", { params: { ...common, dimension: "market" } }),
      axios.get("/api/rms/pace/pickup-groups", {
        params: { ...common, dimension: "company", limit: 10 },
      }),
    ];
    if (cmpCommon) {
      // No limit on the comparison company fetch: the primary call's top 10
      // is ranked by its own window, so a company could rank outside the
      // top 10 in the comparison window yet still need to appear here.
      requests.push(
        axios.get("/api/rms/pace", { params: cmpCommon }),
        axios.get("/api/rms/pace/pickup-groups", {
          params: { ...cmpCommon, dimension: "market" },
        }),
        axios.get("/api/rms/pace/pickup-groups", {
          params: { ...cmpCommon, dimension: "company" },
        }),
      );
    }
    const results = await Promise.all(requests);
    if (disposed || id !== requestId) return;
    paceRows.value = results[0].data.rows;
    segmentRows.value = results[1].data.rows;
    companyRows.value = results[2].data.rows;
    if (cmpCommon) {
      paceRowsCompare.value = results[3].data.rows;
      segmentCompareById.value = new Map(
        results[4].data.rows.map((r: GroupPickupRow) => [r.id, r]),
      );
      companyCompareById.value = new Map(
        results[5].data.rows.map((r: GroupPickupRow) => [r.id, r]),
      );
    } else {
      paceRowsCompare.value = [];
      segmentCompareById.value = new Map();
      companyCompareById.value = new Map();
    }
  } catch (e: any) {
    if (id === requestId) {
      error.value = e?.response?.data?.message || "Could not load pickup data";
      paceRows.value = [];
      segmentRows.value = [];
      companyRows.value = [];
      paceRowsCompare.value = [];
      segmentCompareById.value = new Map();
      companyCompareById.value = new Map();
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
