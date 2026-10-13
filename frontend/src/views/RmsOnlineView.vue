<template>
  <div class="mx-auto w-full max-w-screen-2xl space-y-4 p-4 sm:p-6">
    <PageHeader
      title="Online segment"
      subtitle="Source mix, pace, booking behaviour and Santika Online's share of direct vs OTA demand - market segment: Online."
      compact
    />

    <nav class="seg !flex w-full" role="tablist" aria-label="Online sections">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        class="seg-btn"
        :aria-selected="tab === t.id"
        @click="selectTab(t.id)"
      >
        <component :is="t.icon" class="h-4 w-4" />
        {{ t.label }}
      </button>
    </nav>

    <form class="filter-bar neu-card relative flex flex-wrap items-end gap-2 p-3" @submit.prevent="apply">
      <div ref="dateMenuRef" class="relative">
        <span class="field-label">Stay dates</span>
        <button
          type="button"
          class="neu-input flex items-center gap-1.5 whitespace-nowrap"
          :aria-expanded="dateMenuOpen"
          @click="dateMenuOpen = !dateMenuOpen"
        >
          <CalendarDaysIcon class="h-3.5 w-3.5 text-slate-400" />
          {{ shortDayYear(filters.start) }} – {{ shortDayYear(filters.end) }}
        </button>
        <div
          v-if="dateMenuOpen"
          class="neu-card absolute left-0 top-full z-30 mt-1 w-72 space-y-3 p-3 shadow-lg"
        >
          <div class="grid grid-cols-3 gap-1.5">
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="thisMonth">
              This month
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="applyDatePreset(3)">
              3 months
            </button>
            <button type="button" class="btn-flat px-2 py-1 text-xs" @click="applyDatePreset(5)">
              5 months
            </button>
          </div>
          <div class="border-t border-slate-200 pt-3">
            <span class="field-label">Custom range</span>
            <DateRangeCalendar v-model:start="filters.start" v-model:end="filters.end" />
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
      <div ref="channelMenuRef" class="relative">
        <span class="field-label">Channel</span>
        <button
          type="button"
          class="neu-input flex items-center gap-2 whitespace-nowrap"
          :aria-expanded="channelMenuOpen"
          @click="channelMenuOpen = !channelMenuOpen"
        >
          {{ channelButtonLabel }}
        </button>
        <div
          v-if="channelMenuOpen"
          class="neu-card absolute left-0 top-full z-30 mt-1 w-64 space-y-1 p-3 shadow-lg"
        >
          <label
            v-for="c in dims.channels"
            :key="c.id"
            class="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-50"
          >
            <input v-model="filters.channels" type="checkbox" :value="c.id" class="accent-slate-900" />
            {{ c.name }}
          </label>
          <div class="flex items-center justify-between border-t border-slate-200 pt-2">
            <button
              type="button"
              class="btn-flat px-2 py-1 text-xs"
              :disabled="!filters.channels.length"
              @click="filters.channels = []"
            >
              Clear
            </button>
            <button type="button" class="btn-primary px-3 py-1 text-xs" @click="channelMenuOpen = false">
              Done
            </button>
          </div>
        </div>
      </div>
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
        <input v-model="filters.comparisonStart" type="date" required class="neu-input" />
      </label>
      <button :class="['btn-primary px-3 py-1.5 text-xs', dirty && 'ring-2 ring-amber-300']">
        {{ dirty ? "Apply changes" : "Apply" }}
      </button>
    </form>
    <p v-if="error" role="alert" class="alert-error">{{ error }}</p>

    <RmsOnlineSourceTab v-if="tab === 'source' && loaded" :filters="loaded" />
    <RmsOnlinePaceTab v-if="tab === 'pace' && loaded" :filters="loaded" />
    <RmsOnlineBehaviourTab v-if="tab === 'behaviour' && loaded" :filters="loaded" />
    <RmsOnlineDirectShareTab v-if="tab === 'direct' && loaded" :filters="loaded" />
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  CalendarDaysIcon,
  ChartPieIcon,
  ArrowTrendingUpIcon,
  UserGroupIcon,
  GlobeAltIcon,
} from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import PageHeader from "../components/PageHeader.vue";
import DateRangeCalendar from "../components/DateRangeCalendar.vue";
import RmsOnlineSourceTab from "../components/RmsOnlineSourceTab.vue";
import RmsOnlinePaceTab from "../components/RmsOnlinePaceTab.vue";
import RmsOnlineBehaviourTab from "../components/RmsOnlineBehaviourTab.vue";
import RmsOnlineDirectShareTab from "../components/RmsOnlineDirectShareTab.vue";
import { addDays, hotelToday, loadStoredFilters, saveStoredFilters, shortDayYear } from "../utils/rms";

