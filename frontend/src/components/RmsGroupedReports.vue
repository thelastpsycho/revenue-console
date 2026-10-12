<template>
  <div class="space-y-4">
    <p v-if="loading" role="status" class="text-sm text-slate-500">
      Loading grouped booking reports…
    </p>
    <p
      v-if="error"
      role="alert"
      class="rounded bg-rose-50 p-3 text-sm text-rose-800"
    >
      {{ error }}
    </p>
    <template v-if="data">
      <p class="text-xs text-slate-500">
        Booking history quality: {{ data.quality }}. Revenue covers IDR-priced
        room nights only; ADR divides revenue by IDR room nights. Reports
        describe booking positions.
      </p>
      <template v-if="group === 'behaviour'">
        <div class="neu-card flex flex-wrap items-center gap-3 p-4 text-sm">
          <label
            >Date selection applies to
            <select v-model="dateBasis" class="neu-input ml-2">
              <option value="stay">Stay dates (overlapping stays)</option>
              <option value="booking">Booking creation dates</option>
            </select></label
          ><button class="btn-flat px-3 py-2" @click="exportBehaviour">
            Export behaviour
          </button>
        </div>
        <p class="text-xs text-slate-500">
          Each reservation counts once. Lead time and stay length use active
          bookings, excluding cancelled and no-show reservations. Stay length is
          the full reservation length, even if only some nights fall in the
          selected range.
        </p>
        <p v-if="data.behaviour.invalidLeadTime" class="text-xs text-amber-800">
          {{ data.behaviour.invalidLeadTime }} reservations have negative lead
          time and are excluded from lead-time buckets.
        </p>
        <dl class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div v-for="t in behaviourTiles" :key="t.label" class="neu-card p-4">
            <dt class="text-xs text-slate-500">{{ t.label }}</dt>
            <dd class="text-lg font-semibold">{{ t.value }}</dd>
          </div>
        </dl>
        <div class="grid gap-4 lg:grid-cols-2">
          <div v-for="r in distributions" :key="r.title" class="neu-card p-4">
            <h2 class="font-semibold">{{ r.title }}</h2>
            <div class="mt-3 h-60">
              <Chart
                type="bar"
                :data="distributionChart(r.rows)"
                :options="options"
              />
            </div>
            <table class="mt-3 w-full text-xs">
              <tbody>
                <tr v-for="b in r.rows" :key="b.label" class="border-t">
                  <td class="p-2">{{ b.label }}</td>
                  <td class="p-2 text-right">{{ available(b.bookings) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">Booking and arrival weekday</h2>
          <div class="overflow-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr>
                  <th class="p-3 text-left">Weekday</th>
                  <th class="p-3">Booked</th>
                  <th class="p-3">Arrivals</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in data.behaviour.weekdays"
                  :key="r.label"
                  class="border-t"
                >
                  <td class="p-3">{{ r.label }}</td>
                  <td class="p-3 text-center">{{ available(r.booked) }}</td>
                  <td class="p-3 text-center">{{ available(r.arrivals) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">
            Cancellation & no-show patterns by segment
          </h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            Denominator: all cached reservations in the selected cohort. These
            are current statuses, not a count of cancellation events. Future
            no-show rates are not treated as final outcomes.
          </p>
          <div class="overflow-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr>
                  <th
                    v-for="h in [
                      'Segment',
                      'Bookings',
                      'Cancelled',
                      'Cancellation %',
                      'No-shows',
                    ]"
                    :key="h"
                    class="p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in data.behaviour.losses"
                  :key="r.id"
                  class="border-t"
                >
                  <td class="p-3">{{ r.name }}</td>
                  <td class="p-3">{{ available(r.bookings) }}</td>
                  <td class="p-3">{{ available(r.cancelled) }}</td>
                  <td class="p-3">
                    {{
                      data.quality === "unavailable"
                        ? "Unavailable"
                        : percent(ratio(r.cancelled, r.bookings))
                    }}
                  </td>
                  <td class="p-3">{{ available(r.noShows) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <template v-if="group === 'business' || group === 'rooms'">
        <div
          class="neu-card flex flex-wrap items-center justify-between gap-3 p-4"
        >
          <label v-if="group === 'business'" class="text-sm"
            >Report
            <select v-model="dimension" class="neu-input ml-2">
              <option value="market">Market segment</option>
              <option value="ratePlan">Rate plan</option>
            </select></label
          >
          <h2 v-else class="font-semibold">Room-type production</h2>
          <button class="btn-flat px-3 py-2 text-xs" @click="exportProduction">
            Export production
          </button>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">
            {{
              group === "rooms"
                ? "Room type"
                : dimension === "market"
                  ? "Market segment"
                  : "Rate plan"
            }}
            comparison
          </h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            Pickup uses stay-night positions. New − cancellations + net
            amendments = selected-window pickup. Click a segment or room type to
            open its pace and booking curves. Missing dimensions remain
            Unassigned.
          </p>
          <div class="max-h-[60vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 bg-white">
                <tr>
                  <th
                    v-for="h in headers"
                    :key="h"
                    class="whitespace-nowrap p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in productionRows" :key="r.id" class="border-t">
                  <td class="whitespace-nowrap p-3">
                    <button
                      v-if="
                        activeDimension !== 'ratePlan' && r.id !== 'unassigned'
                      "
                      class="underline font-semibold"
                      @click="$emit('drilldown', activeDimension, r.id)"
                    >
                      {{ rowName(r) }}</button
                    ><span v-else>{{ rowName(r) }}</span>
                  </td>
                  <td class="p-3">{{ number(r.rooms) }}</td>
                  <td class="p-3">{{ percent(ratio(r.rooms, totalRooms)) }}</td>
                  <td class="p-3">{{ money(revenue(r)) }}</td>
                  <td class="p-3">
                    {{ money(ratio(revenue(r), r.idrRooms)) }}
                  </td>
                  <td class="p-3">{{ percent(ratio(r.idrRooms, r.rooms)) }}</td>
                  <td
                    v-for="n in [1, 7, 30]"
                    :key="n"
                    class="p-3"
                    :title="r.pickup[String(n)].quality"
                  >
                    {{ signed(r.pickup[String(n)].rooms) }}
                  </td>
                  <td class="p-3">{{ number(r.newRooms) }}</td>
                  <td class="p-3">{{ number(r.cancelledRooms) }}</td>
                  <td class="p-3">{{ signed(r.amendedRooms) }}</td>
                  <td class="p-3">{{ number(r.comparison?.rooms) }}</td>
                  <td class="p-3">
                    {{
                      signed(difference(r.rooms, r.comparison?.rooms ?? null))
                    }}
                  </td>
                  <td class="p-3">{{ r.comparisonQuality }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-if="activeDimension === 'market'" class="neu-card p-4">
          <div class="flex flex-wrap justify-between gap-2">
            <h2 class="font-semibold">Segment room-night trend</h2>
            <select
              v-model="trendPeriod"
              class="neu-input text-xs"
              aria-label="Segment trend period"
            >
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
          <p class="my-2 text-xs text-slate-500">
            Top five segments by selected-window room nights; remaining segments
            are combined as Other.
          </p>
          <div class="h-72">
            <Chart type="bar" :data="trendData" :options="options" />
          </div>
        </div>
        <div v-if="group === 'rooms'" class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">
            Room-type availability & sellout pressure
          </h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            PMS expected occupied / physical room count. Physical availability
            is separate from channel allotment. PMS reports cover up to the
            first 90 selected days.
          </p>
          <div class="max-h-[50vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 bg-white">
                <tr>
                  <th
                    v-for="h in [
                      'Date',
                      'Room type',
                      'Expected occupied',
                      'Capacity',
                      'Occupancy',
                      'Physical availability',
                    ]"
                    :key="h"
                    class="p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in inventoryRows"
                  :key="r.date + r.typeId"
                  :class="[
                    'border-t',
                    r.roomCount && r.rooms / r.roomCount >= 0.9
                      ? 'bg-amber-50'
                      : '',
                  ]"
                >
                  <td class="p-3">{{ r.date }}</td>
                  <td class="p-3">{{ labels[r.typeId] || r.typeId }}</td>
                  <td class="p-3">{{ number(r.rooms) }}</td>
                  <td class="p-3">{{ number(r.roomCount) }}</td>
                  <td class="p-3">
                    {{ percent(ratio(r.rooms, r.roomCount)) }}
                  </td>
                  <td class="p-3">
                    {{ number(availability[r.date]?.[r.typeId]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!inventoryRows.length" class="p-4 text-sm text-slate-500">
            Physical inventory data is loading or unavailable for this
            selection.
          </p>
        </div>
      </template>
      <div
        v-if="group === 'business' || group === 'performance'"
        class="neu-card p-4"
      >
        <h2 class="font-semibold">Reports needing additional data</h2>
        <p v-for="r in unavailableReports" :key="r.report" class="mt-3 text-xs">
          <strong>{{ r.report }}</strong
          ><br />{{ r.reason }}
        </p>
      </div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { Chart } from "vue-chartjs";
import { type ChartOptions, type ChartTypeRegistry } from "chart.js";
import axios from "../plugins/axios";
import { ratio, difference, csvText, addDays } from "../utils/rms";
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
  group: string;
  filters: {
    start: string;
    end: string;
    roomType: string;
    marketId: string;
    pickupDays: number;
    comparison: string;
    comparisonStart: string;
  };
  basis: "gross" | "net";
  labels: Record<string, string>;
  forecast?: {
    roomTypes: {
      date: string;
      typeId: string;
      rooms: number;
      roomCount: number;
    }[];
    availability: { date: string; values: Record<string, number> }[];
  } | null;
}>();
defineEmits<{ drilldown: [dimension: string, id: string] }>();
const data = ref<ReportData | null>(null),
  loading = ref(false),
  error = ref(""),
  dateBasis = ref("stay"),
  dimension = ref("market"),
  trendPeriod = ref("weekly");
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
  v == null
    ? "Unavailable"
    : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const available = (v: number | null) =>
  number(data.value?.quality === "unavailable" ? null : v);
const money = (v: number | null) =>
  v == null ? "Unavailable" : `IDR ${Math.round(v).toLocaleString("en-US")}`;
const percent = (v: number | null) =>
  v == null ? "Unavailable" : `${(v * 100).toFixed(1)}%`;
const signed = (v: number | null) =>
  v == null ? "Unavailable" : `${v > 0 ? "+" : ""}${number(v)}`;
const activeDimension = computed(() =>
  props.group === "rooms" ? "roomType" : dimension.value,
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
const headers = computed(() => [
  "Group",
  "OTB nights",
  "Share",
  "IDR revenue",
  "IDR ADR",
  "IDR coverage",
  "1d pickup",
  "7d pickup",
  "30d pickup",
  `New (${props.filters.pickupDays}d)`,
  `Cancelled (${props.filters.pickupDays}d)`,
  `Amendments (${props.filters.pickupDays}d)`,
  "Comparison nights",
  "Gap",
  "Comparison quality",
]);
const behaviourTiles = computed(() => {
  const b = data.value?.behaviour;
  return [
    { label: "Active reservations", value: available(b?.bookings ?? null) },
    {
      label: "All cohort reservations",
      value: available(b?.allBookings ?? null),
    },
    {
      label: "Average lead time (days)",
      value: available(b?.averageLeadTime ?? null),
    },
    {
      label: "Average full stay (nights)",
      value: available(b?.averageLengthOfStay ?? null),
    },
  ];
});
const distributions = computed(() => [
  { title: "Lead time", rows: data.value?.behaviour.leadTime || [] },
  { title: "Length of stay", rows: data.value?.behaviour.lengthOfStay || [] },
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
const inventoryRows = computed(() =>
  (props.forecast?.roomTypes || []).filter(
    (r) => !props.filters.roomType || r.typeId === props.filters.roomType,
  ),
);
const availability = computed(() =>
  Object.fromEntries(
    (props.forecast?.availability || []).map((r) => [r.date, r.values]),
  ),
);
const unavailableReports = computed(() =>
  (data.value?.unavailable || []).filter((r) =>
    props.group === "performance"
      ? r.report.startsWith("Audited")
      : !r.report.startsWith("Audited"),
  ),
);
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
        "Comparison nights",
        "Comparison quality",
      ],
      ...productionRows.value.map((r) => [
        rowName(r),
        r.rooms,
        revenue(r),
        ratio(revenue(r), r.idrRooms),
        r.pickup["1"].rooms,
        r.pickup["7"].rooms,
        r.pickup["30"].rooms,
        r.comparison?.rooms,
        r.comparisonQuality,
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
