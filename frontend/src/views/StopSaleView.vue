<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Stop Sale"
      subtitle="Email a stop sale on all static rates to partners when combined inventory shows the hotel or a room type is full. Nothing is sent until you press Send."
    />

    <!-- Tabs (v-show so switching keeps ticks, form input and the preview) -->
    <div class="flex max-w-full gap-1.5 overflow-x-auto rounded-xl bg-app-primary p-1.5 shadow-neu-inset-sm sm:w-fit" role="tablist">
      <button
        v-for="tab in TABS"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.id"
        @click="selectTab(tab.id)"
        :class="[
          activeTab === tab.id ? 'bg-app-primary text-app-accent shadow-neu-sm' : 'text-slate-500 hover:text-app-tertiary',
          'flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200',
        ]"
      >
        <component :is="tab.icon" class="h-4 w-4" />
        {{ tab.name }}
        <span v-if="tab.id === 'send' && closures.length" class="rounded-full bg-rose-50 px-1.5 text-[10px] text-rose-700">{{ closures.length }}</span>
      </button>
    </div>

    <!-- ===== Send ===== -->
    <div v-show="activeTab === 'send'" class="grid grid-cols-1 gap-4 xl:grid-cols-12">
      <!-- Dates -->
      <div class="neu-card overflow-hidden xl:col-span-7">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
          <div>
            <h2 class="text-sm font-semibold text-app-tertiary">Stop sale dates</h2>
            <p class="mt-0.5 text-[11px] text-slate-500">
              From combined inventory<template v-if="updatedAt">, updated {{ formatDateTime(updatedAt) }}</template>.
              Untick a date to leave it out of the email.
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button type="button" class="btn-flat px-2.5 py-1 text-xs" :disabled="!closures.length" @click="tickAll(true)">Tick all</button>
            <button type="button" class="btn-flat px-2.5 py-1 text-xs" :disabled="!closures.length" @click="tickAll(false)">Untick all</button>
            <button type="button" class="btn-icon" :disabled="loading" title="Reload from combined inventory" aria-label="Reload" @click="loadPreview">
              <ArrowPathIcon :class="['h-4 w-4', loading && 'animate-spin']" />
            </button>
          </div>
        </div>

        <p v-if="loadError" class="p-4 text-xs font-semibold text-rose-700">{{ loadError }}</p>
        <div v-else-if="loaded && !closures.length" class="space-y-1 p-4 text-xs text-slate-500">
          <p class="font-semibold text-slate-700">No dates stop sale under the current rule.</p>
          <p>Check the thresholds in Settings, or run the pipeline to refresh combined inventory.</p>
        </div>
        <div v-else class="max-h-[65vh] overflow-auto">
          <table class="min-w-full text-xs">
            <thead class="sticky top-0 z-10 bg-white shadow-[0_1px_0_rgb(226_232_240)]">
              <tr>
                <th class="w-10 px-4 py-2.5 text-left">
                  <input
                    type="checkbox"
                    class="h-3.5 w-3.5 cursor-pointer accent-app-accent"
                    :checked="selectedDates.length === closures.length && closures.length > 0"
                    :indeterminate.prop="selectedDates.length > 0 && selectedDates.length < closures.length"
                    aria-label="Tick or untick all dates"
                    @change="tickAll(($event.target as HTMLInputElement).checked)"
                  />
                </th>
                <th class="px-2 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Date</th>
                <th class="px-2 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">Occ.</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Closes</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr
                v-for="c in closures"
                :key="c.date"
                :class="['cursor-pointer hover:bg-slate-50', unticked.has(c.date) && 'opacity-45']"
                @click="toggle(c.date)"
              >
                <td class="px-4 py-2 align-top">
                  <input
                    type="checkbox"
                    class="h-3.5 w-3.5 cursor-pointer accent-app-accent"
                    :checked="!unticked.has(c.date)"
                    :aria-label="`Include ${formatDay(c.date)}`"
                    @click.stop
                    @change="toggle(c.date)"
                  />
                </td>
                <td class="whitespace-nowrap px-2 py-2 align-top font-semibold text-slate-700">{{ formatDay(c.date) }}</td>
                <td class="whitespace-nowrap px-2 py-2 text-right align-top tabular-nums text-slate-600">
                  {{ c.occupancy === null ? '–' : `${c.occupancy.toFixed(1)}%` }}
                </td>
                <td class="px-4 py-2 align-top">
                  <span v-if="c.allRooms" class="inline-flex rounded-full bg-rose-50 px-2 py-0.5 font-semibold text-rose-700">
                    All room types
                  </span>
                  <div v-else class="flex flex-wrap gap-1">
                    <span v-if="c.hotelFull" class="inline-flex rounded-full bg-rose-50 px-2 py-0.5 font-semibold text-rose-700" title="Whole hotel closes; unticked room types are left out">
                      Hotel full
                    </span>
                    <span
                      v-for="r in c.rooms"
                      :key="r.room"
                      class="inline-flex rounded-full bg-amber-50 px-2 py-0.5 font-semibold text-amber-800"
                      :title="`${r.remaining} remaining, stop sale at ${r.threshold} or fewer`"
                    >
                      {{ r.room }} <span class="ml-1 font-normal text-amber-700">{{ r.remaining }} left</span>
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Send panel -->
      <div class="space-y-4 xl:col-span-5">
        <div class="neu-card space-y-3 p-4 text-xs">
          <h2 class="text-sm font-semibold text-app-tertiary">Send</h2>
          <dl class="grid grid-cols-3 gap-2 text-center">
            <div class="rounded-lg bg-slate-50 p-2">
              <dt class="text-[11px] text-slate-500">Dates ticked</dt>
              <dd class="text-lg font-semibold text-slate-900">{{ selectedDates.length }}</dd>
            </div>
            <div class="rounded-lg bg-slate-50 p-2">
              <dt class="text-[11px] text-slate-500">Date ranges</dt>
              <dd class="text-lg font-semibold text-slate-900">{{ preview?.ranges.length ?? '–' }}</dd>
            </div>
            <div class="rounded-lg bg-slate-50 p-2">
              <dt class="text-[11px] text-slate-500">Recipients</dt>
              <dd class="text-lg font-semibold text-slate-900">{{ activeRecipients }}</dd>
            </div>
          </dl>

          <p v-if="smtp && !smtp.configured" class="rounded-lg bg-amber-50 px-3 py-2 font-semibold text-amber-800">
            The mail server isn't set up yet, so emails can't be sent. See Settings → Mail server.
          </p>
          <p v-if="loaded && !activeRecipients" class="rounded-lg bg-amber-50 px-3 py-2 font-semibold text-amber-800">
            No active recipients. Add them in the Recipients tab.
          </p>

          <!-- Doubles as the progress bar while a send runs: the darker fill grows with the percentage sent. -->
          <button
            type="button"
            :class="[
              'btn-primary relative w-full overflow-hidden',
              job?.running ? 'bg-rose-300 disabled:cursor-progress disabled:opacity-100' : 'bg-rose-700 hover:bg-rose-800',
            ]"
            :disabled="!canSend"
            :aria-label="job?.running ? `Sending stop sale: ${sendPercent}% done` : undefined"
            @click="send"
          >
            <span
              v-if="job?.running"
              class="absolute inset-y-0 left-0 bg-rose-700 transition-[width] duration-700 ease-out"
              :style="{ width: `${sendPercent}%` }"
              role="progressbar"
              :aria-valuenow="sendPercent"
              aria-valuemin="0"
              aria-valuemax="100"
            />
            <span class="relative flex items-center gap-2 tabular-nums">
              <PaperAirplaneIcon class="h-4 w-4" />
              <template v-if="job?.running">
                {{ jobLabel === 'Sending…' ? 'Sending' : jobLabel }} · {{ sendPercent }}% ({{ job.sent + job.failed }}/{{ job.total }})
              </template>
              <template v-else>Send stop sale to {{ activeRecipients }} recipient{{ activeRecipients === 1 ? '' : 's' }}</template>
            </span>
          </button>
          <p class="text-[11px] text-slate-500">
            Each recipient gets their own email (no CC). Room types are recalculated from the latest combined inventory when you send.
          </p>

          <form class="flex gap-2 border-t border-slate-100 pt-3" @submit.prevent="sendTest">
            <input v-model="testEmail" type="email" required placeholder="Send a test to…" class="neu-input py-1 text-xs" />
            <button type="submit" class="btn-flat shrink-0 py-1 text-xs" :disabled="sending || !selectedDates.length || !smtp?.configured">Send test</button>
          </form>

          <p v-if="sendError" class="font-semibold text-rose-700">{{ sendError }}</p>
          <p v-if="testSent" class="font-semibold text-emerald-700">Test sent to {{ testSent }}</p>

          <!-- Full send progress (runs on the server; survives a page reload) -->
          <div v-if="job && (job.running || job.finishedAt)" class="space-y-2 rounded-lg bg-slate-50 p-3">
            <div class="flex items-center justify-between gap-2 font-semibold">
              <span :class="job.running ? 'text-slate-700' : job.failed || job.error || job.stopped ? 'text-amber-800' : 'text-emerald-700'">
                {{ jobLabel }}
              </span>
              <span class="tabular-nums text-slate-600">{{ job.sent + job.failed }} / {{ job.total }}</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                class="h-full rounded-full bg-emerald-500 transition-all"
                :style="{ width: `${job.total ? ((job.sent + job.failed) / job.total) * 100 : 0}%` }"
              />
            </div>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <p class="text-slate-600">
                {{ job.sent }} sent<template v-if="job.failed">, <span class="font-semibold text-rose-700">{{ job.failed }} failed</span></template>
                <template v-if="job.running && remainingEstimate"> · about {{ remainingEstimate }} left</template>
                <template v-if="!job.running && job.stopped"> · {{ job.total - job.sent - job.failed }} not sent</template>
              </p>
              <button
                v-if="job.running"
                type="button"
                class="btn-flat px-2.5 py-1 text-xs text-rose-700"
                :disabled="stopping"
                @click="stopSend"
              >
                {{ stopping ? 'Stopping…' : 'Stop' }}
              </button>
            </div>
            <p v-if="job.error" class="font-semibold text-rose-700">{{ job.error }}</p>
            <ul v-if="job.failed" class="max-h-32 space-y-0.5 overflow-auto text-rose-700">
              <li v-for="r in job.results.filter(r => !r.ok)" :key="r.email">{{ r.email }}: {{ r.error }}</li>
            </ul>
          </div>
        </div>

        <!-- Email preview -->
        <div class="neu-card overflow-hidden text-xs">
          <div class="border-b border-slate-200 p-4">
            <h2 class="text-sm font-semibold text-app-tertiary">Email preview</h2>
            <template v-if="preview">
              <p class="mt-1 text-slate-600"><span class="text-slate-400">From</span> {{ preview.from }}</p>
              <p class="text-slate-600"><span class="text-slate-400">To</span> {{ preview.to }}</p>
              <p class="font-semibold text-slate-800"><span class="font-normal text-slate-400">Subject</span> {{ preview.subject }}</p>
            </template>
          </div>
          <p v-if="!selectedDates.length" class="p-4 text-slate-500">Tick at least one date to see the email.</p>
          <p v-else-if="previewError" class="p-4 font-semibold text-rose-700">{{ previewError }}</p>
          <iframe
            v-else-if="preview"
            :srcdoc="preview.html"
            sandbox=""
            title="Stop sale email preview"
            class="h-[28rem] w-full bg-white"
          />
        </div>
      </div>
    </div>

    <!-- ===== Recipients ===== -->
    <div v-show="activeTab === 'recipients'">
      <StopSaleRecipientsCard @changed="onRecipientsChanged" />
    </div>

    <!-- ===== Settings ===== -->
    <div v-show="activeTab === 'settings'">
      <StopSaleSettingsCard
        :recipient-count="activeRecipients"
        @saved="t => { throttle = t; loadPreview() }"
        @loaded="t => (throttle = t)"
        @smtp="s => (smtp = s)"
      />
    </div>

    <!-- ===== History ===== -->
    <div v-show="activeTab === 'history'" class="neu-card overflow-hidden">
      <div class="flex items-center justify-between gap-2 border-b border-slate-200 p-4">
        <h2 class="text-sm font-semibold text-app-tertiary">Sent stop sales</h2>
        <button type="button" class="btn-icon" aria-label="Reload history" @click="loadHistory"><ArrowPathIcon class="h-4 w-4" /></button>
      </div>
      <p v-if="historyError" class="p-4 text-xs font-semibold text-rose-700">{{ historyError }}</p>
      <p v-else-if="!history.length" class="p-4 text-xs text-slate-500">Nothing sent yet.</p>
      <ul v-else class="divide-y divide-slate-100 text-xs">
        <li v-for="h in history" :key="h.id">
          <button type="button" class="flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-50" @click="toggleHistory(h.id)">
            <span class="font-semibold text-slate-800">{{ formatDateTime(h.sentAt) }}</span>
            <span class="text-slate-500">{{ h.ranges.length }} range{{ h.ranges.length === 1 ? '' : 's' }}</span>
            <span :class="h.failedCount ? 'font-semibold text-amber-800' : 'text-emerald-700'">
              {{ h.sentCount }} sent<template v-if="h.failedCount"> · {{ h.failedCount }} failed</template>
            </span>
          </button>
          <div v-if="openHistory.has(h.id)" class="grid grid-cols-1 gap-4 bg-slate-50 px-4 py-3 md:grid-cols-2">
            <div>
              <p class="mb-1 font-semibold text-slate-600">{{ h.subject }}</p>
              <ul class="space-y-0.5 text-slate-700">
                <li v-for="r in h.ranges" :key="r.start">
                  <span class="font-semibold">{{ formatRange(r.start, r.end) }}</span>:
                  {{ r.allRooms ? 'All room types' : r.rooms.join(', ') }}
                </li>
              </ul>
            </div>
            <ul class="space-y-0.5">
              <li v-for="r in h.results" :key="r.email" :class="r.ok ? 'text-slate-600' : 'text-rose-700'">
                {{ r.ok ? '✓' : '✗' }} {{ r.name }}<template v-if="r.company"> ({{ r.company }})</template> · {{ r.email }}
                <template v-if="!r.ok"> - {{ r.error }}</template>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import { estimateSendSeconds, formatDuration, type Throttle } from '../utils/stopSale'
