<template>
  <form class="neu-card relative p-4" @submit.prevent="$emit('submit')">
    <div class="flex flex-wrap items-end gap-3">
      <div ref="dateMenuRef" class="relative">
        <span class="field-label">Stay dates</span>
        <button
          type="button"
          class="neu-input flex items-center gap-2 whitespace-nowrap"
          :aria-expanded="dateMenuOpen"
          @click="dateMenuOpen = !dateMenuOpen"
        >
          <CalendarDaysIcon class="h-4 w-4 text-slate-400" />
          {{ shortDayYear(filters.start) }} – {{ shortDayYear(filters.end) }}
        </button>
        <div
          v-if="dateMenuOpen"
          class="neu-card absolute left-0 top-full z-30 mt-1 w-72 space-y-3 p-3 shadow-lg"
        >
          <div class="grid grid-cols-3 gap-1.5">
            <button
              type="button"
              class="btn-flat px-2 py-1 text-xs"
              @click="thisMonth"
            >
              This month
            </button>
            <button
              type="button"
              class="btn-flat px-2 py-1 text-xs"
              @click="applyDatePreset(3)"
            >
              3 months
            </button>
            <button
              type="button"
              class="btn-flat px-2 py-1 text-xs"
              @click="applyDatePreset(5)"
            >
              5 months
            </button>
          </div>
          <div class="border-t border-slate-200 pt-3">
            <span class="field-label">Custom range</span>
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
      <label>
        <span class="field-label">Room type</span>
        <select v-model="filters.roomType" class="neu-input">
          <option value="">All room types</option>
          <option v-for="r in dims.roomTypes" :key="r" :value="r">
            {{ dims.labels[r] || r }}
          </option>
        </select>
      </label>
      <label>
        <span class="field-label">Market</span>
        <select v-model="filters.marketId" class="neu-input">
          <option value="">All markets</option>
          <option v-for="m in dims.markets" :key="m.id" :value="String(m.id)">
            {{ m.name }}
          </option>
        </select>
      </label>
      <label>
        <span class="field-label">Compare with</span>
        <select v-model="filters.comparison" class="neu-input">
          <option value="weekday">Same weekday last year</option>
          <option value="calendar">Same date last year</option>
          <option value="custom">Matched event / holiday</option>
        </select>
      </label>
      <label v-if="filters.comparison === 'custom'">
        <span class="field-label">Comparison begins</span>
        <input
          v-model="filters.comparisonStart"
          type="date"
          required
          class="neu-input"
        />
      </label>
      <label>
        <span class="field-label">Pickup window</span>
        <select v-model.number="filters.pickupDays" class="neu-input">
          <option v-for="d in [1, 3, 7, 14, 30]" :key="d" :value="d">
            {{ d }} {{ d === 1 ? "day" : "days" }}
          </option>
        </select>
      </label>
      <label>
        <span class="field-label">Revenue basis</span>
        <select v-model="basis" class="neu-input">
          <option value="gross">Gross IDR</option>
          <option value="net">Estimated net IDR</option>
        </select>
      </label>
      <button
        :class="['btn-primary', dirty && 'ring-2 ring-amber-300']"
        :disabled="loading"
      >
        <ArrowPathIcon v-if="loading" class="h-4 w-4 animate-spin" />
        {{ loading ? "Loading…" : dirty ? "Apply changes" : "Apply" }}
      </button>
    </div>

    <div
      class="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-3"
    >
      <span v-if="dirty" class="pill pill-warn">
        Filters changed — figures still show the previous selection
      </span>
      <span v-if="sync" :class="['pill', syncPill.tone]" :title="syncPill.title">
        {{ syncPill.text }}
      </span>
      <span v-if="newDataAvailable" class="pill pill-warn">
        New booking data — press Apply
      </span>
      <span
        v-if="forecast"
        :class="['pill', pmsPill.tone]"
        :title="pmsPill.title"
      >
        {{ pmsPill.text }}
      </span>
      <button
        v-if="forecast"
        type="button"
        class="pill pill-muted cursor-pointer hover:border-slate-300"
        :disabled="forecastBusy"
        @click="$emit('refreshForecast')"
      >
        <ArrowPathIcon :class="['h-3 w-3', forecastBusy && 'animate-spin']" />
        Refresh PMS reports
      </button>
      <details class="group ml-auto text-xs text-slate-500">
        <summary
          class="flex cursor-pointer list-none items-center gap-1 font-semibold hover:text-slate-900"
        >
          <InformationCircleIcon class="h-4 w-4" />
          About this data
        </summary>
        <div
          class="neu-card absolute right-4 z-30 mt-2 max-w-lg space-y-2 p-4 text-xs leading-relaxed text-slate-600 shadow-lg sm:right-6"
        >
          <p v-if="loaded">
            <strong>Showing:</strong> {{ loaded.start }} – {{ loaded.end }} ·
            {{ loaded.roomType ? dims.labels[loaded.roomType] || loaded.roomType : "all room types" }}
            · {{ loaded.marketId ? marketName(loaded.marketId) : "all markets" }}
            · {{ comparisonLabel }} · {{ loaded.pickupDays }}-day pickup.
          </p>
          <p>
            <strong>Booking data:</strong> last successful sync
            {{ timestamp(sync?.lastSuccessfulSync) }}; figures shown are from
            the sync of {{ timestamp(reportSync?.lastSuccessfulSync) }}.
            Booking-date coverage from
            {{ sync?.coverageFrom || "— (run backfill in Data & settings)" }}.
          </p>
          <p>
            Observed history records what each sync saw. Earlier history is
            reconstructed and marked <em>est.</em> A dash (—) means the figure
            is unavailable. No currency conversion is applied: revenue and ADR
            cover IDR-priced room nights only.
          </p>
          <p>
            PMS reports cover the first 90 selected days; pace covers up to
            366. PMS forecast revenue uses the PMS definition and is not
            combined with booking-rate revenue.
          </p>
          <ul v-if="forecast" class="space-y-0.5">
            <li v-for="(s, k) in forecast.sections" :key="k">
              <strong>{{ k }}</strong>: {{ sectionState(s) }} ·
              {{ timestamp(s.fetchedAt) }}
              <span v-if="s.error" class="text-rose-700">— {{ s.error }}</span>
            </li>
          </ul>
        </div>
      </details>
    </div>
  </form>
