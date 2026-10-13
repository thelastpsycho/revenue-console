<template>
  <RmsCard
    title="Online pace vs last year"
    description="Room nights and ADR for the Online market segment, compared with last year per the Compare with filter above."
  >
    <template #actions>
      <div class="seg" role="group" aria-label="Chart grouping">
        <button
          v-for="v in views"
          :key="v.id"
          type="button"
          class="seg-btn"
          :aria-pressed="chartView === v.id"
          @click="chartView = v.id"
        >
          {{ v.label }}
        </button>
      </div>
    </template>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>
    <div class="h-72 p-4">
      <RmsSkeleton v-if="loading" variant="chart" />
      <Chart v-else type="bar" :data="chartData" :options="chartOptions" />
    </div>
  </RmsCard>

  <RmsCard
    title="Online on-the-books by stay date"
    description="Current room nights and revenue for the Online segment, with net pickup over the last 7 days."
    scroll
  >
    <RmsSkeleton v-if="loading" variant="table" :count="6" :columns="5" />
    <table v-else-if="rows.length" class="data-table">
      <thead>
        <tr>
          <th>Stay date</th>
          <th class="num">OTB</th>
          <th class="num">vs LY</th>
          <th class="num">Net pickup (7d)</th>
          <th class="num">Revenue</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.date">
          <td class="whitespace-nowrap">
            {{ dayLabel(r.date) }}
            <span
              v-if="estimated(r)"
              class="ml-1 text-[11px] font-semibold text-amber-700"
              >est.</span
            >
          </td>
          <td class="num">{{ num(currentRooms(r)) }}</td>
          <td :class="['num', signClass(gap(r))]">{{ signed(gap(r)) }}</td>
          <td class="num">{{ signed(r.pickupRooms) }}</td>
          <td class="num" :title="money(rowRevenue(r))">
            {{ moneyShort(rowRevenue(r)) }}
          </td>
        </tr>
      </tbody>
    </table>
    <template v-if="!loading && !rows.length" #empty>
      No online bookings cover this range.
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Chart } from "vue-chartjs";
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
import RmsCard from "./RmsCard.vue";
import RmsSkeleton from "./RmsSkeleton.vue";
import {
  num,
  money,
  moneyShort,
  signed,
  dayLabel,
  difference,
  signClass,
  currentRooms,
  addDays,
  sumKnown,
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

const ONLINE_MARKET_ID = "8";

const props = defineProps<{
  filters: {
    start: string;
    end: string;
    roomType: string;
    channels: string[];
    comparison: string;
    comparisonStart: string;
  };
}>();

const rows = ref<PaceRow[]>([]),
  loading = ref(false),
  error = ref("");
let generation = 0,
  disposed = false;

watch(
  () => props.filters,
  async () => {
    const id = ++generation;
    loading.value = true;
    error.value = "";
    try {
      const { channels, ...rest } = props.filters;
      const r = await axios.get("/api/rms/pace", {
        params: { ...rest, channels: channels.join(",") || undefined, marketId: ONLINE_MARKET_ID },
        timeout: 120000,
      });
      if (id === generation && !disposed) rows.value = r.data.rows;
    } catch (e: any) {
      if (id === generation && !disposed)
        error.value = e?.response?.data?.message || "Could not load online pace";
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

const gap = (r: PaceRow) => difference(currentRooms(r), r.stlyRooms);
const rowRevenue = (r: PaceRow) =>
  currentRooms(r) == null ? null : r.revenue;
const estimated = (r: PaceRow) =>
  [r.comparisonQuality, r.pickupQuality].includes("estimated");

const chartView = ref<string>("monthly");
const views = [
  { id: "daily", label: "Daily" },
  { id: "weekly", label: "Weekly" },
  { id: "monthly", label: "Monthly" },
];
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
    const revenue = sumKnown(rs.map((r) => (currentRooms(r) == null ? null : r.revenue))),
      idrRooms = rs.reduce((s, r) => s + r.idrRooms, 0),
      stlyRevenue = sumKnown(rs.map((r) => r.stlyRevenue)),
      stlyIdrRooms = sumKnown(rs.map((r) => r.stlyIdrRooms));
    return {
      key,
      rooms: sumKnown(rs.map(currentRooms)),
      stlyRooms: sumKnown(rs.map((r) => r.stlyRooms)),
      adr: ratio(revenue, idrRooms),
      stlyAdr: ratio(stlyRevenue, stlyIdrRooms),
    };
  });
});
const chartData = computed(() => ({
  labels: buckets.value.map((b) => b.key),
  datasets: [
    {
      type: "bar" as const,
      label: "OTB room nights",
      data: buckets.value.map((b) => b.rooms),
      backgroundColor: "#334155",
      yAxisID: "rooms",
    },
    {
      type: "bar" as const,
      label: "Last year",
      data: buckets.value.map((b) => b.stlyRooms),
      backgroundColor: "#cbd5e1",
      yAxisID: "rooms",
    },
    {
      type: "line" as const,
      label: "IDR ADR",
      data: buckets.value.map((b) => b.adr),
      borderColor: "#0f766e",
      yAxisID: "adr",
    },
    {
      type: "line" as const,
      label: "Last year ADR",
      data: buckets.value.map((b) => b.stlyAdr),
      borderColor: "#64748b",
      borderDash: [4, 4],
      yAxisID: "adr",
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
</script>
