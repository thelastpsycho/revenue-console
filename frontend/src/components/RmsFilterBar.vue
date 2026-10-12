<template>
  <form
    class="neu-card flex flex-wrap items-end gap-3 p-4 text-xs"
    @submit.prevent="$emit('submit')"
  >
    <div ref="dateMenuRef" class="relative space-y-1">
      <span class="block font-semibold text-slate-600">Stay dates</span>
      <button
        type="button"
        class="neu-input flex items-center gap-2 py-1.5 text-xs"
        @click="dateMenuOpen = !dateMenuOpen"
      >
        {{ shortDayYear(filters.start) }} – {{ shortDayYear(filters.end) }}
      </button>
      <div
        v-if="dateMenuOpen"
        class="neu-card absolute left-0 top-full z-20 mt-1 w-72 space-y-3 p-3 shadow-neu-sm"
      >
        <div class="flex gap-1.5">
          <button
            type="button"
            class="btn-flat flex-1 px-2 py-1 text-xs"
            @click="applyDatePreset(3)"
          >
            Next 3 months
          </button>
          <button
            type="button"
            class="btn-flat flex-1 px-2 py-1 text-xs"
            @click="applyDatePreset(5)"
          >
            Next 5 months
          </button>
        </div>
        <div class="border-t border-slate-200 pt-3">
          <p class="mb-1.5 font-semibold text-slate-600">Custom range</p>
          <DateRangeCalendar
            v-model:start="filters.start"
            v-model:end="filters.end"
          />
          <div class="mt-2 flex justify-end">
            <button
              type="button"
              class="btn-primary px-3 py-1 text-xs"
              :disabled="!filters.start || !filters.end"
              @click="dateMenuOpen = false"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
    <label
      >Room type<select v-model="filters.roomType" class="neu-input mt-1 block">
        <option value="">All</option>
        <option v-for="r in dims.roomTypes" :key="r" :value="r">
          {{ dims.labels[r] || r }}
        </option>
      </select></label
    >
    <label
      >Market<select v-model="filters.marketId" class="neu-input mt-1 block">
        <option value="">All</option>
        <option v-for="m in dims.markets" :key="m.id" :value="String(m.id)">
          {{ m.name }}
        </option>
      </select></label
    >
    <label
      >Pickup<select
        v-model.number="filters.pickupDays"
        class="neu-input mt-1 block"
      >
        <option v-for="d in [1, 3, 7, 14, 30]" :key="d" :value="d">
          {{ d }} days
        </option>
      </select></label
    >
    <label
      >Compare with<select
        v-model="filters.comparison"
        class="neu-input mt-1 block"
      >
        <option value="weekday">Same weekday last year</option>
        <option value="calendar">Same calendar date last year</option>
        <option value="custom">Matched event / holiday</option>
      </select></label
    >
    <label v-if="filters.comparison === 'custom'"
      >Comparison begins<input
        v-model="filters.comparisonStart"
        type="date"
        required
        class="neu-input mt-1 block"
    /></label>
    <label
      >Revenue basis<select v-model="basis" class="neu-input mt-1 block">
        <option value="gross">Gross IDR rate</option>
        <option value="net">Estimated net IDR rate</option>
      </select></label
    >
    <button class="btn-primary px-3 py-2" :disabled="loading">
      {{ loading ? "Loading…" : "Apply" }}</button
    ><button type="button" class="btn-flat px-3 py-2" @click="thisMonth">
      This month</button
    ><button
      type="button"
      class="btn-flat px-3 py-2"
      :disabled="!rowsLength"
      @click="$emit('exportCsv')"
    >
      Export CSV
    </button>
  </form>
  <p v-if="dirty" class="text-xs text-amber-800">
    Filters changed. Press Apply. Displayed data and exports still use the
    previous selection.
  </p>
  <p v-if="loaded" class="text-xs text-slate-500">
    Showing {{ loaded.start }}–{{ loaded.end }} ·
    {{ loaded.roomType ? dims.labels[loaded.roomType] || loaded.roomType : "All room types" }} ·
    {{ loaded.marketId ? marketName(loaded.marketId) : "All markets" }} ·
    {{ comparisonLabel }} · {{ loaded.pickupDays }}-day pickup.
  </p>
  <div v-if="forecast" class="flex flex-wrap gap-3 text-xs text-slate-500">
    <span v-for="(s, k) in forecast.sections" :key="k"
      >{{ k }}:
      {{
        s.refreshing
          ? "refreshing…"
          : s.error
            ? "failed"
            : s.stale
              ? "stale"
              : "ready"
      }}
      · {{ timestamp(s.fetchedAt)
      }}<span v-if="s.error" class="text-rose-700"> {{ s.error }}</span></span
    ><button class="underline" :disabled="forecastBusy" @click="$emit('refreshForecast')">
      Refresh PMS reports
    </button>
  </div>
  <p v-if="loaded" class="text-xs text-slate-500">
    Displayed booking data from sync: {{ timestamp(reportSync?.lastSuccessfulSync) }}.
    {{
      reportSync?.lastSuccessfulSync !== sync?.lastSuccessfulSync
        ? "New data is available — press Apply."
        : ""
    }}
  </p>
  <p class="text-xs text-slate-500">
    PMS reports cover the first 90 selected days; pace covers up to 366. PMS
    forecast revenue uses the PMS definition and is not combined with
    booking-rate revenue.
  </p>
</template>
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import DateRangeCalendar from "./DateRangeCalendar.vue";
import { addDays, shortDayYear, timestamp } from "../utils/rms";
import type { Filters, Forecast, Sync } from "../utils/rms";

const props = defineProps<{
  filters: Filters;
  dims: {
    roomTypes: string[];
    markets: { id: number; name: string }[];
    labels: Record<string, string>;
  };
  loading: boolean;
  dirty: boolean;
  loaded: Filters | null;
  comparisonLabel: string;
  forecast: Forecast | null;
  forecastBusy: boolean;
  reportSync: Sync | null;
  sync: Sync | null;
  rowsLength: number;
  today: string;
}>();
const emit = defineEmits<{
  submit: [];
  exportCsv: [];
  refreshForecast: [];
}>();
const basis = defineModel<"gross" | "net">("basis", { required: true });

const marketName = (id: string) =>
  props.dims.markets.find((m) => String(m.id) === id)?.name || id;

const dateMenuOpen = ref(false),
  dateMenuRef = ref<HTMLElement | null>(null);
function onDateMenuClickOutside(e: MouseEvent) {
  if (
    dateMenuOpen.value &&
    dateMenuRef.value &&
    !dateMenuRef.value.contains(e.target as Node)
  )
    dateMenuOpen.value = false;
}
function applyDatePreset(months: number) {
  const d = new Date(`${props.today}T00:00:00Z`);
  props.filters.start = addDays(props.today, -(d.getUTCDate() - 1));
  const end = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + months, 0));
  props.filters.end = end.toISOString().slice(0, 10);
  dateMenuOpen.value = false;
}
function thisMonth() {
  const t = props.today;
  props.filters.start = `${t.slice(0, 7)}-01`;
  props.filters.end = addDays(
    new Date(Date.UTC(Number(t.slice(0, 4)), Number(t.slice(5, 7)), 1))
      .toISOString()
      .slice(0, 10),
    -1,
  );
  emit("submit");
}
onMounted(() => document.addEventListener("mousedown", onDateMenuClickOutside));
onBeforeUnmount(() =>
  document.removeEventListener("mousedown", onDateMenuClickOutside),
);
</script>
