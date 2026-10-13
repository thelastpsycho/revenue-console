<template>
  <div class="mx-auto w-full max-w-screen-2xl space-y-4 p-4 sm:p-6">
    <PageHeader
      title="Revenue management"
      :subtitle="`Daily decisions · ${dayLabel(today)} · Bali time`"
    >
      <template #actions>
        <button
          type="button"
          class="btn-flat"
          :disabled="!rows.length"
          title="Export the loaded stay dates as CSV"
          @click="exportCsv"
        >
          <ArrowDownTrayIcon class="h-4 w-4" /> Export CSV
        </button>
      </template>
    </PageHeader>

    <nav class="seg !flex w-full" role="tablist" aria-label="RMS sections">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        :class="['seg-btn', t.id === 'data' && 'ml-auto']"
        :aria-selected="tab === t.id"
        @click="selectTab(t.id)"
      >
        <component :is="t.icon" class="h-4 w-4" />
        {{ t.label }}
      </button>
    </nav>

    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>

    <template v-if="tab !== 'data'">
      <RmsFilterBar
        :filters="filters"
        :dims="dims"
        :loading="loading"
        :dirty="!!dirty"
        :loaded="loaded"
        :comparison-label="comparisonLabel"
        :forecast="forecast"
        :forecast-busy="forecastBusy"
        :report-sync="reportSync"
        :sync="sync"
        :today="today"
        v-model:basis="basis"
        @submit="loadAll"
        @refresh-forecast="refreshForecast"
      />
      <RmsOverviewTab
        v-if="tab === 'overview'"
        :tiles="tiles"
        :attention-rows="attentionRows"
        :flagged-count="flaggedCount"
        v-model:only-attention="onlyAttention"
        :rows-length="rows.length"
        :notes="notes"
        :bar-updated-at="bar.updatedAt"
        :months="months"
        :basis-label="basisLabel"
        @open-day="openDay"
      />
      <RmsPaceTab
        v-if="tab === 'pace'"
        :rows="rows"
        v-model:chart-view="chartView"
        :chart-data="chartData"
        :chart-options="chartOptions"
        :chart-table="chartTable"
        :basis-label="basisLabel"
        :idr-coverage="idrCoverage"
        :basis="basis"
        :pickup-days="loaded?.pickupDays || filters.pickupDays"
        :compare-with-budget="compareWithBudget"
        @open-day="openDay"
      />
      <RmsForecastTab
        v-if="tab === 'forecast'"
        :forecast="forecast"
        :forecast-busy="forecastBusy"
        :segment-totals="segmentTotals"
      />
      <RmsGroupedReports
        v-if="loaded && (tab === 'behaviour' || tab === 'business')"
        :group="tab"
        :filters="loaded"
        :basis="basis"
        :labels="dims.labels"
        @drilldown="drilldownGroup"
      />
      <RmsRateBreakdown
        v-if="tab === 'business'"
        :breakdown="breakdown"
        :basis="basis"
        :basis-label="basisLabel"
        :label="label"
      />
      <RmsInventoryTab
        v-if="tab === 'rooms'"
        :forecast="forecast"
        :forecast-busy="forecastBusy"
        :room-type="loaded?.roomType || ''"
        :label="label"
        @open-day="openDay"
      />
      <RmsDayDetail
        :selected-date="selectedDate"
        :curve="curve"
        :curve-loading="curveLoading"
        :curve-error="curveError"
        :curve-data="curveData"
        :curve-options="curveOptions"
        :today-marker="todayMarker"
        :selected-availability="selectedAvailability"
        :selected-segments="selectedSegments"
        :saved-note="notes[selectedDate]"
        :note-saving="noteSaving"
        :label="label"
        v-model:note-draft="noteDraft"
        @close="closeDay"
        @save-note="saveNote"
      />
    </template>
    <RmsDataSettingsTab
      v-else
      :today="today"
      v-model:sync="sync"
      @synced="onSynced"
    />
  </div>
