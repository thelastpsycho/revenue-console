<template>
  <RmsCard
    title="Source mix"
    description="Online segment room nights and revenue by booking company, current on-the-books."
  >
    <template #actions>
      <button class="btn-flat" :disabled="!rows.length" @click="exportCsv">
        <ArrowDownTrayIcon class="h-4 w-4" /> Export CSV
      </button>
    </template>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>
    <RmsSkeleton v-if="loading" variant="table" :count="6" :columns="5" />
    <table v-else-if="rows.length" class="data-table">
      <thead>
        <tr>
          <th>Company</th>
          <th class="num">Room nights</th>
          <th class="num">Share</th>
          <th class="num">Revenue</th>
          <th class="num">ADR</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td class="whitespace-nowrap font-semibold text-slate-900">
            {{ r.name }}
          </td>
          <td class="num whitespace-nowrap">
            {{ num(r.rooms) }}
            <span
              class="ml-2 inline-block h-1.5 w-16 rounded-full bg-slate-100 align-middle"
            >
              <span
                class="block h-1.5 rounded-full bg-slate-700"
                :style="{ width: `${share(r)}%` }"
              />
            </span>
          </td>
          <td class="num">{{ percent(share(r)) }}</td>
          <td class="num" :title="money(r.revenue)">{{ moneyShort(r.revenue) }}</td>
          <td class="num">{{ moneyShort(ratio(r.revenue, r.idrRooms)) }}</td>
        </tr>
      </tbody>
      <tfoot>
        <tr class="font-semibold text-slate-900">
          <td>Total</td>
          <td class="num">{{ num(total?.rooms ?? null) }}</td>
          <td class="num">100%</td>
          <td class="num">{{ moneyShort(total?.revenue ?? null) }}</td>
          <td class="num">{{ moneyShort(ratio(total?.revenue ?? null, total?.idrRooms ?? null)) }}</td>
        </tr>
      </tfoot>
    </table>
    <template v-if="!loading && !rows.length" #empty>
      No online bookings cover this range.
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { ArrowDownTrayIcon } from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import RmsCard from "./RmsCard.vue";
import RmsSkeleton from "./RmsSkeleton.vue";
import {
  csvText,
  money,
  moneyShort,
  num,
  percent,
  ratio,
  type CompanyRow,
  type BreakdownMetrics,
} from "../utils/rms";

const props = defineProps<{
  filters: { start: string; end: string; roomType: string; channels: string[] };
}>();

const rows = ref<CompanyRow[]>([]),
  total = ref<BreakdownMetrics | null>(null),
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
      const r = await axios.get("/api/rms/online/source", {
        params: { ...rest, channels: channels.join(",") || undefined },
        timeout: 120000,
      });
      if (id === generation && !disposed) {
        rows.value = r.data.companies;
        total.value = r.data.total;
      }
    } catch (e: any) {
      if (id === generation && !disposed)
        error.value = e?.response?.data?.message || "Could not load source mix";
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

const share = (r: CompanyRow) =>
  total.value?.rooms ? (r.rooms / total.value.rooms) * 100 : 0;

function exportCsv() {
  const out: unknown[][] = [
    ["Company", "Room nights", "Share %", "Revenue", "ADR"],
  ];
  for (const r of rows.value)
    out.push([r.name, r.rooms, share(r).toFixed(1), r.revenue, ratio(r.revenue, r.idrRooms)]);
  const url = URL.createObjectURL(
      new Blob([csvText(out)], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = `rms-online-source-${props.filters.start}-${props.filters.end}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
</script>