import StopSaleRecipientsCard, { type Recipient } from '../components/StopSaleRecipientsCard.vue'
import StopSaleSettingsCard, { type SmtpStatus } from '../components/StopSaleSettingsCard.vue'
import {
  ArrowPathIcon,
  PaperAirplaneIcon,
  NoSymbolIcon,
  UserGroupIcon,
  Cog6ToothIcon,
  ClockIcon,
} from '@heroicons/vue/24/outline'

interface Closure {
  date: string
  occupancy: number | null
  hotelFull: boolean
  allRooms: boolean
  rooms: { room: string; remaining: number | null; threshold: number | null }[]
}
interface Range { start: string; end: string; allRooms: boolean; rooms: string[] }
interface SendResultRow { name: string; email: string; company: string; ok: boolean; error: string | null }
interface HistoryEntry {
  id: number
  sentAt: string
  subject: string
  ranges: Range[]
  results: SendResultRow[]
  sentCount: number
  failedCount: number
}

type TabId = 'send' | 'recipients' | 'settings' | 'history'
const TABS: { id: TabId; name: string; icon: Component }[] = [
  { id: 'send', name: 'Send', icon: NoSymbolIcon },
  { id: 'recipients', name: 'Recipients', icon: UserGroupIcon },
  { id: 'settings', name: 'Settings', icon: Cog6ToothIcon },
  { id: 'history', name: 'History', icon: ClockIcon },
]
const route = useRoute()
const router = useRouter()
const activeTab = ref<TabId>(TABS.some(t => t.id === route.query.tab) ? route.query.tab as TabId : 'send')
function selectTab(id: TabId) {
  activeTab.value = id
  router.replace({ query: { ...route.query, tab: id === 'send' ? undefined : id } })
  if (id === 'history') loadHistory()
}

