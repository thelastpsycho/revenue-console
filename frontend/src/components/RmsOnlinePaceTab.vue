<template>
  <RmsCard
    title="Online pace vs last year"
    description="Room nights and ADR for the Online market segment, compared with the same calendar date last year."
  >
    <p v-if="loading" role="status" class="px-4 py-3 text-xs text-slate-500">
      Loading pace…
    </p>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>
    <div class="h-72 p-4">
      <Chart type="bar" :data="chartData" :options="chartOptions" />
    </div>
  </RmsCard>

  <RmsCard
    title="Online on-the-books by stay date"
    description="Current room nights and revenue for the Online segment, with net pickup over the last 7 days."
    scroll
  >
    <table v-if="rows.length" class="data-table">
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
import {
  num,
  money,
  moneyShort,
  signed,
  dayLabel,
  difference,
  signClass,
  currentRooms,
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
  filters: { start: string; end: string; roomType: string; channels: string[] };
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
        params: { ...rest, channels: channels.join(",") || undefined, marketId: ONLINE_MARKET_ID, comparison: "calendar" },
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

const chartData = computed(() => ({
  labels: rows.value.map((r) => r.date),
  datasets: [
    {
      type: "bar" as const,
      label: "OTB room nights",
      data: rows.value.map((r) => currentRooms(r)),
      backgroundColor: "#334155",
      yAxisID: "rooms",
    },
    {
      type: "bar" as const,
      label: "Last year",
      data: rows.value.map((r) => r.stlyRooms),
      backgroundColor: "#cbd5e1",
      yAxisID: "rooms",
    },
  ],
}));
const chartOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    rooms: { beginAtZero: true, title: { display: true, text: "Room nights" } },
  },
};
</script>
