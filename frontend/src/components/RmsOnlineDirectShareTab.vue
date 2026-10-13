<template>
  <RmsCard
    title="Santika Online vs OTA"
    :description="`Daily room nights by channel, current on-the-books. ${quality === 'estimated' ? 'Based on partially reconstructed history.' : ''}`"
  >
    <template #actions>
      <button class="btn-flat" :disabled="!series.length" @click="exportCsv">
        <ArrowDownTrayIcon class="h-4 w-4" /> Export CSV
      </button>
    </template>
    <p v-if="loading" role="status" class="px-4 py-3 text-xs text-slate-500">
      Loading direct share…
    </p>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>
    <dl v-if="buckets.length" class="grid grid-cols-2 gap-3 p-4 lg:grid-cols-4">
      <div class="stat-tile">
        <dt>Direct (Santika Online) share</dt>
        <dd>{{ percent(directSharePct) }}</dd>
      </div>
      <div v-for="b in topBuckets" :key="b.id" class="stat-tile">
        <dt>{{ b.name }}</dt>
        <dd>{{ num(b.rooms) }}</dd>
      </div>
    </dl>
    <div class="h-72 p-4">
      <Chart type="bar" :data="chartData" :options="chartOptions" />
    </div>
    <table v-if="buckets.length" class="data-table border-t border-slate-200">
      <thead>
        <tr>
          <th>Channel</th>
          <th class="num">Room nights</th>
          <th class="num">Share</th>
          <th class="num">Revenue</th>
          <th class="num">ADR</th>
          <th class="num">Net ADR</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in buckets" :key="b.id">
          <td class="whitespace-nowrap font-semibold text-slate-900">
            {{ b.name }}
          </td>
          <td class="num">{{ num(b.rooms) }}</td>
          <td class="num">{{ percent(share(b)) }}</td>
          <td class="num" :title="money(b.revenue)">{{ moneyShort(b.revenue) }}</td>
          <td class="num" :title="money(adr(b))">{{ moneyShort(adr(b)) }}</td>
          <td class="num" :title="money(netAdr(b))">{{ moneyShort(netAdr(b)) }}</td>
        </tr>
      </tbody>
    </table>
    <template v-if="!loading && !series.length" #empty>
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
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartTypeRegistry,
} from "chart.js";
import { ArrowDownTrayIcon } from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import RmsCard from "./RmsCard.vue";
import {
  csvText,
  money,
  moneyShort,
  num,
  percent,
  ratio,
  type ChannelBucket,
  type DirectShareSeriesPoint,
} from "../utils/rms";
ChartJS.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const props = defineProps<{
  filters: { start: string; end: string; roomType: string; channels: string[] };
}>();

const BUCKET_COLORS: Record<string, string> = {
  direct: "#0f766e",
  booking_com: "#1d4ed8",
  agoda: "#be123c",
  traveloka: "#0891b2",
  expedia: "#9333ea",
  tiket_com: "#ea580c",
  trip_com: "#65a30d",
  other: "#94a3b8",
  unassigned: "#cbd5e1",
};

const buckets = ref<ChannelBucket[]>([]),
  series = ref<DirectShareSeriesPoint[]>([]),
  directSharePct = ref<number | null>(null),
  quality = ref(""),
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
      const r = await axios.get("/api/rms/online/direct-share", {
        params: { ...rest, channels: channels.join(",") || undefined },
        timeout: 120000,
      });
      if (id === generation && !disposed) {
        buckets.value = r.data.buckets;
        series.value = r.data.series;
        directSharePct.value = r.data.directSharePct;
        quality.value = r.data.quality;
      }
    } catch (e: any) {
      if (id === generation && !disposed)
        error.value = e?.response?.data?.message || "Could not load direct share";
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

const totalRooms = computed(() =>
  buckets.value.reduce((s, b) => s + b.rooms, 0),
);
const share = (b: ChannelBucket) =>
  totalRooms.value ? (b.rooms / totalRooms.value) * 100 : 0;
const adr = (b: ChannelBucket) => ratio(b.revenue, b.idrRooms);
const netAdr = (b: ChannelBucket) => ratio(b.netRevenue, b.idrRooms);
const topBuckets = computed(() =>
  buckets.value
    .filter((b) => b.id !== "direct" && b.rooms > 0)
    .sort((a, b) => b.rooms - a.rooms)
    .slice(0, 3),
);

const chartData = computed(() => ({
  labels: series.value.map((s) => s.date),
  datasets: buckets.value
    .filter((b) => b.rooms > 0 || b.id === "direct")
    .map((b) => ({
      label: b.name,
      data: series.value.map((s) => (s[b.id] as any)?.rooms ?? 0),
      backgroundColor: BUCKET_COLORS[b.id] || "#94a3b8",
      stack: "channel",
    })),
}));
const chartOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    x: { stacked: true, ticks: { maxTicksLimit: 14 } },
    y: { stacked: true, beginAtZero: true, title: { display: true, text: "Room nights" } },
  },
};

function exportCsv() {
  const out: unknown[][] = [
    ["Date", ...buckets.value.map((b) => b.name)],
  ];
  for (const s of series.value)
    out.push([s.date, ...buckets.value.map((b) => (s[b.id] as any)?.rooms ?? 0)]);
  const url = URL.createObjectURL(
      new Blob([csvText(out)], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = `rms-online-direct-share-${props.filters.start}-${props.filters.end}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
</script>
