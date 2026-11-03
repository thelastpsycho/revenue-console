<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 pb-24 sm:p-6 lg:p-8">
    <PageHeader
      title="Allotment Rules"
      subtitle="How many rooms go online per room type, and how suites borrow from each other when a category sells out. Edit the thresholds and routing below; nothing changes until you press Save."
    />

    <p v-if="loadError" class="rounded-lg bg-rose-50 p-3 text-xs font-semibold text-rose-700">{{ loadError }}</p>

    <template v-if="settings">
      <!-- Release rules -->
      <div class="neu-card space-y-3 p-4 text-xs">
        <h2 class="text-sm font-semibold text-app-tertiary">Release rules</h2>
        <p class="text-slate-500">How many rooms open online given how many physically remain. "Tiered" matches remaining rooms against a bucket schedule; "Keep back" holds a fixed number back; "Sell as remaining" releases everything.</p>
        <div v-for="room in roomTypes" :key="room" class="space-y-2 rounded-lg bg-app-primary p-3 shadow-neu-inset-sm">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <span class="font-semibold text-slate-700">{{ room }}</span>
            <select v-model="settings.releaseRules[room].kind" class="neu-input w-40 py-1" @change="onKindChange(room)">
              <option value="tiered">Tiered</option>
              <option value="keepBack">Keep back</option>
              <option value="sellAsRemaining">Sell as remaining</option>
            </select>
          </div>

          <!-- Tiered rows -->
          <div v-if="settings.releaseRules[room].kind === 'tiered'" class="space-y-1.5">
            <div
              v-for="(row, i) in (settings.releaseRules[room] as TieredRule).rows"
              :key="i"
              class="flex flex-wrap items-center gap-2"
            >
              <label class="flex items-center gap-1">
                <span class="text-slate-500">Min</span>
                <input v-model.number="row.min" type="number" min="1" class="neu-input w-16 py-1" />
              </label>
              <label class="flex items-center gap-1">
                <span class="text-slate-500">Max</span>
                <input
                  :value="row.max ?? ''"
                  @input="row.max = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"
                  type="number"
                  min="1"
                  placeholder="∞"
                  class="neu-input w-16 py-1"
                />
              </label>
              <label class="flex items-center gap-1">
                <span class="text-slate-500">Release</span>
                <input v-model.number="row.release" type="number" min="0" class="neu-input w-16 py-1" />
              </label>
              <button type="button" class="rounded px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50" @click="(settings!.releaseRules[room] as TieredRule).rows.splice(i, 1)">
                Remove
              </button>
            </div>
            <button
              type="button"
              class="rounded-lg px-2 py-1 font-semibold text-app-accent hover:bg-slate-100"
              @click="(settings!.releaseRules[room] as TieredRule).rows.push({ min: 1, max: null, release: 0 })"
            >
              + Add row
            </button>
          </div>

          <!-- Keep back -->
          <div v-else-if="settings.releaseRules[room].kind === 'keepBack'" class="flex flex-wrap items-center gap-4">
            <label class="flex items-center gap-1.5">
              <span class="text-slate-500">Keep back</span>
              <input v-model.number="(settings.releaseRules[room] as KeepBackRule).amount" type="number" min="0" class="neu-input w-16 py-1" />
            </label>
            <label class="flex cursor-pointer items-center gap-1.5">
              <input v-model="(settings.releaseRules[room] as KeepBackRule).exceptLast" type="checkbox" class="h-3.5 w-3.5 accent-app-accent" />
              Sell the very last room
            </label>
          </div>
        </div>
      </div>

      <!-- Deluxe Suite borrow -->
      <div class="neu-card space-y-3 p-4 text-xs">
        <h2 class="text-sm font-semibold text-app-tertiary">Deluxe Suite borrow</h2>
        <p class="text-slate-500">When Deluxe Suite Room is fully sold, borrow a room from another category if it has more than the threshold remaining.</p>
        <div class="flex flex-wrap items-end gap-3">
          <label>
            <span class="mb-1 block font-semibold text-slate-600">From</span>
            <select v-model="settings.deluxeSuiteBorrow.fromRoomType" class="neu-input">
              <option v-for="room in roomTypes.filter(r => r !== 'Deluxe Suite Room')" :key="room" :value="room">{{ room }}</option>
            </select>
          </label>
          <label>
            <span class="mb-1 block font-semibold text-slate-600">Threshold (more than)</span>
            <input v-model.number="settings.deluxeSuiteBorrow.threshold" type="number" min="0" class="neu-input w-24" />
          </label>
          <label>
            <span class="mb-1 block font-semibold text-slate-600">Borrow amount</span>
            <input v-model.number="settings.deluxeSuiteBorrow.amount" type="number" min="0" class="neu-input w-24" />
          </label>
        </div>
      </div>

      <!-- Suite routing -->
      <div class="neu-card space-y-3 p-4 text-xs">
        <h2 class="text-sm font-semibold text-app-tertiary">Suite routing</h2>
        <p class="text-slate-500">Which categories a shortage can borrow from. A selection that exceeds the hotel's tier order is rejected on save.</p>
        <div v-for="room in roomTypes" :key="room" class="space-y-1 rounded-lg bg-app-primary p-3 shadow-neu-inset-sm">
          <span class="font-semibold text-slate-700">{{ room }}</span>
          <div class="flex flex-wrap gap-x-4 gap-y-1">
            <label v-for="dest in roomTypes.filter(r => r !== room)" :key="dest" class="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" :value="dest" v-model="routes[room]" class="h-3 w-3 accent-app-accent" />
              {{ dest }}
            </label>
          </div>
        </div>

        <h3 class="pt-2 font-semibold text-slate-700">Buffers (rooms held back before upgrades are even considered)</h3>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label v-for="room in roomTypes" :key="room" class="flex items-center justify-between gap-2 rounded-lg bg-app-primary px-2 py-1 shadow-neu-inset-sm">
            <span class="truncate text-slate-600" :title="room">{{ room }}</span>
            <input v-model.number="buffers[room]" type="number" min="0" class="neu-input w-14 py-0.5" />
          </label>
        </div>

        <h3 class="pt-2 font-semibold text-slate-700">Manual holds</h3>
        <ul v-if="holds.length" class="space-y-1.5">
          <li v-for="(h, i) in holds" :key="i" class="flex items-start justify-between gap-2 rounded-lg bg-app-primary px-3 py-2 shadow-neu-inset-sm">
            <div class="min-w-0">
              <p class="font-semibold text-slate-700">{{ h.room_type }} · {{ h.start_date }} – {{ h.end_date }}</p>
              <p class="text-slate-500">
                {{ h.rooms }} room{{ h.rooms === 1 ? '' : 's' }} held<template v-if="h.max_online !== undefined"> · online capped at {{ h.max_online }}</template>
              </p>
            </div>
            <button type="button" class="shrink-0 rounded-lg px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50" @click="holds.splice(i, 1)">Remove</button>
          </li>
        </ul>
        <div class="flex flex-wrap items-end gap-2 rounded-lg bg-app-primary p-3 shadow-neu-inset-sm">
          <label>
            <span class="mb-1 block font-semibold text-slate-600">Room type</span>
            <select v-model="newHold.room_type" class="neu-input">
              <option v-for="room in roomTypes" :key="room" :value="room">{{ room }}</option>
            </select>
          </label>
          <label>
            <span class="mb-1 block font-semibold text-slate-600">Start</span>
            <input v-model="newHold.start_date" type="date" class="neu-input" />
          </label>
          <label>
            <span class="mb-1 block font-semibold text-slate-600">End</span>
            <input v-model="newHold.end_date" type="date" class="neu-input" />
          </label>
          <label>
            <span class="mb-1 block font-semibold text-slate-600">Rooms held</span>
            <input v-model.number="newHold.rooms" type="number" min="0" class="neu-input w-20" />
          </label>
          <label>
            <span class="mb-1 block font-semibold text-slate-600">Max online (optional)</span>
            <input v-model="newHoldMaxOnline" type="number" min="0" class="neu-input w-24" />
          </label>
          <button type="button" class="btn-flat py-1.5" :disabled="!newHold.start_date || !newHold.end_date" @click="addHold">
            + Add hold
          </button>
        </div>
      </div>
    </template>

    <div class="fixed inset-x-0 bottom-0 z-10 mx-auto flex max-w-7xl items-center gap-3 border-t border-slate-200 bg-white/95 px-4 py-3 shadow-lg sm:px-6 lg:px-8">
      <button type="button" class="btn-primary" :disabled="busy || !settings" @click="save">
        {{ busy ? 'Saving…' : 'Save settings' }}
      </button>
      <span v-if="saveMessage" class="text-xs text-slate-600" role="status">{{ saveMessage }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'

interface TieredRow { min: number; max: number | null; release: number }
interface TieredRule { kind: 'tiered'; rows: TieredRow[] }
interface KeepBackRule { kind: 'keepBack'; amount: number; exceptLast: boolean }
interface SellAsRemainingRule { kind: 'sellAsRemaining' }
type ReleaseRule = TieredRule | KeepBackRule | SellAsRemainingRule

interface Hold { room_type: string; start_date: string; end_date: string; rooms: number; max_online?: number }

interface Settings {
  releaseRules: Record<string, ReleaseRule>
  deluxeSuiteBorrow: { fromRoomType: string; threshold: number; amount: number }
  suiteRouting: { routes?: Record<string, string[]>; buffers?: Record<string, number>; holds?: Hold[] }
}

const roomTypes = ref<string[]>([])
const settings = ref<Settings | null>(null)
const loadError = ref('')
const busy = ref(false)
const saveMessage = ref('')

// Editable mirrors of suiteRouting's sub-fields, reassembled on save.
const routes = reactive<Record<string, string[]>>({})
// Snapshot of what was in effect at load time (defaults included), so an
// untouched room isn't re-saved as an explicit override of its default -
// only rooms the operator actually changed become stored overrides.
let routesAtLoad: Record<string, string[]> = {}
const buffers = reactive<Record<string, number>>({})
const holds = ref<Hold[]>([])
const newHold = reactive({ room_type: '', start_date: '', end_date: '', rooms: 1 })
const newHoldMaxOnline = ref<number | null>(null)

const message = (err: any, fallback: string) => err?.response?.data?.message || fallback

function onKindChange(room: string) {
  const kind = settings.value!.releaseRules[room].kind
  const fresh: ReleaseRule =
    kind === 'tiered' ? { kind, rows: [{ min: 1, max: null, release: 0 }] } :
    kind === 'keepBack' ? { kind, amount: 1, exceptLast: false } :
    { kind: 'sellAsRemaining' }
  settings.value!.releaseRules[room] = fresh
}

function addHold() {
  holds.value.push({
    room_type: newHold.room_type || roomTypes.value[0],
    start_date: newHold.start_date,
    end_date: newHold.end_date,
    rooms: newHold.rooms,
    ...(newHoldMaxOnline.value !== null ? { max_online: newHoldMaxOnline.value } : {}),
  })
  Object.assign(newHold, { room_type: '', start_date: '', end_date: '', rooms: 1 })
  newHoldMaxOnline.value = null
}

async function load() {
  try {
    const res = await axios.get('/api/allotment-rules/settings')
    roomTypes.value = res.data.roomTypes
    settings.value = res.data.settings
    const effectiveRoutes: Record<string, string[]> = res.data.effectiveRoutes
    routesAtLoad = effectiveRoutes
    for (const room of roomTypes.value) {
      // Show what's actually in effect (defaults included), not just the
      // possibly-empty stored override - an untouched room isn't "no
      // upgrades allowed", it's "still on the hotel's default tier order".
      routes[room] = [...(effectiveRoutes[room] || [])]
      buffers[room] = settings.value!.suiteRouting.buffers?.[room] || 0
    }
    holds.value = settings.value!.suiteRouting.holds || []
    loadError.value = ''
  } catch (err: any) {
    loadError.value = message(err, 'Could not load allotment rules.')
  }
}

function sameRoutes(a: string[], b: string[]) {
  return a.length === b.length && [...a].sort().join() === [...b].sort().join()
}

async function save() {
  if (!settings.value) return
  busy.value = true
  saveMessage.value = ''
  // Start from whatever was actually stored (a room absent here is already
  // relying on the default), and only overwrite rooms the operator changed
  // this session - otherwise an unrelated edit elsewhere on the page would
  // silently wipe out a pre-existing custom override on save, since the
  // whole suiteRouting.routes document gets replaced, not merged.
  const changedRoutes = { ...(settings.value.suiteRouting.routes || {}) }
  for (const room of roomTypes.value) {
    if (!sameRoutes(routes[room] || [], routesAtLoad[room] || [])) changedRoutes[room] = routes[room]
  }
  const payload: Settings = {
    releaseRules: settings.value.releaseRules,
    deluxeSuiteBorrow: settings.value.deluxeSuiteBorrow,
    suiteRouting: {
      routes: changedRoutes,
      buffers: Object.fromEntries(Object.entries(buffers).filter(([, v]) => v > 0)),
      holds: holds.value,
    },
  }
  try {
    await axios.put('/api/allotment-rules/settings', payload)
    await load()
    saveMessage.value = 'Saved.'
  } catch (err: any) {
    saveMessage.value = message(err, 'Could not save allotment rules.')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
