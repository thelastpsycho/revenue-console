<template>
  <div class="mx-auto w-full max-w-screen-2xl space-y-4 p-4 sm:p-6">
    <PageHeader
      title="Company analytics"
      subtitle="Length of stay, nationality, booking behaviour, pace & pickups and production - filterable to one or more companies."
      compact
    />

    <form class="filter-bar neu-card relative flex flex-wrap items-end gap-2 p-3" @submit.prevent="apply">
      <div ref="dateMenuRef" class="relative">
        <span class="field-label">Stay dates</span>
        <button
          type="button"
          class="neu-input flex items-center gap-1.5 whitespace-nowrap"
          :aria-expanded="dateMenuOpen"
          @click="dateMenuOpen = !dateMenuOpen"
        >
          <CalendarDaysIcon class="h-3.5 w-3.5 text-slate-400" />
          {{ shortDayYear(filters.start) }} – {{ shortDayYear(filters.end) }}
        </button>
        <div
          v-if="dateMenuOpen"
          class="neu-card absolute left-0 top-full z-30 mt-1 w-72 space-y-3 p-3 shadow-lg"
        >
          <div class="grid grid-cols-3 gap-1.5">
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="thisMonth">
              This month
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="applyDatePreset(3)">
              3 months
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="applyDatePreset(5)">
              5 months
            </button>
          </div>
          <div class="border-t border-slate-200 pt-3">
            <span class="field-label">Custom range</span>
            <DateRangeCalendar v-model:start="filters.start" v-model:end="filters.end" />
            <div class="mt-2 flex justify-end">
              <button
                type="button"
                class="btn-primary px-3 py-1 text-xs"
                :disabled="!filters.start || !filters.end"
                @click="dateMenuOpen = false"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      </div>
      <label>
        <span class="field-label">Room type</span>
        <select v-model="filters.roomType" class="neu-input">
          <option value="">All room types</option>
          <option v-for="r in dims.roomTypes" :key="r" :value="r">
            {{ dims.labels[r] || r }}
          </option>
        </select>
      </label>
      <label>
        <span class="field-label">Market</span>
        <select v-model="filters.marketId" class="neu-input">
          <option value="">All markets</option>
          <option v-for="m in dims.markets" :key="m.id" :value="String(m.id)">
            {{ m.name }}
          </option>
        </select>
      </label>
      <RmsCompanyFilter v-model="filters.companyIds" :companies="dims.companies" />
      <label>
        <span class="field-label">Compare with</span>
        <select v-model="compareSelection" class="neu-input">
          <option value="weekday">Same weekday last year</option>
          <option value="calendar">Same date last year</option>
          <option value="custom">Matched event / holiday</option>
          <option value="budget">Budget (gross)</option>
        </select>
      </label>
      <label v-if="compareSelection === 'custom'">
        <span class="field-label">Comparison begins</span>
        <input v-model="filters.comparisonStart" type="date" required class="neu-input" />
      </label>
      <label>
        <span class="field-label">Pickup window</span>
        <select v-model.number="filters.pickupDays" class="neu-input">
          <option v-for="d in [1, 3, 7, 14, 30]" :key="d" :value="d">
            {{ d }} {{ d === 1 ? "day" : "days" }}
          </option>
        </select>
      </label>
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

    <nav class="seg !flex w-full" role="tablist" aria-label="Company analytics sections">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        class="seg-btn"
        :aria-selected="tab === t.id"
        @click="selectTab(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>

    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>

    <RmsPaceTab
      v-if="tab === 'pace' && loaded"
      :loading="paceLoading"
      :rows="paceRows"
      v-model:chart-view="chartView"
      :chart-data="chartData"
      :chart-options="PACE_CHART_OPTIONS"
      :chart-table="chartTable"
      :basis-label="basisLabel"
      :idr-coverage="idrCoverage"
      :basis="basis"
      :pickup-days="loaded.pickupDays"
      :compare-with-budget="loaded.compareWith === 'budget'"
      @open-day="() => {}"
    />
    <RmsGroupedReports
      v-if="loaded && ['lengthOfStay', 'nationality', 'behaviour', 'business'].includes(tab)"
      :group="tab as 'lengthOfStay' | 'nationality' | 'behaviour' | 'business'"
      :filters="reportFilters"
      :basis="basis"
      :labels="dims.labels"
      :extra-dimensions="[{ id: 'company', label: 'Company' }]"
      :split-length-of-stay="true"
      @drilldown="drilldownGroup"
    />
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { CalendarDaysIcon } from "@heroicons/vue/24/outline";
import {
  Chart as ChartJS,
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from "chart.js";
import axios from "../plugins/axios";
import PageHeader from "../components/PageHeader.vue";
import DateRangeCalendar from "../components/DateRangeCalendar.vue";
import RmsCompanyFilter from "../components/RmsCompanyFilter.vue";
import RmsPaceTab from "../components/RmsPaceTab.vue";
import RmsGroupedReports from "../components/RmsGroupedReports.vue";
import {
  addDays,
  hotelToday,
  shortDayYear,
  loadStoredFilters,
  saveStoredFilters,
  paceBuckets,
  paceChartTable,
  paceChartData,
  PACE_CHART_OPTIONS,
  ratio,
  type PaceRow,
} from "../utils/rms";
ChartJS.register(
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
);

const today = hotelToday(),
  route = useRoute(),
  router = useRouter();

const tabs = [
  { id: "lengthOfStay", label: "Length of stay" },
  { id: "nationality", label: "Nationality" },
  { id: "behaviour", label: "Booking behaviour" },
  { id: "pace", label: "Pace & pickups" },
  { id: "business", label: "Production" },
];
const STORAGE_KEY = "rms-company-analytics";
const stored = loadStoredFilters(STORAGE_KEY) || {};
const query = (k: string, f = "") =>
  typeof route.query[k] === "string" ? String(route.query[k]) : (stored[k] ?? f);
const tab = ref(tabs.some((t) => t.id === query("tab")) ? query("tab") : "lengthOfStay");
const basis = ref<"gross" | "net">(query("basis") === "net" ? "net" : "gross");

interface CompanyFilters {
  start: string;
  end: string;
  roomType: string;
  marketId: string;
  companyIds: number[];
  comparison: "weekday" | "calendar" | "custom";
  comparisonStart: string;
  compareWith: "yoy" | "budget";
  pickupDays: number;
}
const filters = reactive<CompanyFilters>({
  start: query("start", today),
  end: query("end", addDays(today, 29)),
  roomType: query("roomType"),
  marketId: query("marketId"),
  companyIds: query("companyIds")
    ? query("companyIds").split(",").filter(Boolean).map(Number)
    : [],
  comparison: (query("comparison", "weekday") as CompanyFilters["comparison"]) || "weekday",
  comparisonStart: query("comparisonStart"),
  compareWith: query("compareWith") === "budget" ? "budget" : "yoy",
  pickupDays: Number(query("pickupDays", "7")),
});
const loaded = ref<CompanyFilters | null>(null);
const error = ref("");
const dims = reactive<{
  roomTypes: string[];
  markets: { id: number; name: string }[];
  companies: { id: number; name: string }[];
  labels: Record<string, string>;
}>({ roomTypes: [], markets: [], companies: [], labels: {} });

const dirty = computed(
  () => loaded.value && JSON.stringify(filters) !== JSON.stringify(loaded.value),
);
const compareSelection = computed<string>({
  get: () => (filters.compareWith === "budget" ? "budget" : filters.comparison),
  set: (value) => {
    if (value === "budget") {
      filters.compareWith = "budget";
    } else {
      filters.compareWith = "yoy";
      filters.comparison = value as CompanyFilters["comparison"];
    }
  },
});
const basisLabel = computed(() =>
  basis.value === "gross"
    ? "Gross quoted room-rate revenue (USD converted to IDR)"
    : "Estimated room-rate revenue net of breakfast and tax/service (USD converted to IDR)",
);

function saveUrl() {
  const f = loaded.value || filters;
  const q = {
    start: f.start,
    end: f.end,
    roomType: f.roomType,
    marketId: f.marketId,
    companyIds: f.companyIds.length ? f.companyIds.join(",") : undefined,
    comparison: f.comparison,
    comparisonStart: f.comparison === "custom" ? f.comparisonStart : undefined,
    compareWith: f.compareWith,
    pickupDays: String(f.pickupDays),
    tab: tab.value,
    basis: basis.value,
  };
  router.replace({ query: q });
  saveStoredFilters(STORAGE_KEY, q as unknown as Record<string, string>);
}
function selectTab(id: string) {
  tab.value = id;
  saveUrl();
}
watch(basis, saveUrl);
function apply() {
  if (
    !filters.start ||
    !filters.end ||
    filters.end < filters.start ||
    (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000 >= 366
  ) {
    error.value = "Choose a valid range of at most 366 days.";
    return;
  }
  if (filters.compareWith !== "budget" && filters.comparison === "custom" && !filters.comparisonStart) {
    error.value = "Choose a comparison start date.";
    return;
  }
  error.value = "";
  loaded.value = { ...filters, companyIds: [...filters.companyIds] };
  saveUrl();
}
function drilldownGroup(dimension: string, id: string) {
  if (loaded.value) Object.assign(filters, loaded.value);
  if (dimension === "market") filters.marketId = id;
  else if (dimension === "company") filters.companyIds = [Number(id)];
  else filters.roomType = id;
  tab.value = "pace";
  apply();
}

// "Pace & pickups" params for RmsGroupedReports (comma-joined company ids,
// matching how roomType/marketId are already passed as plain scalar params).
const reportFilters = computed(() => ({
  start: loaded.value?.start || filters.start,
  end: loaded.value?.end || filters.end,
  roomType: loaded.value?.roomType || "",
  marketId: loaded.value?.marketId || "",
  companyIds: loaded.value?.companyIds.length ? loaded.value.companyIds.join(",") : undefined,
  pickupDays: loaded.value?.pickupDays ?? filters.pickupDays,
  comparison: loaded.value?.comparison || filters.comparison,
  comparisonStart: loaded.value?.comparisonStart || "",
  compareWith: loaded.value?.compareWith || filters.compareWith,
}));

const paceRows = ref<PaceRow[]>([]),
  paceLoading = ref(false);
let requestId = 0,
  disposed = false;
async function loadPace(f: CompanyFilters) {
  const id = ++requestId;
  paceLoading.value = true;
  try {
    const r = await axios.get("/api/rms/pace", {
      params: {
        start: f.start,
        end: f.end,
        roomType: f.roomType || undefined,
        marketId: f.marketId || undefined,
        companyIds: f.companyIds.length ? f.companyIds.join(",") : undefined,
        pickupDays: f.pickupDays,
        comparison: f.comparison,
        comparisonStart: f.comparisonStart || undefined,
      },
      timeout: 120000,
    });
    if (disposed || id !== requestId) return;
    paceRows.value = r.data.rows;
  } catch (e: any) {
    if (id === requestId && !disposed) error.value = e?.response?.data?.message || "Could not load pace";
  } finally {
    if (id === requestId) paceLoading.value = false;
  }
}
watch(loaded, (f) => {
  if (f) void loadPace(f);
});

const chartView = ref("monthly");
const buckets = computed(() => paceBuckets(paceRows.value, chartView.value, basis.value));
const chartTable = computed(() => paceChartTable(buckets.value, paceRows.value));
const chartData = computed(() => paceChartData(buckets.value, loaded.value?.compareWith === "budget"));
const idrCoverage = computed(() => {
  const r = ratio(
    paceRows.value.reduce((s, row) => s + row.idrRooms, 0),
    paceRows.value.reduce((s, row) => s + row.rooms, 0),
  );
  return r == null ? null : r * 100;
});

const dateMenuOpen = ref(false),
  dateMenuRef = ref<HTMLElement | null>(null);
function onClickOutside(e: MouseEvent) {
  if (dateMenuOpen.value && dateMenuRef.value && !dateMenuRef.value.contains(e.target as Node))
    dateMenuOpen.value = false;
}
function applyDatePreset(months: number) {
  const d = new Date(`${today}T00:00:00Z`);
  filters.start = addDays(today, -(d.getUTCDate() - 1));
  const end = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + months, 0));
  filters.end = end.toISOString().slice(0, 10);
  dateMenuOpen.value = false;
}
function thisMonth() {
  filters.start = `${today.slice(0, 7)}-01`;
  filters.end = addDays(
    new Date(Date.UTC(Number(today.slice(0, 4)), Number(today.slice(5, 7)), 1))
      .toISOString()
      .slice(0, 10),
    -1,
  );
  dateMenuOpen.value = false;
  apply();
}

onMounted(async () => {
  document.addEventListener("mousedown", onClickOutside);
  try {
    const d = await axios.get("/api/rms/room-types");
    Object.assign(dims, d.data);
  } catch (e: any) {
    error.value = e?.response?.data?.message || "Could not load room types";
  }
  apply();
});
onBeforeUnmount(() => {
  disposed = true;
  document.removeEventListener("mousedown", onClickOutside);
});
</script>
