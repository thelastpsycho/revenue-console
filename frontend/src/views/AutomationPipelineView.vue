<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Pipeline"
      subtitle="Run the entire scrape-to-BAR-pricing pipeline end-to-end with one click."
    />

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <!-- Left: status + stepper + log -->
      <div class="space-y-4 lg:col-span-2">
        <!-- Status / stepper card -->
        <div class="neu-card p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-app-tertiary">Pipeline status</h2>
              <p class="mt-0.5 text-xs text-slate-500">{{ progressLabel }}</p>
            </div>
            <div class="flex items-center gap-2">
              <div class="flex items-center gap-2">
                <div class="h-1.5 w-24 overflow-hidden rounded-full bg-app-primary shadow-neu-inset-sm">
                  <div class="h-full rounded-full transition-all" :class="progressBarColor" :style="{ width: progressPercent + '%' }" />
                </div>
                <span class="text-[11px] font-semibold text-slate-500">{{ progressPercent }}%</span>
              </div>
              <button
                v-if="isRunning"
                type="button"
                @click="requestStop"
                :disabled="stopping"
                class="rounded-lg bg-app-primary px-2.5 py-1 text-xs font-semibold text-rose-600 shadow-neu-sm transition-all hover:text-rose-700 active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer"
              >
                Stop
              </button>
              <span
                :class="[
                  'inline-flex items-center gap-1.5 rounded-full bg-app-primary px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm',
                  isRunning ? 'text-amber-700' : overallError ? 'text-rose-700' : overallSuccess ? 'text-emerald-700' : 'text-slate-500',
                ]"
              >
                <span :class="['h-1.5 w-1.5 rounded-full', isRunning ? 'bg-amber-500 animate-pulse' : overallError ? 'bg-rose-500' : overallSuccess ? 'bg-emerald-500' : 'bg-slate-400']" />
                {{ isRunning ? 'Running' : overallError ? 'Failed' : overallSuccess ? 'Success' : 'Ready' }}
              </span>
            </div>
          </div>

          <!-- Compact horizontal stepper, with a per-step checkbox to include/skip it -->
          <div class="mt-4 flex flex-wrap items-center gap-1.5">
            <template v-for="(step, index) in stepStates" :key="step.id">
              <label
                class="flex cursor-pointer items-center gap-1.5 rounded-full bg-app-primary py-1 pl-1.5 pr-2.5 shadow-neu-inset-sm"
                :class="{
                  'ring-1 ring-app-accent/40': step.status === 'running',
                  'opacity-50': !stepEnabled[step.id],
                }"
                :title="step.label"
              >
                <input
                  type="checkbox"
                  class="h-3 w-3 cursor-pointer accent-app-accent disabled:cursor-not-allowed"
                  :checked="stepEnabled[step.id]"
                  :disabled="isRunning"
                  @change="toggleStep(step.id)"
                />
                <span v-if="step.status === 'pending'" class="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-300" />
                <span v-else-if="step.status === 'running'" class="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent" />
                <CheckCircleIcon v-else-if="step.status === 'success'" class="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                <MinusCircleIcon v-else-if="step.status === 'skipped'" class="h-3.5 w-3.5 shrink-0 text-slate-400" />
                <XCircleIcon v-else-if="step.status === 'error'" class="h-3.5 w-3.5 shrink-0 text-rose-600" />
                <span v-else class="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-300" />
                <span class="text-[11px] font-semibold text-slate-600">{{ step.label }}</span>
              </label>
              <span v-if="index < stepStates.length - 1" class="h-px w-2 shrink-0 bg-slate-300" />
            </template>
          </div>

          <!-- Room-type narrowing for the two steps that can target either room -->
          <div v-if="stepEnabled.allotment || stepEnabled.bar" class="mt-2 flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
            <div v-if="stepEnabled.allotment" class="flex items-center gap-2">
              <span class="font-semibold text-slate-600">Allotment rooms:</span>
              <label class="inline-flex cursor-pointer items-center gap-1">
                <input type="checkbox" v-model="allotmentRooms.deluxe" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Deluxe
              </label>
              <label class="inline-flex cursor-pointer items-center gap-1">
                <input type="checkbox" v-model="allotmentRooms.premiere" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Premiere
              </label>
              <label class="inline-flex cursor-pointer items-center gap-1" title="Compares against the current channel-manager value and skips dates that already match, instead of always pushing every date.">
                <input type="checkbox" v-model="skipUnchanged" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Skip unchanged dates
              </label>
            </div>
            <div v-if="stepEnabled.bar" class="flex items-center gap-2">
              <span class="font-semibold text-slate-600">BAR rooms:</span>
              <label class="inline-flex cursor-pointer items-center gap-1">
                <input type="checkbox" v-model="barRooms.deluxe" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Deluxe
              </label>
              <label class="inline-flex cursor-pointer items-center gap-1">
                <input type="checkbox" v-model="barRooms.premiere" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Premiere
              </label>
            </div>
          </div>

          <label v-if="stepEnabled.bar" class="mt-2 inline-flex items-start gap-2 text-xs text-amber-800">
            <input v-model="resetCheckpoint" type="checkbox" :disabled="isRunning" class="mt-0.5 accent-app-accent" />
            <span>Start a fresh BAR batch (discard partial-run checkpoint). Check existing D-EDGE changes before selecting.</span>
          </label>

          <button
            @click="startPipeline"
            :disabled="isRunning"
            class="btn-primary mt-4 w-full px-5 py-2.5"
          >
            <svg v-if="isRunning" class="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <BoltIcon v-else class="h-4 w-4" />
            {{ isRunning ? 'Pipeline running…' : 'Start pipeline' }}
          </button>
          <p v-if="isRunning" class="mt-2 text-center text-[11px] text-slate-400">
            Stop is best-effort — it may take effect only once the current step finishes.
          </p>
          <div v-if="configError" class="mt-3 rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
            {{ configError }}
          </div>
        </div>

        <!-- Unified process log, same pattern as Allotment.vue -->
        <div class="neu-card p-4">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-semibold text-app-tertiary">Process log</h2>
            <button
              @click="clearLogs"
              :disabled="isRunning"
              class="rounded-lg bg-app-primary px-2.5 py-1 text-xs font-semibold text-slate-500 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer"
            >
              Clear logs
            </button>
          </div>
          <div ref="logContainer" class="h-96 overflow-y-auto rounded-xl bg-app-primary p-4 shadow-neu-inset">
            <div v-if="logs.length === 0" class="py-8 text-center text-sm text-slate-500">
              No logs yet. Start the pipeline to see live progress.
            </div>
            <div v-else class="space-y-1.5">
              <div
                v-for="(log, index) in logs"
                :key="index"
                class="flex items-start gap-2 font-mono text-xs"
                :class="{
                  'text-app-accent': log.type === 'info',
                  'text-emerald-700': log.type === 'success',
                  'text-rose-600': log.type === 'error',
                  'text-slate-400': log.type === 'skipped',
                }"
              >
                <span class="text-slate-500">{{ formatTime(log.timestamp) }}</span>
                <span v-if="log.step" class="shrink-0 rounded bg-app-primary px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 shadow-neu-inset-sm">{{ stepLabel(log.step) }}</span>
                <span class="flex-1">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: compact config -->
      <div class="space-y-4 lg:col-span-1">
        <div class="neu-card p-4">
          <h2 class="text-sm font-semibold text-app-tertiary">Credentials &amp; run settings</h2>
          <div class="mt-3 space-y-3">
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="mb-1 block text-xs font-semibold text-slate-600">PMS username</label>
                <input v-model="pmsUsername" type="text" autocomplete="username" class="neu-input disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="mb-1 block text-xs font-semibold text-slate-600">PMS password</label>
                <input v-model="pmsPassword" type="password" autocomplete="current-password" class="neu-input disabled:opacity-60" :disabled="isRunning" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="mb-1 block text-xs font-semibold text-slate-600">D-EDGE username</label>
                <input v-model="dedgeUsername" type="text" autocomplete="off" class="neu-input disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="mb-1 block text-xs font-semibold text-slate-600">D-EDGE password</label>
                <input v-model="dedgePassword" type="password" autocomplete="off" class="neu-input disabled:opacity-60" :disabled="isRunning" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 items-end">
              <div>
                <label class="mb-1 block text-xs font-semibold text-slate-600">Start date</label>
                <input v-model="startDate" type="date" class="neu-input disabled:opacity-60" :disabled="isRunning" />
              </div>
              <label class="inline-flex cursor-pointer items-center gap-2 pb-2 text-xs font-semibold text-slate-500">
                <button
                  type="button"
                  role="switch"
                  :aria-checked="headless"
                  :disabled="isRunning"
                  @click="headless = !headless"
                  :class="[
                    'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full shadow-neu-inset-sm transition-colors disabled:opacity-50',
                    headless ? 'bg-app-accent' : 'bg-app-primary',
                  ]"
                >
                  <span :class="['inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-neu-sm transition-transform', headless ? 'translate-x-[20px]' : 'translate-x-0.5']" />
                </button>
                Headless
              </label>
            </div>
          </div>
        </div>

        <!-- Yield config, collapsed by default to save space -->
        <details class="neu-card overflow-hidden p-4">
          <summary class="cursor-pointer text-sm font-semibold text-app-tertiary">
            Yield configuration
            <span class="ml-1 text-xs font-normal text-slate-500">(same as Yield Management page)</span>
          </summary>
          <div class="mt-3 space-y-3">
            <div>
              <label class="block text-xs font-semibold text-slate-600">Demand bins</label>
              <input v-model="yieldForm.demand_bins" type="text" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" placeholder="[0, 70, 85, 100]" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600">Demand labels</label>
              <input v-model="yieldForm.demand_labels" type="text" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" placeholder="['Low', 'Medium', 'High']" />
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-xs font-semibold text-slate-600">Very low (%)</label>
                <input v-model.number="yieldForm.very_low_threshold_pct" type="number" step="0.01" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-600">Low (%)</label>
                <input v-model.number="yieldForm.low_threshold_pct" type="number" step="0.01" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-xs font-semibold text-slate-600">Deluxe rooms</label>
                <input v-model.number="yieldForm.room_caps['Deluxe Room']" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-600">Premiere rooms</label>
                <input v-model.number="yieldForm.room_caps['Premiere Room']" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
            </div>
            <div class="grid grid-cols-3 gap-2">
              <div>
                <label class="block text-xs font-semibold text-slate-600">Occupancy (%)</label>
                <input v-model.number="yieldForm.deluxe_override_occupancy" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-600">Premiere min</label>
                <input v-model.number="yieldForm.deluxe_override_premiere" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-600">Amount</label>
                <input v-model.number="yieldForm.deluxe_override_amount" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600">BAR shift levels</label>
              <input v-model.number="yieldForm.bar_level_shift" type="number" step="1" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
            </div>
          </div>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import { usePipelineStream, type PipelineStepDef } from '../composables/usePipelineStream'
