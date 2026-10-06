<template>
  <div class="neu-card p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 class="flex items-center gap-1.5 text-sm font-semibold text-app-tertiary">
        <ClockIcon class="h-4 w-4" />
        Schedule
      </h2>
      <span
        :class="[
          'inline-flex shrink-0 items-center whitespace-nowrap gap-1.5 rounded-full bg-app-primary px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm',
          schedulerOnline ? 'text-emerald-700' : 'text-rose-700',
        ]"
        :title="schedulerLastSeenText"
      >
        <span :class="['h-1.5 w-1.5 rounded-full', schedulerOnline ? 'bg-emerald-500' : 'bg-rose-500']" />
        {{ schedulerOnline ? 'Scheduler online' : 'Scheduler offline' }}
      </span>
    </div>

    <div v-if="loadError" class="mt-3 rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
      {{ loadError }}
    </div>

    <div v-else-if="server" class="mt-3 space-y-3 text-xs">
      <p v-if="!schedulerOnline && form.enabled" class="rounded-lg bg-app-primary px-3 py-2 font-semibold text-amber-700 shadow-neu-inset-sm">
        The scheduler container isn't checking in, so no scheduled runs will happen until it's running again.
      </p>

      <!-- On/off -->
      <label class="flex cursor-pointer items-center justify-between gap-2">
        <span class="font-semibold text-slate-600">Run automatically</span>
        <button
          type="button"
          role="switch"
          :aria-checked="form.enabled"
          @click="form.enabled = !form.enabled"
          :class="[
            'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full shadow-neu-inset-sm transition-colors',
            form.enabled ? 'bg-app-accent' : 'bg-app-primary',
          ]"
        >
          <span :class="['inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-neu-sm transition-transform', form.enabled ? 'translate-x-[20px]' : 'translate-x-0.5']" />
        </button>
      </label>

      <!-- Interval -->
      <div class="flex items-center justify-between gap-2">
        <label for="schedule-interval" class="font-semibold text-slate-600">Every</label>
        <select id="schedule-interval" v-model.number="form.intervalMinutes" class="neu-input w-36 py-1">
          <option v-for="opt in intervalOptions" :key="opt" :value="opt">{{ formatInterval(opt) }}</option>
        </select>
      </div>

      <!-- Mode -->
      <div class="space-y-1">
        <span class="font-semibold text-slate-600">Mode</span>
        <label class="flex cursor-pointer items-start gap-2">
          <input type="radio" :value="false" v-model="form.live" class="mt-0.5 h-3 w-3 accent-app-accent" />
          <span>Preview <span class="text-slate-500">— allotment dry run, BAR step off. Nothing is sent to the PMS or D-EDGE.</span></span>
        </label>
        <label class="flex cursor-pointer items-start gap-2">
          <input type="radio" :value="true" v-model="form.live" class="mt-0.5 h-3 w-3 accent-rose-600" />
          <span :class="form.live ? 'font-semibold text-rose-700' : ''">Live <span class="font-normal text-slate-500">— pushes allotments to the PMS and BAR prices to D-EDGE.</span></span>
        </label>
      </div>

      <!-- Run config -->
      <div class="rounded-lg bg-app-primary p-3 shadow-neu-inset-sm">
        <div class="flex items-center justify-between gap-2">
          <span class="font-semibold text-slate-600">Run settings</span>
          <span v-if="configDirty" class="text-[11px] font-semibold text-amber-700">unsaved</span>
        </div>
        <p class="mt-1 text-slate-500">{{ configSourceText }}</p>
        <ul v-if="configSummary.length" class="mt-1.5 space-y-0.5 text-slate-600">
          <li v-for="line in configSummary" :key="line">{{ line }}</li>
        </ul>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <button
            type="button"
            @click="useCurrentPageSettings"
            class="rounded-lg bg-app-primary px-2 py-1 font-semibold text-app-accent shadow-neu-sm active:shadow-neu-inset-sm"
            title="Steps, room types, skip-unchanged options, concurrency, company ID and the yield configuration currently set on this page. Credentials and start date are never stored - scheduled runs use the server's credentials and today's date."
          >
            Use this page's settings
          </button>
          <button
            v-if="effectiveSource === 'custom'"
            type="button"
            @click="pendingConfig = null"
            class="rounded-lg bg-app-primary px-2 py-1 font-semibold text-slate-500 shadow-neu-sm active:shadow-neu-inset-sm"
          >
            Revert to default
          </button>
        </div>
        <p v-if="snapshotError" class="mt-1.5 font-semibold text-rose-700">{{ snapshotError }}</p>
      </div>

      <!-- Timing -->
      <div class="space-y-1 text-slate-600">
        <p>
          <span class="font-semibold">Next run:</span>
          {{ nextRunText }}
        </p>
        <p>
          <span class="font-semibold">Last scheduled run:</span>{{ ' ' }}
          <template v-if="lastRun">
            <span :class="lastRunClass">{{ lastRun.status }}</span>
            · {{ formatDateTime(lastRun.started_at) }}
            <router-link to="/fast-pipeline-history" class="ml-1 font-semibold text-app-accent hover:underline">History</router-link>
          </template>
          <span v-else class="text-slate-500">none yet</span>
        </p>
        <p v-if="pipelineActive" class="font-semibold text-amber-700">A pipeline run is in progress right now.</p>
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          @click="discardChanges"
          :disabled="!dirty || saving"
          class="flex-1 rounded-xl bg-app-primary px-3 py-2 font-semibold text-slate-600 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm disabled:opacity-50"
        >
          Discard
        </button>
        <button
          type="button"
          @click="requestSave"
          :disabled="!dirty || saving"
          :class="form.enabled && form.live ? 'bg-rose-600 hover:bg-rose-700' : 'bg-app-accent hover:brightness-110'"
          class="flex-1 rounded-xl px-3 py-2 font-semibold text-white shadow-neu-sm transition-colors disabled:opacity-50"
        >
          {{ saving ? 'Saving…' : 'Save schedule' }}
        </button>
      </div>
      <p v-if="saveError" class="rounded-lg bg-app-primary px-3 py-2 font-semibold text-rose-700 shadow-neu-inset-sm">{{ saveError }}</p>
      <p v-if="saveNotice" class="text-center font-semibold text-emerald-700">{{ saveNotice }}</p>
    </div>

    <div v-else class="mt-3 flex items-center gap-2 text-xs text-slate-500">
      <span class="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-app-accent"></span>
      Loading schedule…
    </div>

    <!-- Confirm before saving a live schedule -->
    <div v-if="showLiveConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-500/20 p-4 backdrop-blur-sm">
      <div class="relative w-full max-w-md rounded-xl bg-app-primary p-6 shadow-neu">
        <h3 class="flex items-center gap-2 text-base font-semibold text-app-tertiary">
          <ExclamationTriangleIcon class="h-5 w-5 shrink-0 text-amber-600" />
          Save a LIVE schedule?
        </h3>
        <div class="mt-3 space-y-2 rounded-xl bg-app-primary p-4 text-sm text-slate-600 shadow-neu-inset">
          <p class="font-semibold text-rose-700">Every {{ formatInterval(form.intervalMinutes) }}, unattended:</p>
          <ul class="list-disc space-y-0.5 pl-5">
            <li v-for="line in liveConfirmLines" :key="line">{{ line }}</li>
          </ul>
          <p>{{ firstRunText }}</p>
        </div>
        <p class="mt-3 rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-amber-700 shadow-neu-inset-sm">
          Only one machine should run a live schedule — make sure no other copy of this app (e.g. the Mac) is pushing to the same PMS and D-EDGE accounts.
        </p>
        <div class="mt-5 flex gap-3">
          <button
            type="button"
            @click="showLiveConfirm = false"
            class="flex-1 rounded-xl bg-app-primary px-4 py-2.5 text-sm font-semibold text-slate-600 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            @click="save"
            class="flex-1 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white shadow-neu-sm transition-colors hover:bg-rose-700"
          >
            Yes, save LIVE schedule
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from '../plugins/axios'
import { ClockIcon, ExclamationTriangleIcon } from '@heroicons/vue/24/outline'

