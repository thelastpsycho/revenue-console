<template>
  <div class="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="PMS API test"
      subtitle="Try the Selenium-free PMS client (login.aspx form → JWT cookie → JSON API) side by side with the existing scraper, without touching production code paths."
    />

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <!-- Inventory fetch test -->
      <section class="neu-card space-y-4 p-6">
        <div>
          <h2 class="text-base font-semibold text-app-tertiary">Room availability fetch</h2>
          <p class="mt-1 text-sm text-slate-500">Read-only. Calls the PMS JSON API directly - no browser, no writes.</p>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">Start date</label>
            <input type="date" v-model="invStartDate" class="neu-input" />
          </div>
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">Days (7-100)</label>
            <input type="number" min="7" max="100" v-model.number="invDays" class="neu-input" />
            <p class="mt-1 text-xs text-slate-400">PMS API quirk: values below 7 are silently ignored and it returns its default ~14-day window instead.</p>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">PMS username</label>
            <input type="text" v-model="invUsername" placeholder="Falls back to server env" class="neu-input" />
          </div>
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">PMS password</label>
            <input type="password" v-model="invPassword" placeholder="Falls back to server env" class="neu-input" />
          </div>
        </div>

        <button @click="runInventoryFetch" :disabled="invLoading" class="btn-primary w-full px-5 py-3">
          <span v-if="invLoading" class="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white"></span>
          {{ invLoading ? 'Fetching…' : 'Run fetch' }}
        </button>

        <div v-if="invError" class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
          {{ invError }}
        </div>
        <div v-if="invResult" class="space-y-2">
          <div class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-emerald-700 shadow-neu-inset-sm">
            {{ invResult.count }} row(s) in {{ invResult.elapsedSeconds }}s
          </div>
          <div class="max-h-80 overflow-auto rounded-xl bg-app-primary p-3 shadow-neu-inset">
            <pre class="font-mono text-xs text-slate-600">{{ JSON.stringify(invResult.rows.slice(0, 5), null, 2) }}</pre>
            <p v-if="invResult.rows.length > 5" class="mt-2 text-xs text-slate-400">Showing first 5 of {{ invResult.rows.length }} rows.</p>
          </div>
        </div>
      </section>

      <!-- Allotment push test -->
      <section class="neu-card space-y-4 p-6">
        <div>
          <h2 class="text-base font-semibold text-app-tertiary">Allotment push (single row)</h2>
          <p class="mt-1 text-sm text-slate-500">Mirrors one row of the PMS "Add Allotment Room" modal.</p>
        </div>

        <div>
          <label class="mb-1.5 block text-sm font-semibold text-slate-600">Room type</label>
          <select v-model="roomType" class="neu-input">
            <option v-for="rt in roomTypes" :key="rt.value" :value="rt.value">{{ rt.label }} ({{ rt.value }})</option>
          </select>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">Start date</label>
            <input type="date" v-model="allotStartDate" class="neu-input" />
          </div>
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">End date</label>
            <input type="date" v-model="allotEndDate" class="neu-input" />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">Number of rooms</label>
            <input type="number" v-model.number="numberOfRooms" class="neu-input" />
          </div>
          <div>
            <label class="mb-1.5 block text-sm font-semibold text-slate-600">Company ID</label>
            <input type="number" v-model.number="companyId" class="neu-input" />
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-sm font-semibold text-slate-600">Remark (blank = auto-generated)</label>
          <input type="text" v-model="remark" placeholder="Updated from yield matrix - ..." class="neu-input" />
        </div>

        <label class="flex items-center gap-2 rounded-lg bg-app-primary px-3 py-2 text-sm font-medium shadow-neu-inset-sm">
          <input type="checkbox" v-model="dryRun" class="h-4 w-4" />
          Dry run (build the request only, don't send it)
        </label>

        <div v-if="!dryRun" class="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
          Live mode: this will write a real allotment change to the production PMS for the ANVAYA.
        </div>

        <button
          @click="runAllotmentPush"
          :disabled="allotLoading"
          :class="dryRun ? 'btn-primary' : 'w-full rounded-xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-rose-700 disabled:opacity-50'"
          class="w-full px-5 py-3"
        >
          <span v-if="allotLoading" class="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white"></span>
          {{ allotLoading ? 'Sending…' : (dryRun ? 'Build request (dry run)' : 'Send live request') }}
        </button>

        <div v-if="allotError" class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
          {{ allotError }}
        </div>
        <div v-if="allotResult" class="space-y-2">
          <div class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-emerald-700 shadow-neu-inset-sm">
            {{ allotResult.dry_run ? 'Dry run built' : 'Sent' }} in {{ allotResult.elapsed_seconds.toFixed(3) }}s
          </div>
          <div class="rounded-xl bg-app-primary p-3 shadow-neu-inset">
            <p class="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Request payload</p>
            <pre class="font-mono text-xs text-slate-600">{{ JSON.stringify(allotResult.request_payload, null, 2) }}</pre>
          </div>
          <div v-if="allotResult.response" class="rounded-xl bg-app-primary p-3 shadow-neu-inset">
            <p class="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">PMS response</p>
            <pre class="font-mono text-xs text-slate-600">{{ JSON.stringify(allotResult.response, null, 2) }}</pre>
          </div>
        </div>
      </section>
    </div>

    <!-- Bulk allotment push test -->
    <section class="neu-card space-y-4 p-6">
      <div>
        <h2 class="text-base font-semibold text-app-tertiary">Bulk allotment push</h2>
        <p class="mt-1 text-sm text-slate-500">
          Reads the real <code class="rounded bg-app-primary px-1 py-0.5">inventory_allocation.db</code> (same source the production Selenium updaters read),
          builds the same contiguous date-range jobs, and fires them concurrently via the JSON API.
        </p>
      </div>

      <div>
        <p class="mb-1.5 text-sm font-semibold text-slate-600">Room types (empty = all 13)</p>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          <label
            v-for="rt in roomTypeConfig"
            :key="rt.key"
            class="flex items-center gap-2 rounded-lg bg-app-primary px-3 py-2 text-xs font-medium shadow-neu-inset-sm"
          >
            <input type="checkbox" :value="rt.key" v-model="selectedRoomTypeKeys" class="h-3.5 w-3.5" />
            {{ rt.label }}
          </label>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label class="mb-1.5 block text-sm font-semibold text-slate-600">Max dates</label>
          <input type="number" min="1" v-model.number="bulkMaxDates" placeholder="All" class="neu-input" />
        </div>
        <div>
          <label class="mb-1.5 block text-sm font-semibold text-slate-600">Max concurrency</label>
          <input type="number" min="1" max="20" v-model.number="bulkMaxConcurrency" class="neu-input" />
        </div>
        <div>
          <label class="mb-1.5 block text-sm font-semibold text-slate-600">Company ID</label>
          <input type="number" v-model.number="bulkCompanyId" class="neu-input" />
        </div>
        <label class="mt-6 flex items-center gap-2 rounded-lg bg-app-primary px-3 py-2 text-sm font-medium shadow-neu-inset-sm">
          <input type="checkbox" v-model="bulkSkipUnchanged" class="h-4 w-4" />
          Skip unchanged (vs CM)
        </label>
      </div>

      <div class="flex flex-col gap-3 sm:flex-row">
        <button @click="runBulkPlan" :disabled="bulkPlanLoading" class="btn-primary flex-1 px-5 py-3">
          <span v-if="bulkPlanLoading" class="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white"></span>
          {{ bulkPlanLoading ? 'Building plan…' : 'Preview plan (no network)' }}
        </button>

        <label class="flex items-center gap-2 rounded-lg bg-app-primary px-3 py-2 text-sm font-medium shadow-neu-inset-sm">
          <input type="checkbox" v-model="bulkDryRun" class="h-4 w-4" />
          Dry run
        </label>

        <button
          @click="runBulkPush"
          :disabled="bulkPushLoading"
          :class="bulkDryRun ? 'btn-primary' : 'rounded-xl bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50'"
          class="flex-1 px-5 py-3 text-sm font-semibold transition-colors"
        >
          <span v-if="bulkPushLoading" class="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white"></span>
          {{ bulkPushLoading ? 'Pushing…' : (bulkDryRun ? 'Push (dry run)' : 'Push LIVE') }}
        </button>
      </div>

      <div v-if="!bulkDryRun" class="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
        Live mode: this will write real allotment changes to the production PMS for every job below. Start with a small "Max dates" value.
      </div>

      <div v-if="bulkError" class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
        {{ bulkError }}
      </div>

      <div v-if="bulkPlan" class="space-y-2">
        <div class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-emerald-700 shadow-neu-inset-sm">
          {{ bulkPlan.totalJobs }} job(s) planned, {{ bulkPlan.skippedRanges }} range(s) skipped (already matches CM)
        </div>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div
            v-for="(v, k) in bulkPlan.byRoomType"
            :key="k"
            class="rounded-lg bg-app-primary px-3 py-2 text-xs shadow-neu-inset-sm"
          >
            <p class="font-semibold text-app-tertiary">{{ v.label }}</p>
            <p class="text-slate-500">{{ v.job_count }} job(s)</p>
          </div>
        </div>
      </div>

      <div v-if="bulkResult" class="space-y-2">
        <div class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-emerald-700 shadow-neu-inset-sm">
          {{ bulkResult.dry_run ? 'Dry run' : 'Live push' }}: {{ bulkResult.success_count }}/{{ bulkResult.total }} succeeded
          in {{ bulkResult.elapsed_seconds.toFixed(3) }}s
        </div>
        <div class="max-h-96 overflow-auto rounded-xl bg-app-primary p-3 shadow-neu-inset">
          <table class="w-full text-left text-xs">
            <thead>
              <tr class="text-slate-400">
                <th class="pb-1 pr-2">Room type</th>
                <th class="pb-1 pr-2">Start</th>
                <th class="pb-1 pr-2">End</th>
                <th class="pb-1 pr-2">Rooms</th>
                <th class="pb-1 pr-2">Status</th>
                <th class="pb-1">Error</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in bulkResult.results" :key="i" class="border-t border-slate-200">
                <td class="py-1 pr-2 font-mono">{{ r.job.checkbox_value }}</td>
                <td class="py-1 pr-2 font-mono">{{ r.job.start_date }}</td>
                <td class="py-1 pr-2 font-mono">{{ r.job.end_date }}</td>
                <td class="py-1 pr-2 font-mono">{{ r.job.number_of_rooms }}</td>
                <td class="py-1 pr-2" :class="r.success ? 'text-emerald-700' : 'text-rose-700'">
                  {{ r.success ? 'OK' : 'FAILED' }}
                </td>
                <td class="py-1 text-rose-700">{{ r.error || '' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="bulkResult.total > bulkResult.results.length" class="mt-2 text-xs text-slate-400">
            Showing first {{ bulkResult.results.length }} of {{ bulkResult.total }} results.
          </p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import { todayLocalDateString } from '../utils/date'

const todayIso = todayLocalDateString()

// Inventory fetch state
const invStartDate = ref(todayIso)
const invDays = ref(14)
const invUsername = ref('')
const invPassword = ref('')
const invLoading = ref(false)
const invError = ref('')
const invResult = ref<{ count: number; elapsedSeconds: number; rows: Record<string, unknown>[] } | null>(null)

async function runInventoryFetch() {
  invLoading.value = true
  invError.value = ''
  invResult.value = null
  try {
    const res = await axios.post('/api/pms-fast/inventory', {
      startDate: invStartDate.value,
      days: invDays.value,
      username: invUsername.value || undefined,
      password: invPassword.value || undefined,
    })
    invResult.value = res.data
  } catch (err: any) {
    invError.value = err?.response?.data?.message || 'Failed to fetch inventory.'
  } finally {
    invLoading.value = false
  }
}

// Allotment push state
const roomTypes = ref<{ label: string; value: string }[]>([])
const roomType = ref('')
const allotStartDate = ref(todayIso)
const allotEndDate = ref(todayIso)
const numberOfRooms = ref(1)
const companyId = ref(1001)
const remark = ref('')
const dryRun = ref(true)
const allotLoading = ref(false)
const allotError = ref('')
const allotResult = ref<{ dry_run: boolean; elapsed_seconds: number; request_payload: Record<string, unknown>; response: unknown } | null>(null)

onMounted(async () => {
  try {
    const res = await axios.get('/api/pms-fast/room-types')
    roomTypes.value = res.data.roomTypes
    if (roomTypes.value.length) roomType.value = roomTypes.value[0].value
  } catch {
    // Non-fatal: the dropdown will just be empty.
  }
  try {
    const res = await axios.get('/api/pms-fast/room-type-config')
    roomTypeConfig.value = res.data.roomTypes
  } catch {
    // Non-fatal: the checkbox list will just be empty (bulk push still works, defaults to all).
  }
})

async function runAllotmentPush() {
  if (!dryRun.value) {
    const confirmed = window.confirm(
      'This will send a LIVE allotment change to the production PMS. Continue?'
    )
    if (!confirmed) return
  }
  allotLoading.value = true
  allotError.value = ''
  allotResult.value = null
  try {
    const res = await axios.post('/api/pms-fast/allotment', {
      roomType: roomType.value,
      startDate: allotStartDate.value,
      endDate: allotEndDate.value,
      numberOfRooms: numberOfRooms.value,
      companyId: companyId.value,
      remark: remark.value,
      dryRun: dryRun.value,
    })
    allotResult.value = res.data
  } catch (err: any) {
    allotError.value = err?.response?.data?.message || 'Failed to push allotment.'
  } finally {
    allotLoading.value = false
  }
}

// Bulk allotment push state
type BulkJob = { room_type: string; label: string; checkbox_value: string; start_date: string; end_date: string; number_of_rooms: number }
type BulkResultRow = { job: BulkJob; payload: Record<string, unknown>; success: boolean; response: unknown; error: string | null }

const roomTypeConfig = ref<{ key: string; label: string; checkboxValue: string }[]>([])
const selectedRoomTypeKeys = ref<string[]>([])
const bulkMaxDates = ref<number | null>(null)
const bulkMaxConcurrency = ref(4)
const bulkCompanyId = ref(1001)
const bulkSkipUnchanged = ref(true)
const bulkDryRun = ref(true)
const bulkPlanLoading = ref(false)
const bulkPushLoading = ref(false)
const bulkError = ref('')
const bulkPlan = ref<{ totalJobs: number; skippedRanges: number; byRoomType: Record<string, { label: string; job_count: number }> } | null>(null)
const bulkResult = ref<{ dry_run: boolean; total: number; success_count: number; failed_count: number; elapsed_seconds: number; results: BulkResultRow[] } | null>(null)

function bulkParams() {
  return {
    roomTypes: selectedRoomTypeKeys.value.length ? selectedRoomTypeKeys.value : undefined,
    maxDates: bulkMaxDates.value || undefined,
    skipUnchanged: bulkSkipUnchanged.value,
  }
}

async function runBulkPlan() {
  bulkPlanLoading.value = true
  bulkError.value = ''
  bulkPlan.value = null
  try {
    const res = await axios.post('/api/pms-fast/allotment-bulk/plan', bulkParams())
    bulkPlan.value = res.data
  } catch (err: any) {
    bulkError.value = err?.response?.data?.message || 'Failed to build plan.'
  } finally {
    bulkPlanLoading.value = false
  }
}

async function runBulkPush() {
  if (!bulkDryRun.value) {
    const confirmed = window.confirm(
      'This will send LIVE allotment changes to the production PMS for every planned job. Continue?'
    )
    if (!confirmed) return
  }
  bulkPushLoading.value = true
  bulkError.value = ''
  bulkResult.value = null
  try {
    const res = await axios.post('/api/pms-fast/allotment-bulk/push', {
      ...bulkParams(),
      dryRun: bulkDryRun.value,
      companyId: bulkCompanyId.value,
      maxConcurrency: bulkMaxConcurrency.value,
    })
    bulkResult.value = res.data
  } catch (err: any) {
    bulkError.value = err?.response?.data?.message || 'Failed to push bulk allotment.'
  } finally {
    bulkPushLoading.value = false
  }
}
</script>
