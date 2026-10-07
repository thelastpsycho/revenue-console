<template>
  <div class="grid grid-cols-1 gap-4 xl:grid-cols-12">
    <!-- Add / edit -->
    <div class="space-y-4 xl:col-span-4">
      <form class="neu-card space-y-3 p-4 text-xs" @submit.prevent="save">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-app-tertiary">{{ editingId ? 'Edit recipient' : 'Add recipient' }}</h2>
          <button v-if="editingId" type="button" class="font-semibold text-slate-500 hover:text-slate-900" @click="resetForm">Cancel</button>
        </div>
        <div>
          <label for="ss-r-name" class="mb-1 block font-semibold text-slate-600">Name</label>
          <input id="ss-r-name" v-model="form.name" required maxlength="120" class="neu-input" placeholder="Contact name, e.g. Ana Putri" />
        </div>
        <div>
          <label for="ss-r-email" class="mb-1 block font-semibold text-slate-600">Email</label>
          <input id="ss-r-email" v-model="form.email" required type="email" maxlength="254" class="neu-input" placeholder="contracting@partner.com" />
        </div>
        <div>
          <label for="ss-r-company" class="mb-1 block font-semibold text-slate-600">Company</label>
          <input id="ss-r-company" v-model="form.company" maxlength="160" class="neu-input" placeholder="e.g. Hotelbeds" />
        </div>
        <div>
          <label for="ss-r-segment" class="mb-1 block font-semibold text-slate-600">Segment</label>
          <input id="ss-r-segment" v-model="form.segment" maxlength="60" list="ss-segments" class="neu-input" placeholder="e.g. Wholesaler" />
          <datalist id="ss-segments">
            <option v-for="s in segmentOptions" :key="s" :value="s" />
          </datalist>
        </div>
        <label class="flex cursor-pointer items-center gap-2 font-semibold text-slate-600">
          <input v-model="form.active" type="checkbox" class="h-3.5 w-3.5 accent-app-accent" />
          Active (receives stop sale emails)
        </label>
        <div class="flex flex-wrap items-center gap-2">
          <button type="submit" class="btn-primary py-1.5 text-xs" :disabled="busy">{{ editingId ? 'Save changes' : 'Add recipient' }}</button>
          <span v-if="formError" class="font-semibold text-rose-700">{{ formError }}</span>
        </div>
      </form>

      <!-- Bulk import -->
      <form class="neu-card space-y-2 p-4 text-xs" @submit.prevent="importRows">
        <h2 class="text-sm font-semibold text-app-tertiary">Import a list</h2>
        <p class="text-slate-500">
          One recipient per line: <span class="font-mono">Name, Email, Company, Segment</span>.
          Tabs work too, so you can paste straight from Excel. Addresses already on the list are skipped.
        </p>
        <textarea
          v-model="importText"
          rows="5"
          class="neu-input font-mono text-xs"
          placeholder="Ana Putri, ana@partner.com, Hotelbeds, Wholesaler"
        />
        <div class="flex flex-wrap items-center gap-2">
          <button type="submit" class="btn-flat py-1.5 text-xs" :disabled="busy || !importText.trim()">Import</button>
          <span v-if="importResult" class="text-slate-600">{{ importResult }}</span>
        </div>
      </form>
    </div>

    <!-- List -->
    <div class="neu-card overflow-hidden xl:col-span-8">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
        <h2 class="text-sm font-semibold text-app-tertiary">
          Recipients
          <span class="ml-1 font-normal text-slate-500">{{ activeCount }} active of {{ recipients.length }}</span>
        </h2>
        <div class="flex w-full flex-wrap gap-2 sm:w-auto">
          <input v-model="search" type="search" placeholder="Search" class="neu-input w-full py-1 text-xs sm:w-44" />
          <select v-model="segmentFilter" class="neu-input w-full py-1 text-xs sm:w-36">
            <option value="">All segments</option>
            <option v-for="s in usedSegments" :key="s" :value="s">{{ s || '(none)' }}</option>
          </select>
        </div>
      </div>
      <p v-if="loadError" class="p-4 text-xs font-semibold text-rose-700">{{ loadError }}</p>
      <p v-else-if="loaded && !recipients.length" class="p-4 text-xs text-slate-500">
        No recipients yet. Add them on the left or import a list. Include the sales and revenue team so they get a copy of every stop sale.
      </p>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-xs">
          <thead class="bg-app-primary">
            <tr>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Name</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Email</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Company</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Segment</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Active</th>
              <th class="px-4 py-2.5"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="r in filtered" :key="r.id" :class="!r.active && 'text-slate-400'">
              <td class="whitespace-nowrap px-4 py-2 font-semibold">{{ r.name }}</td>
              <td class="px-4 py-2 break-all">{{ r.email }}</td>
              <td class="px-4 py-2">{{ r.company }}</td>
              <td class="px-4 py-2">
                <span v-if="r.segment" class="rounded-full bg-slate-100 px-2 py-0.5 font-semibold text-slate-600">{{ r.segment }}</span>
              </td>
              <td class="px-4 py-2">
                <button
                  type="button"
                  role="switch"
                  :aria-checked="r.active"
                  :aria-label="`${r.active ? 'Deactivate' : 'Activate'} ${r.name}`"
                  :disabled="busy"
                  @click="toggleActive(r)"
                  :class="['relative inline-flex h-4 w-7 items-center rounded-full transition-colors', r.active ? 'bg-emerald-500' : 'bg-slate-300']"
                >
                  <span :class="['inline-block h-3 w-3 rounded-full bg-white transition-transform', r.active ? 'translate-x-3.5' : 'translate-x-0.5']" />
                </button>
              </td>
              <td class="whitespace-nowrap px-4 py-2 text-right">
                <button type="button" class="rounded px-2 py-1 font-semibold text-slate-600 hover:bg-slate-100" @click="edit(r)">Edit</button>
                <button type="button" class="rounded px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50" :disabled="busy" @click="remove(r)">Delete</button>
              </td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="6" class="px-4 py-3 text-slate-500">No recipients match.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '../plugins/axios'

