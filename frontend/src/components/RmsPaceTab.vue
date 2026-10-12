<template>
  <div class="neu-card p-4">
    <div class="flex justify-between">
      <h2 class="font-semibold">Room nights & ADR</h2>
      <select
        v-model="chartView"
        aria-label="Chart grouping"
        class="neu-input text-xs"
      >
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
      </select>
    </div>
    <p class="my-2 text-xs text-slate-500">
      {{ basisLabel }}. IDR ADR coverage: {{ percent(idrCoverage) }} of room
      nights. Comparison history may be estimated.
    </p>
    <div class="h-72">
      <Chart type="bar" :data="chartData" :options="chartOptions" />
    </div>
    <div class="overflow-x-auto border-t border-slate-200 pt-3">
      <table class="min-w-full text-xs">
        <thead>
          <tr>
            <th class="sticky left-0 bg-white p-2 text-left">&nbsp;</th>
            <th
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="whitespace-nowrap p-2 text-right font-bold text-slate-500"
            >
              {{ b.key }}
            </th>
            <th class="whitespace-nowrap p-2 text-right font-bold">Total</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr>
            <td class="sticky left-0 bg-white p-2 font-semibold">
              Room nights
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums"
            >
              {{ num(b.rooms) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold">
              {{ num(chartTable.totals.rooms) }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 text-slate-500">
              Room nights (Last year)
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums text-slate-500"
            >
              {{ num(b.comparison) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold text-slate-500">
              {{ num(chartTable.totals.comparison) }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 text-slate-500">
              % difference
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums"
            >
              {{ pctLabel(pctDiff(b.rooms, b.comparison)) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold">
              {{
                pctLabel(
                  pctDiff(chartTable.totals.rooms, chartTable.totals.comparison),
                )
              }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 pt-3 font-semibold">
              Revenue
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 pt-3 text-right tabular-nums"
            >
              {{ money(b.revenue) }}
            </td>
            <td class="p-2 pt-3 text-right tabular-nums font-semibold">
              {{ money(chartTable.totals.revenue) }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 text-slate-500">
              Revenue (Last year)
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums text-slate-500"
            >
              {{ money(b.comparisonRevenue) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold text-slate-500">
              {{ money(chartTable.totals.comparisonRevenue) }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 text-slate-500">
              % difference
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums"
            >
              {{ pctLabel(pctDiff(b.revenue, b.comparisonRevenue)) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold">
              {{
                pctLabel(
                  pctDiff(
                    chartTable.totals.revenue,
                    chartTable.totals.comparisonRevenue,
                  ),
                )
              }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 pt-3 font-semibold">
              Average daily rate
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 pt-3 text-right tabular-nums"
            >
              {{ money(b.adr) }}
            </td>
            <td class="p-2 pt-3 text-right tabular-nums font-semibold">
              {{ money(chartTable.totals.adr) }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 text-slate-500">
              Average daily rate (Last year)
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums text-slate-500"
            >
              {{ money(b.comparisonAdr) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold text-slate-500">
              {{ money(chartTable.totals.comparisonAdr) }}
            </td>
          </tr>
          <tr>
            <td class="sticky left-0 bg-white p-2 text-slate-500">
              % difference
            </td>
            <td
              v-for="b in chartTable.buckets"
              :key="b.key"
              class="p-2 text-right tabular-nums"
            >
              {{ pctLabel(pctDiff(b.adr, b.comparisonAdr)) }}
            </td>
            <td class="p-2 text-right tabular-nums font-semibold">
              {{
                pctLabel(
                  pctDiff(chartTable.totals.adr, chartTable.totals.comparisonAdr),
                )
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="neu-card overflow-hidden">
    <h2 class="p-4 font-semibold">Pickup by stay date</h2>
    <p class="px-4 pb-3 text-xs text-slate-500">
      New − cancellations + net amendments = net pickup, in room nights.
      Amendments include date/segment moves and reinstatements.
      Pre-observation breakdowns are estimates.
    </p>
    <div class="max-h-[60vh] overflow-auto">
      <table class="min-w-full text-xs">
        <thead class="sticky top-0 bg-white">
          <tr>
            <th
              v-for="h in [
                'Date',
                'OTB',
                'Revenue',
                'New',
                'Cancelled',
                'Amendments',
                'Net pickup',
                'Comparison',
                'Gap',
                'LY / matched final',
                'Quality',
              ]"
              :key="h"
              class="whitespace-nowrap p-3 text-left"
            >
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.date" class="border-t border-slate-100">
            <td class="whitespace-nowrap p-3">
              <button class="underline" @click="$emit('openDay', r.date)">
                {{ dayLabel(r.date) }}
              </button>
            </td>
            <td class="p-3">{{ num(currentRooms(r)) }}</td>
            <td class="p-3">
              {{
                money(currentRooms(r) == null ? null : revenueFor(r, basis))
              }}
            </td>
            <td class="p-3">{{ num(r.newRooms) }}</td>
            <td class="p-3">{{ num(r.cancelledRooms) }}</td>
            <td class="p-3">{{ signed(r.amendedRooms) }}</td>
            <td class="p-3">{{ signed(r.pickupRooms) }}</td>
            <td class="p-3">{{ num(r.stlyRooms) }}</td>
            <td class="p-3">
              {{ signed(difference(currentRooms(r), r.stlyRooms)) }}
            </td>
            <td class="p-3">{{ num(r.lyFinalRooms) }}</td>
            <td class="p-3">
              Comparison: {{ r.comparisonQuality }}<br />Pickup:
              {{ r.pickupQuality }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="neu-card overflow-hidden">
    <h2 class="p-4 font-semibold">Breakdown by room and rate</h2>
    <p class="px-4 pb-3 text-xs text-slate-500">
      {{ basisLabel }}. Current on-the-books nights and revenue for the
      selected stay dates, by room type and rate plan. Rate plan is the PMS
      rate code, not a channel-specific plan name.
    </p>
    <div class="max-h-[60vh] overflow-auto">
      <table class="min-w-full text-xs">
        <thead class="sticky top-0 bg-white">
          <tr>
            <th
              v-for="h in ['Room / rate plan', 'Room nights', 'Revenue', 'ADR']"
              :key="h"
              class="whitespace-nowrap p-3 text-left"
            >
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="rt in breakdown?.roomTypes || []" :key="rt.id">
            <tr class="border-t border-slate-200 bg-slate-50 font-semibold">
              <td class="p-3">{{ label(rt.id) }}</td>
              <td class="p-3">{{ num(rt.rooms) }}</td>
              <td class="p-3">{{ money(breakdownRevenue(rt, basis)) }}</td>
              <td class="p-3">
                {{ money(ratio(breakdownRevenue(rt, basis), rt.idrRooms)) }}
              </td>
            </tr>
            <tr
              v-for="p in rt.ratePlans"
              :key="rt.id + ':' + p.id"
              class="border-t border-slate-100"
            >
              <td class="p-3 pl-8 text-slate-600">{{ p.id }}</td>
              <td class="p-3">{{ num(p.rooms) }}</td>
              <td class="p-3">{{ money(breakdownRevenue(p, basis)) }}</td>
              <td class="p-3">
                {{ money(ratio(breakdownRevenue(p, basis), p.idrRooms)) }}
              </td>
            </tr>
          </template>
        </tbody>
        <tfoot
          v-if="breakdown?.roomTypes.length"
          class="sticky bottom-0 bg-slate-100 font-semibold"
        >
          <tr>
            <td class="p-3">Total</td>
            <td class="p-3">{{ num(breakdown.total.rooms) }}</td>
            <td class="p-3">{{ money(breakdownRevenue(breakdown.total, basis)) }}</td>
            <td class="p-3">
              {{
                money(
                  ratio(breakdownRevenue(breakdown.total, basis), breakdown.total.idrRooms),
                )
              }}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
    <p v-if="!breakdown?.roomTypes.length" class="p-4 text-sm text-slate-500">
      Apply a range to load data.
    </p>
  </div>
</template>
<script setup lang="ts">
import { Chart } from "vue-chartjs";
import type { ChartOptions, ChartTypeRegistry } from "chart.js";
import {
  num,
  money,
  signed,
  percent,
  dayLabel,
  difference,
  ratio,
  pctDiff,
  pctLabel,
  currentRooms,
  revenueFor,
  breakdownRevenue,
  type PaceRow,
  type Breakdown,
} from "../utils/rms";
interface Bucket {
  key: string;
  rooms: number | null;
  comparison: number | null;
  revenue: number | null;
  comparisonRevenue: number | null;
  adr: number | null;
  comparisonAdr: number | null;
}
defineProps<{
  rows: PaceRow[];
  chartData: any;
  chartOptions: ChartOptions<keyof ChartTypeRegistry>;
  chartTable: { buckets: Bucket[]; totals: Omit<Bucket, "key"> };
  basisLabel: string;
  idrCoverage: number | null;
  breakdown: Breakdown | null;
  basis: "gross" | "net";
  label: (code: string) => string;
}>();
defineEmits<{ openDay: [date: string] }>();
const chartView = defineModel<string>("chartView", { required: true });
</script>