import { todayLocalDateString } from '../utils/date'
import {
  BoltIcon,
  CheckCircleIcon,
  XCircleIcon,
  MinusCircleIcon,
} from '@heroicons/vue/24/outline'

const PIPELINE_STEPS: PipelineStepDef[] = [
  { id: 'scrape_pms', label: 'Scrape PMS' },
  { id: 'scrape_cm', label: 'Scrape CM' },
  { id: 'combine', label: 'Combine' },
  { id: 'yield', label: 'Yield' },
  { id: 'verify', label: 'Verify' },
  { id: 'allotment', label: 'Allotment' },
  { id: 'bar', label: 'BAR' },
]
const STEP_LABEL_BY_ID = Object.fromEntries(PIPELINE_STEPS.map(s => [s.id, s.label]))
const stepLabel = (id: string) => STEP_LABEL_BY_ID[id] || id

const { stepStates, logs, isRunning, overallError, overallSuccess, start } = usePipelineStream(PIPELINE_STEPS)

// Per-step include/skip toggles, e.g. uncheck "Allotment" (or just its
// Premiere room) to go straight from Verify to BAR.
const stepEnabled = ref<Record<string, boolean>>(
  Object.fromEntries(PIPELINE_STEPS.map(s => [s.id, true]))
)
function toggleStep(id: string) {
  if (isRunning.value) return
  stepEnabled.value[id] = !stepEnabled.value[id]
}

