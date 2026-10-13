<template>
  <RmsCard
    title="Room type inventory"
    description="PMS expected occupied vs physical room count, first 90 selected days. Physical availability is separate from channel allotment. Select a date for its detail."
  >
    <template #actions>
      <div class="seg" role="group" aria-label="Cell value">
        <button
          v-for="m in modes"
          :key="m.id"
          type="button"
          class="seg-btn"
          :aria-pressed="mode === m.id"
          @click="mode = m.id"
        >
          {{ m.label }}
        </button>
      </div>
    </template>
    <RmsSkeleton v-if="forecastBusy && !types.length" variant="table" :count="8" :columns="10" />
    <div v-else-if="types.length" class="max-h-[65vh] overflow-auto">
      <table class="data-table">
        <thead>
          <tr>
            <th class="sticky-col">Room type</th>
            <th v-for="d in dates" :key="d" class="num !px-1.5">
              <button class="row-link !font-bold !no-underline" @click="$emit('openDay', d)">
                {{ weekday(d) }}<span class="block">{{ d.slice(8) }}/{{ d.slice(5, 7) }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in types" :key="t.typeId">
            <td class="sticky-col whitespace-nowrap font-semibold text-slate-900">
              {{ label(t.typeId) }}
              <span class="sub">{{ num(t.capacity) }} rooms</span>
            </td>
            <td
              v-for="d in dates"
              :key="d"
              :class="['num !px-1.5', heat(t, d)]"
              :title="cellTitle(t, d)"
            >
              {{ cellValue(t, d) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div
      v-if="types.length"
      class="flex flex-wrap items-center gap-3 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500"
    >
      <span class="flex items-center gap-1"><span class="h-3 w-3 rounded-sm border border-slate-200 bg-white" /> under 70%</span>
      <span class="flex items-center gap-1"><span class="h-3 w-3 rounded-sm bg-amber-50" /> 70–89%</span>
      <span class="flex items-center gap-1"><span class="h-3 w-3 rounded-sm bg-amber-200" /> 90–99%</span>
      <span class="flex items-center gap-1"><span class="h-3 w-3 rounded-sm bg-rose-200" /> full or oversold</span>
    </div>
    <template v-if="!forecastBusy && !types.length" #empty>
      No room type inventory for this selection.
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import RmsCard from "./RmsCard.vue";
import RmsSkeleton from "./RmsSkeleton.vue";
import { num, percent, ratio, EMPTY, type Forecast } from "../utils/rms";

interface TypeRow {
  typeId: string;
  capacity: number;
  values: Record<string, number>;
}
const props = defineProps<{
  forecast: Forecast | null;
  forecastBusy: boolean;
  roomType: string;
  label: (code: string) => string;
}>();
defineEmits<{ openDay: [date: string] }>();

const modes = [
  { id: "occupancy", label: "Occupancy %" },
  { id: "occupied", label: "Occupied" },
  { id: "available", label: "Available" },
] as const;
const mode = ref<(typeof modes)[number]["id"]>("occupancy");

const availability = computed(() =>
  Object.fromEntries(
    (props.forecast?.availability || []).map((r) => [r.date, r.values]),
  ),
);
const filtered = computed(() =>
  (props.forecast?.roomTypes || []).filter(
    (r) => !props.roomType || r.typeId === props.roomType,
  ),
);
const dates = computed(() => [...new Set(filtered.value.map((r) => r.date))].sort());
const types = computed(() => {
  const m = new Map<string, TypeRow>();
  for (const r of filtered.value) {
    const t = m.get(r.typeId) || { typeId: r.typeId, capacity: r.roomCount, values: {} };
    t.values[r.date] = r.rooms;
    m.set(r.typeId, t);
  }
  return [...m.values()];
});

const occ = (t: TypeRow, d: string) => {
  const r = ratio(t.values[d] ?? null, t.capacity);
  return r == null ? null : r * 100;
};
const avail = (t: TypeRow, d: string) => availability.value[d]?.[t.typeId] ?? null;
const weekday = (d: string) =>
  new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "short",
  });
function cellValue(t: TypeRow, d: string) {
  if (mode.value === "occupied") return num(t.values[d]);
  if (mode.value === "available") return num(avail(t, d));
  const o = occ(t, d);
  return o == null ? EMPTY : `${Math.round(o)}%`;
}
function heat(t: TypeRow, d: string) {
  const o = occ(t, d),
    a = avail(t, d);
  if ((a != null && a <= 0) || (o != null && o >= 100)) return "!bg-rose-200 text-rose-900";
  if (o == null) return "";
  if (o >= 90) return "!bg-amber-200 text-amber-900";
  if (o >= 70) return "!bg-amber-50";
  return "";
}
const cellTitle = (t: TypeRow, d: string) =>
  `${props.label(t.typeId)} · ${d}\nExpected occupied ${num(t.values[d])} of ${num(t.capacity)} (${percent(occ(t, d))})\nPhysical availability ${num(avail(t, d))}`;
</script>
