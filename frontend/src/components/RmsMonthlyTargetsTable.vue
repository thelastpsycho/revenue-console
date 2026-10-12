<template>
  <div class="neu-card overflow-hidden">
    <h2 class="p-4 font-semibold">Monthly booking position & targets</h2>
    <p class="px-4 pb-3 text-xs text-slate-500">
      {{ basisLabel }}. ADR uses IDR nights only. RevPAR is the IDR revenue
      component / room capacity. Targets require complete, unfiltered months
      on the same basis. These are booking positions, not audited actuals.
    </p>
    <div class="overflow-x-auto">
      <table class="min-w-full text-xs">
        <thead>
          <tr>
            <th
              v-for="h in [
                'Month',
                'Room nights',
                'Room revenue',
                'ADR',
                'RevPAR (IDR component)',
                'Target',
                'Target gap',
                'Required revenue / remaining day',
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
            v-for="m in months"
            :key="m.month"
            class="border-t border-slate-100"
          >
            <td class="p-3">
              {{ m.month
              }}<span v-if="!m.fullMonth" class="block text-amber-800"
                >Partial month</span
              ><span v-if="m.hasForeign" class="block text-slate-500"
                >Foreign revenue excluded</span
              >
            </td>
            <td class="p-3">{{ num(m.roomNights) }}</td>
            <td class="p-3">{{ money(m.revenue) }}</td>
            <td class="p-3">{{ money(m.adr) }}</td>
            <td class="p-3">{{ money(m.revpar) }}</td>
            <td class="p-3">{{ money(m.budget) }}</td>
            <td class="p-3">{{ money(m.gap) }}</td>
            <td class="p-3">{{ money(m.required) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script setup lang="ts">
import { num, money, type MonthSummary } from "../utils/rms";
defineProps<{
  months: MonthSummary[];
  basisLabel: string;
}>();
</script>
