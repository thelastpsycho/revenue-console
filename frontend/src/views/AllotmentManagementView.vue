<template>
  <div class="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Allotment"
      subtitle="Push the calculated allotment changes back into the PMS."
    />

    <div class="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <!-- Left: actions + log -->
      <div class="space-y-6 xl:col-span-2">
        <!-- Status / Actions Card -->
        <div class="neu-card p-6">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-base font-semibold text-app-tertiary">Update status</h2>
              <p class="mt-1 text-sm text-slate-500">{{ statusMessage }}</p>
            </div>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div v-if="progress" class="flex items-center gap-2">
                <div class="h-2 w-28 overflow-hidden rounded-full bg-app-primary shadow-neu-inset-sm">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="progressBarColor"
                    :style="{ width: progressPercent + '%' }"
                  />
                </div>
                <span class="text-xs font-semibold text-slate-500">{{ progressPercent }}%</span>
              </div>
              <div v-if="isUpdating && activeFlow === 'allotment'" class="flex items-center gap-2">
                <button
                  type="button"
                  @click="togglePause"
                  class="rounded-lg bg-app-primary px-2.5 py-1.5 text-xs font-semibold text-slate-500 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm cursor-pointer"
                >
                  {{ isPaused ? 'Resume' : 'Pause' }}
                </button>
                <button
                  type="button"
                  @click="stopUpdate"
                  class="rounded-lg bg-app-primary px-2.5 py-1.5 text-xs font-semibold text-rose-600 shadow-neu-sm transition-all hover:text-rose-700 active:shadow-neu-inset-sm cursor-pointer"
                >
                  Stop
                </button>
              </div>
              <label class="inline-flex cursor-pointer items-center gap-2 whitespace-nowrap text-xs font-semibold text-slate-500" title="Compares against the current channel-manager value and skips dates that already match, instead of always pushing every date.">
                Skip unchanged dates
                <button
                  type="button"
                  role="switch"
                  :aria-checked="skipUnchanged"
                  :disabled="isUpdating"
                  @click="skipUnchanged = !skipUnchanged"
                  :class="[
                    'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full shadow-neu-inset-sm transition-colors disabled:opacity-50',
                    skipUnchanged ? 'bg-app-accent' : 'bg-app-primary',
                  ]"
                >
                  <span
                    :class="[
                      'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-neu-sm transition-transform',
                      skipUnchanged ? 'translate-x-[20px]' : 'translate-x-0.5',
                    ]"
                  />
                </button>
              </label>
              <label class="inline-flex cursor-pointer items-center gap-2 whitespace-nowrap text-xs font-semibold text-slate-500">
                Run headless
                <button
                  type="button"
                  role="switch"
                  :aria-checked="headless"
                  :disabled="isUpdating"
                  @click="headless = !headless"
                  :class="[
                    'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full shadow-neu-inset-sm transition-colors disabled:opacity-50',
                    headless ? 'bg-app-accent' : 'bg-app-primary',
                  ]"
                >
                  <span
                    :class="[
                      'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-neu-sm transition-transform',
                      headless ? 'translate-x-[20px]' : 'translate-x-0.5',
                    ]"
                  />
                </button>
              </label>
              <span
                :class="[
                  'inline-flex items-center gap-1.5 rounded-full bg-app-primary px-3 py-1.5 text-xs font-semibold shadow-neu-inset-sm',
                  isUpdating ? 'text-amber-700' : 'text-emerald-700',
                ]"
              >
                <span :class="['h-1.5 w-1.5 rounded-full', isUpdating ? 'bg-amber-500' : 'bg-emerald-500']" />
                {{ isUpdating ? 'Running' : 'Ready' }}
              </span>
            </div>
          </div>

          <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <button
              @click="triggerUpdate('deluxe')"
              :disabled="isUpdating"
              class="btn-flat !text-app-accent"
            >
              Update Deluxe
            </button>
            <button
              @click="triggerUpdate('premiere')"
              :disabled="isUpdating"
              class="btn-flat !text-violet-600"
            >
              Update Premiere
            </button>
            <button
              @click="triggerUpdateRest"
              :disabled="isUpdating"
              class="btn-flat !text-emerald-700"
            >
              Update the rest
            </button>
          </div>
        </div>

        <!-- BAR Pricing (D-EDGE) Card -->
        <div class="neu-card p-6">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-base font-semibold text-app-tertiary">BAR pricing (D-EDGE)</h2>
              <p class="mt-1 text-sm text-slate-500">
                Push the yielder's BAR price levels onto the Availpro extranet.
              </p>
            </div>
            <label class="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-500">
              Dry run
              <button
                type="button"
                role="switch"
                :aria-checked="barDryRun"
                :disabled="isUpdating"
                @click="barDryRun = !barDryRun"
                :class="[
                  'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full shadow-neu-inset-sm transition-colors disabled:opacity-50',
                  barDryRun ? 'bg-app-accent' : 'bg-app-primary',
                ]"
              >
                <span
                  :class="[
                    'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-neu-sm transition-transform',
                    barDryRun ? 'translate-x-[20px]' : 'translate-x-0.5',
                  ]"
                />
              </button>
            </label>
          </div>

          <label class="mt-3 inline-flex items-start gap-2 text-xs text-amber-800">
            <input v-model="resetBarCheckpoint" type="checkbox" :disabled="isUpdating" class="mt-0.5 accent-app-accent" />
            <span>Start fresh (discard partial BAR checkpoint). Verify existing D-EDGE changes before selecting.</span>
          </label>

          <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <button
              @click="triggerBarUpdate(['deluxe'])"
              :disabled="isUpdating"
              class="btn-flat !text-app-accent"
            >
              Update Deluxe BAR
            </button>
            <button
              @click="triggerBarUpdate(['premiere'])"
              :disabled="isUpdating"
              class="btn-flat !text-violet-600"
            >
              Update Premiere BAR
            </button>
            <button
              @click="triggerBarUpdate(['deluxe', 'premiere'])"
              :disabled="isUpdating"
              class="btn-flat !text-emerald-700"
            >
              Update both
            </button>
          </div>
        </div>

        <!-- Process Log Card -->
        <div class="neu-card p-6">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-base font-semibold text-app-tertiary">Process log</h2>
            <button
              @click="clearLogs"
              class="rounded-lg bg-app-primary px-2.5 py-1.5 text-xs font-semibold text-slate-500 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer"
              :disabled="isUpdating"
            >
              Clear logs
            </button>
          </div>
          <div ref="logContainer" class="h-96 overflow-y-auto rounded-xl bg-app-primary p-4 shadow-neu-inset">
            <div v-if="logs.length === 0" class="py-8 text-center text-sm text-slate-500">
              No logs yet. Start an update to see live progress.
            </div>
            <div v-else class="space-y-1.5">
              <div
                v-for="(log, index) in logs"
                :key="index"
                class="flex items-start gap-2 font-mono text-xs"
                :class="{
                  'text-app-accent': log.type === 'info',
                  'text-emerald-700': log.type === 'success',
                  'text-rose-600': log.type === 'error'
                }"
              >
                <span class="text-slate-500">{{ formatTime(log.timestamp) }}</span>
                <span class="flex-1">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Credentials Card -->
      <div class="xl:col-span-1">
        <div class="neu-card p-6">
          <h2 class="text-base font-semibold text-app-tertiary">Credentials</h2>
          <p class="mt-1 text-sm text-slate-500">PMS login used to push allotment changes.</p>
          <div class="mt-5 space-y-4">
            <div>
              <label class="mb-1.5 block text-sm font-semibold text-slate-600">Username</label>
              <input
                v-model="username"
                type="text"
                autocomplete="username"
                placeholder="Username"
                class="neu-input disabled:opacity-60"
                :disabled="isUpdating"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-sm font-semibold text-slate-600">Password</label>
              <input
                v-model="password"
                type="password"
                autocomplete="current-password"
                placeholder="Password"
                class="neu-input disabled:opacity-60"
                :disabled="isUpdating"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-sm font-semibold text-slate-600">Max dates</label>
              <input
                v-model="maxDates"
                type="number"
                min="1"
                placeholder="Leave empty for a full run"
                class="neu-input disabled:opacity-60"
                :disabled="isUpdating"
              />
            </div>
          </div>
        </div>

        <!-- D-EDGE Credentials Card -->
        <div class="neu-card mt-6 p-6">
          <h2 class="text-base font-semibold text-app-tertiary">D-EDGE credentials</h2>
          <p class="mt-1 text-sm text-slate-500">
            Availpro login for BAR pricing. Optional — leave blank to use the saved
            session / server env vars.
          </p>
          <div class="mt-5 space-y-4">
            <div>
              <label class="mb-1.5 block text-sm font-semibold text-slate-600">Username</label>
              <input
                v-model="dedgeUsername"
                type="text"
                autocomplete="off"
                placeholder="D-EDGE username"
                class="neu-input disabled:opacity-60"
                :disabled="isUpdating"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-sm font-semibold text-slate-600">Password</label>
              <input
                v-model="dedgePassword"
                type="password"
                autocomplete="off"
                placeholder="D-EDGE password"
                class="neu-input disabled:opacity-60"
                :disabled="isUpdating"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'