const today = hotelToday(),
  route = useRoute(),
  router = useRouter();

const tabs = [
  { id: "source", label: "Source", icon: ChartPieIcon },
  { id: "pace", label: "Pace", icon: ArrowTrendingUpIcon },
  { id: "behaviour", label: "Booking behaviour", icon: UserGroupIcon },
  { id: "direct", label: "Direct share", icon: GlobeAltIcon },
];
const STORAGE_KEY = "rms-online";
const stored = loadStoredFilters(STORAGE_KEY) || {};
const query = (k: string, f = "") =>
  typeof route.query[k] === "string" ? String(route.query[k]) : (stored[k] ?? f);
const tab = ref(tabs.some((t) => t.id === query("tab")) ? query("tab") : "source");

interface OnlineFilters {
  start: string;
  end: string;
  roomType: string;
  channels: string[];
  comparison: "weekday" | "calendar" | "custom";
  comparisonStart: string;
}
const filters = reactive<OnlineFilters>({
  start: query("start", today),
  end: query("end", addDays(today, 29)),
  roomType: query("roomType"),
  channels: query("channels") ? query("channels").split(",").filter(Boolean) : [],
  comparison: (query("comparison", "weekday") as OnlineFilters["comparison"]) || "weekday",
  comparisonStart: query("comparisonStart"),
});
const loaded = ref<OnlineFilters | null>(null);
const error = ref("");
const dims = reactive<{
  roomTypes: string[];
  labels: Record<string, string>;
  channels: { id: string; name: string }[];
}>({
  roomTypes: [],
  labels: {},
  channels: [],
});

const dirty = computed(
  () => loaded.value && JSON.stringify(filters) !== JSON.stringify(loaded.value),
);
const channelButtonLabel = computed(() => {
  const n = filters.channels.length;
  if (!n) return "All channels";
  if (n === 1)
    return dims.channels.find((c) => c.id === filters.channels[0])?.name || "1 channel";
  return `${n} channels`;
});

function saveUrl() {
  const f = loaded.value || filters;
  const q = {
    start: f.start,
    end: f.end,
    roomType: f.roomType,
    channels: f.channels.length ? f.channels.join(",") : undefined,
    comparison: f.comparison,
    comparisonStart: f.comparison === "custom" ? f.comparisonStart : undefined,
    tab: tab.value,
  };
  router.replace({ query: q });
  saveStoredFilters(STORAGE_KEY, q);
}
function selectTab(id: string) {
  tab.value = id;
  saveUrl();
}
function apply() {
  if (
    !filters.start ||
    !filters.end ||
    filters.end < filters.start ||
    (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000 >= 366
  ) {
    error.value = "Choose a valid range of at most 366 days.";
    return;
  }
  if (filters.comparison === "custom" && !filters.comparisonStart) {
    error.value = "Choose a start date for the matched comparison.";
    return;
  }
  error.value = "";
  loaded.value = { ...filters, channels: [...filters.channels] };
  saveUrl();
}

const dateMenuOpen = ref(false),
  dateMenuRef = ref<HTMLElement | null>(null),
  channelMenuOpen = ref(false),
  channelMenuRef = ref<HTMLElement | null>(null);
function onDateMenuClickOutside(e: MouseEvent) {
  if (
    dateMenuOpen.value &&
    dateMenuRef.value &&
    !dateMenuRef.value.contains(e.target as Node)
  )
    dateMenuOpen.value = false;
  if (
    channelMenuOpen.value &&
    channelMenuRef.value &&
    !channelMenuRef.value.contains(e.target as Node)
  )
    channelMenuOpen.value = false;
}
function applyDatePreset(months: number) {
  const d = new Date(`${today}T00:00:00Z`);
  filters.start = addDays(today, -(d.getUTCDate() - 1));
  const end = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + months, 0));
  filters.end = end.toISOString().slice(0, 10);
  dateMenuOpen.value = false;
}
function thisMonth() {
  filters.start = `${today.slice(0, 7)}-01`;
  filters.end = addDays(
    new Date(Date.UTC(Number(today.slice(0, 4)), Number(today.slice(5, 7)), 1))
      .toISOString()
      .slice(0, 10),
    -1,
  );
  dateMenuOpen.value = false;
  apply();
}

onMounted(async () => {
  document.addEventListener("mousedown", onDateMenuClickOutside);
  try {
    const d = await axios.get("/api/rms/room-types");
    Object.assign(dims, d.data);
  } catch (e: any) {
    error.value = e?.response?.data?.message || "Could not load room types";
  }
  apply();
});
onBeforeUnmount(() => document.removeEventListener("mousedown", onDateMenuClickOutside));
</script>