const message = (err: any, fallback: string) => err?.response?.data?.message || fallback

// ---- dates
const closures = ref<Closure[]>([])
const updatedAt = ref<string | null>(null)
const loaded = ref(false)
const loading = ref(false)
const loadError = ref('')
// Track unticked dates (not ticked ones) so dates that newly qualify after a
// reload start ticked.
const unticked = ref(new Set<string>())
const selectedDates = computed(() => closures.value.filter(c => !unticked.value.has(c.date)).map(c => c.date))

function toggle(date: string) {
  const next = new Set(unticked.value)
  if (next.has(date)) next.delete(date)
  else next.add(date)
  unticked.value = next
}
function tickAll(on: boolean) {
  unticked.value = on ? new Set() : new Set(closures.value.map(c => c.date))
}

async function loadPreview() {
  loading.value = true
  try {
    const res = await axios.get('/api/stop-sale/preview')
    closures.value = res.data.closures
    updatedAt.value = res.data.updatedAt
    loadError.value = ''
  } catch (err: any) {
    closures.value = []
    loadError.value = message(err, 'Could not load stop sale dates.')
  } finally {
    loading.value = false
    loaded.value = true
  }
}

// ---- recipients / smtp
const activeRecipients = ref(0)
const smtp = ref<SmtpStatus | null>(null)
function onRecipientsChanged(list: Recipient[]) {
  activeRecipients.value = list.filter(r => r.active).length
  refreshEmailPreview()
}

