<template>
  <RmsMonthlyTargetsTable :months="months" :basis-label="basisLabel" />
  <div class="neu-card overflow-hidden">
    <h2 class="p-4 font-semibold">PMS hotel forecast — whole hotel</h2>
    <p class="px-4 pb-3 text-xs text-slate-500">
      RoomUsed and revenue are reported by PMS. Room-type/market filters apply
      to pace; this table remains hotel-wide.
    </p>
    <div class="max-h-[60vh] overflow-auto">
      <table class="min-w-full text-xs">
        <thead class="sticky top-0 bg-white">
          <tr>
            <th
              v-for="h in [
                'Date',
                'Occupancy',
                'RoomUsed / capacity',
                'PMS revenue',
                'PMS ADR',
                'Comp / house use',
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
            v-for="r in forecast?.hotel || []"
            :key="r.date"
            class="border-t border-slate-100"
          >
            <td class="p-3">{{ dayLabel(r.date) }}</td>
            <td class="p-3">{{ percent(r.occupancy) }}</td>
            <td class="p-3">{{ num(r.roomsSold) }} / {{ num(r.roomCount) }}</td>
            <td class="p-3">{{ money(r.revenue) }}</td>
            <td class="p-3">{{ money(r.adr) }}</td>
            <td class="p-3">
              {{ num(r.complimentary) }} / {{ num(r.houseUse) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!forecast?.hotel.length" class="p-4 text-sm">
      {{
        forecastBusy
          ? "Hotel totals are loading independently…"
          : "No hotel forecast available."
      }}
    </p>
  </div>
  <div class="neu-card overflow-hidden">
    <h2 class="p-4 font-semibold">Market segments — whole forecast window</h2>
    <div class="overflow-x-auto">
      <table class="min-w-full text-xs">
        <thead>
          <tr>
            <th
              v-for="h in [
                'Segment',
                'Room nights',
                'PMS revenue',
                'PMS revenue / night',
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
            v-for="s in segmentTotals"
            :key="s.market"
            class="border-t border-slate-100"
          >
            <td class="p-3">{{ s.market }}</td>
            <td class="p-3">{{ num(s.rooms) }}</td>
            <td class="p-3">{{ money(s.revenue) }}</td>
            <td class="p-3">{{ money(ratio(s.revenue, s.rooms)) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="neu-card overflow-hidden">
    <h2 class="p-4 font-semibold">Expected occupied by room type</h2>
    <div class="max-h-[50vh] overflow-auto">
      <table class="min-w-full text-xs">
        <thead class="sticky top-0 bg-white">
          <tr>
            <th class="sticky left-0 bg-white p-3 text-left">Room type</th>
            <th
              v-for="d in matrix.dates"
              :key="d"
              class="whitespace-nowrap p-2"
            >
              {{ d.slice(5) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in matrix.types"
            :key="r.typeId"
            class="border-t border-slate-100"
          >
            <td class="sticky left-0 whitespace-nowrap bg-white p-3">
              {{ label(r.typeId) }}
            </td>
            <td
              v-for="d in matrix.dates"
              :key="d"
              :class="[
                'p-2 text-right',
                r.capacity && r.values[d] >= r.capacity * 0.9
                  ? 'bg-amber-50'
                  : '',
              ]"
            >
              {{ num(r.values[d]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script setup lang="ts">
import { num, money, percent, ratio, dayLabel } from "../utils/rms";
import type { Forecast, MonthSummary } from "../utils/rms";
import RmsMonthlyTargetsTable from "./RmsMonthlyTargetsTable.vue";
defineProps<{
  months: MonthSummary[];
  basisLabel: string;
  forecast: Forecast | null;
  forecastBusy: boolean;
  segmentTotals: { market: string; rooms: number; revenue: number }[];
  matrix: {
    dates: string[];
    types: {
      typeId: string;
      capacity: number;
      values: Record<string, number>;
    }[];
  };
  label: (code: string) => string;
}>();
</script>