</template>
<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowDownTrayIcon,
  ArrowTrendingUpIcon,
  ChartPieIcon,
  Cog6ToothIcon,
  PresentationChartLineIcon,
  Squares2X2Icon,
  TableCellsIcon,
  UserGroupIcon,
} from "@heroicons/vue/24/outline";
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
  type ChartOptions,
  type ChartTypeRegistry,
} from "chart.js";
import axios from "../plugins/axios";
import PageHeader from "../components/PageHeader.vue";
import RmsGroupedReports from "../components/RmsGroupedReports.vue";
import RmsRateBreakdown from "../components/RmsRateBreakdown.vue";
import RmsInventoryTab from "../components/RmsInventoryTab.vue";
import RmsFilterBar from "../components/RmsFilterBar.vue";
import RmsOverviewTab from "../components/RmsOverviewTab.vue";
import RmsPaceTab from "../components/RmsPaceTab.vue";
import RmsForecastTab from "../components/RmsForecastTab.vue";
import RmsDataSettingsTab from "../components/RmsDataSettingsTab.vue";
import RmsDayDetail from "../components/RmsDayDetail.vue";
import {
  addDays,
  hotelToday,
  difference,
  ratio,
  sumKnown,
  monthlySummary,
  csvText,
  num,
  money,
  moneyShort,
  signed,
  percent,
  pctDiff,
  pctLabel,
  signClass,
  dayLabel,
  currentRooms,
  revenueFor,
  type PaceRow,
  type Settings,
  type Sync,
  type Forecast,
  type Breakdown,
  type Filters,
  type Curve,
  type CurvePoint,
  loadStoredFilters,
  saveStoredFilters,
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
// chart.js is a shared singleton module, so this default applies to every
// Chart instance in the app, not just RMS - matching style.css's root font
// instead of chart.js's own Helvetica/Arial fallback.
ChartJS.defaults.font.family = "'Nunito Sans', ui-sans-serif, system-ui, sans-serif";
const today = hotelToday(),
  route = useRoute(),
  router = useRouter();
// Tab ids are kept from the earlier layout so saved ?tab= links still work.
const tabs = [
  { id: "overview", label: "Overview", icon: Squares2X2Icon },
  { id: "pace", label: "Pace & pickup", icon: ArrowTrendingUpIcon },
  { id: "forecast", label: "Forecast", icon: PresentationChartLineIcon },
  { id: "behaviour", label: "Booking behaviour", icon: UserGroupIcon },
  { id: "business", label: "Production", icon: ChartPieIcon },
  { id: "rooms", label: "Inventory", icon: TableCellsIcon },
  { id: "data", label: "Data & settings", icon: Cog6ToothIcon },
];
const STORAGE_KEY = "rms";
const stored = loadStoredFilters(STORAGE_KEY) || {};
const query = (k: string, f = "") =>
  typeof route.query[k] === "string" ? String(route.query[k]) : (stored[k] ?? f);
const tab = ref(
    tabs.some((t) => t.id === query("tab")) ? query("tab") : "overview",
  ),
  basis = ref<"gross" | "net">(query("basis") === "net" ? "net" : "gross");
const filters = reactive<Filters>({
  start: query("start", today),
  end: query("end", addDays(today, 29)),
  roomType: query("roomType"),
  marketId: query("marketId"),
  pickupDays: Number(query("pickupDays", "7")),
  comparison: query("comparison", "calendar"),
  comparisonStart: query("comparisonStart"),
  compareWith: query("compareWith") === "budget" ? "budget" : "yoy",
});
const reportSync = ref<Sync | null>(null);
const loaded = ref<Filters | null>(null),
  rows = ref<PaceRow[]>([]),
  forecast = ref<Forecast | null>(null),
  breakdown = ref<Breakdown | null>(null);
const dims = reactive<{
  roomTypes: string[];
  markets: { id: number; name: string }[];
  labels: Record<string, string>;
}>({ roomTypes: [], markets: [], labels: {} });
const sync = ref<Sync | null>(null),
  appliedSettings = ref<Settings | null>(null);
const notes = ref<Record<string, { text: string; updatedAt: string }>>({}),
  bar = ref<{
    byDate: Record<string, Record<string, string>>;
    updatedAt: string | null;
  }>({ byDate: {}, updatedAt: null });
const loading = ref(false),
  error = ref(""),
  onlyAttention = ref(true),
  chartView = ref("monthly");
const selectedDate = ref(""),
  curve = ref<Curve | null>(null),
  curveLoading = ref(false),
  curveError = ref(""),
  noteDraft = ref(""),
  noteSaving = ref(false);
let requestId = 0,
  curveId = 0,
  forecastTimer: ReturnType<typeof setTimeout> | undefined,
  syncTimer: ReturnType<typeof setTimeout> | undefined,
  disposed = false;
const label = (code: string) => dims.labels[code] || code;
const message = (e: any) =>
  e?.response?.data?.message || e?.message || "Request failed";
const basisLabel = computed(() =>
  basis.value === "gross"
    ? "Gross quoted room-rate revenue (IDR only)"
    : "Estimated room-rate revenue net of breakfast and tax/service (IDR only)",
);
const revenue = (r: PaceRow) => revenueFor(r, basis.value);
const dirty = computed(
  () =>
    loaded.value && JSON.stringify(filters) !== JSON.stringify(loaded.value),
);
const compareWithBudget = computed(() => loaded.value?.compareWith === "budget");
const comparisonLabel = computed(() =>
  loaded.value?.compareWith === "budget"
    ? "Budget (gross)"
    : loaded.value?.comparison === "custom"
      ? `Matched period from ${loaded.value.comparisonStart}`
      : loaded.value?.comparison === "calendar"
        ? "Same calendar date last year"
        : "Same weekday last year",
);
const forecastBusy = computed(() =>
  Object.values(forecast.value?.sections || {}).some((s) => s.refreshing),
);
function saveUrl() {
  const q = { ...(loaded.value || filters), tab: tab.value, basis: basis.value };
  router.replace({ query: q });
  saveStoredFilters(STORAGE_KEY, q as unknown as Record<string, string>);
}
function drilldownGroup(dimension: string, id: string) {
  if (loaded.value) Object.assign(filters, loaded.value);
  if (dimension === "market") filters.marketId = id;
  else filters.roomType = id;
  tab.value = "pace";
  void loadAll();
}
function selectTab(id: string) {
  tab.value = id;
  saveUrl();
  if (id !== "data" && !loaded.value && !loading.value) void loadAll();
}
watch(basis, saveUrl);
async function loadAll() {
  if (
    !filters.start ||
    !filters.end ||
    filters.end < filters.start ||
    (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000 >= 366
  ) {
    error.value = "Choose a valid range of at most 366 days.";
    return;
  }
  if (
    filters.compareWith !== "budget" &&
    filters.comparison === "custom" &&
    !filters.comparisonStart
  ) {
    error.value = "Choose a comparison start date.";
    return;
  }
  const id = ++requestId,
    f = { ...filters };
  loading.value = true;
  error.value = "";
  clearTimeout(forecastTimer);
  try {
    const r = await axios.get("/api/rms/pace", { params: f, timeout: 120000 });
    if (disposed || id !== requestId) return;
    rows.value = r.data.rows;
    loaded.value = f;
    sync.value = r.data.sync;
    reportSync.value = r.data.sync;
    appliedSettings.value = JSON.parse(JSON.stringify(r.data.settings));
    notes.value = r.data.notes;
    bar.value = r.data.bar;
    closeDay();
    forecast.value = null;
    breakdown.value = null;
    saveUrl();
    void loadForecast(id, f);
    void loadBreakdown(id, f);
  } catch (e) {
    if (id === requestId) error.value = message(e);
  } finally {
    if (id === requestId) loading.value = false;
  }
}
async function loadBreakdown(id: number, f: Filters) {
  try {
    const r = await axios.get("/api/rms/pace/breakdown", {
      params: { start: f.start, end: f.end, roomType: f.roomType, marketId: f.marketId },
      timeout: 120000,
    });
    if (!disposed && id === requestId) breakdown.value = r.data;
  } catch (e) {
    if (id === requestId && !disposed) error.value = message(e);
  }
}
async function loadForecast(id: number, f: Filters, refresh = false) {
  clearTimeout(forecastTimer);
  try {
    const days = Math.min(
      90,
      Math.round((Date.parse(f.end) - Date.parse(f.start)) / 86400000) + 1,
    );
    const r = await axios.get("/api/rms/forecast", {
      params: { start: f.start, days, refresh: refresh ? "1" : undefined },
    });
    if (disposed || id !== requestId) return;
    forecast.value = r.data;
    if (forecastBusy.value)
      forecastTimer = setTimeout(() => loadForecast(id, f), 2000);
  } catch (e) {
    if (id === requestId && !disposed) error.value = message(e);
  }
}
function refreshForecast() {
  if (loaded.value) void loadForecast(requestId, loaded.value, true);
}
async function pollSync() {
  try {
    const r = await axios.get("/api/rms/sync");
    if (disposed) return;
    sync.value = r.data;
  } catch (e) {
    if (!disposed) error.value = message(e);
  }
  if (!disposed)
    syncTimer = setTimeout(pollSync, sync.value?.job.running ? 2000 : 30000);
}
function onSynced() {
  clearTimeout(syncTimer);
  void pollSync();
}
function closeDay() {
  selectedDate.value = "";
  curve.value = null;
  ++curveId;
}
async function openDay(day: string) {
  const id = ++curveId;
  selectedDate.value = day;
  noteDraft.value = notes.value[day]?.text || "";
  curve.value = null;
  curveLoading.value = true;
  curveError.value = "";
  try {
    const r = await axios.get("/api/rms/pace/curve", {
      params: { ...loaded.value, date: day, maxLead: 180 },
      timeout: 120000,
    });
    if (id === curveId && !disposed) curve.value = r.data;
  } catch (e) {
    if (id === curveId) curveError.value = message(e);
  } finally {
    if (id === curveId) curveLoading.value = false;
  }
}
async function saveNote() {
  const day = selectedDate.value,
    text = noteDraft.value;
  noteSaving.value = true;
  try {
    const r = await axios.put(`/api/rms/notes/${day}`, { text });
    notes.value[day] = r.data.note;
  } catch (e) {
    error.value = message(e);
  } finally {
    noteSaving.value = false;
  }
}
const idrCoverage = computed(() => {
  const r = ratio(
    rows.value.reduce((s, r) => s + r.idrRooms, 0),
    rows.value.reduce((s, r) => s + r.rooms, 0),
  );
  return r == null ? null : r * 100;
});
const hotelMap = computed(() =>
    Object.fromEntries((forecast.value?.hotel || []).map((r) => [r.date, r])),
  ),
  availabilityMap = computed(() =>
    Object.fromEntries(
      (forecast.value?.availability || []).map((r) => [r.date, r.values]),
    ),
  );
const capacities = computed(() => {
  const m: Record<string, number> = {};
  if (loaded.value?.roomType) {
    for (const r of forecast.value?.roomTypes || [])
      if (r.typeId === loaded.value.roomType) m[r.date] = r.roomCount;
  } else
    for (const r of forecast.value?.hotel || [])
      if (r.roomCount != null) m[r.date] = r.roomCount;
  return m;
});
const attention = computed(() =>
  rows.value.map((r) => {
    const h = hotelMap.value[r.date],
      a = availabilityMap.value[r.date],
      otb = currentRooms(r),
      occ = ratio(otb, capacities.value[r.date] ?? null),
      occupancy = occ == null ? null : occ * 100,
      gap = difference(otb, r.stlyRooms),
      t = appliedSettings.value?.thresholds,
      reasons: string[] = [];
    if (otb == null) reasons.push("Booking coverage unavailable");
    if (reportSync.value?.stale) reasons.push("Stale booking data");
    if (reportSync.value?.lastSuccessfulSync !== sync.value?.lastSuccessfulSync)
      reasons.push("Booking data changed — apply again");
    if (t && occupancy != null && occupancy >= t.occupancy)
      reasons.push("High occupancy");
    if (
      t &&
      gap != null &&
      gap <= -t.behindRooms &&
      r.pickupRooms != null &&
      r.pickupRooms < t.weakPickup
    )
      reasons.push("Behind pace; weak pickup");
    const available = a?.[loaded.value?.roomType || "RoomAvailable"] ?? null;
    if (available != null && available < 0)
      reasons.push("Negative physical availability");
    const reconciliation =
      !loaded.value?.roomType && !loaded.value?.marketId && h
        ? difference(otb, h.roomsSold)
        : null;
    if (reconciliation != null && reconciliation !== 0)
      reasons.push("Check booking/PMS room difference");
    if (r.comparisonQuality === "unavailable")
      reasons.push("Comparison unavailable");
    return {
      ...r,
      otb,
      occupancy,
      gap,
      available,
      reconciliation,
      reasons,
      bar: Object.entries(bar.value.byDate[r.date] || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join("; "),
    };
  }),
);
const attentionRows = computed(() =>
    attention.value.filter((r) => !onlyAttention.value || r.reasons.length),
  ),
  flaggedCount = computed(
    () => attention.value.filter((r) => r.reasons.length).length,
  );
const months = computed(() =>
  monthlySummary(
    rows.value,
    basis.value,
    appliedSettings.value?.budgets || [],
    loaded.value?.marketId ? {} : capacities.value,
    today,
    !!loaded.value?.roomType || !!loaded.value?.marketId,
  ),
);
// Each tile shows the loaded total with its comparison underneath.
const vsLy = (cur: number | null, ly: number | null, fmt: (v: number | null) => string) => {
  const d = pctDiff(cur, ly);
  if (cur == null) return { text: "vs LY —" };
  return {
    text: `${pctLabel(d)} vs LY (${fmt(ly)})`,
    tone: signClass(d) || undefined,
  };
};
const tiles = computed(() => {
  const known =
      rows.value.length &&
      rows.value.every((r) => r.currentQuality !== "unavailable"),
    t = chartTable.value.totals,
    rooms = known ? t.rooms : null,
    rev = known ? t.revenue : null,
    budgets = months.value.map((m) => m.budget),
    target =
      budgets.length && budgets.every((b) => b != null)
        ? sumKnown(budgets)
        : null,
    targetShare = ratio(rev, target);
  return [
    {
      label: "OTB room nights",
      value: num(rooms),
      subs: [vsLy(rooms, t.comparison, num)],
    },
    {
      label: basis.value === "gross" ? "Room revenue" : "Est. net revenue",
      value: moneyShort(rev),
      title: money(rev),
      subs: [
        vsLy(rev, t.comparisonRevenue, moneyShort),
        {
          text:
            targetShare == null
              ? "No target for this range"
              : `${(targetShare * 100).toFixed(0)}% of target (${moneyShort(target)})`,
        },
      ],
    },
    {
      label: "IDR ADR",
      value: moneyShort(known ? t.adr : null),
      title: money(known ? t.adr : null),
      subs: [
        vsLy(known ? t.adr : null, t.comparisonAdr, moneyShort),
        { text: `IDR coverage ${percent(known ? idrCoverage.value : null)}` },
      ],
    },
    {
      label: `Net pickup (${loaded.value?.pickupDays || 7}d)`,
      value: signed(
        rows.value.length
          ? sumKnown(rows.value.map((r) => r.pickupRooms))
          : null,
      ),
      subs: [{ text: "room nights" }],
    },
  ];
});
const segmentTotals = computed(() => {
  const m = new Map<
    string,
    { market: string; rooms: number; revenue: number }
  >();
  for (const s of forecast.value?.segments || []) {
    const r = m.get(s.market) || { market: s.market, rooms: 0, revenue: 0 };
    r.rooms += s.rooms || 0;
    r.revenue += s.revenue || 0;
    m.set(s.market, r);
  }
  return [...m.values()].sort((a, b) => b.rooms - a.rooms);
});
const selectedAvailability = computed(() =>
    Object.entries(availabilityMap.value[selectedDate.value] || {})
      .filter(([k]) => k in dims.labels || dims.roomTypes.includes(k))
      .map(([type, rooms]) => ({ type, rooms })),
  ),
  selectedSegments = computed(() =>
    (forecast.value?.segments || []).filter(
      (r) => r.date === selectedDate.value,
    ),
  );
const buckets = computed(() => {
  const m = new Map<string, PaceRow[]>();
  for (const r of rows.value) {
    let key = r.date;
    if (chartView.value === "monthly") key = key.slice(0, 7);
    if (chartView.value === "weekly")
      key = addDays(key, -((new Date(`${key}T00:00:00Z`).getUTCDay() + 6) % 7));
    m.set(key, [...(m.get(key) || []), r]);
  }
  return [...m].map(([key, rs]) => {
    const bucketRevenue = sumKnown(
        rs.map((r) => (currentRooms(r) == null ? null : revenue(r))),
      ),
      bucketIdrRooms = rs.reduce((s, r) => s + r.idrRooms, 0),
      bucketComparisonRevenue = sumKnown(
        rs.map((r) =>
          basis.value === "gross" ? r.stlyRevenue : r.stlyNetRevenue,
        ),
      ),
      bucketStlyIdrRooms = sumKnown(rs.map((r) => r.stlyIdrRooms)),
      bucketBudgetRooms = sumKnown(rs.map((r) => r.budgetRooms)),
      bucketBudgetRevenue = sumKnown(rs.map((r) => r.budgetRevenue));
    return {
      key,
      rooms: sumKnown(rs.map(currentRooms)),
      comparison: sumKnown(rs.map((r) => r.stlyRooms)),
      revenue: bucketRevenue,
      comparisonRevenue: bucketComparisonRevenue,
      adr: ratio(bucketRevenue, bucketIdrRooms),
      comparisonAdr: ratio(bucketComparisonRevenue, bucketStlyIdrRooms),
      budgetRooms: bucketBudgetRooms,
      budgetRevenue: bucketBudgetRevenue,
      // Budget revenue is already all-IDR, so this divides by its own room
      // count rather than idrRooms (the actual-booking currency subset).
      budgetAdr: ratio(bucketBudgetRevenue, bucketBudgetRooms),
    };
  });
});
const chartTable = computed(() => {
  const b = buckets.value,
    totalRevenue = sumKnown(b.map((x) => x.revenue)),
    totalComparisonRevenue = sumKnown(b.map((x) => x.comparisonRevenue)),
    totalIdrRooms = rows.value.reduce((s, r) => s + r.idrRooms, 0),
    totalStlyIdrRooms = sumKnown(rows.value.map((r) => r.stlyIdrRooms)),
    totalBudgetRooms = sumKnown(b.map((x) => x.budgetRooms)),
    totalBudgetRevenue = sumKnown(b.map((x) => x.budgetRevenue));
  return {
    buckets: b,
    totals: {
      rooms: sumKnown(b.map((x) => x.rooms)),
      comparison: sumKnown(b.map((x) => x.comparison)),
      revenue: totalRevenue,
      comparisonRevenue: totalComparisonRevenue,
      adr: ratio(totalRevenue, totalIdrRooms),
      comparisonAdr: ratio(totalComparisonRevenue, totalStlyIdrRooms),
      budgetRooms: totalBudgetRooms,
      budgetRevenue: totalBudgetRevenue,
      budgetAdr: ratio(totalBudgetRevenue, totalBudgetRooms),
    },
  };
});
// The comparator bar/line swaps between LY and budget rather than showing
// both, so the chart only clutters up with budget when the operator asks
// for it via "Compare with".
const chartData = computed(() => ({
  labels: buckets.value.map((b) => b.key),
  datasets: [
    {
      type: "bar" as const,
      label: "OTB room nights",
      data: buckets.value.map((b) => b.rooms),
      backgroundColor: "#334155",
      yAxisID: "rooms",
      order: 2,
    },
    compareWithBudget.value
      ? {
          type: "bar" as const,
          label: "Budget nights (gross)",
          data: buckets.value.map((b) => b.budgetRooms),
          backgroundColor: "#fcd34d",
          yAxisID: "rooms",
          order: 2,
        }
      : {
          type: "bar" as const,
          label: "Comparison nights",
          data: buckets.value.map((b) => b.comparison),
          backgroundColor: "#cbd5e1",
          yAxisID: "rooms",
          order: 2,
        },
    {
      type: "line" as const,
      label: "IDR ADR",
      data: buckets.value.map((b) => b.adr),
      borderColor: "#0f766e",
      yAxisID: "adr",
      order: 1,
    },
    compareWithBudget.value
      ? {
          type: "line" as const,
          label: "Budget ADR (gross)",
          data: buckets.value.map((b) => b.budgetAdr),
          borderColor: "#b45309",
          borderDash: [4, 4],
          yAxisID: "adr",
          order: 1,
        }
      : {
          type: "line" as const,
          label: "Comparison ADR",
          data: buckets.value.map((b) => b.comparisonAdr),
          borderColor: "#64748b",
          borderDash: [4, 4],
          yAxisID: "adr",
          order: 1,
        },
  ],
}));
const chartOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    rooms: {
      position: "left",
      beginAtZero: true,
      title: { display: true, text: "Room nights" },
    },
    adr: {
      position: "right",
      min: 1000000,
      grid: { drawOnChartArea: false },
      title: { display: true, text: "ADR (IDR)" },
    },
  },
};
const curveData = computed(() => {
  const c = curve.value,
    leads = Array.from(
      { length: (c?.maxLead || 180) + 1 },
      (_, i) => (c?.maxLead || 180) - i,
    ),
    point = (pts: CurvePoint[], lead: number) =>
      pts.find((p) => p.lead === lead)?.rooms ?? null;
  return {
    labels: leads.map((l) => (l === c?.todayLead ? `${l} · Today` : String(l))),
    datasets: [
      {
        label: "Current observed / reconstructed",
        data: leads.map((l) => point(c?.current || [], l)),
        borderColor: "#0f766e",
        pointRadius: 0,
        spanGaps: false,
      },
      {
        label: "Comparison observed / reconstructed",
        data: leads.map((l) => point(c?.lastYear || [], l)),
        borderColor: "#94a3b8",
        borderDash: [4, 4],
        pointRadius: 0,
        spanGaps: false,
      },
    ],
  };
});
const todayMarker = {
  id: "rms-today",
  afterDraw(chart: ChartJS) {
    const c = curve.value;
    if (!c || c.todayLead < 0 || c.todayLead > c.maxLead) return;
    const x = chart.scales.x.getPixelForValue(c.maxLead - c.todayLead);
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = "#0f766e";
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.stroke();
    ctx.fillStyle = "#0f766e";
    ctx.textAlign = x > chartArea.right - 50 ? "right" : "left";
    ctx.fillText("Today", x, chartArea.top + 12);
    ctx.restore();
  },
};
const curveOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    x: {
      title: { display: true, text: "Days before stay date" },
      ticks: { maxTicksLimit: 10 },
    },
    y: { beginAtZero: true, title: { display: true, text: "Room nights" } },
  },
};
function exportCsv() {
  const out: unknown[][] = [
    [
      "Stay date",
      "Comparison date",
      "Room type",
      "Market",
      "Revenue basis",
      "OTB rooms",
      "IDR revenue",
      "IDR ADR",
      "New rooms",
      "Cancelled rooms",
      "Amended rooms",
      "Net pickup",
      "Comparison rooms",
      "Current quality",
      "Comparison quality",
      "Pickup quality",
      "Last successful sync",
      "Note",
    ],
  ];
  for (const r of rows.value)
    out.push([
      r.date,
      r.lyDate,
      loaded.value?.roomType || "All",
      loaded.value?.marketId || "All",
      basisLabel.value,
      currentRooms(r),
      currentRooms(r) == null ? null : revenue(r),
      currentRooms(r) == null ? null : ratio(revenue(r), r.idrRooms),
      r.newRooms,
      r.cancelledRooms,
      r.amendedRooms,
      r.pickupRooms,
      r.stlyRooms,
      r.currentQuality,
      r.comparisonQuality,
      r.pickupQuality,
      reportSync.value?.lastSuccessfulSync,
      notes.value[r.date]?.text || "",
    ]);
  const url = URL.createObjectURL(
      new Blob([csvText(out)], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = `rms-${loaded.value?.start}-${loaded.value?.end}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
onMounted(async () => {
  void pollSync();
  try {
    const d = await axios.get("/api/rms/room-types");
    if (disposed) return;
    Object.assign(dims, d.data);
  } catch (e) {
    error.value = message(e);
  }
  if (!disposed && tab.value !== "data") void loadAll();
});
onBeforeUnmount(() => {
  disposed = true;
  ++requestId;
  ++curveId;
  clearTimeout(forecastTimer);
  clearTimeout(syncTimer);
});
</script>
