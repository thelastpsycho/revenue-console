<template>
  <div class="flex justify-between">
    <h2 class="font-semibold">
      {{ dayLabel(selectedDate) }} — booking curve & review
    </h2>
    <button class="text-xs underline" @click="$emit('close')">Close</button>
  </div>
  <p v-if="curveLoading" class="text-xs">Loading booking curve…</p>
  <p v-if="curveError" role="alert" class="text-xs text-rose-700">
    {{ curveError }}
  </p>
  <p class="text-xs text-slate-500">
    Current curve stops at today. Earlier reconstructed history is estimated;
    gaps mean unavailable. Comparison: {{ curve?.lyDate }}.
  </p>
  <div class="h-60">
    <Chart type="line" :data="curveData" :options="curveOptions" :plugins="[todayMarker]" />
  </div>
  <div class="grid gap-4 md:grid-cols-2">
    <div>
      <h3 class="text-sm font-semibold">Physical availability</h3>
      <p v-if="!selectedAvailability.length" class="text-xs">
        Unavailable for this date.
      </p>
      <div class="mt-2 flex flex-wrap gap-2">
        <span
          v-for="r in selectedAvailability"
          :key="r.type"
          class="rounded bg-slate-50 p-2 text-xs"
          >{{ label(r.type) }}: {{ num(r.rooms) }}</span
        >
      </div>
    </div>
    <div>
      <h3 class="text-sm font-semibold">PMS segment breakdown</h3>
      <p v-if="!selectedSegments.length" class="text-xs">
        Unavailable for this date.
      </p>
      <p v-for="s in selectedSegments" :key="s.marketId" class="mt-1 text-xs">
        {{ s.market }}: {{ num(s.rooms) }} nights · {{ money(s.revenue) }}
      </p>
    </div>
  </div>
  <label class="block text-xs font-semibold"
    >Meeting note — do not enter guest details<textarea
      v-model="noteDraft"
      maxlength="2000"
      rows="3"
      class="neu-input mt-1 w-full"
    /></label
  ><button
    class="btn-primary px-3 py-2 text-xs"
    :disabled="noteSaving"
    @click="$emit('saveNote')"
  >
    {{ noteSaving ? "Saving…" : "Save note" }}</button
  ><span v-if="savedNote" class="ml-3 text-xs"
    >Saved {{ timestamp(savedNote.updatedAt) }}</span
  >
</template>
<script setup lang="ts">
import { Chart } from "vue-chartjs";
import type { ChartOptions, ChartTypeRegistry } from "chart.js";
import { num, money, timestamp, dayLabel } from "../utils/rms";
import type { Curve } from "../utils/rms";

defineProps<{
  selectedDate: string;
  curve: Curve | null;
  curveLoading: boolean;
  curveError: string;
  curveData: any;
  curveOptions: ChartOptions<keyof ChartTypeRegistry>;
  todayMarker: any;
  selectedAvailability: { type: string; rooms: number }[];
  selectedSegments: { marketId: number; market: string; rooms: number; revenue: number }[];
  savedNote: { text: string; updatedAt: string } | undefined;
  noteSaving: boolean;
  label: (code: string) => string;
}>();
defineEmits<{ close: []; saveNote: [] }>();
const noteDraft = defineModel<string>("noteDraft", { required: true });
</script>
