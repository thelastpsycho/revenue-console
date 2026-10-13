<template>
  <div class="space-y-4">
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>
    <template v-if="loading">
      <RmsSkeleton variant="tiles" :count="4" />
      <div class="grid gap-4 lg:grid-cols-2">
        <RmsCard v-for="i in 2" :key="i" title="Loading…">
          <div class="h-56 p-4">
            <RmsSkeleton variant="chart" />
          </div>
        </RmsCard>
      </div>
      <RmsCard title="Loading…">
        <RmsSkeleton variant="table" :count="8" :columns="6" />
      </RmsCard>
    </template>
    <template v-else-if="data">
      <!-- ===== Booking behaviour ===== -->
      <template v-if="group === 'behaviour'">
        <div class="neu-card flex flex-wrap items-end justify-between gap-3 p-4">
          <label>
            <span class="field-label">Date selection applies to</span>
            <select v-model="dateBasis" class="neu-input">
              <option value="stay">Stay dates (overlapping stays)</option>
              <option value="booking">Booking creation dates</option>
            </select>
          </label>
          <button class="btn-flat" @click="exportBehaviour">
            <ArrowDownTrayIcon class="h-4 w-4" /> Export behaviour
          </button>
        </div>
        <p v-if="data.behaviour.invalidLeadTime" class="alert-warn">
          {{ data.behaviour.invalidLeadTime }} reservations have negative lead
          time and are left out of the lead-time buckets.
        </p>
        <dl class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div v-for="t in behaviourTiles" :key="t.label" class="stat-tile">
            <dt>{{ t.label }}</dt>
            <dd>{{ t.value }}</dd>
          </div>
        </dl>
        <div class="grid gap-4 lg:grid-cols-2">
          <RmsCard
            v-for="r in distributions"
            :key="r.title"
            :title="r.title"
            :description="r.description"
          >
            <div class="h-56 p-4">
              <Chart
                type="bar"
                :data="distributionChart(r.rows)"
                :options="options"
              />
            </div>
            <table class="data-table border-t border-slate-200">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th class="num">Reservations</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in r.rows" :key="b.label">
                  <td>{{ b.label }}</td>
                  <td class="num">{{ available(b.bookings) }}</td>
                </tr>
              </tbody>
            </table>
          </RmsCard>
        </div>
        <div class="grid gap-4 lg:grid-cols-2">
          <RmsCard title="Booking and arrival weekday">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Weekday</th>
                  <th class="num">Booked</th>
                  <th class="num">Arrivals</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in data.behaviour.weekdays" :key="r.label">
                  <td>{{ r.label }}</td>
                  <td class="num">{{ available(r.booked) }}</td>
                  <td class="num">{{ available(r.arrivals) }}</td>
                </tr>
              </tbody>
            </table>
          </RmsCard>
          <RmsCard
            title="Cancellations and no-shows by segment"
            description="Current status of every reservation in the cohort, not a count of cancellation events. Future no-shows aren't final."
          >
            <div class="overflow-x-auto">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Segment</th>
                    <th class="num">Bookings</th>
                    <th class="num">Cancelled</th>
                    <th class="num">Cancel %</th>
                    <th class="num">No-shows</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in data.behaviour.losses" :key="r.id">
                    <td class="font-semibold text-slate-900">{{ r.name }}</td>
                    <td class="num">{{ available(r.bookings) }}</td>
                    <td class="num">{{ available(r.cancelled) }}</td>
                    <td class="num">
                      {{
                        data.quality === "unavailable"
                          ? EMPTY
                          : percent(ratio(r.cancelled, r.bookings))
                      }}
                    </td>
                    <td class="num">{{ available(r.noShows) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </RmsCard>
        </div>
        <p class="text-[11px] text-slate-500">
          History quality: {{ data.quality }}. Each reservation counts once.
          Lead time and stay length use active bookings (no cancellations or
          no-shows); stay length is the full reservation, even if only some
          nights fall in the selected range.
        </p>
      </template>

      <!-- ===== Production ===== -->
      <template v-if="group === 'business'">
        <RmsCard
          :title="`Production by ${dimensionLabel.toLowerCase()}`"
          :description="`Stay-night positions · history quality ${data.quality}. ${activeDimension !== 'ratePlan' ? 'Select a row to open its pace.' : ''}`"
          scroll
        >
          <template #actions>
            <div class="seg" role="group" aria-label="Group by">
              <button
                v-for="d in dimensions"
                :key="d.id"
                type="button"
                class="seg-btn"
                :aria-pressed="dimension === d.id"
                @click="dimension = d.id"
              >
                {{ d.label }}
              </button>
            </div>
            <button
              type="button"
              class="btn-flat px-2.5 py-1 text-xs"
              :aria-pressed="moreColumns"
              @click="moreColumns = !moreColumns"
            >
              {{ moreColumns ? "Fewer columns" : "More columns" }}
            </button>
            <button
              type="button"
              class="btn-icon"
              title="Export production"
              aria-label="Export production"
              @click="exportProduction"
            >
              <ArrowDownTrayIcon class="h-4 w-4" />
            </button>
          </template>
          <table class="data-table">
            <thead>
              <tr>
                <th class="sticky-col">{{ dimensionLabel }}</th>
                <th class="num">OTB nights</th>
                <th class="num">Share</th>
                <th class="num">Revenue</th>
                <th class="num">ADR</th>
                <th class="num">Pickup ({{ pickupKey }}d)</th>
                <template v-if="activeDimension === 'market' && compareWithBudget">
                  <th class="num">Budget nights</th>
                  <th class="num">Budget revenue (gross)</th>
                  <th class="num">vs budget (gross)</th>
                </template>
                <template v-else>
                  <th class="num">LY nights</th>
                  <th class="num">vs LY</th>
                </template>
                <template v-if="moreColumns">
                  <th class="num">IDR coverage</th>
                  <th v-for="n in otherPickups" :key="n" class="num">
                    Pickup ({{ n }}d)
                  </th>
                  <th class="num">New ({{ filters.pickupDays }}d)</th>
                  <th class="num">Cancelled ({{ filters.pickupDays }}d)</th>
                  <th class="num">Amended ({{ filters.pickupDays }}d)</th>
                  <th>LY quality</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in productionRows" :key="r.id">
                <td class="sticky-col whitespace-nowrap">
                  <button
                    v-if="activeDimension !== 'ratePlan' && r.id !== 'unassigned'"
                    class="row-link"
                    @click="$emit('drilldown', activeDimension, r.id)"
                  >
                    {{ rowName(r) }}</button
                  ><span v-else class="font-semibold text-slate-900">{{
                    rowName(r)
                  }}</span>
                  <span
                    v-if="r.comparisonQuality === 'estimated'"
                    class="ml-1 text-[11px] font-semibold text-amber-700"
                    title="Comparison is estimated"
                    >est.</span
                  >
                </td>
                <td class="num">{{ number(r.rooms) }}</td>
                <td class="num">{{ percent(ratio(r.rooms, totalRooms)) }}</td>
                <td class="num" :title="money(revenue(r))">
                  {{ moneyShort(revenue(r)) }}
                </td>
                <td class="num" :title="money(ratio(revenue(r), r.idrRooms))">
                  {{ moneyShort(ratio(revenue(r), r.idrRooms)) }}
                </td>
                <td class="num" :title="r.pickup[pickupKey]?.quality">
                  {{ signed(r.pickup[pickupKey]?.rooms ?? null) }}
                </td>
                <template v-if="activeDimension === 'market' && compareWithBudget">
                  <td class="num">{{ number(r.budget?.rooms ?? null) }}</td>
                  <td class="num" :title="money(r.budget?.revenue ?? null)">
                    {{ moneyShort(r.budget?.revenue ?? null) }}
                  </td>
                  <td
                    :class="['num', gapClass(difference(revenue(r), r.budget?.revenue ?? null))]"
                  >
                    {{ signed(difference(revenue(r), r.budget?.revenue ?? null)) }}
                  </td>
                </template>
                <template v-else>
                  <td class="num">{{ number(r.comparison?.rooms) }}</td>
                  <td
                    :class="['num', gapClass(difference(r.rooms, r.comparison?.rooms ?? null))]"
                  >
                    {{ signed(difference(r.rooms, r.comparison?.rooms ?? null)) }}
                  </td>
                </template>
                <template v-if="moreColumns">
                  <td class="num">{{ percent(ratio(r.idrRooms, r.rooms)) }}</td>
                  <td
                    v-for="n in otherPickups"
                    :key="n"
                    class="num"
                    :title="r.pickup[n].quality"
                  >
                    {{ signed(r.pickup[n].rooms) }}
                  </td>
                  <td class="num">{{ number(r.newRooms) }}</td>
                  <td class="num">{{ number(r.cancelledRooms) }}</td>
                  <td class="num">{{ signed(r.amendedRooms) }}</td>
                  <td>{{ r.comparisonQuality }}</td>
                </template>
              </tr>
            </tbody>
          </table>
          <template v-if="!productionRows.length" #empty>
            No production for this selection.
          </template>
        </RmsCard>

        <RmsCard
          v-if="activeDimension === 'market'"
          title="Segment room-night trend"
          description="Top five segments by room nights; the rest are combined as Other."
        >
          <template #actions>
            <div class="seg" role="group" aria-label="Trend period">
              <button
                v-for="p in ['weekly', 'monthly']"
                :key="p"
                type="button"
                class="seg-btn capitalize"
                :aria-pressed="trendPeriod === p"
                @click="trendPeriod = p"
              >
                {{ p }}
              </button>
            </div>
          </template>
          <div class="h-72 p-4">
            <Chart type="bar" :data="trendData" :options="options" />
          </div>
        </RmsCard>


        <details
          v-if="data.unavailable.length"
          class="neu-card px-4 py-3 text-xs text-slate-600"
        >
          <summary class="cursor-pointer font-semibold text-slate-900">
            Reports not available yet ({{ data.unavailable.length }})
          </summary>
          <dl class="mt-2 space-y-2">
            <div v-for="r in data.unavailable" :key="r.report">
              <dt class="font-semibold text-slate-800">{{ r.report }}</dt>
              <dd>{{ r.reason }}</dd>
            </div>
          </dl>
        </details>
      </template>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { Chart } from "vue-chartjs";
import { type ChartOptions, type ChartTypeRegistry } from "chart.js";
import { ArrowDownTrayIcon } from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import RmsCard from "./RmsCard.vue";
import RmsSkeleton from "./RmsSkeleton.vue";
import {
  ratio,
  difference,
  csvText,
  addDays,
  money,
  moneyShort,
  EMPTY,
} from "../utils/rms";
interface Metrics {
  rooms: number | null;
  idrRooms: number | null;
  revenue: number | null;
  netRevenue: number | null;
}
interface Production extends Metrics {
  id: string;
  name: string;
  pickup: Record<string, { rooms: number | null; quality: string }>;
  newRooms: number | null;
  cancelledRooms: number | null;
  amendedRooms: number | null;
  comparison: Metrics | null;
  comparisonQuality: string;
  budget: { rooms: number | null; revenue: number | null } | null;
}
interface ReportData {
  quality: string;
  production: Record<string, Production[]>;
  marketTrend: { date: string; id: string; name: string; rooms: number }[];
  behaviour: {
    dateBasis: string;
    bookings: number;
    allBookings: number;
    averageLeadTime: number | null;
    averageLengthOfStay: number | null;
    invalidLeadTime: number;
    leadTime: { label: string; bookings: number }[];
    lengthOfStay: { label: string; bookings: number }[];
    weekdays: { label: string; booked: number; arrivals: number }[];
    losses: {
      id: string;
      name: string;
      bookings: number;
      cancelled: number;
      noShows: number;
    }[];
  };
  unavailable: { report: string; reason: string }[];
}
const props = defineProps<{
  group: "behaviour" | "business";
  filters: {
    start: string;
    end: string;
    roomType: string;
    marketId: string;
    pickupDays: number;
    comparison: string;
    comparisonStart: string;
    compareWith: "yoy" | "budget";
  };
  basis: "gross" | "net";
  labels: Record<string, string>;
}>();
const compareWithBudget = computed(() => props.filters.compareWith === "budget");
defineEmits<{ drilldown: [dimension: string, id: string] }>();
const dimensions = [
  { id: "market", label: "Market" },
  { id: "ratePlan", label: "Rate plan" },
  { id: "roomType", label: "Room type" },
];
const data = ref<ReportData | null>(null),
  loading = ref(false),
  error = ref(""),
  dateBasis = ref("stay"),
  dimension = ref("market"),
  trendPeriod = ref("weekly"),
  moreColumns = ref(false);
let generation = 0,
  disposed = false;
watch(
  () => [props.filters, dateBasis.value],
  async () => {
    const id = ++generation;
    loading.value = true;
    data.value = null;
    error.value = "";
    try {
      const r = await axios.get("/api/rms/reports", {
        params: { ...props.filters, dateBasis: dateBasis.value },
        timeout: 120000,
      });
      if (id === generation && !disposed) data.value = r.data;
    } catch (e: any) {
      if (id === generation && !disposed)
        error.value =
          e?.response?.data?.message || "Could not load grouped reports";
    } finally {
      if (id === generation) loading.value = false;
    }
  },
  { immediate: true, deep: true },
);
onBeforeUnmount(() => {
  disposed = true;
  ++generation;
});
const number = (v: number | null | undefined) =>
  v == null ? EMPTY : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const available = (v: number | null) =>
  number(data.value?.quality === "unavailable" ? null : v);
const percent = (v: number | null) =>
  v == null ? EMPTY : `${(v * 100).toFixed(1)}%`;
const signed = (v: number | null) =>
  v == null ? EMPTY : `${v > 0 ? "+" : ""}${number(v)}`;
const gapClass = (v: number | null) =>
  v == null ? "" : v > 0 ? "text-emerald-700" : v < 0 ? "text-rose-700" : "";
const activeDimension = computed(() => dimension.value);
const dimensionLabel = computed(
  () => dimensions.find((d) => d.id === dimension.value)?.label || "",
);
// The headline pickup column follows the filter's pickup window when the
// report has it (1/7/30 days); otherwise 7 days.
const pickupKey = computed(() =>
  ["1", "7", "30"].includes(String(props.filters.pickupDays))
    ? String(props.filters.pickupDays)
    : "7",
);
const otherPickups = computed(() =>
  ["1", "7", "30"].filter((n) => n !== pickupKey.value),
);
const productionRows = computed(
  () => data.value?.production[activeDimension.value] || [],
);
const totalRooms = computed(() =>
  productionRows.value.some((r) => r.rooms == null)
    ? null
    : productionRows.value.reduce((s, r) => s + (r.rooms || 0), 0),
);
const revenue = (r: Metrics) =>
  props.basis === "net" ? r.netRevenue : r.revenue;
const rowName = (r: Production) =>
  activeDimension.value === "roomType" ? props.labels[r.id] || r.name : r.name;
const behaviourTiles = computed(() => {
  const b = data.value?.behaviour;
  return [
    { label: "Active reservations", value: available(b?.bookings ?? null) },
    {
      label: "All cohort reservations",
      value: available(b?.allBookings ?? null),
    },
    {
      label: "Avg lead time (days)",
      value: available(b?.averageLeadTime ?? null),
    },
    {
      label: "Avg full stay (nights)",
      value: available(b?.averageLengthOfStay ?? null),
    },
  ];
});
const distributions = computed(() => [
  {
    title: "Lead time",
    description: "Days between booking and arrival, active reservations.",
    rows: data.value?.behaviour.leadTime || [],
  },
  {
    title: "Length of stay",
    description: "Full reservation length in nights, active reservations.",
    rows: data.value?.behaviour.lengthOfStay || [],
  },
]);
const distributionChart = (rows: { label: string; bookings: number }[]) => ({
  labels: rows.map((r) => r.label),
  datasets: [
    {
      label: "Active reservations",
      data: rows.map((r) =>
        data.value?.quality === "unavailable" ? null : r.bookings,
      ),
      backgroundColor: "#0f766e",
    },
  ],
});
const options: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: { y: { beginAtZero: true } },
};
const trendData = computed(() => {
  const top = productionRows.value.slice(0, 5).map((r) => r.id),
    groups = new Map<string, Record<string, number>>();
  for (const r of data.value?.marketTrend || []) {
    const id = top.includes(r.id) ? r.id : "other";
    let key = r.date.slice(0, 7);
    if (trendPeriod.value === "weekly")
      key = addDays(
        r.date,
        -((new Date(`${r.date}T00:00:00Z`).getUTCDay() + 6) % 7),
      );
    const bucket = groups.get(key) || {};
    bucket[id] = (bucket[id] || 0) + r.rooms;
    groups.set(key, bucket);
  }
  const keys = [...groups.keys()].sort(),
    ids = [
      ...top,
      ...([...groups.values()].some((r) => "other" in r) ? ["other"] : []),
    ],
    colors = ["#0f766e", "#334155", "#6366f1", "#d97706", "#0284c7", "#94a3b8"];
  return {
    labels: keys,
    datasets: ids.map((id, i) => ({
      label: productionRows.value.find((r) => r.id === id)?.name || "Other",
      data: keys.map((k) =>
        data.value?.quality === "unavailable" ? null : groups.get(k)?.[id] || 0,
      ),
      backgroundColor: colors[i],
    })),
  };
});
function download(rows: unknown[][], name: string) {
  const url = URL.createObjectURL(
      new Blob([csvText(rows)], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = `rms-${name}-${props.filters.start}-${props.filters.end}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportProduction() {
  const budgetCols = activeDimension.value === "market" && compareWithBudget.value;
  download(
    [
      [
        "Group",
        "OTB nights",
        "IDR revenue",
        `ADR (${props.basis})`,
        "1d pickup",
        "7d pickup",
        "30d pickup",
        ...(budgetCols
          ? ["Budget nights", "Budget revenue (gross)"]
          : ["Comparison nights", "Comparison quality"]),
      ],
      ...productionRows.value.map((r) => [
        rowName(r),
        r.rooms,
        revenue(r),
        ratio(revenue(r), r.idrRooms),
        r.pickup["1"].rooms,
        r.pickup["7"].rooms,
        r.pickup["30"].rooms,
        ...(budgetCols
          ? [r.budget?.rooms ?? null, r.budget?.revenue ?? null]
          : [r.comparison?.rooms ?? null, r.comparisonQuality]),
      ]),
    ],
    activeDimension.value,
  );
}
function exportBehaviour() {
  const b = data.value?.behaviour;
  if (!b) return;
  download(
    [
      ["Report", "Bucket", "Reservations", "Date basis", "Quality"],
      ...b.leadTime.map((r) => [
        "Lead time",
        r.label,
        data.value?.quality === "unavailable" ? null : r.bookings,
        dateBasis.value,
        data.value?.quality,
      ]),
      ...b.lengthOfStay.map((r) => [
        "Length of stay",
        r.label,
        data.value?.quality === "unavailable" ? null : r.bookings,
        dateBasis.value,
        data.value?.quality,
      ]),
    ],
    "behaviour",
  );
}
</script>