const isUpdating = ref(false)
const statusMessage = ref('Ready to update allotment')
const progress = ref<{ current: number; total: number } | null>(null)
const progressStatus = ref<'running' | 'success' | 'error'>('running')
const progressPercent = computed(() =>
  progress.value ? Math.round((progress.value.current / progress.value.total) * 100) : 0
)
const progressBarColor = computed(() => {
  if (progressStatus.value === 'success') return 'bg-emerald-500'
  if (progressStatus.value === 'error') return 'bg-rose-500'
  return 'bg-app-accent'
})
const activeFlow = ref<'allotment' | 'bar' | null>(null)
const isPaused = ref(false)
const username = ref('')
const password = ref('')
const maxDates = ref<number | null>(null)
const headless = ref(false)
const skipUnchanged = ref(true)
// TODO: prefilled for convenience — move server-side before shipping (ships to
// the browser and is committed to git).
const dedgeUsername = ref('')
const dedgePassword = ref('')
const barDryRun = ref(false)
const resetBarCheckpoint = ref(false)
const logs = ref<Array<{message: string, type: 'info' | 'success' | 'error', timestamp: Date}>>([])
const logContainer = ref<HTMLElement | null>(null)

const formatTime = (date: Date) => {
  return date.toLocaleTimeString()
}

