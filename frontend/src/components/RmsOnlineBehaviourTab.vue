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
        <RmsSkeleton variant="table" :count="7" :columns="3" />
      </RmsCard>
    </template>
    <template v-else-if="data">
      <p v-if="data.behaviour.invalidLeadTime" class="alert-warn">
        {{ data.behaviour.invalidLeadTime }} reservations have negative lead
        time and are left out of the lead-time buckets.
      </p>
      <dl class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="t in tiles" :key="t.label" class="stat-tile">
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
            <Chart type="bar" :data="distributionChart(r.rows)" :options="chartOptions" />
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
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Chart } from "vue-chartjs";
import {
  Chart as ChartJS,
  BarController,
  BarElement,
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
import { EMPTY } from "../utils/rms";
ChartJS.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const ONLINE_MARKET_ID = "8";

interface ReportData {
  quality: string;
  behaviour: {
    bookings: number;
    allBookings: number;
    averageLeadTime: number | null;
    averageLengthOfStay: number | null;
    invalidLeadTime: number;
    leadTime: { label: string; bookings: number }[];
    lengthOfStay: { label: string; bookings: number }[];
    weekdays: { label: string; booked: number; arrivals: number }[];
    losses: { id: string; name: string; bookings: number; cancelled: number; noShows: number }[];
  };
}

const props = defineProps<{
  filters: { start: string; end: string; roomType: string; channels: string[] };
}>();

const data = ref<ReportData | null>(null),
  loading = ref(false),
  error = ref("");
let generation = 0,
  disposed = false;

watch(
  () => props.filters,
  async () => {
    const id = ++generation;
    loading.value = true;
    data.value = null;
    error.value = "";
    try {
      const { channels, ...rest } = props.filters;
      const r = await axios.get("/api/rms/reports", {
        params: { ...rest, channels: channels.join(",") || undefined, marketId: ONLINE_MARKET_ID, dateBasis: "stay" },
        timeout: 120000,
      });
      if (id === generation && !disposed) data.value = r.data;
    } catch (e: any) {
      if (id === generation && !disposed)
        error.value = e?.response?.data?.message || "Could not load booking behaviour";
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

const loss = computed(() => data.value?.behaviour.losses?.[0] || null);
const tiles = computed(() => {
  const b = data.value?.behaviour,
    l = loss.value;
  return [
    { label: "Active reservations", value: available(b?.bookings ?? null) },
    { label: "All cohort reservations", value: available(b?.allBookings ?? null) },
    { label: "Avg lead time (days)", value: available(b?.averageLeadTime ?? null) },
    { label: "Avg length of stay (nights)", value: available(b?.averageLengthOfStay ?? null) },
    { label: "Cancelled", value: available(l?.cancelled ?? null) },
    {
      label: "Cancel rate",
      value: l ? percent(l.cancelled / (l.bookings || 1)) : EMPTY,
    },
    { label: "No-shows", value: available(l?.noShows ?? null) },
  ];
});
const distributions = computed(() => [
  {
    title: "Lead time",
    description: "Days between booking and arrival, active online reservations.",
    rows: data.value?.behaviour.leadTime || [],
  },
  {
    title: "Length of stay",
    description: "Full reservation length in nights, active online reservations.",
    rows: data.value?.behaviour.lengthOfStay || [],
  },
]);
const distributionChart = (rows: { label: string; bookings: number }[]) => ({
  labels: rows.map((r) => r.label),
  datasets: [
    {
      label: "Active reservations",
      data: rows.map((r) => (data.value?.quality === "unavailable" ? null : r.bookings)),
      backgroundColor: "#0f766e",
    },
  ],
});
const chartOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: { y: { beginAtZero: true } },
};
</script>