export interface ScheduleRunConfig {
  steps?: Record<string, boolean>
  barRooms?: string[]
  allotmentRoomTypes?: string[]
  yieldConfig: Record<string, unknown>
  skipUnchanged?: boolean
  barSkipUnchanged?: boolean
  allotmentConcurrency?: number
  companyId?: number
}

interface ScheduleState {
  enabled: boolean
  intervalMinutes: number
  live: boolean
  config: ScheduleRunConfig | null
  configSavedAt: string | null
  configSource: 'default' | 'custom'
  effectiveConfig: ScheduleRunConfig | null
  defaultConfig: ScheduleRunConfig | null
  nextRunAt: string | null
  lastRunAt: string | null
  schedulerOnline: boolean
  schedulerLastSeen: string | null
}

interface RunSummary {
  id: number
  status: string
  started_at: string
  finished_at: string | null
  error: string | null
}

const props = defineProps<{
  // Snapshot of the page's current run settings; throws on invalid input.
  pageConfig: () => ScheduleRunConfig
  stepLabel: (id: string) => string
}>()

const POLL_MS = 15000
const BASE_INTERVALS = [15, 30, 60, 120, 180, 360, 720, 1440]

const server = ref<ScheduleState | null>(null)
const lastRun = ref<RunSummary | null>(null)
const pipelineActive = ref(false)
const loadError = ref('')

