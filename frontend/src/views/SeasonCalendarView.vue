<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Season Calendar"
      subtitle="Named date ranges that drive the yield engine's season tier (Peak / High / Shoulder / Normal) - Nyepi, Lunar New Year, Lebaran, Easter, Australian school holidays, events, and the Jul-Aug / Christmas-New Year ranges. Add next year's dates as they're confirmed; overlapping ranges resolve to the higher tier."
    />

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-12">
      <!-- Add / edit -->
      <div class="xl:col-span-4">
        <form class="neu-card space-y-3 p-4 text-xs" @submit.prevent="save">
          <div class="flex items-center justify-between gap-2">
            <h2 class="text-sm font-semibold text-app-tertiary">{{ editingId ? 'Edit period' : 'Add period' }}</h2>
            <button v-if="editingId" type="button" class="font-semibold text-slate-500 hover:text-slate-900" @click="resetForm">Cancel</button>
          </div>
          <div>
            <label for="sc-label" class="mb-1 block font-semibold text-slate-600">Label</label>
            <input id="sc-label" v-model="form.label" required maxlength="200" class="neu-input" placeholder="e.g. Nyepi 2027" />
          </div>
          <div>
            <label class="mb-1 block font-semibold text-slate-600">Tier</label>
            <select v-model="form.tier" required class="neu-input">
              <option v-for="t in TIERS" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <DateRangeCalendar v-model:start="form.startDate" v-model:end="form.endDate" :marked="coveredDays" />
          <div class="flex items-center justify-between gap-2">
            <span :class="form.startDate ? 'font-semibold text-slate-700' : 'text-slate-500'">{{ selectionText }}</span>
            <button
              v-if="form.startDate"
              type="button"
              @click="form.startDate = ''; form.endDate = ''"
              class="shrink-0 rounded-lg px-2 py-0.5 font-semibold text-slate-500 hover:bg-slate-100"
            >
              Clear
            </button>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button type="submit" class="btn-primary py-1.5 text-xs" :disabled="busy || !form.startDate">
              {{ editingId ? 'Save changes' : 'Add period' }}
            </button>
            <span v-if="formError" class="font-semibold text-rose-700">{{ formError }}</span>
          </div>
        </form>
      </div>

      <!-- List -->
      <div class="neu-card overflow-hidden xl:col-span-8">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
          <h2 class="text-sm font-semibold text-app-tertiary">
            Periods
            <span class="ml-1 font-normal text-slate-500">{{ periods.length }}</span>
          </h2>
        </div>
        <p v-if="loadError" class="p-4 text-xs font-semibold text-rose-700">{{ loadError }}</p>
        <p v-else-if="loaded && !periods.length" class="p-4 text-xs text-slate-500">
          No periods yet. Add one on the left.
        </p>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-xs">
            <thead class="bg-app-primary">
              <tr>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Label</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Dates</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Tier</th>
                <th class="px-4 py-2.5"><span class="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="p in sortedPeriods" :key="p.id">
                <td class="px-4 py-2 font-semibold">{{ p.label }}</td>
                <td class="whitespace-nowrap px-4 py-2">{{ formatRange(p.startDate, p.endDate) }}</td>
                <td class="px-4 py-2">
                  <span :class="['rounded-full px-2 py-0.5 font-semibold', tierBadgeClass(p.tier)]">{{ p.tier }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-2 text-right">
                  <button type="button" class="rounded px-2 py-1 font-semibold text-slate-600 hover:bg-slate-100" @click="edit(p)">Edit</button>
                  <button type="button" class="rounded px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50" :disabled="busy" @click="remove(p)">Delete</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '../plugins/axios'
import { confirmDialog } from '../composables/useDialog'
import PageHeader from '../components/PageHeader.vue'
import DateRangeCalendar from '../components/DateRangeCalendar.vue'

interface SeasonPeriod {
  id: number
  label: string
  startDate: string
  endDate: string
  tier: 'Peak' | 'High' | 'Shoulder' | 'Normal'
}

const TIERS = ['Peak', 'High', 'Shoulder', 'Normal'] as const
const TIER_BADGE_CLASS: Record<string, string> = {
  Peak: 'bg-rose-100 text-rose-700',
  High: 'bg-amber-100 text-amber-700',
  Shoulder: 'bg-sky-100 text-sky-700',
  Normal: 'bg-slate-100 text-slate-600',
}
const tierBadgeClass = (tier: string) => TIER_BADGE_CLASS[tier] || TIER_BADGE_CLASS.Normal

function localIsoDate(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const periods = ref<SeasonPeriod[]>([])
const loaded = ref(false)
const loadError = ref('')
const busy = ref(false)
const formError = ref('')
const editingId = ref<number | null>(null)
const form = reactive<{ label: string; startDate: string; endDate: string; tier: 'Peak' | 'High' | 'Shoulder' | 'Normal' }>({
  label: '', startDate: '', endDate: '', tier: 'High',
})

const sortedPeriods = computed(() => [...periods.value].sort((a, b) => a.startDate.localeCompare(b.startDate)))

function formatDay(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}
function formatRange(start: string, end: string) {
  return start === end ? formatDay(start) : `${formatDay(start)} – ${formatDay(end)}`
}

// Every day already covered by an existing period, dotted in the calendar.
const coveredDays = computed(() => {
  const days = new Set<string>()
  for (const p of periods.value) {
    if (editingId.value === p.id) continue
    const [y, m, d] = p.startDate.split('-').map(Number)
    for (let day = new Date(y, m - 1, d); localIsoDate(day) <= p.endDate; day.setDate(day.getDate() + 1)) {
      days.add(localIsoDate(day))
    }
  }
  return days
})

const selectionText = computed(() => {
  if (!form.startDate) return 'Pick the first day on the calendar'
  if (!form.endDate) return `${formatDay(form.startDate)} - pick the last day, or add as a single day`
  return formatRange(form.startDate, form.endDate)
})

const message = (err: any, fallback: string) => err?.response?.data?.message || fallback

async function load() {
  try {
    const res = await axios.get('/api/season-calendar/periods')
    periods.value = res.data.periods
    loadError.value = ''
  } catch (err: any) {
    loadError.value = message(err, 'Could not load the season calendar.')
  } finally {
    loaded.value = true
  }
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { label: '', startDate: '', endDate: '', tier: 'High' })
  formError.value = ''
}

function edit(p: SeasonPeriod) {
  editingId.value = p.id
  Object.assign(form, { label: p.label, startDate: p.startDate, endDate: p.endDate, tier: p.tier })
  formError.value = ''
}

async function save() {
  busy.value = true
  formError.value = ''
  const payload = { label: form.label, startDate: form.startDate, endDate: form.endDate || form.startDate, tier: form.tier }
  try {
    if (editingId.value) await axios.put(`/api/season-calendar/periods/${editingId.value}`, payload)
    else await axios.post('/api/season-calendar/periods', payload)
    resetForm()
    await load()
  } catch (err: any) {
    formError.value = message(err, 'Could not save the period.')
  } finally {
    busy.value = false
  }
}

async function remove(p: SeasonPeriod) {
  const ok = await confirmDialog({
    tone: 'warning',
    title: 'Delete period?',
    message: 'Dates in this range fall back to whatever tier another period assigns them, or Normal if none do.',
    details: [
      { label: 'Label', value: p.label },
      { label: 'Dates', value: formatRange(p.startDate, p.endDate) },
      { label: 'Tier', value: p.tier },
    ],
    confirmText: 'Delete',
  })
  if (!ok) return
  busy.value = true
  try {
    await axios.delete(`/api/season-calendar/periods/${p.id}`)
    if (editingId.value === p.id) resetForm()
  } catch (err: any) {
    loadError.value = message(err, 'Could not delete the period.')
  } finally {
    busy.value = false
    await load()
  }
}

onMounted(load)
</script>
