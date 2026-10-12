<template>
  <RmsCard
    title="Room and rate plan breakdown"
    :description="`On-the-books nights and revenue by room type and PMS rate code · ${basisLabel}.`"
    scroll
  >
    <table v-if="breakdown?.roomTypes.length" class="data-table">
      <thead>
        <tr>
          <th>Room / rate plan</th>
          <th class="num">Room nights</th>
          <th class="num">Revenue</th>
          <th class="num">ADR</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="rt in breakdown.roomTypes" :key="rt.id">
          <tr class="[&>td]:bg-slate-50">
            <td class="font-semibold text-slate-900">{{ label(rt.id) }}</td>
            <td class="num font-semibold">{{ num(rt.rooms) }}</td>
            <td class="num font-semibold" :title="money(rev(rt))">
              {{ moneyShort(rev(rt)) }}
            </td>
            <td class="num font-semibold" :title="money(ratio(rev(rt), rt.idrRooms))">
              {{ moneyShort(ratio(rev(rt), rt.idrRooms)) }}
            </td>
          </tr>
          <tr v-for="p in rt.ratePlans" :key="rt.id + ':' + p.id">
            <td class="pl-8 text-slate-600">{{ p.id }}</td>
            <td class="num">{{ num(p.rooms) }}</td>
            <td class="num" :title="money(rev(p))">{{ moneyShort(rev(p)) }}</td>
            <td class="num" :title="money(ratio(rev(p), p.idrRooms))">
              {{ moneyShort(ratio(rev(p), p.idrRooms)) }}
            </td>
          </tr>
        </template>
      </tbody>
      <tfoot>
        <tr>
          <td>Total</td>
          <td class="num">{{ num(breakdown.total.rooms) }}</td>
          <td class="num" :title="money(rev(breakdown.total))">
            {{ moneyShort(rev(breakdown.total)) }}
          </td>
          <td
            class="num"
            :title="money(ratio(rev(breakdown.total), breakdown.total.idrRooms))"
          >
            {{ moneyShort(ratio(rev(breakdown.total), breakdown.total.idrRooms)) }}
          </td>
        </tr>
      </tfoot>
    </table>
    <template v-if="!breakdown?.roomTypes.length" #empty>
      {{ breakdown ? "No bookings for this selection." : "Loading breakdown…" }}
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import RmsCard from "./RmsCard.vue";
import {
  num,
  money,
  moneyShort,
  ratio,
  breakdownRevenue,
  type Breakdown,
  type BreakdownMetrics,
} from "../utils/rms";
const props = defineProps<{
  breakdown: Breakdown | null;
  basis: "gross" | "net";
  basisLabel: string;
  label: (code: string) => string;
}>();
const rev = (m: BreakdownMetrics) => breakdownRevenue(m, props.basis);
</script>
