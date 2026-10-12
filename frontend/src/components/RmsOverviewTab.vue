<template>
  <dl class="grid grid-cols-2 gap-3 lg:grid-cols-4">
    <div v-for="t in tiles" :key="t.label" class="stat-tile">
      <dt>{{ t.label }}</dt>
      <dd :title="t.title">{{ t.value }}</dd>
      <p
        v-for="s in t.subs"
        :key="s.text"
        :class="['mt-0.5 text-[11px] tabular-nums', s.tone || 'text-slate-500']"
      >
        {{ s.text }}
      </p>
    </div>
  </dl>

  <RmsCard
    title="Dates to review"
    :description="`${flaggedCount} of ${rowsLength} dates flagged. Select a date for its booking curve, availability and notes. Flags never change rates.`"
    scroll
  >
    <template #actions>
      <div class="seg" role="group" aria-label="Rows shown">
        <button
          type="button"
          class="seg-btn"
          :aria-pressed="onlyAttention"
          @click="onlyAttention = true"
        >
          Flagged
        </button>
        <button
          type="button"
          class="seg-btn"
          :aria-pressed="!onlyAttention"
          @click="onlyAttention = false"
        >
          All dates
        </button>
      </div>
    </template>
    <table v-if="attentionRows.length" class="data-table">
      <thead>
        <tr>
          <th>Stay date</th>
          <th>Why</th>
          <th class="num">OTB</th>
          <th class="num">Occ.</th>
          <th class="num">vs LY</th>
          <th class="num">Pickup</th>
          <th class="num">Avail.</th>
          <th :title="`Last applied BAR levels; live prices may differ. Updated ${timestamp(barUpdatedAt)}.`">
            Last BAR
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in attentionRows" :key="r.date">
          <td class="whitespace-nowrap">
            <button class="row-link" @click="$emit('openDay', r.date)">
              {{ dayLabel(r.date) }}
            </button>
            <span
              v-if="notes[r.date]?.text"
              class="sub"
              :title="notes[r.date].text"
              >Has note</span
            >
          </td>
          <td>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="reason in r.reasons"
                :key="reason"
                :class="['pill', reasonChip(reason, r).tone]"
                :title="reason"
                >{{ reasonChip(reason, r).text }}</span
              >
              <span v-if="!r.reasons.length" class="text-slate-400">—</span>
            </div>
          </td>
          <td class="num">{{ num(r.otb) }}</td>
          <td class="num">{{ percent(r.occupancy) }}</td>
          <td :class="['num', signClass(r.gap)]">{{ signed(r.gap) }}</td>
          <td class="num">{{ signed(r.pickupRooms) }}</td>
          <td :class="['num', r.available != null && r.available < 0 && 'text-rose-700']">
            {{ num(r.available) }}
          </td>
          <td class="max-w-48 text-slate-500">{{ r.bar || "—" }}</td>
        </tr>
      </tbody>
    </table>
    <template #empty v-if="!attentionRows.length">
      {{
        rowsLength
          ? "No dates are flagged for this selection."
          : "Apply a range to load data."
      }}
    </template>
  </RmsCard>

  <RmsMonthlyTargetsTable :months="months" :basis-label="basisLabel" />
</template>
<script setup lang="ts">
import {
  num,
  signed,
  percent,
  timestamp,
  dayLabel,
  signClass,
} from "../utils/rms";
import type { PaceRow, MonthSummary } from "../utils/rms";
import RmsCard from "./RmsCard.vue";
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
export interface Tile {
  label: string;
  value: string;
  title?: string;
  subs: { text: string; tone?: string }[];
}
defineProps<{
  tiles: Tile[];
  attentionRows: AttentionRow[];
  flaggedCount: number;
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
// Short chip text for each review reason; the full reason is the chip's title.
const reasonChip = (reason: string, r: AttentionRow) => {
  switch (reason) {
    case "High occupancy":
      return { text: "High occ.", tone: "pill-warn" };
    case "Behind pace; weak pickup":
      return { text: "Behind pace", tone: "pill-bad" };
    case "Negative physical availability":
      return { text: "Negative avail.", tone: "pill-bad" };
    case "Check booking/PMS room difference":
      return { text: `PMS diff ${signed(r.reconciliation)}`, tone: "pill-warn" };
    case "Booking coverage unavailable":
      return { text: "No coverage", tone: "pill-muted" };
    case "Stale booking data":
      return { text: "Stale data", tone: "pill-muted" };
    case "Booking data changed — apply again":
      return { text: "Re-apply", tone: "pill-muted" };
    case "Comparison unavailable":
      return { text: "No LY", tone: "pill-muted" };
    default:
      return { text: reason, tone: "pill-muted" };
  }
};
</script>
