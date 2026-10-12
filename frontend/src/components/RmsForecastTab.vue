<template>
  <RmsCard
    title="PMS hotel forecast"
    description="Whole hotel, as reported by the PMS. Room type and market filters don't apply here."
    scroll
  >
    <table v-if="forecast?.hotel.length" class="data-table">
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
        <tr v-for="r in forecast.hotel" :key="r.date">
          <td class="whitespace-nowrap font-semibold text-slate-900">
            {{ dayLabel(r.date) }}
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
    <template v-if="!forecast?.hotel.length" #empty>
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
import { computed } from "vue";
import RmsCard from "./RmsCard.vue";
import {
  num,
  money,
  moneyShort,
  percent,
  ratio,
  dayLabel,
} from "../utils/rms";
import type { Forecast } from "../utils/rms";
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
</script>