// ---- email preview (debounced on tick changes)
const preview = ref<{ ranges: Range[]; subject: string; from: string; to: string; html: string } | null>(null)
const previewError = ref('')
let previewTimer: ReturnType<typeof setTimeout> | undefined
let previewSeq = 0
function refreshEmailPreview() {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(async () => {
    const seq = ++previewSeq
    if (!selectedDates.value.length) { preview.value = null; return }
    try {
      const res = await axios.post('/api/stop-sale/email-preview', { dates: selectedDates.value })
      if (seq !== previewSeq) return
      preview.value = res.data
      previewError.value = ''
    } catch (err: any) {
      if (seq !== previewSeq) return
      preview.value = null
      previewError.value = message(err, 'Could not build the email preview.')
    }
  }, 300)
}
watch(selectedDates, refreshEmailPreview)

// ---- send
interface SendJob {
  running: boolean
  total: number
  sent: number
  failed: number
  results: SendResultRow[]
  error: string | null
  logId: number | null
  finishedAt: string | null
  pausedUntil: string | null
  stopped: boolean
  throttle: Throttle | null
}
const sending = ref(false)
const sendError = ref('')
const testSent = ref('')
const testEmail = ref('')
const job = ref<SendJob | null>(null)
const canSend = computed(() =>
  !sending.value && !job.value?.running && selectedDates.value.length > 0 &&
  activeRecipients.value > 0 && !!smtp.value?.configured)

