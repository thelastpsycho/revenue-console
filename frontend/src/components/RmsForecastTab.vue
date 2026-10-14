<template>
  <RmsCard
    title="PMS hotel forecast"
    description="Whole hotel, as reported by the PMS. Room type and market filters don't apply here."
    scroll
  >
    <template #actions>
      <div class="seg" role="group" aria-label="Forecast grouping">
        <button
          v-for="v in views"
          :key="v.id"
          type="button"
          class="seg-btn"
          :aria-pressed="hotelView === v.id"
          @click="hotelView = v.id"
        >
          {{ v.label }}
        </button>
      </div>
    </template>
    <table v-if="hotelBuckets.length" class="data-table">
      <thead>
        <tr>
          <th>Date</th>
          <th class="num">Occupancy</th>
          <th class="num">Rooms used / capacity</th>
          <th class="num">PMS revenue</th>
          <th class="num">PMS ADR</th>
          <th class="num">Comp / house use</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in hotelBuckets" :key="r.date">
          <td class="whitespace-nowrap font-semibold text-slate-900">
            {{ rowLabel(r) }}
          </td>
          <td class="num">{{ percent(r.occupancy) }}</td>
          <td class="num">{{ num(r.roomsSold) }} / {{ num(r.roomCount) }}</td>
          <td class="num" :title="money(r.revenue)">
            {{ moneyShort(r.revenue) }}
          </td>
          <td class="num" :title="money(r.adr)">{{ moneyShort(r.adr) }}</td>
          <td class="num">
            {{ num(r.complimentary) }} / {{ num(r.houseUse) }}
          </td>
        </tr>
      </tbody>
    </table>
    <template v-if="!hotelBuckets.length" #empty>
      {{
        forecastBusy
          ? "Hotel totals are loading…"
          : "No hotel forecast available."
      }}
    </template>
  </RmsCard>

  <RmsCard
    title="Market segments"
    description="PMS forecast for the whole window, largest segment first."
  >
    <div class="overflow-x-auto">
      <table v-if="segmentTotals.length" class="data-table">
        <thead>
          <tr>
            <th>Segment</th>
            <th class="num">Room nights</th>
            <th class="num">Share</th>
            <th class="num">PMS revenue</th>
            <th class="num">Revenue / night</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in segmentTotals" :key="s.market">
            <td class="font-semibold text-slate-900">{{ s.market }}</td>
            <td class="num">{{ num(s.rooms) }}</td>
            <td class="num">
              {{ percent(shareOf(s.rooms)) }}
            </td>
            <td class="num" :title="money(s.revenue)">
              {{ moneyShort(s.revenue) }}
            </td>
            <td class="num" :title="money(ratio(s.revenue, s.rooms))">
              {{ moneyShort(ratio(s.revenue, s.rooms)) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <template v-if="!segmentTotals.length" #empty>
      {{ forecastBusy ? "Segments are loading…" : "No segment forecast available." }}
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import RmsCard from "./RmsCard.vue";
import {
  num,
  money,
  moneyShort,
  percent,
  ratio,
  sumKnown,
  addDays,
  dayLabel,
  shortDayYear,
} from "../utils/rms";
import type { Forecast, Hotel } from "../utils/rms";
const props = defineProps<{
  forecast: Forecast | null;
  forecastBusy: boolean;
  segmentTotals: { market: string; rooms: number; revenue: number }[];
}>();
const totalRooms = computed(() =>
  props.segmentTotals.reduce((s, r) => s + r.rooms, 0),
);
const shareOf = (rooms: number) => {
  const r = ratio(rooms, totalRooms.value);
  return r == null ? null : r * 100;
};

const views: { id: "daily" | "weekly" | "monthly"; label: string }[] = [
  { id: "daily", label: "Daily" },
  { id: "weekly", label: "Weekly" },
  { id: "monthly", label: "Monthly" },
];
const hotelView = ref<"daily" | "weekly" | "monthly">("daily");
// Week buckets key off the Monday of each ISO week; month buckets off YYYY-MM.
const hotelBuckets = computed<Hotel[]>(() => {
  const rows = props.forecast?.hotel ?? [];
  if (hotelView.value === "daily") return rows;
  const m = new Map<string, Hotel[]>();
  for (const r of rows) {
    const key =
      hotelView.value === "monthly"
        ? r.date.slice(0, 7)
        : addDays(r.date, -((new Date(`${r.date}T00:00:00Z`).getUTCDay() + 6) % 7));
    m.set(key, [...(m.get(key) || []), r]);
  }
  return [...m].map(([key, rs]) => {
    const roomsSold = sumKnown(rs.map((r) => r.roomsSold)),
      roomCount = sumKnown(rs.map((r) => r.roomCount)),
      revenue = sumKnown(rs.map((r) => r.revenue)),
      occ = ratio(roomsSold, roomCount);
    return {
      date: key,
      roomsSold,
      roomCount,
      occupancy: occ == null ? null : occ * 100,
      revenue,
      adr: ratio(revenue, roomsSold),
      complimentary: sumKnown(rs.map((r) => r.complimentary)),
      houseUse: sumKnown(rs.map((r) => r.houseUse)),
    };
  });
});
function rowLabel(r: Hotel) {
  if (hotelView.value === "daily") return dayLabel(r.date);
  if (hotelView.value === "monthly")
    return new Date(`${r.date}-01T00:00:00Z`).toLocaleDateString("en-GB", {
      timeZone: "UTC",
      month: "long",
      year: "numeric",
    });
  return `Week of ${shortDayYear(r.date)}`;
}
</script>