// Which rooms the Allotment/BAR steps should cover - unchecking a room here
// (while leaving the step itself checked) narrows that step instead of
// skipping it entirely.
const allotmentRooms = ref({ deluxe: true, premiere: true })
const barRooms = ref({ deluxe: true, premiere: true })
const resetCheckpoint = ref(false)
const skipUnchanged = ref(true)

const pmsUsername = ref('')
const pmsPassword = ref('')
const dedgeUsername = ref('')
const dedgePassword = ref('')
const startDate = ref(todayLocalDateString())
const headless = ref(false)
const configError = ref('')
const stopping = ref(false)
const logContainer = ref<HTMLElement | null>(null)

const formatTime = (date: Date) => date.toLocaleTimeString()

// Keep the newest log line in view, same pattern as Allotment.vue's single log panel.
watch(
  () => logs.value.length,
  () => {
    nextTick(() => {
      const el = logContainer.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
)

function clearLogs() {
  logs.value = []
}

interface YieldConfigForm {
  demand_bins: number[] | string
  demand_labels: string[] | string
  very_low_threshold_pct: number
  low_threshold_pct: number
  room_caps: {
    'Deluxe Room': number
    'Premiere Room': number
  }
  deluxe_override_occupancy: number
  deluxe_override_premiere: number
  deluxe_override_amount: number
  bar_level_shift: number
}

const defaultYieldConfig: YieldConfigForm = {
  demand_bins: [0, 70, 85, 100],
  demand_labels: ['Low', 'Medium', 'High'],
  very_low_threshold_pct: 5,
  low_threshold_pct: 20,
  room_caps: {
    'Deluxe Room': 160,
    'Premiere Room': 260,
  },
  deluxe_override_occupancy: 70,
  deluxe_override_premiere: 61,
  deluxe_override_amount: 2,
  bar_level_shift: 0,
}

const yieldForm = ref<YieldConfigForm>({
  ...defaultYieldConfig,
  room_caps: { ...defaultYieldConfig.room_caps },
})

// Same parse logic as YieldManagementView.vue's calculateYield(), so the payload we send
// as yieldConfig is byte-compatible with what /api/custom-yield already expects.
function parseArrayInput(input: string | any[]): any[] {
  if (Array.isArray(input)) return input
  const str = input.toString().trim()
  try {
    return JSON.parse(str.replace(/'/g, '"'))
  } catch {
    return str.split(',').map(item => item.trim())
  }
}

function buildYieldConfig() {
  const roomCaps = yieldForm.value.room_caps
  if (!roomCaps['Deluxe Room'] || !roomCaps['Premiere Room']) {
    throw new Error('Room capacities must be specified for both Deluxe Room and Premiere Room')
  }

  const parsed = {
    ...yieldForm.value,
    demand_bins: parseArrayInput(yieldForm.value.demand_bins).map(Number),
    demand_labels: parseArrayInput(yieldForm.value.demand_labels),
    room_caps: {
      'Deluxe Room': Number(roomCaps['Deluxe Room']),
      'Premiere Room': Number(roomCaps['Premiere Room']),
    },
  }

  if (
    isNaN(parsed.very_low_threshold_pct) ||
    isNaN(parsed.low_threshold_pct) ||
    isNaN(parsed.deluxe_override_occupancy) ||
    isNaN(parsed.deluxe_override_premiere) ||
    isNaN(parsed.deluxe_override_amount) ||
    isNaN(parsed.bar_level_shift)
  ) {
    throw new Error('All numeric values must be valid numbers')
  }

  return parsed
}

async function startPipeline() {
  configError.value = ''
  let yieldConfig
  try {
    yieldConfig = buildYieldConfig()
  } catch (err: any) {
    configError.value = err instanceof Error ? err.message : 'Invalid yield configuration'
    return
  }

  const allotmentRoomTypes = Object.entries(allotmentRooms.value).filter(([, v]) => v).map(([k]) => k)
  const barRoomTypes = Object.entries(barRooms.value).filter(([, v]) => v).map(([k]) => k)

  try {
    await start('/api/pipeline/start', {
      pmsUsername: pmsUsername.value,
      pmsPassword: pmsPassword.value,
      dedgeUsername: dedgeUsername.value,
      dedgePassword: dedgePassword.value,
      startDate: startDate.value,
      headless: headless.value,
      yieldConfig,
      steps: stepEnabled.value,
      allotmentRoomTypes,
      barRooms: barRoomTypes,
      resetCheckpoint: resetCheckpoint.value,
      skipUnchanged: skipUnchanged.value,
    })
  } catch {
    // overallError is already surfaced reactively by the composable
  }
}

async function requestStop() {
  stopping.value = true
  try {
    await axios.post('/api/pipeline/stop')
  } catch {
    // best-effort; ignore failures here, the stream will report the actual outcome
  } finally {
    stopping.value = false
  }
}

const completedCount = computed(() => stepStates.filter(s => s.status === 'success' || s.status === 'skipped').length)
const progressPercent = computed(() => Math.round((completedCount.value / stepStates.length) * 100))
const progressLabel = computed(() => `${completedCount.value} of ${stepStates.length} steps complete`)
const progressBarColor = computed(() => {
  if (overallError.value) return 'bg-rose-500'
  if (overallSuccess.value) return 'bg-emerald-500'
  return 'bg-app-accent'
})
</script>