let pollTimer: ReturnType<typeof setTimeout> | undefined
async function pollJob() {
  clearTimeout(pollTimer)
  try {
    const res = await axios.get('/api/stop-sale/send-status')
    job.value = res.data.job
  } catch {
    // keep polling; a blip shouldn't hide a send that's still running
  }
  if (job.value?.running) {
    pollTimer = setTimeout(pollJob, 1000)
    return
  }
  stopping.value = false
  if (job.value?.finishedAt) loadHistory()
}

async function send() {
  const ranges = preview.value?.ranges.length
  const summary = `${selectedDates.value.length} date${selectedDates.value.length === 1 ? '' : 's'}${ranges ? ` (${ranges} range${ranges === 1 ? '' : 's'})` : ''}`
  const duration = throttle.value ? ` It will take about ${formatDuration(estimateSendSeconds(activeRecipients.value, throttle.value))}.` : ''
  if (!window.confirm(`Send the stop sale for ${summary} to ${activeRecipients.value} recipient${activeRecipients.value === 1 ? '' : 's'}?${duration}`)) return
  sending.value = true
  sendError.value = ''
  testSent.value = ''
  try {
    const res = await axios.post('/api/stop-sale/send', { dates: selectedDates.value })
    job.value = res.data.job
    pollJob()
  } catch (err: any) {
    sendError.value = message(err, 'Sending failed.')
  } finally {
    sending.value = false
  }
}