const form = ref({ enabled: false, intervalMinutes: 60, live: false })
// undefined = config unchanged; null = revert to default; object = new snapshot
const pendingConfig = ref<ScheduleRunConfig | null | undefined>(undefined)
const snapshotError = ref('')
const saving = ref(false)
const saveError = ref('')
const saveNotice = ref('')
const showLiveConfirm = ref(false)
const now = ref(Date.now())

const configDirty = computed(() => pendingConfig.value !== undefined)
const dirty = computed(() => {
  const s = server.value
  if (!s) return false
  return (
    form.value.enabled !== s.enabled ||
    form.value.intervalMinutes !== s.intervalMinutes ||
    form.value.live !== s.live ||
    configDirty.value
  )
})

function resetForm() {
  const s = server.value
  if (!s) return
  form.value = { enabled: s.enabled, intervalMinutes: s.intervalMinutes, live: s.live }
  pendingConfig.value = undefined
  snapshotError.value = ''
}

async function load() {
  try {
    const res = await axios.get('/api/fast-pipeline/schedule')
    const wasDirty = dirty.value
    server.value = res.data.schedule
    lastRun.value = res.data.lastScheduledRun
    pipelineActive.value = res.data.pipelineActive
    loadError.value = ''
    // Background refreshes must not clobber edits in progress.
    if (!wasDirty) resetForm()
  } catch (err: any) {
    if (!server.value) loadError.value = err?.response?.data?.message || 'Could not load the schedule.'
  }
}

let pollTimer: ReturnType<typeof setInterval> | undefined
let clockTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  load()
  pollTimer = setInterval(load, POLL_MS)
  clockTimer = setInterval(() => { now.value = Date.now() }, 30000)
})
onBeforeUnmount(() => {
  clearInterval(pollTimer)
  clearInterval(clockTimer)
})

const schedulerOnline = computed(() => server.value?.schedulerOnline ?? false)
const schedulerLastSeenText = computed(() =>
  server.value?.schedulerLastSeen ? `Last check-in: ${formatDateTime(server.value.schedulerLastSeen)}` : 'No check-in since the backend started'
)

const intervalOptions = computed(() => {
  const opts = new Set(BASE_INTERVALS)
  if (server.value) opts.add(server.value.intervalMinutes)
  opts.add(form.value.intervalMinutes)
  return [...opts].sort((a, b) => a - b)
})

