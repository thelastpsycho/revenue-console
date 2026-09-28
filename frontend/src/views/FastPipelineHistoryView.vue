<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Fast Pipeline History"
      subtitle="Every Fast API Pipeline run, persisted to fast_pipeline_logs.db so past logs survive after the run finishes and the browser tab closes."
    >
      <template #actions>
        <button
          @click="loadRuns"
          :disabled="loadingRuns"
          class="rounded-lg bg-app-primary px-2.5 py-1 text-xs font-semibold text-slate-500 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer"
        >
          Refresh
        </button>
      </template>
    </PageHeader>

    <div class="neu-card p-4">
      <!-- Run list search + status filter -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <input
          v-model="runSearch"
          type="text"
          placeholder="Search run # / date / error / full log content…"
          class="neu-input flex-1 min-w-[200px] py-1.5 text-xs"
        />
        <span v-if="searchingContent" class="text-[11px] text-slate-400">Searching logs…</span>
        <div class="flex items-center gap-1">
          <button
            v-for="opt in statusFilterOptions"
            :key="opt.value"
            type="button"
            @click="statusFilter = opt.value"
            :class="[
              'rounded-full px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm transition-all',
              statusFilter === opt.value ? 'bg-app-accent text-white' : 'bg-app-primary text-slate-500 hover:text-app-accent',
            ]"
          >
            {{ opt.label }}
          </button>
        </div>
        <button
          v-if="runSearch || statusFilter !== 'all'"
          type="button"
          @click="runSearch = ''; statusFilter = 'all'"
          class="rounded-lg bg-app-primary px-2.5 py-1 text-xs font-semibold text-slate-500 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm"
        >
          Clear
        </button>
      </div>

      <div v-if="loadingRuns" class="py-10 text-center text-sm text-slate-500">Loading runs…</div>
      <div v-else-if="loadError" class="py-10 text-center text-sm font-semibold text-rose-600">{{ loadError }}</div>
      <div v-else-if="runs.length === 0" class="py-10 text-center text-sm text-slate-500">
        No pipeline runs recorded yet. Start a run from the Fast API Pipeline page.
      </div>
      <div v-else-if="filteredRuns.length === 0" class="py-10 text-center text-sm text-slate-500">
        No runs match the current search/filter.
      </div>
      <div v-else class="overflow-auto rounded-xl bg-app-primary p-1 shadow-neu-inset">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <thead class="bg-app-primary sticky top-0 z-10">
            <tr>
              <th scope="col" class="py-3 px-4 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Run</th>
              <th scope="col" class="py-3 px-4 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Started</th>
              <th scope="col" class="py-3 px-4 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Finished</th>
              <th scope="col" class="py-3 px-4 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Status</th>
              <th scope="col" class="py-3 px-4 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Error</th>
              <th v-if="runSearch.trim()" scope="col" class="py-3 px-4 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Log matches</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200">
            <template v-for="run in filteredRuns" :key="run.id">
              <tr
                class="cursor-pointer transition-colors hover:bg-app-secondary/50"
                :class="{ 'bg-app-secondary/40': expandedRunId === run.id }"
                @click="toggleRun(run.id)"
              >
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-600">#{{ run.id }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-xs text-slate-600">{{ formatDateTime(run.started_at) }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-xs text-slate-600">{{ run.finished_at ? formatDateTime(run.finished_at) : '—' }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    :class="[
                      'inline-flex items-center gap-1.5 rounded-full bg-app-primary px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm',
                      run.status === 'running' ? 'text-amber-700' : run.status === 'error' ? 'text-rose-700' : 'text-emerald-700',
                    ]"
                  >
                    <span :class="['h-1.5 w-1.5 rounded-full', run.status === 'running' ? 'bg-amber-500 animate-pulse' : run.status === 'error' ? 'bg-rose-500' : 'bg-emerald-500']" />
                    {{ run.status }}
                  </span>
                </td>
                <td class="max-w-xs truncate px-4 py-3 text-xs text-rose-600" :title="run.error || ''">{{ run.error || '—' }}</td>
                <td v-if="runSearch.trim()" class="whitespace-nowrap px-4 py-3 text-xs">
                  <span v-if="contentMatchCountByRun.get(run.id)" class="rounded-full bg-app-primary px-2 py-0.5 font-semibold text-app-accent shadow-neu-inset-sm">
                    {{ contentMatchCountByRun.get(run.id) }} line(s)
                  </span>
                  <span v-else class="text-slate-400">—</span>
                </td>
              </tr>
              <tr v-if="expandedRunId === run.id">
                <td :colspan="runSearch.trim() ? 6 : 5" class="bg-app-primary/60 px-4 py-4">
                  <div v-if="loadingDetail" class="py-4 text-center text-sm text-slate-500">Loading log…</div>
                  <div v-else-if="detailError" class="py-4 text-center text-sm font-semibold text-rose-600">{{ detailError }}</div>
                  <template v-else>
                    <div class="mb-2 flex flex-wrap items-center gap-2">
                      <input
                        v-model="logSearch"
                        type="text"
                        placeholder="Search log messages…"
                        class="neu-input flex-1 min-w-[180px] py-1.5 text-xs"
                      />
                      <select v-model="logStepFilter" class="neu-input py-1.5 text-xs">
                        <option value="all">All steps</option>
                        <option v-for="step in detailSteps" :key="step" :value="step">{{ step }}</option>
                      </select>
                      <div class="flex items-center gap-1">
                        <button
                          v-for="opt in logTypeFilterOptions"
                          :key="opt.value"
                          type="button"
                          @click="logTypeFilter = opt.value"
                          :class="[
                            'rounded-full px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm transition-all',
                            logTypeFilter === opt.value ? 'bg-app-accent text-white' : 'bg-app-primary text-slate-500 hover:text-app-accent',
                          ]"
                        >
                          {{ opt.label }}
                        </button>
                      </div>
                    </div>
                    <div class="h-96 overflow-y-auto rounded-xl bg-app-primary p-4 shadow-neu-inset">
                    <div v-if="detailLogs.length === 0" class="py-8 text-center text-sm text-slate-500">No log entries for this run.</div>
                    <div v-else-if="filteredLogs.length === 0" class="py-8 text-center text-sm text-slate-500">No log entries match the current search/filter.</div>
                    <div v-else class="space-y-1.5">
                      <div
                        v-for="(log, index) in filteredLogs"
                        :key="index"
                        class="flex items-start gap-2 font-mono text-xs"
                        :class="{
                          'text-app-accent': log.type === 'info',
                          'text-emerald-700': log.type === 'success',
                          'text-rose-600': log.type === 'error',
                          'text-slate-400': log.type === 'skipped',
                        }"
                      >
                        <span class="text-slate-500">{{ formatTime(log.created_at) }}</span>
                        <span v-if="log.step" class="shrink-0 rounded bg-app-primary px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 shadow-neu-inset-sm">{{ log.step }}</span>
                        <span class="flex-1 whitespace-pre-wrap break-words">{{ log.message }}</span>
                      </div>
                    </div>
                    </div>
                  </template>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'