const throttle = ref<Throttle | null>(null)
const stopping = ref(false)
const jobLabel = computed(() => {
  const j = job.value
  if (!j) return ''
  if (j.running && stopping.value) return 'Stopping…'
  if (j.running && j.pausedUntil) {
    const until = new Date(j.pausedUntil)
    // Only call out the long batch pauses, not the few seconds between emails.
    if (until.getTime() - Date.now() > 30000) {
      return `Batch pause until ${until.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`
    }
  }
  if (j.running) return 'Sending…'
  if (j.error) return 'Stopped by an error'
  if (j.stopped) return 'Stopped'
  return 'Done'
})
const sendPercent = computed(() => {
  const j = job.value
  return j?.total ? Math.floor(((j.sent + j.failed) / j.total) * 100) : 0
})
const remainingEstimate = computed(() => {
  const j = job.value
  if (!j?.running || !j.throttle) return ''
  const left = j.total - j.sent - j.failed
  return left > 0 ? formatDuration(estimateSendSeconds(left, j.throttle)) : ''
})

async function stopSend() {
  if (!window.confirm("Stop sending? Emails already sent stay sent; the rest won't go out.")) return
  stopping.value = true
  try {
    await axios.post('/api/stop-sale/send-stop')
    await pollJob()
  } catch (err: any) {
    sendError.value = message(err, 'Could not stop the send.')
  }
}

async function sendTest() {
  sending.value = true
  sendError.value = ''
  testSent.value = ''
  try {
    await axios.post('/api/stop-sale/send-test', { dates: selectedDates.value, email: testEmail.value }, { timeout: 60000 })
    testSent.value = testEmail.value
  } catch (err: any) {
    sendError.value = message(err, 'The test email failed.')
  } finally {
    sending.value = false
  }
}

// ---- history
const history = ref<HistoryEntry[]>([])
const historyError = ref('')
const openHistory = ref(new Set<number>())
async function loadHistory() {
  try {
    const res = await axios.get('/api/stop-sale/history')
    history.value = res.data.history
    historyError.value = ''
  } catch (err: any) {
    historyError.value = message(err, 'Could not load history.')
  }
}
function toggleHistory(id: number) {
  const next = new Set(openHistory.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  openHistory.value = next
}

// ---- formatting
function parseDay(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}
function formatDay(iso: string, withYear = true) {
  return parseDay(iso).toLocaleDateString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}),
  })
}
function formatRange(start: string, end: string) {
  return start === end ? formatDay(start) : `${formatDay(start, start.slice(0, 4) !== end.slice(0, 4))} – ${formatDay(end)}`
}
function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  loadPreview()
  pollJob()
  if (activeTab.value === 'history') loadHistory()
})
onBeforeUnmount(() => clearTimeout(pollTimer))
</script>
