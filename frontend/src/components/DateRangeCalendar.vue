<template>
  <div class="mx-auto w-full max-w-xs select-none">
    <div class="flex items-center justify-between">
      <button
        type="button"
        @click="shiftMonth(-1)"
        :disabled="!canGoBack"
        class="rounded-lg p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
        aria-label="Previous month"
      >
        <ChevronLeftIcon class="h-4 w-4" />
      </button>
      <span class="text-xs font-semibold text-slate-700">{{ monthLabel }}</span>
      <button
        type="button"
        @click="shiftMonth(1)"
        class="rounded-lg p-1 text-slate-500 hover:bg-slate-100"
        aria-label="Next month"
      >
        <ChevronRightIcon class="h-4 w-4" />
      </button>
    </div>

    <div class="mt-1 grid grid-cols-7 text-center text-[10px] font-semibold uppercase text-slate-400">
      <span v-for="d in WEEKDAYS" :key="d" class="py-1">{{ d }}</span>
    </div>
    <div class="grid grid-cols-7 gap-y-0.5" @mouseleave="hover = ''">
      <span v-for="n in leadingBlanks" :key="`b${n}`" />
      <button
        v-for="day in days"
        :key="day.iso"
        type="button"
        :disabled="day.disabled"
        @click="pick(day.iso)"
        @mouseenter="hover = day.iso"
        :aria-pressed="day.isEdge"
        :aria-label="day.label"
        :title="day.marked ? `${day.label} - already on hold` : day.label"
        :class="[
          'relative h-8 text-xs transition-colors disabled:cursor-not-allowed disabled:text-slate-300',
          day.inRange && !day.isEdge ? 'bg-slate-100 text-slate-900' : '',
          day.isStart ? (day.isEnd || !day.inRange ? 'rounded-lg' : 'rounded-l-lg') : day.isEnd ? 'rounded-r-lg' : '',
          day.isEdge ? 'bg-app-accent font-semibold text-white' : '',
          !day.inRange && !day.isEdge && !day.disabled ? 'rounded-lg text-slate-700 hover:bg-slate-100' : '',
          day.isToday && !day.isEdge ? 'font-semibold text-app-accent' : '',
        ]"
      >
        {{ day.date }}
        <span
          v-if="day.marked"
          :class="['absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full', day.isEdge ? 'bg-white' : 'bg-amber-500']"
        />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/vue/24/outline'

// Inline single-month range picker. First click sets the start, second click
// the end (clicking a day before the start starts over; clicking the start
// again makes a one-day range). Dates are local "YYYY-MM-DD" strings.
const props = defineProps<{
  start: string
  end: string
  min?: string
  // Days to flag with a dot, e.g. dates already on hold.
  marked?: Set<string>
}>()
const emit = defineEmits<{ (e: 'update:start', v: string): void; (e: 'update:end', v: string): void }>()

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function parse(value: string) {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

const todayIso = iso(new Date())
const initial = parse(props.start || props.min || todayIso)
const view = ref({ year: initial.getFullYear(), month: initial.getMonth() })
const hover = ref('')

// Follow the selection when it's set from outside (e.g. cleared after adding).
watch(() => props.start, (value) => {
  if (!value) return
  const d = parse(value)
  view.value = { year: d.getFullYear(), month: d.getMonth() }
})

const monthLabel = computed(() =>
  new Date(view.value.year, view.value.month, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' }))

const canGoBack = computed(() => {
  if (!props.min) return true
  const min = parse(props.min)
  return view.value.year * 12 + view.value.month > min.getFullYear() * 12 + min.getMonth()
})

function shiftMonth(delta: number) {
  const d = new Date(view.value.year, view.value.month + delta, 1)
  view.value = { year: d.getFullYear(), month: d.getMonth() }
}

// Monday-first offset of the 1st of the month.
const leadingBlanks = computed(() => (new Date(view.value.year, view.value.month, 1).getDay() + 6) % 7)

const days = computed(() => {
  const { year, month } = view.value
  const count = new Date(year, month + 1, 0).getDate()
  // While choosing the end, preview the range up to the hovered day.
  const rangeEnd = props.end || (props.start && hover.value >= props.start ? hover.value : '')
  return Array.from({ length: count }, (_, i) => {
    const date = new Date(year, month, i + 1)
    const value = iso(date)
    const isStart = value === props.start
    const isEnd = !!rangeEnd && value === rangeEnd
    return {
      iso: value,
      date: i + 1,
      label: date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
      disabled: !!props.min && value < props.min,
      isStart,
      isEnd,
      isEdge: isStart || (!!props.end && value === props.end),
      inRange: !!props.start && !!rangeEnd && value >= props.start && value <= rangeEnd,
      isToday: value === todayIso,
      marked: !!props.marked?.has(value),
    }
  })
})

function pick(value: string) {
  if (!props.start || props.end || value < props.start) {
    emit('update:start', value)
    emit('update:end', '')
  } else {
    emit('update:end', value)
  }
}
</script>
