<template>
  <div class="mx-auto w-full max-w-5xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="MCP Access"
      subtitle="Connect this console's data to Claude Code, Claude Desktop, claude.ai, or any other MCP-capable client. A personal key below carries your own account's permissions, but only applies when you run the MCP server locally - the shared remote tunnel (claude.ai, or Claude Code against the URL above) uses one fixed identity for everyone, gated by a separate shared secret. See 'How to connect' below for which one you need."
    />

    <div class="neu-card space-y-3 p-4 text-xs">
      <h2 class="text-sm font-semibold text-app-tertiary">MCP server URL</h2>
      <p class="text-slate-500">
        The MCP server runs as its own service, on its own tunnel hostname. Only edit this
        if that hostname ever changes (see <code>mcp-server/README.md</code>) - any change is
        saved in this browser only.
      </p>
      <div class="flex items-center gap-2">
        <input v-model="serverUrl" placeholder="https://mcp.yourdomain.com/mcp" class="neu-input flex-1" />
        <button type="button" class="btn-flat shrink-0 px-3 py-2" :disabled="!serverUrl" @click="copy(serverUrl, 'url')">
          {{ copiedId === 'url' ? 'Copied' : 'Copy' }}
        </button>
      </div>
    </div>

    <div class="neu-card space-y-3 p-4 text-xs">
      <h2 class="text-sm font-semibold text-app-tertiary">How to connect</h2>
      <div class="seg !flex flex-wrap" role="tablist" aria-label="MCP client setup">
        <button
          v-for="tab in clientTabs"
          :key="tab.key"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.key"
          class="seg-btn"
          :aria-current="activeTab === tab.key ? 'page' : undefined"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <div v-if="activeTab === 'remote-cli'" class="space-y-2">
        <p class="text-slate-500">
          Claude Code and Cursor can take a remote MCP server and a header directly on the
          command line. The server URL above goes through this deployment's Cloudflare
          tunnel, which is gated by a single shared secret (<code>MCP_ACCESS_TOKEN</code> in
          <code>mcp-server/.env</code> on the server) - <strong>not</strong> one of your
          personal keys below. Look it up there.
        </p>
        <div class="flex items-center gap-2">
          <code class="flex-1 truncate rounded-lg bg-app-primary px-3 py-2 text-slate-700">{{ sampleCommand }}</code>
          <button type="button" class="btn-flat shrink-0 px-3 py-2" @click="copy(sampleCommand, 'cmd')">
            {{ copiedId === 'cmd' ? 'Copied' : 'Copy' }}
          </button>
        </div>
        <p class="text-slate-500">Replace <code>&lt;MCP_ACCESS_TOKEN&gt;</code> with that value.</p>
      </div>

      <div v-else-if="activeTab === 'remote-claude-app'" class="space-y-2">
        <p class="text-slate-500">
          Claude.ai and Claude Desktop support custom connectors with a fixed request header
          - no OAuth needed. Same shared secret as the CLI tab: look up
          <code>MCP_ACCESS_TOKEN</code> in <code>mcp-server/.env</code> on the server, not a
          personal key below.
        </p>
        <ol class="list-inside list-decimal space-y-1 text-slate-600">
          <li>Go to <strong>Settings → Connectors</strong>.</li>
          <li>Click <strong>Add</strong> → <strong>Custom</strong> → <strong>Web</strong>, name it, and paste the server URL above.</li>
          <li>For <strong>Authentication</strong>, choose <strong>No sign-in</strong>.</li>
          <li>Under <strong>Request headers</strong>, add header <code>Authorization</code> with value <code>Bearer &lt;MCP_ACCESS_TOKEN&gt;</code>.</li>
          <li>Click <strong>Add</strong> to finish.</li>
        </ol>
      </div>

      <div v-else-if="activeTab === 'local'" class="space-y-2">
        <p class="text-slate-500">
          Running <code>server.py</code> directly on your own machine (stdio, no tunnel
          involved) is where a personal key below actually applies - it becomes
          <code>REVENUE_CONSOLE_API_KEY</code> and the server calls the console's API as you,
          with your own permissions.
        </p>
        <div class="flex items-center gap-2">
          <code class="flex-1 truncate rounded-lg bg-app-primary px-3 py-2 text-slate-700">{{ localCommand }}</code>
          <button type="button" class="btn-flat shrink-0 px-3 py-2" @click="copy(localCommand, 'localCmd')">
            {{ copiedId === 'localCmd' ? 'Copied' : 'Copy' }}
          </button>
        </div>
        <p class="text-slate-500">
          Replace <code>&lt;your-key&gt;</code> with a key created below and the path with
          where you cloned this repo. Claude Desktop uses the equivalent
          <code>claude_desktop_config.json</code> form - see <code>mcp-server/README.md</code>.
        </p>
      </div>
    </div>

    <p v-if="loadError" class="rounded-lg bg-rose-50 p-3 text-xs font-semibold text-rose-700">{{ loadError }}</p>

    <div class="neu-card overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
        <h2 class="text-sm font-semibold text-app-tertiary">
          {{ scope === 'all' ? "Everyone's keys (admin view)" : 'Your keys' }}
          <span class="ml-1 font-normal text-slate-500">{{ keys.length }}</span>
        </h2>
        <button type="button" class="btn-primary py-1.5 text-xs" :disabled="busy" @click="openCreate">
          + New key
        </button>
      </div>

      <div v-if="createOpen" class="space-y-2 border-b border-slate-200 bg-app-primary p-4 text-xs">
        <label class="block">
          <span class="mb-1 block font-semibold text-slate-600">Label</span>
          <input v-model="newLabel" maxlength="120" placeholder="e.g. laptop, MCP server" class="neu-input w-64" />
        </label>
        <p v-if="createError" class="font-semibold text-rose-700">{{ createError }}</p>
        <div class="flex gap-2">
          <button type="button" class="btn-primary py-1.5" :disabled="busy || !newLabel.trim()" @click="onCreate">Create key</button>
          <button type="button" class="btn-flat py-1.5" @click="createOpen = false">Cancel</button>
        </div>
      </div>

      <div v-if="revealedKey" class="space-y-2 border-b border-slate-200 bg-amber-50 p-4 text-xs">
        <p class="font-semibold text-amber-800">Copy this key now - it won't be shown again.</p>
        <p class="text-amber-800">
          This is for the <strong>Run locally</strong> tab above (<code>REVENUE_CONSOLE_API_KEY</code>)
          or the server's own <code>mcp-server/.env</code> - it does <strong>not</strong> go
          into a remote claude.ai/Claude Code connector's header field (that uses the shared
          <code>MCP_ACCESS_TOKEN</code> instead).
        </p>
        <label class="block text-slate-600">
          Plain key
          <div class="mt-1 flex items-center gap-2">
            <code class="flex-1 truncate rounded-lg bg-white px-3 py-2 text-slate-700">{{ revealedKey }}</code>
            <button type="button" class="btn-flat shrink-0 px-3 py-2" @click="copy(revealedKey, 'reveal')">
              {{ copiedId === 'reveal' ? 'Copied' : 'Copy' }}
            </button>
          </div>
        </label>
        <button type="button" class="btn-flat py-1.5" @click="revealedKey = null">Done</button>
      </div>

      <p v-if="loaded && !keys.length" class="p-4 text-xs text-slate-500">No keys yet. Create one to connect an MCP client.</p>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-xs">
          <thead class="bg-app-primary">
            <tr>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Label</th>
              <th v-if="scope === 'all'" class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Owner</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Created</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Last used</th>
              <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Status</th>
              <th class="px-4 py-2.5"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="k in keys" :key="k.id" :class="{ 'opacity-50': k.revokedAt }">
              <td class="px-4 py-2 font-semibold text-slate-700">{{ k.label }}</td>
              <td v-if="scope === 'all'" class="px-4 py-2 text-slate-600">{{ k.ownerDisplayName || k.ownerUsername || '—' }}</td>
              <td class="whitespace-nowrap px-4 py-2 text-slate-600">{{ formatDate(k.createdAt) }}</td>
              <td class="whitespace-nowrap px-4 py-2 text-slate-600">{{ k.lastUsedAt ? formatDate(k.lastUsedAt) : 'Never' }}</td>
              <td class="px-4 py-2">
                <span :class="['rounded-full px-2 py-0.5 font-semibold', k.revokedAt ? 'bg-slate-100 text-slate-500' : 'bg-emerald-100 text-emerald-700']">
                  {{ k.revokedAt ? 'Revoked' : 'Active' }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-2 text-right">
                <button v-if="!k.revokedAt" type="button" class="rounded px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50"
                  :disabled="busy" @click="askRevoke(k)">Revoke</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import { confirmDialog } from '../composables/useDialog'

interface McpKey {
  id: number
  label: string
  createdAt: string
  revokedAt: string | null
  lastUsedAt: string | null
  ownerUsername?: string
  ownerDisplayName?: string
}

// This console's MCP server has its own Cloudflare tunnel hostname (it's a
// separate service, not reachable on this app's own domain) - defaulted here
// since there's only ever one deployment of this app. Still editable/saved
// locally in case the tunnel hostname ever changes.
const DEFAULT_SERVER_URL = 'https://revcon-mcp.krisnatha.com/mcp'
const SERVER_URL_KEY = 'mcpAccess.serverUrl'
const serverUrl = ref(localStorage.getItem(SERVER_URL_KEY) || DEFAULT_SERVER_URL)
watch(serverUrl, (value) => {
  if (value && value !== DEFAULT_SERVER_URL) localStorage.setItem(SERVER_URL_KEY, value)
  else localStorage.removeItem(SERVER_URL_KEY)
})
const sampleCommand = computed(
  () => `claude mcp add --transport http revenue-console ${serverUrl.value || '<server URL>'} --header "Authorization: Bearer <MCP_ACCESS_TOKEN>"`,
)
const localCommand = computed(
  () => `claude mcp add revenue-console -e REVENUE_CONSOLE_URL=https://<console URL> -e REVENUE_CONSOLE_API_KEY=<your-key> -- python /path/to/mcp-server/server.py`,
)

type ClientTab = 'remote-cli' | 'remote-claude-app' | 'local'
const clientTabs: { key: ClientTab; label: string }[] = [
  { key: 'remote-cli', label: 'Claude Code / Cursor (remote)' },
  { key: 'remote-claude-app', label: 'Claude.ai / Desktop (remote)' },
  { key: 'local', label: 'Run locally (no tunnel)' },
]
const activeTab = ref<ClientTab>('remote-cli')

const keys = ref<McpKey[]>([])
const scope = ref<'own' | 'all'>('own')
const loaded = ref(false)
const loadError = ref('')
const busy = ref(false)

const message = (err: any, fallback: string) => err?.response?.data?.message || fallback

async function load() {
  try {
    const res = await axios.get('/api/mcp-keys', { params: { scope: 'all' } })
    keys.value = res.data.keys
    scope.value = res.data.scope
    loadError.value = ''
  } catch (err: any) {
    loadError.value = message(err, 'Could not load keys.')
  } finally {
    loaded.value = true
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const copiedId = ref<string | null>(null)
function copy(text: string, id: string) {
  navigator.clipboard.writeText(text).then(() => {
    copiedId.value = id
    setTimeout(() => { if (copiedId.value === id) copiedId.value = null }, 2000)
  }).catch(() => {})
}

const createOpen = ref(false)
const newLabel = ref('')
const createError = ref('')
const revealedKey = ref<string | null>(null)

function openCreate() {
  newLabel.value = ''
  createError.value = ''
  createOpen.value = true
}

async function onCreate() {
  busy.value = true
  createError.value = ''
  try {
    const res = await axios.post('/api/mcp-keys', { label: newLabel.value })
    revealedKey.value = res.data.apiKey
    createOpen.value = false
    await load()
  } catch (err: any) {
    createError.value = message(err, 'Could not create key.')
  } finally {
    busy.value = false
  }
}

async function askRevoke(k: McpKey) {
  const ok = await confirmDialog({
    tone: 'warning',
    title: `Revoke "${k.label}"?`,
    message: 'Any client using this key will immediately lose access. This can\'t be undone.',
    confirmText: 'Revoke',
  })
  if (!ok) return
  busy.value = true
  try {
    await axios.post(`/api/mcp-keys/${k.id}/revoke`)
    await load()
  } catch (err: any) {
    loadError.value = message(err, 'Could not revoke key.')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