const addLog = (message: string, type: 'info' | 'success' | 'error' = 'info') => {
  logs.value.push({
    message,
    type,
    timestamp: new Date()
  })
  // Keep the newest line in view (scroll the log panel, not the first
  // scrollable element on the page).
  nextTick(() => {
    const el = logContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

const clearLogs = () => {
  logs.value = []
  progress.value = null
}

const stopUpdate = async () => {
  try {
    await axios.post('/api/update-allotment/stop')
  } catch (error: any) {
    addLog(`Error requesting stop: ${error.response?.data?.message || error.message}`, 'error')
  }
}

const togglePause = async () => {
  try {
    if (isPaused.value) {
      await axios.post('/api/update-allotment/resume')
      isPaused.value = false
    } else {
      await axios.post('/api/update-allotment/pause')
      isPaused.value = true
    }
  } catch (error: any) {
    addLog(`Error requesting ${isPaused.value ? 'resume' : 'pause'}: ${error.response?.data?.message || error.message}`, 'error')
  }
}

const triggerUpdate = async (roomType: 'deluxe' | 'premiere') => {
  const roomLabel = roomType === 'deluxe' ? 'Deluxe' : 'Premiere'
  try {
    isUpdating.value = true
    activeFlow.value = 'allotment'
    isPaused.value = false
    statusMessage.value = `Updating ${roomLabel} allotment...`
    progress.value = null
    progressStatus.value = 'running'
    addLog(`Starting ${roomLabel} allotment update process...`, 'info')

    // Create EventSource for real-time updates
    const eventSource = new EventSource('/api/update-allotment/stream')

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      addLog(data.message, data.type)
      if (data.progress) progress.value = data.progress

      if (data.type === 'success' || data.type === 'error') {
        eventSource.close()
        isUpdating.value = false
        progressStatus.value = data.type
        statusMessage.value = data.type === 'success'
          ? `${roomLabel} allotment updated successfully!`
          : `Error: ${data.message}`
      }
    }

    eventSource.onerror = () => {
      addLog('Connection error occurred', 'error')
      eventSource.close()
      isUpdating.value = false
      statusMessage.value = 'Error: Connection lost'
    }

    // Send credentials to start the process
    await axios.post('/api/update-allotment', {
      username: username.value,
      password: password.value,
      room_type: roomType,
      max_dates: maxDates.value || null,
      headless: headless.value,
      skip_unchanged: skipUnchanged.value
    })

  } catch (error: any) {
    addLog(`Error: ${error.response?.data?.message || error.message}`, 'error')
    statusMessage.value = `Error: ${error.response?.data?.message || error.message}`
    isUpdating.value = false
  }
}

const triggerUpdateRest = async () => {
  try {
    isUpdating.value = true
    activeFlow.value = 'allotment'
    isPaused.value = false
    statusMessage.value = 'Updating the rest of the room types allotment...'
    progress.value = null
    progressStatus.value = 'running'
    addLog('Starting allotment update process for the rest of the room types...', 'info')

    // Create EventSource for real-time updates
    const eventSource = new EventSource('/api/update-allotment/stream')

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      addLog(data.message, data.type)
      if (data.progress) progress.value = data.progress

      if (data.type === 'success' || data.type === 'error') {
        eventSource.close()
        isUpdating.value = false
        progressStatus.value = data.type
        statusMessage.value = data.type === 'success'
          ? 'The rest of the room types allotment updated successfully!'
          : `Error: ${data.message}`
      }
    }

    eventSource.onerror = () => {
      addLog('Connection error occurred', 'error')
      eventSource.close()
      isUpdating.value = false
      statusMessage.value = 'Error: Connection lost'
    }

    // Send credentials to start the process
    await axios.post('/api/update-rest-allotment', {
      username: username.value,
      password: password.value,
      max_dates: maxDates.value || null,
      headless: headless.value,
      skip_unchanged: skipUnchanged.value
    })

  } catch (error: any) {
    addLog(`Error: ${error.response?.data?.message || error.message}`, 'error')
    statusMessage.value = `Error: ${error.response?.data?.message || error.message}`
    isUpdating.value = false
  }
}

const triggerBarUpdate = async (rooms: Array<'deluxe' | 'premiere'>) => {
  const roomLabel = rooms.map(r => r === 'deluxe' ? 'Deluxe' : 'Premiere').join(' + ')
  try {
    isUpdating.value = true
    activeFlow.value = 'bar'
    isPaused.value = false
    statusMessage.value = `Updating ${roomLabel} BAR pricing${barDryRun.value ? ' (dry run)' : ''}...`
    progress.value = null
    progressStatus.value = 'running'
    addLog(`Starting ${roomLabel} BAR price-level update${barDryRun.value ? ' (dry run)' : ''}...`, 'info')

    // Create EventSource for real-time updates
    const eventSource = new EventSource('/api/update-bar/stream')

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      addLog(data.message, data.type)
      if (data.progress) progress.value = data.progress

      if (data.type === 'success' || data.type === 'error') {
        eventSource.close()
        isUpdating.value = false
        progressStatus.value = data.type
        statusMessage.value = data.type === 'success'
          ? `${roomLabel} BAR pricing updated successfully!`
          : `Error: ${data.message}`
      }
    }

    eventSource.onerror = () => {
      addLog('Connection error occurred', 'error')
      eventSource.close()
      isUpdating.value = false
      statusMessage.value = 'Error: Connection lost'
    }

    // Send request to start the process (D-EDGE credentials are optional)
    await axios.post('/api/update-bar', {
      username: dedgeUsername.value || null,
      password: dedgePassword.value || null,
      rooms,
      dry_run: barDryRun.value,
      resetCheckpoint: resetBarCheckpoint.value,
      headless: headless.value
    })

  } catch (error: any) {
    addLog(`Error: ${error.response?.data?.message || error.message}`, 'error')
    statusMessage.value = `Error: ${error.response?.data?.message || error.message}`
    isUpdating.value = false
  }
}
</script>