interface RunSummary {
  id: number
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'error'
  error: string | null
}

interface LogEntry {
  step: string | null
  type: 'info' | 'success' | 'error' | 'skipped'
  message: string
  created_at: string
}

interface ContentMatch extends LogEntry {
  run_id: number
}

const runs = ref<RunSummary[]>([])
const loadingRuns = ref(false)
const loadError = ref<string | null>(null)

const runSearch = ref('')
const statusFilter = ref<'all' | 'running' | 'success' | 'error'>('all')
const statusFilterOptions: { value: typeof statusFilter.value; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'success', label: 'Success' },
  { value: 'error', label: 'Error' },
]

// Content search hits the backend (searches every run's persisted log lines,
// not just the ones currently loaded in `runs`), debounced so it doesn't fire
// on every keystroke.
const contentMatches = ref<ContentMatch[]>([])
const searchingContent = ref(false)
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

const contentMatchCountByRun = computed(() => {
  const counts = new Map<number, number>()
  for (const m of contentMatches.value) counts.set(m.run_id, (counts.get(m.run_id) || 0) + 1)
  return counts
})

async function runContentSearch(q: string) {
  try {
    const { data } = await axios.get('/api/fast-pipeline/search', { params: { q, limit: 200 } })
    contentMatches.value = data.matches
  } catch {
    contentMatches.value = []
  } finally {
    searchingContent.value = false
  }
}

