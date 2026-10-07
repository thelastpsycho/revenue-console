<template>
  <div class="neu-card p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 class="flex items-center gap-1.5 text-sm font-semibold text-app-tertiary">
        <NoSymbolIcon class="h-4 w-4" />
        BAR hold dates
      </h2>
      <span
        v-if="holds.length"
        class="inline-flex shrink-0 items-center whitespace-nowrap rounded-full bg-app-primary px-2.5 py-1 text-[11px] font-semibold text-amber-700 shadow-neu-inset-sm"
      >
        {{ holds.length }} active
      </span>
    </div>

    <div class="mt-3 space-y-3 text-xs text-slate-600">
      <p class="text-slate-500">
        BAR updates leave these dates alone on D-EDGE (all runs, scheduled or manual) until you remove the hold.
        Allotment is not affected. Holds drop off once their dates have passed.
      </p>

      <p v-if="loadError" class="font-semibold text-rose-700">{{ loadError }}</p>

      <p v-if="checkpointPending" class="rounded-lg bg-app-primary px-3 py-2 font-semibold text-amber-700 shadow-neu-inset-sm">
        A BAR run didn't finish. Changing holds changes its plan, so the next run will stop until you tick
        "Start a fresh BAR batch" - check D-EDGE first.
      </p>

      <!-- Active holds -->
      <ul v-if="holds.length" class="space-y-1.5">
        <li
          v-for="hold in holds"
          :key="hold.id"
          class="flex items-start justify-between gap-2 rounded-lg bg-app-primary px-3 py-2 shadow-neu-inset-sm"
        >
          <div class="min-w-0">
            <p class="font-semibold text-slate-700">{{ formatRange(hold.start, hold.end) }}</p>
            <p class="text-slate-500">
              {{ hold.rooms.map(roomLabel).join(', ') }}<template v-if="hold.note"> · {{ hold.note }}</template>
            </p>
          </div>
          <button
            type="button"
            :disabled="busy"
            @click="remove(hold)"
            class="shrink-0 rounded-lg px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            :aria-label="`Remove hold ${formatRange(hold.start, hold.end)}`"
          >
            Remove
          </button>
        </li>
      </ul>
      <p v-else-if="loaded" class="text-slate-500">No dates on hold.</p>

      <!-- Add -->
      <form class="space-y-2 rounded-lg bg-app-primary p-3 shadow-neu-inset-sm" @submit.prevent="add">
        <DateRangeCalendar
          v-model:start="form.start"
          v-model:end="form.end"
          :min="today"
          :marked="heldDays"
        />
        <div class="flex items-center justify-between gap-2">
          <span :class="form.start ? 'font-semibold text-slate-700' : 'text-slate-500'">{{ selectionText }}</span>
          <button
            v-if="form.start"
            type="button"
            @click="form.start = ''; form.end = ''"
            class="shrink-0 rounded-lg px-2 py-0.5 font-semibold text-slate-500 hover:bg-slate-100"
          >
            Clear
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span class="font-semibold text-slate-600">Rooms</span>
          <label v-for="room in ROOMS" :key="room" class="flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" :value="room" v-model="form.rooms" class="h-3 w-3 accent-app-accent" />
            {{ roomLabel(room) }}
          </label>
        </div>
        <input
          v-model="form.note"
          type="text"
          maxlength="200"
          placeholder="Note (optional), e.g. wedding buyout - manual rate"
          class="neu-input w-full py-1"
        />
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            :disabled="busy || !form.start || !form.rooms.length"
            class="rounded-lg bg-app-primary px-2 py-1 font-semibold text-app-accent shadow-neu-sm active:shadow-neu-inset-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            Add hold
          </button>
          <span v-if="formError" class="font-semibold text-rose-700">{{ formError }}</span>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '../plugins/axios'
import { NoSymbolIcon } from '@heroicons/vue/24/outline'
import DateRangeCalendar from './DateRangeCalendar.vue'

interface BarHold {
  id: string
  start: string
  end: string
  rooms: string[]
  note: string
}

const ROOMS = ['deluxe', 'premiere']
const roomLabel = (room: string) => room.charAt(0).toUpperCase() + room.slice(1)

function localIsoDate(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const today = localIsoDate()

const holds = ref<BarHold[]>([])
const checkpointPending = ref(false)
const loaded = ref(false)
const loadError = ref('')
const formError = ref('')
const busy = ref(false)
const form = reactive({ start: '', end: '', rooms: [...ROOMS], note: '' })

function formatDay(iso: string, withYear: boolean) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}),
  })
}
function formatRange(start: string, end: string) {
  return start === end ? formatDay(start, true) : `${formatDay(start, false)} – ${formatDay(end, true)}`
}

// Every day covered by an existing hold, flagged with a dot in the calendar.
const heldDays = computed(() => {
  const days = new Set<string>()
  for (const hold of holds.value) {
    const [y, m, d] = hold.start.split('-').map(Number)
    for (let day = new Date(y, m - 1, d); localIsoDate(day) <= hold.end; day.setDate(day.getDate() + 1)) {
      days.add(localIsoDate(day))
    }
  }
  return days
})

const selectionText = computed(() => {
  if (!form.start) return 'Pick the first day on the calendar'
  if (!form.end) return `${formatDay(form.start, true)} - pick the last day, or add as a single day`
  const [y1, m1, d1] = form.start.split('-').map(Number)
  const [y2, m2, d2] = form.end.split('-').map(Number)
  const count = Math.round((new Date(y2, m2 - 1, d2).getTime() - new Date(y1, m1 - 1, d1).getTime()) / 86400000) + 1
  return `${formatRange(form.start, form.end)} (${count} day${count === 1 ? '' : 's'})`
})

async function load() {
  try {
    const res = await axios.get('/api/bar/holds')
    holds.value = res.data.holds
    checkpointPending.value = res.data.checkpointPending
    loadError.value = ''
  } catch (err: any) {
    loadError.value = err?.response?.data?.message || 'Could not load hold dates.'
  } finally {
    loaded.value = true
  }
}

async function add() {
  busy.value = true
  formError.value = ''
  try {
    await axios.post('/api/bar/holds', {
      start: form.start,
      end: form.end || form.start,
      rooms: form.rooms,
      note: form.note,
    })
    Object.assign(form, { start: '', end: '', rooms: [...ROOMS], note: '' })
    await load()
  } catch (err: any) {
    formError.value = err?.response?.data?.message || 'Could not add the hold.'
  } finally {
    busy.value = false
  }
}

async function remove(hold: BarHold) {
  if (!window.confirm(`Remove the hold on ${formatRange(hold.start, hold.end)}? The next live run will update BAR on these dates again.`)) return
  busy.value = true
  try {
    await axios.delete(`/api/bar/holds/${hold.id}`)
  } catch (err: any) {
    loadError.value = err?.response?.data?.message || 'Could not remove the hold.'
  } finally {
    busy.value = false
    await load()
  }
}

onMounted(load)
</script>