</template>
<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from "vue";
import {
  ArrowPathIcon,
  CalendarDaysIcon,
  InformationCircleIcon,
} from "@heroicons/vue/24/outline";
import DateRangeCalendar from "./DateRangeCalendar.vue";
import { addDays, shortDayYear, timestamp } from "../utils/rms";
import type { Filters, Forecast, Sync } from "../utils/rms";

type Section = Forecast["sections"][string];

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
  today: string;
}>();
const emit = defineEmits<{
  submit: [];
  refreshForecast: [];
}>();
const basis = defineModel<"gross" | "net">("basis", { required: true });

const marketName = (id: string) =>
  props.dims.markets.find((m) => String(m.id) === id)?.name || id;

const sectionState = (s: Section) =>
  s.refreshing ? "refreshing…" : s.error ? "failed" : s.stale ? "stale" : "ready";

const newDataAvailable = computed(
  () =>
    !!props.loaded &&
    !!props.sync &&
    props.reportSync?.lastSuccessfulSync !== props.sync.lastSuccessfulSync,
);

const syncPill = computed(() => {
  const s = props.sync;
  const title = `Last successful sync: ${timestamp(s?.lastSuccessfulSync)}`;
  if (s?.job.running)
    return {
      tone: "pill-muted",
      text: `Syncing bookings ${s.job.done}/${s.job.total}`,
      title,
    };
  if (s?.stale)
    return { tone: "pill-warn", text: "Booking data needs refresh", title };
  return {
    tone: "pill-ok",
    text: `Bookings synced ${timestamp(s?.lastSuccessfulSync)}`,
    title,
  };
});

const pmsPill = computed(() => {
  const sections = Object.entries(props.forecast?.sections || {});
  const title = sections
    .map(([k, s]) => `${k}: ${sectionState(s)}${s.error ? ` — ${s.error}` : ""}`)
    .join("\n");
  const failed = sections.filter(([, s]) => s.error).length;
  if (sections.some(([, s]) => s.refreshing))
    return { tone: "pill-muted", text: "PMS reports refreshing…", title };
  if (failed)
    return {
      tone: "pill-bad",
      text: `${failed} PMS report${failed > 1 ? "s" : ""} failed`,
      title,
    };
  if (sections.some(([, s]) => s.stale))
    return { tone: "pill-warn", text: "PMS reports stale", title };
  return { tone: "pill-ok", text: "PMS reports ready", title };
});

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
  dateMenuOpen.value = false;
  emit("submit");
}
onMounted(() => document.addEventListener("mousedown", onDateMenuClickOutside));
onBeforeUnmount(() =>
  document.removeEventListener("mousedown", onDateMenuClickOutside),
);
</script>
