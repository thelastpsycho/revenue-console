<template>
  <RmsCard
    title="Pace vs last year"
    :description="`Room nights and ADR · ${basisLabel}. IDR ADR coverage ${percent(idrCoverage)} of room nights.`"
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
    <div class="h-72 p-4">
      <Chart type="bar" :data="chartData" :options="chartOptions" />
    </div>
    <div
      v-if="chartTable.buckets.length"
      class="overflow-x-auto border-t border-slate-200"
    >
      <table class="data-table">
        <thead>
          <tr>
            <th class="sticky-col">&nbsp;</th>
            <th v-for="b in chartTable.buckets" :key="b.key" class="num">
              {{ b.key }}
            </th>
            <th class="num text-slate-900">Total</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in metrics" :key="m.label">
            <td class="sticky-col whitespace-nowrap font-semibold text-slate-900">
              {{ m.label }}
            </td>
            <td
              v-for="b in [...chartTable.buckets, totalBucket]"
              :key="b.key"
              :class="['num whitespace-nowrap', b.key === 'Total' && 'font-semibold text-slate-900']"
              :title="m.money ? `${money(m.cur(b))} · LY ${money(m.ly(b))}` : undefined"
            >
              {{ m.fmt(m.cur(b)) }}
              <span v-if="!compareWithBudget" class="sub">
                LY {{ m.fmt(m.ly(b)) }} ·
                <span :class="signClass(pctDiff(m.cur(b), m.ly(b)))">{{
                  pctLabel(pctDiff(m.cur(b), m.ly(b)))
                }}</span>
              </span>
              <span v-else-if="m.budget(b) != null" class="sub">
                Budget {{ m.fmt(m.budget(b)) }} ·
                <span :class="signClass(pctDiff(m.cur(b), m.budget(b)))">{{
                  pctLabel(pctDiff(m.cur(b), m.budget(b)))
                }}</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </RmsCard>

  <RmsCard
    title="Pickup by stay date"
    :description="`Net pickup over the last ${pickupDays} days = new − cancelled + amendments, in room nights. Select a date for its booking curve.`"
    scroll
  >
    <template #actions>
      <label class="flex items-center gap-1.5 text-xs text-slate-600">
        <input v-model="behindOnly" type="checkbox" class="accent-slate-900" />
        Behind LY only
      </label>
    </template>
    <table v-if="pickupRows.length" class="data-table">
      <thead>
        <tr>
          <th>Stay date</th>
          <th class="num">OTB</th>
          <th class="num" title="On the books minus the comparison date's position at the same lead time">
            vs LY
          </th>
          <th class="num">Net pickup</th>
          <th class="num">Revenue</th>
          <th class="num" title="Final room nights on the last-year / matched date">
            LY final
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in pickupRows" :key="r.date">
          <td class="whitespace-nowrap">
            <button class="row-link" @click="$emit('openDay', r.date)">
              {{ dayLabel(r.date) }}
            </button>
            <span
              v-if="estimated(r)"
              class="ml-1 text-[11px] font-semibold text-amber-700"
              :title="`Comparison: ${r.comparisonQuality} · Pickup: ${r.pickupQuality}`"
              >est.</span
            >
          </td>
          <td class="num">{{ num(currentRooms(r)) }}</td>
          <td :class="['num', signClass(gap(r))]">{{ signed(gap(r)) }}</td>
          <td class="num whitespace-nowrap">
            {{ signed(r.pickupRooms) }}
            <span class="sub">{{ pickupParts(r) }}</span>
          </td>
          <td class="num" :title="money(rowRevenue(r))">
            {{ moneyShort(rowRevenue(r)) }}
          </td>
          <td class="num">{{ num(r.lyFinalRooms) }}</td>
        </tr>
      </tbody>
    </table>
    <template v-if="!pickupRows.length" #empty>
      {{
        rows.length
          ? "No dates are behind last year."
          : "Apply a range to load data."
      }}
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import { Chart } from "vue-chartjs";
import type { ChartOptions, ChartTypeRegistry } from "chart.js";
import RmsCard from "./RmsCard.vue";
import {
  num,
  money,
  moneyShort,
  signed,
  percent,
  dayLabel,
  difference,
  pctDiff,
  pctLabel,
  signClass,
  currentRooms,
  revenueFor,
  type PaceRow,
} from "../utils/rms";
interface Bucket {
  key: string;
  rooms: number | null;
  comparison: number | null;
  revenue: number | null;
  comparisonRevenue: number | null;
  adr: number | null;
  comparisonAdr: number | null;
  budgetRooms: number | null;
  budgetRevenue: number | null;
  budgetAdr: number | null;
}
const props = defineProps<{
  rows: PaceRow[];
  chartData: any;
  chartOptions: ChartOptions<keyof ChartTypeRegistry>;
  chartTable: { buckets: Bucket[]; totals: Omit<Bucket, "key"> };
  basisLabel: string;
  idrCoverage: number | null;
  basis: "gross" | "net";
  pickupDays: number;
  compareWithBudget: boolean;
}>();
defineEmits<{ openDay: [date: string] }>();
const chartView = defineModel<string>("chartView", { required: true });
const behindOnly = ref(false);

const views = [
  { id: "daily", label: "Daily" },
  { id: "weekly", label: "Weekly" },
  { id: "monthly", label: "Monthly" },
];
// Each summary row shows the current value with LY and budget (gross) % change underneath.
const metrics = [
  { label: "Room nights", cur: (b: Bucket) => b.rooms, ly: (b: Bucket) => b.comparison, budget: (b: Bucket) => b.budgetRooms, fmt: num, money: false },
  { label: "Revenue", cur: (b: Bucket) => b.revenue, ly: (b: Bucket) => b.comparisonRevenue, budget: (b: Bucket) => b.budgetRevenue, fmt: moneyShort, money: true },
  { label: "ADR", cur: (b: Bucket) => b.adr, ly: (b: Bucket) => b.comparisonAdr, budget: (b: Bucket) => b.budgetAdr, fmt: moneyShort, money: true },
];
const totalBucket = computed<Bucket>(() => ({
  key: "Total",
  ...props.chartTable.totals,
}));

const gap = (r: PaceRow) => difference(currentRooms(r), r.stlyRooms);
const rowRevenue = (r: PaceRow) =>
  currentRooms(r) == null ? null : revenueFor(r, props.basis);
const estimated = (r: PaceRow) =>
  [r.comparisonQuality, r.pickupQuality].includes("estimated");
function pickupParts(r: PaceRow) {
  const parts = [`${num(r.newRooms)} new`, `${num(r.cancelledRooms)} cxl`];
  if (r.amendedRooms) parts.push(`${signed(r.amendedRooms)} amd`);
  return parts.join(" · ");
}
const pickupRows = computed(() =>
  behindOnly.value
    ? props.rows.filter((r) => (gap(r) ?? 0) < 0)
    : props.rows,
);
</script>