function formatInterval(minutes: number) {
  if (minutes % 60 === 0) {
    const h = minutes / 60
    return h === 1 ? '1 hour' : `${h} hours`
  }
  return `${minutes} minutes`
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatRelative(iso: string) {
  const diffMin = Math.round((new Date(iso).getTime() - now.value) / 60000)
  if (diffMin <= 0) return 'due now'
  if (diffMin < 60) return `in ${diffMin} min`
  const h = Math.floor(diffMin / 60)
  const m = diffMin % 60
  return m ? `in ${h} h ${m} min` : `in ${h} h`
}

const nextRunText = computed(() => {
  const s = server.value
  if (!s?.enabled || !s.nextRunAt) return 'not scheduled (off)'
  return `${formatDateTime(s.nextRunAt)} (${formatRelative(s.nextRunAt)})`
})

const lastRunClass = computed(() => {
  const status = lastRun.value?.status
  if (status === 'success') return 'font-semibold text-emerald-700'
  if (status === 'error') return 'font-semibold text-rose-700'
  return 'font-semibold text-amber-700'
})

const effectiveSource = computed<'default' | 'custom'>(() => {
  if (pendingConfig.value === null) return 'default'
  if (pendingConfig.value) return 'custom'
  return server.value?.configSource ?? 'default'
})

const effectiveConfig = computed<ScheduleRunConfig | null>(() => {
  if (pendingConfig.value) return pendingConfig.value
  if (pendingConfig.value === null) return server.value?.defaultConfig ?? null
  return server.value?.effectiveConfig ?? null
})

const configSourceText = computed(() => {
  if (pendingConfig.value) return 'Settings taken from this page (not saved yet).'
  if (pendingConfig.value === null) return 'Reverting to the default scheduled config (scheduled_fast_pipeline_config.json).'
  if (server.value?.configSource === 'custom') return `Saved from this page on ${formatDateTime(server.value.configSavedAt)}.`
  return 'Default scheduled config (scheduled_fast_pipeline_config.json).'
})

const BAR_LABELS: Record<string, string> = { deluxe: 'Deluxe', premiere: 'Premiere' }

const configSummary = computed(() => {
  const c = effectiveConfig.value
  if (!c) return []
  const lines: string[] = []
  const steps = c.steps || {}
  const off = Object.entries(steps).filter(([, on]) => on === false).map(([id]) => props.stepLabel(id))
  lines.push(off.length ? `Steps skipped: ${off.join(', ')}` : 'All steps enabled')
  const allotmentOn = steps.allotment !== false
  const roomCount = c.allotmentRoomTypes ? c.allotmentRoomTypes.length : 2
  lines.push(allotmentOn ? `Allotment: ${roomCount} room type(s)${form.value.live ? ' — LIVE' : ' — dry run'}` : 'Allotment: off')
  const barRooms = (c.barRooms ?? ['deluxe', 'premiere']).map(r => BAR_LABELS[r] || r)
  if (!form.value.live) lines.push('BAR: off (preview mode)')
  else if (steps.bar === false || barRooms.length === 0) lines.push('BAR: off')
  else lines.push(`BAR: ${barRooms.join(', ')} — LIVE`)
  return lines
})

const liveConfirmLines = computed(() => configSummary.value.filter(l => !l.startsWith('Steps')))

const firstRunText = computed(() => {
  const s = server.value
  if (!s?.enabled) return 'The first run starts within about 30 seconds of saving.'
  if (form.value.intervalMinutes !== s.intervalMinutes) return 'The next run is re-timed from the last run using the new interval (immediately if that time has already passed).'
  return s.nextRunAt ? `The next run stays at ${formatDateTime(s.nextRunAt)}.` : 'The first run starts within about 30 seconds of saving.'
})

function useCurrentPageSettings() {
  snapshotError.value = ''
  try {
    pendingConfig.value = props.pageConfig()
  } catch (err: any) {
    snapshotError.value = err instanceof Error ? err.message : 'This page has invalid settings.'
  }
}

function discardChanges() {
  resetForm()
  saveError.value = ''
}

function requestSave() {
  saveError.value = ''
  saveNotice.value = ''
  if (form.value.enabled && form.value.live) {
    showLiveConfirm.value = true
    return
  }
  save()
}

async function save() {
  showLiveConfirm.value = false
  saving.value = true
  saveError.value = ''
  const payload: Record<string, unknown> = { ...form.value }
  if (pendingConfig.value !== undefined) payload.config = pendingConfig.value
  try {
    const res = await axios.put('/api/fast-pipeline/schedule', payload)
    server.value = res.data.schedule
    resetForm()
    saveNotice.value = 'Schedule saved.'
    setTimeout(() => { saveNotice.value = '' }, 4000)
  } catch (err: any) {
    saveError.value = err?.response?.data?.message || 'Could not save the schedule.'
  } finally {
    saving.value = false
  }
}
</script>