export interface Recipient {
  id: number
  name: string
  email: string
  company: string
  segment: string
  active: boolean
}

const emit = defineEmits<{ (e: 'changed', recipients: Recipient[]): void }>()

const DEFAULT_SEGMENTS = ['Wholesaler', 'Travel Agent', 'OTA', 'Corporate', 'MICE', 'Internal']

const recipients = ref<Recipient[]>([])
const loaded = ref(false)
const loadError = ref('')
const busy = ref(false)
const formError = ref('')
const editingId = ref<number | null>(null)
const form = reactive({ name: '', email: '', company: '', segment: '', active: true })
const search = ref('')
const segmentFilter = ref('')
const importText = ref('')
const importResult = ref('')

const activeCount = computed(() => recipients.value.filter(r => r.active).length)
const usedSegments = computed(() => [...new Set(recipients.value.map(r => r.segment))].sort())
const segmentOptions = computed(() => [...new Set([...DEFAULT_SEGMENTS, ...usedSegments.value.filter(Boolean)])])
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return recipients.value.filter(r =>
    (!segmentFilter.value || r.segment === segmentFilter.value) &&
    (!q || [r.name, r.email, r.company, r.segment].some(v => v.toLowerCase().includes(q))))
})

const message = (err: any, fallback: string) => err?.response?.data?.message || fallback

async function load() {
  try {
    const res = await axios.get('/api/stop-sale/recipients')
    recipients.value = res.data.recipients
    loadError.value = ''
    emit('changed', recipients.value)
  } catch (err: any) {
    loadError.value = message(err, 'Could not load recipients.')
  } finally {
    loaded.value = true
  }
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { name: '', email: '', company: '', segment: '', active: true })
  formError.value = ''
}

function edit(r: Recipient) {
  editingId.value = r.id
  Object.assign(form, { name: r.name, email: r.email, company: r.company, segment: r.segment, active: r.active })
  formError.value = ''
}

async function save() {
  busy.value = true
  formError.value = ''
  try {
    if (editingId.value) await axios.put(`/api/stop-sale/recipients/${editingId.value}`, { ...form })
    else await axios.post('/api/stop-sale/recipients', { ...form })
    resetForm()
    await load()
  } catch (err: any) {
    formError.value = message(err, 'Could not save the recipient.')
  } finally {
    busy.value = false
  }
}

async function toggleActive(r: Recipient) {
  busy.value = true
  try {
    await axios.put(`/api/stop-sale/recipients/${r.id}`, { ...r, active: !r.active })
  } catch (err: any) {
    loadError.value = message(err, 'Could not update the recipient.')
  } finally {
    busy.value = false
    await load()
  }
}

async function remove(r: Recipient) {
  if (!window.confirm(`Delete ${r.name} (${r.email}) from the stop sale list?`)) return
  busy.value = true
  try {
    await axios.delete(`/api/stop-sale/recipients/${r.id}`)
    if (editingId.value === r.id) resetForm()
  } catch (err: any) {
    loadError.value = message(err, 'Could not delete the recipient.')
  } finally {
    busy.value = false
    await load()
  }
}

async function importRows() {
  busy.value = true
  importResult.value = ''
  const known = new Set(recipients.value.map(r => r.email.toLowerCase()))
  let added = 0
  let skipped = 0
  const failures: string[] = []
  for (const line of importText.value.split(/\r?\n/)) {
    if (!line.trim()) continue
    const [name = '', email = '', company = '', segment = ''] = line.split(line.includes('\t') ? '\t' : ',').map(v => v.trim())
    if (name.toLowerCase() === 'name' && email.toLowerCase() === 'email') continue // header row
    if (known.has(email.toLowerCase())) { skipped++; continue }
    try {
      await axios.post('/api/stop-sale/recipients', { name, email, company, segment, active: true })
      known.add(email.toLowerCase())
      added++
    } catch (err: any) {
      failures.push(`${email || name}: ${message(err, 'failed')}`)
    }
  }
  importResult.value = [`${added} added`, skipped ? `${skipped} already on the list` : '', ...failures].filter(Boolean).join(' · ')
  if (!failures.length) importText.value = ''
  busy.value = false
  await load()
}

onMounted(load)
defineExpose({ load })
</script>