watch(runSearch, (val) => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  const q = val.trim()
  if (!q) {
    contentMatches.value = []
    searchingContent.value = false
    return
  }
  searchingContent.value = true
  searchDebounceTimer = setTimeout(() => runContentSearch(q), 300)
})

onBeforeUnmount(() => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
})

const filteredRuns = computed(() => {
  const q = runSearch.value.trim().toLowerCase()
  return runs.value.filter((run) => {
    if (statusFilter.value !== 'all' && run.status !== statusFilter.value) return false
    if (!q) return true
    const metadataMatch =
      String(run.id).includes(q) ||
      formatDateTime(run.started_at).toLowerCase().includes(q) ||
      (run.finished_at ? formatDateTime(run.finished_at).toLowerCase().includes(q) : false) ||
      (run.error || '').toLowerCase().includes(q)
    return metadataMatch || contentMatchCountByRun.value.has(run.id)
  })
})

const expandedRunId = ref<number | null>(null)
const detailLogs = ref<LogEntry[]>([])
const loadingDetail = ref(false)
const detailError = ref<string | null>(null)

const logSearch = ref('')
const logStepFilter = ref<string>('all')
const logTypeFilter = ref<'all' | 'info' | 'success' | 'error' | 'skipped'>('all')
const logTypeFilterOptions: { value: typeof logTypeFilter.value; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'info', label: 'Info' },
  { value: 'success', label: 'Success' },
  { value: 'error', label: 'Error' },
  { value: 'skipped', label: 'Skipped' },
]

const detailSteps = computed(() => {
  const steps = new Set(detailLogs.value.map((l) => l.step).filter((s): s is string => !!s))
  return Array.from(steps)
})

const filteredLogs = computed(() => {
  const q = logSearch.value.trim().toLowerCase()
  return detailLogs.value.filter((log) => {
    if (logTypeFilter.value !== 'all' && log.type !== logTypeFilter.value) return false
    if (logStepFilter.value !== 'all' && log.step !== logStepFilter.value) return false
    if (!q) return true
    return log.message.toLowerCase().includes(q) || (log.step || '').toLowerCase().includes(q)
  })
})

async function loadRuns() {
  loadingRuns.value = true
  loadError.value = null
  try {
    const { data } = await axios.get('/api/fast-pipeline/history', { params: { limit: 200 } })
    runs.value = data.runs
  } catch (err: any) {
    loadError.value = err?.response?.data?.message || 'Failed to load pipeline history'
  } finally {
    loadingRuns.value = false
  }
}

async function toggleRun(runId: number) {
  if (expandedRunId.value === runId) {
    expandedRunId.value = null
    return
  }
  expandedRunId.value = runId
  loadingDetail.value = true
  detailError.value = null
  detailLogs.value = []
  // Carry the run-list search term into the log panel so a run opened from a
  // content-search hit lands already filtered to the matching lines.
  logSearch.value = runSearch.value.trim()
  logStepFilter.value = 'all'
  logTypeFilter.value = 'all'
  try {
    const { data } = await axios.get(`/api/fast-pipeline/history/${runId}`)
    detailLogs.value = data.logs
  } catch (err: any) {
    detailError.value = err?.response?.data?.message || 'Failed to load run log'
  } finally {
    loadingDetail.value = false
  }
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString()
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString()
}

onMounted(loadRuns)
</script>
