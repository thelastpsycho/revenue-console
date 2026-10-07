<template>
  <form class="grid grid-cols-1 gap-4 xl:grid-cols-12" @submit.prevent="save">
    <!-- Rule -->
    <div class="neu-card space-y-4 p-4 text-xs xl:col-span-5">
      <div>
        <h2 class="text-sm font-semibold text-app-tertiary">Stop sale rule</h2>
        <p class="mt-0.5 text-slate-500">Checked against combined inventory for every scraped date from today on.</p>
      </div>

      <div class="rounded-lg bg-slate-50 p-3">
        <label for="ss-occ" class="block font-semibold text-slate-700">Whole hotel: stop sale all room types when occupancy is at least</label>
        <div class="mt-2 flex items-center gap-2">
          <input id="ss-occ" v-model="occupancy" type="number" min="1" max="200" step="1" class="neu-input w-24 py-1" placeholder="Off" />
          <span class="font-semibold text-slate-600">%</span>
          <span class="text-slate-500">Leave empty to switch this off.</span>
        </div>
      </div>

      <div>
        <p class="font-semibold text-slate-700">Single room type: stop sale when remaining rooms are at or below</p>
        <p class="mt-0.5 text-slate-500">
          Untick a room type to leave it out of the stop sale email completely, even when the whole hotel closes.
          Empty threshold = the room type only closes with the whole hotel. 0 = only when sold out. Overbooked (negative) counts as below.
        </p>
        <div class="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
          <div class="flex items-center justify-between gap-3 bg-slate-50 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <label class="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                class="h-3.5 w-3.5 cursor-pointer accent-app-accent"
                :checked="!excluded.size"
                :indeterminate.prop="excluded.size > 0 && excluded.size < roomTypes.length"
                aria-label="Tick or untick all room types"
                @change="setAll(($event.target as HTMLInputElement).checked)"
              />
              Room type in email
            </label>
            <span>Remaining ≤</span>
          </div>
          <div
            v-for="room in roomTypes"
            :key="room"
            :class="['flex items-center justify-between gap-3 px-3 py-1.5', excluded.has(room) && 'bg-slate-50']"
          >
            <label class="flex min-w-0 cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                class="h-3.5 w-3.5 shrink-0 cursor-pointer accent-app-accent"
                :checked="!excluded.has(room)"
                @change="toggleRoom(room)"
              />
              <span :class="['font-semibold', excluded.has(room) ? 'text-slate-400 line-through' : 'text-slate-600']">{{ room }}</span>
            </label>
            <input
              v-model="roomThresholds[room]"
              type="number"
              min="0"
              max="500"
              step="1"
              :placeholder="excluded.has(room) ? '–' : 'Off'"
              :disabled="excluded.has(room)"
              :aria-label="`${room} threshold`"
              class="neu-input w-20 shrink-0 py-1 text-right disabled:opacity-40"
            />
          </div>
        </div>
        <p v-if="excluded.size" class="mt-2 text-amber-700">
          {{ excluded.size }} room type{{ excluded.size === 1 ? '' : 's' }} left out, so whole-hotel days list the ticked room types one by one instead of "All room types".
        </p>
      </div>
    </div>

    <div class="space-y-4 xl:col-span-7">
      <!-- Sending speed -->
      <div class="neu-card space-y-3 p-4 text-xs">
        <div>
          <h2 class="text-sm font-semibold text-app-tertiary">Sending speed</h2>
          <p class="mt-0.5 text-slate-500">
            Slow the send down so the mail server doesn't flag it as bulk mail or hit its hourly limit.
            Ask your mail host for the limit if you're unsure.
          </p>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label for="ss-delay" class="mb-1 block font-semibold text-slate-600">Seconds between emails</label>
            <input id="ss-delay" v-model.number="throttle.delaySeconds" type="number" min="0" max="300" step="1" class="neu-input py-1" />
          </div>
          <div>
            <label for="ss-batch" class="mb-1 block font-semibold text-slate-600">Pause after every … emails</label>
            <input id="ss-batch" v-model.number="throttle.batchSize" type="number" min="0" max="1000" step="1" class="neu-input py-1" placeholder="0 = no batches" />
          </div>
          <div>
            <label for="ss-pause" class="mb-1 block font-semibold text-slate-600">Pause length (minutes)</label>
            <input id="ss-pause" v-model.number="throttle.batchPauseMinutes" type="number" min="0" max="180" step="1" class="neu-input py-1" :disabled="!throttle.batchSize" />
          </div>
        </div>
        <p class="rounded-lg bg-slate-50 px-3 py-2 text-slate-600">
          <template v-if="throttle.batchSize > 0">
            Sends {{ throttle.batchSize }} emails, waits {{ throttle.batchPauseMinutes || 0 }} min, then the next {{ throttle.batchSize }}.
          </template>
          {{ recipientCount }} recipients take about <span class="font-semibold text-slate-800">{{ estimate }}</span>.
        </p>
      </div>

      <!-- Email -->
      <div class="neu-card space-y-3 p-4 text-xs">
        <div>
          <h2 class="text-sm font-semibold text-app-tertiary">Email</h2>
          <p class="mt-0.5 text-slate-500">
            Every recipient gets their own email starting "Dear &lt;name&gt;,", then the intro, the stop sale dates
            (consecutive dates grouped into ranges, with hotel room names), and the closing. You can use
            <span class="font-mono">{name}</span> and <span class="font-mono">{company}</span> in the subject, intro and closing.
          </p>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label for="ss-from" class="mb-1 block font-semibold text-slate-600">Sender display name</label>
            <input id="ss-from" v-model="email.fromName" required maxlength="120" class="neu-input" />
          </div>
          <div>
            <label for="ss-subject" class="mb-1 block font-semibold text-slate-600">Subject</label>
            <input id="ss-subject" v-model="email.subject" required maxlength="200" class="neu-input" />
          </div>
        </div>
        <div>
          <label for="ss-intro" class="mb-1 block font-semibold text-slate-600">Intro</label>
          <textarea id="ss-intro" v-model="email.intro" rows="4" maxlength="4000" class="neu-input" />
        </div>
        <div>
          <label for="ss-closing" class="mb-1 block font-semibold text-slate-600">Closing</label>
          <textarea id="ss-closing" v-model="email.closing" rows="5" maxlength="4000" class="neu-input" />
        </div>
      </div>

      <!-- SMTP -->
      <div class="neu-card space-y-2 p-4 text-xs">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-app-tertiary">Mail server</h2>
          <span
            v-if="smtp"
            :class="['rounded-full px-2.5 py-1 text-[11px] font-semibold', smtp.configured ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700']"
          >
            {{ smtp.configured ? 'Ready' : 'Not set up' }}
          </span>
        </div>
        <template v-if="smtp?.configured">
          <p class="text-slate-600">
            Sending from <span class="font-semibold">{{ email.fromName }} &lt;{{ smtp.fromEmail }}&gt;</span>
            via {{ smtp.host }}:{{ smtp.port }} ({{ smtp.security }}).
          </p>
        </template>
        <template v-else-if="smtp">
          <ul class="list-inside list-disc text-amber-700">
            <li v-for="p in smtp.problems" :key="p">{{ p }}</li>
          </ul>
        </template>
        <p class="text-slate-500">
          The SMTP details live in <span class="font-mono">backend/.env</span>, not here, so the password never reaches the browser:
          <span class="font-mono">SMTP_HOST, SMTP_PORT, SMTP_SECURITY, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL</span>.
          Restart the backend after changing them.
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <button type="submit" class="btn-primary" :disabled="busy || !loaded">Save settings</button>
        <span v-if="saved" class="text-xs font-semibold text-emerald-700">Saved</span>
        <span v-if="error" class="text-xs font-semibold text-rose-700">{{ error }}</span>
      </div>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '../plugins/axios'
