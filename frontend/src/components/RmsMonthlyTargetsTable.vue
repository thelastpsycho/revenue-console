<template>
  <RmsCard
    title="Monthly position and targets"
    :description="`${basisLabel}. Booking positions, not audited actuals. Targets use the imported segment budget per day where available (partial ranges and market filters included); otherwise the manual monthly figure, which needs a complete, unfiltered month on the same basis.`"
  >
    <div class="overflow-x-auto">
      <RmsSkeleton v-if="loading" variant="table" :count="3" :columns="8" />
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>Month</th>
            <th class="num">Room nights</th>
            <th class="num">Revenue</th>
            <th class="num">ADR</th>
            <th class="num" title="IDR revenue component / room capacity">
              RevPAR
            </th>
            <th class="num">Target</th>
            <th class="num">Gap to target</th>
            <th class="num">Needed / remaining day</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in months" :key="m.month">
            <td class="whitespace-nowrap font-semibold text-slate-900">
              {{ m.month }}
              <span v-if="!m.fullMonth" class="sub text-amber-700"
                >Partial month</span
              ><span v-if="m.hasForeign" class="sub"
                >Foreign revenue excluded</span
              >
            </td>
            <td class="num">{{ num(m.roomNights) }}</td>
            <td class="num" :title="money(m.revenue)">
              {{ moneyShort(m.revenue) }}
            </td>
            <td class="num" :title="money(m.adr)">{{ moneyShort(m.adr) }}</td>
            <td class="num" :title="money(m.revpar)">
              {{ moneyShort(m.revpar) }}
            </td>
            <td class="num" :title="money(m.budget)">
              {{ moneyShort(m.budget) }}
            </td>
            <td :class="['num', signClass(m.gap)]" :title="money(m.gap)">
              {{ moneyShort(m.gap) }}
            </td>
            <td class="num" :title="money(m.required)">
              {{ moneyShort(m.required) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <template v-if="!loading && !months.length" #empty>Apply a range to load data.</template>
  </RmsCard>
</template>
<script setup lang="ts">
import RmsCard from "./RmsCard.vue";
import RmsSkeleton from "./RmsSkeleton.vue";
import {
  num,
  money,
  moneyShort,
  signClass,
  type MonthSummary,
} from "../utils/rms";
defineProps<{
  loading: boolean;
  months: MonthSummary[];
  basisLabel: string;
}>();
</script>
