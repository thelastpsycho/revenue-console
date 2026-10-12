<template>
  <dl class="grid grid-cols-2 gap-3 lg:grid-cols-4">
    <div v-for="t in tiles" :key="t.label" class="neu-card p-4">
      <dt class="text-xs text-slate-500">{{ t.label }}</dt>
      <dd class="mt-1 text-lg font-semibold tabular-nums">{{ t.value }}</dd>
    </div>
  </dl>
  <div class="neu-card overflow-hidden">
    <div class="flex flex-wrap justify-between gap-2 p-4">
      <h2 class="font-semibold">Dates requiring attention</h2>
      <label class="text-xs"
        ><input v-model="onlyAttention" type="checkbox" /> Only flagged
        dates</label
      >
    </div>
    <p class="px-4 pb-3 text-xs text-slate-500">
      Flags never change rates. Availability is physical PMS inventory;
      last-applied BAR levels may differ from live prices. BAR record
      updated: {{ timestamp(barUpdatedAt) }}.
    </p>
    <div class="max-h-[55vh] overflow-auto">
      <table class="min-w-full text-xs">
        <thead class="sticky top-0 bg-white">
          <tr>
            <th
              v-for="h in [
                'Stay date',
                'OTB',
                'OTB occ.',
                'Pickup',
                'Comparison gap',
                'Available',
                'Last applied BAR',
                'PMS room difference',
                'Review reason',
              ]"
              :key="h"
              class="whitespace-nowrap p-3 text-left"
            >
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in attentionRows"
            :key="r.date"
            class="border-t border-slate-100 hover:bg-slate-50"
          >
            <td class="whitespace-nowrap p-3">
              <button
                class="font-semibold underline"
                @click="$emit('openDay', r.date)"
              >
                {{ dayLabel(r.date) }}
              </button>
            </td>
            <td class="p-3">{{ num(r.otb) }}</td>
            <td class="p-3">{{ percent(r.occupancy) }}</td>
            <td class="p-3">{{ signed(r.pickupRooms) }}</td>
            <td class="p-3">{{ signed(r.gap) }}</td>
            <td class="p-3">{{ num(r.available) }}</td>
            <td class="max-w-48 p-3">{{ r.bar || "Unavailable" }}</td>
            <td class="p-3">{{ signed(r.reconciliation) }}</td>
            <td class="min-w-44 p-3">
              {{ r.reasons.join(" · ") || "No flags"
              }}<span v-if="notes[r.date]?.text" class="block text-slate-500"
                >Note saved</span
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!attentionRows.length" class="p-4 text-sm text-slate-500">
      {{
        rowsLength
          ? "No dates match the attention filter."
          : "Apply a range to load data."
      }}
    </p>
  </div>
  <RmsMonthlyTargetsTable :months="months" :basis-label="basisLabel" />
</template>
<script setup lang="ts">
import { num, signed, percent, timestamp, dayLabel } from "../utils/rms";
import type { PaceRow, MonthSummary } from "../utils/rms";
import RmsMonthlyTargetsTable from "./RmsMonthlyTargetsTable.vue";
interface AttentionRow extends PaceRow {
  otb: number | null;
  occupancy: number | null;
  gap: number | null;
  available: number | null;
  reconciliation: number | null;
  reasons: string[];
  bar: string;
}
defineProps<{
  tiles: { label: string; value: string }[];
  attentionRows: AttentionRow[];
  rowsLength: number;
  notes: Record<string, { text: string; updatedAt: string }>;
  barUpdatedAt: string | null;
  months: MonthSummary[];
  basisLabel: string;
}>();
defineEmits<{ openDay: [date: string] }>();
const onlyAttention = defineModel<boolean>("onlyAttention", {
  required: true,
});
</script>