import { estimateSendSeconds, formatDuration, type Throttle } from '../utils/stopSale'

export interface SmtpStatus {
  configured: boolean
  problems: string[]
  host: string
  port: number
  security: string
  fromEmail: string
}

const props = defineProps<{ recipientCount: number }>()
const emit = defineEmits<{ (e: 'saved', throttle: Throttle): void; (e: 'smtp', status: SmtpStatus): void; (e: 'loaded', throttle: Throttle): void }>()

const roomTypes = ref<string[]>([])
// Inputs hold '' for "off"; v-model on number inputs gives numbers otherwise.
const occupancy = ref<number | ''>('')
const roomThresholds = reactive<Record<string, number | ''>>({})
const excluded = ref(new Set<string>())
function toggleRoom(room: string) {
  const next = new Set(excluded.value)
  if (next.has(room)) next.delete(room)
  else next.add(room)
  excluded.value = next
}
function setAll(on: boolean) {
  excluded.value = on ? new Set() : new Set(roomTypes.value)
}
const email = reactive({ fromName: '', subject: '', intro: '', closing: '' })
const throttle = reactive<Throttle>({ delaySeconds: 2, batchSize: 0, batchPauseMinutes: 0 })
const estimate = computed(() => formatDuration(estimateSendSeconds(props.recipientCount, {
  delaySeconds: Number(throttle.delaySeconds) || 0,
  batchSize: Number(throttle.batchSize) || 0,
  batchPauseMinutes: Number(throttle.batchPauseMinutes) || 0,
})))
const smtp = ref<SmtpStatus | null>(null)
const loaded = ref(false)
const busy = ref(false)
const saved = ref(false)
const error = ref('')

const toInput = (v: number | null) => (v === null || v === undefined ? '' : v)
const toValue = (v: number | '' | string) => (v === '' || v === null || v === undefined ? null : Number(v))

async function load() {
  try {
    const res = await axios.get('/api/stop-sale/settings')
    const s = res.data.settings
    roomTypes.value = res.data.roomTypes
    occupancy.value = toInput(s.occupancyThreshold)
    for (const room of roomTypes.value) roomThresholds[room] = toInput(s.roomThresholds[room])
    excluded.value = new Set(s.excludedRooms)
    Object.assign(email, s.email)
    Object.assign(throttle, s.throttle)
    smtp.value = res.data.smtp
    emit('smtp', res.data.smtp)
    emit('loaded', { ...s.throttle })
    error.value = ''
    loaded.value = true
  } catch (err: any) {
    error.value = err?.response?.data?.message || 'Could not load settings.'
  }
}

async function save() {
  busy.value = true
  saved.value = false
  error.value = ''
  try {
    await axios.put('/api/stop-sale/settings', {
      occupancyThreshold: toValue(occupancy.value),
      roomThresholds: Object.fromEntries(roomTypes.value.map(room => [room, toValue(roomThresholds[room])])),
      excludedRooms: [...excluded.value],
      email: { ...email },
      throttle: {
        delaySeconds: Number(throttle.delaySeconds) || 0,
        batchSize: Number(throttle.batchSize) || 0,
        batchPauseMinutes: Number(throttle.batchPauseMinutes) || 0,
      },
    })
    saved.value = true
    setTimeout(() => { saved.value = false }, 2500)
    emit('saved', { ...throttle })
  } catch (err: any) {
    error.value = err?.response?.data?.message || 'Could not save settings.'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
