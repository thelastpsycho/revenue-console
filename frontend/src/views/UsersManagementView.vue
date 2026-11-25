<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Users"
      subtitle="Operator accounts and what each one is allowed to do. Every account can view dashboards and reports; the checkboxes below only control who can trigger scrapes, pushes, sends and settings changes."
    />

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-12">
      <!-- Add / edit -->
      <div class="xl:col-span-4">
        <form class="neu-card space-y-3 p-4 text-xs" @submit.prevent="save">
          <div class="flex items-center justify-between gap-2">
            <h2 class="text-sm font-semibold text-app-tertiary">{{ editingId ? 'Edit user' : 'Add user' }}</h2>
            <button v-if="editingId" type="button" class="font-semibold text-slate-500 hover:text-slate-900" @click="resetForm">Cancel</button>
          </div>
          <div>
            <label for="u-username" class="mb-1 block font-semibold text-slate-600">Username</label>
            <input id="u-username" v-model="form.username" required maxlength="60" class="neu-input"
              :disabled="!!editingId" placeholder="e.g. andi" />
          </div>
          <div>
            <label for="u-display-name" class="mb-1 block font-semibold text-slate-600">Display name</label>
            <input id="u-display-name" v-model="form.displayName" maxlength="120" class="neu-input" placeholder="Defaults to username" />
          </div>
          <div>
            <label for="u-password" class="mb-1 block font-semibold text-slate-600">
              {{ editingId ? 'New password' : 'Password' }}
            </label>
            <input id="u-password" v-model="form.password" type="password" autocomplete="new-password" minlength="8"
              class="neu-input" :required="!editingId" :placeholder="editingId ? 'Leave blank to keep the current password' : 'At least 8 characters'" />
          </div>
          <div v-if="editingId">
            <label class="flex items-center gap-2 font-semibold text-slate-600">
              <input v-model="form.isActive" type="checkbox" :disabled="isSelf(editingId)" />
              Active
            </label>
            <p v-if="isSelf(editingId)" class="mt-1 text-slate-500">You can't deactivate your own account.</p>
          </div>
          <div>
            <label class="flex items-center gap-2 font-semibold text-slate-600">
              <input v-model="form.twoFactorRequired" type="checkbox" />
              Require 2FA
            </label>
            <p class="mt-1 text-slate-500">They won't be able to use anything else until they set up an authenticator app.</p>
          </div>
          <div>
            <p class="mb-1 font-semibold text-slate-600">Permissions</p>
            <div class="space-y-2">
              <div v-for="group in permissionGroups" :key="group.name">
                <p class="text-[11px] font-bold uppercase tracking-wider text-slate-400">{{ group.name }}</p>
                <label v-for="perm in group.permissions" :key="perm.key" class="flex items-start gap-2 py-0.5">
                  <input v-model="form.permissions" type="checkbox" :value="perm.key"
                    :disabled="perm.key === 'manage_users' && isSelf(editingId)" class="mt-0.5" />
                  <span>
                    <span class="font-semibold">{{ perm.label }}</span>
                    <span class="block text-slate-500">{{ perm.description }}</span>
                  </span>
                </label>
              </div>
            </div>
            <p v-if="editingId && isSelf(editingId)" class="mt-1 text-slate-500">
              You can't remove your own "Manage users" permission.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button type="submit" class="btn-primary py-1.5 text-xs" :disabled="busy">
              {{ editingId ? 'Save changes' : 'Add user' }}
            </button>
            <span v-if="formError" class="font-semibold text-rose-700">{{ formError }}</span>
          </div>
        </form>
      </div>

      <!-- List -->
      <div class="neu-card overflow-hidden xl:col-span-8">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
          <h2 class="text-sm font-semibold text-app-tertiary">
            Accounts
            <span class="ml-1 font-normal text-slate-500">{{ users.length }}</span>
          </h2>
        </div>
        <p v-if="loadError" class="p-4 text-xs font-semibold text-rose-700">{{ loadError }}</p>
        <p v-else-if="loaded && !users.length" class="p-4 text-xs text-slate-500">No accounts yet. Add one on the left.</p>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-xs">
            <thead class="bg-app-primary">
              <tr>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Username</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Permissions</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Status</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">2FA</th>
                <th class="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Last login</th>
                <th class="px-4 py-2.5"><span class="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="u in sortedUsers" :key="u.id">
                <td class="px-4 py-2">
                  <span class="font-semibold">{{ u.displayName }}</span>
                  <span class="block text-slate-500">{{ u.username }}{{ isSelf(u.id) ? ' (you)' : '' }}</span>
                </td>
                <td class="px-4 py-2 text-slate-600">
                  {{ u.permissions.length ? `${u.permissions.length} permission${u.permissions.length === 1 ? '' : 's'}` : 'None' }}
                </td>
                <td class="px-4 py-2">
                  <span :class="['rounded-full px-2 py-0.5 font-semibold', u.isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500']">
                    {{ u.isActive ? 'Active' : 'Disabled' }}
                  </span>
                </td>
                <td class="px-4 py-2">
                  <span :class="['rounded-full px-2 py-0.5 font-semibold', twoFactorBadge(u).class]">
                    {{ twoFactorBadge(u).label }}
                  </span>
                </td>
                <td class="whitespace-nowrap px-4 py-2 text-slate-600">{{ u.lastLoginAt ? formatDateTime(u.lastLoginAt) : 'Never' }}</td>
                <td class="whitespace-nowrap px-4 py-2 text-right">
                  <button type="button" class="rounded px-2 py-1 font-semibold text-slate-600 hover:bg-slate-100" @click="edit(u)">Edit</button>
                  <button v-if="u.twoFactorEnabled" type="button" class="rounded px-2 py-1 font-semibold text-slate-600 hover:bg-slate-100"
                    :disabled="busy" @click="resetTwoFactor(u)">Reset 2FA</button>
                  <button type="button" class="rounded px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50"
                    :disabled="busy || isSelf(u.id)" @click="remove(u)">Delete</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '../plugins/axios'
import { confirmDialog } from '../composables/useDialog'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'

interface ConsoleUser {
  id: number
  username: string
  displayName: string
  permissions: string[]
  isActive: boolean
  twoFactorEnabled: boolean
  twoFactorRequired: boolean
  lastLoginAt: string | null
}

interface Permission {
  key: string
  label: string
  group: string
  description: string
}

const auth = useAuthStore()

const users = ref<ConsoleUser[]>([])
const permissions = ref<Permission[]>([])
const loaded = ref(false)
const loadError = ref('')
const busy = ref(false)
const formError = ref('')
const editingId = ref<number | null>(null)
const form = reactive({
  username: '', displayName: '', password: '', isActive: true, twoFactorRequired: false,
  permissions: [] as string[],
})

const sortedUsers = computed(() => [...users.value].sort((a, b) => a.username.localeCompare(b.username)))

const permissionGroups = computed(() => {
  const groups: { name: string; permissions: Permission[] }[] = []
  for (const perm of permissions.value) {
    let group = groups.find(g => g.name === perm.group)
    if (!group) { group = { name: perm.group, permissions: [] }; groups.push(group) }
    group.permissions.push(perm)
  }
  return groups
})

function isSelf(id: number | null) {
  return id !== null && id === auth.user?.id
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function twoFactorBadge(u: ConsoleUser) {
  if (u.twoFactorEnabled) return { label: 'Enabled', class: 'bg-emerald-100 text-emerald-700' }
  if (u.twoFactorRequired) return { label: 'Required', class: 'bg-amber-100 text-amber-700' }
  return { label: 'Off', class: 'bg-slate-100 text-slate-500' }
}

const message = (err: any, fallback: string) => err?.response?.data?.message || fallback

async function load() {
  try {
    const [usersRes, permsRes] = await Promise.all([
      axios.get('/api/users'),
      axios.get('/api/users/permissions'),
    ])
    users.value = usersRes.data.users
    permissions.value = permsRes.data.permissions
    loadError.value = ''
  } catch (err: any) {
    loadError.value = message(err, 'Could not load users.')
  } finally {
    loaded.value = true
  }
}

function resetForm() {
  editingId.value = null
  Object.assign(form, {
    username: '', displayName: '', password: '', isActive: true, twoFactorRequired: false, permissions: [],
  })
  formError.value = ''
}

function edit(u: ConsoleUser) {
  editingId.value = u.id
  Object.assign(form, {
    username: u.username, displayName: u.displayName, password: '', isActive: u.isActive,
    twoFactorRequired: u.twoFactorRequired, permissions: [...u.permissions],
  })
  formError.value = ''
}

async function save() {
  busy.value = true
  formError.value = ''
  try {
    if (editingId.value) {
      const payload: Record<string, unknown> = {
        displayName: form.displayName, isActive: form.isActive,
        twoFactorRequired: form.twoFactorRequired, permissions: form.permissions,
      }
      if (form.password) payload.password = form.password
      await axios.put(`/api/users/${editingId.value}`, payload)
    } else {
      await axios.post('/api/users', {
        username: form.username, displayName: form.displayName, password: form.password,
        twoFactorRequired: form.twoFactorRequired, permissions: form.permissions,
      })
    }
    resetForm()
    await load()
  } catch (err: any) {
    formError.value = message(err, 'Could not save the user.')
  } finally {
    busy.value = false
  }
}

async function remove(u: ConsoleUser) {
  const ok = await confirmDialog({
    tone: 'warning',
    title: 'Delete this account?',
    message: 'They will be signed out immediately and can no longer log in.',
    details: [{ label: 'Username', value: u.username }, { label: 'Display name', value: u.displayName }],
    confirmText: 'Delete',
  })
  if (!ok) return
  busy.value = true
  try {
    await axios.delete(`/api/users/${u.id}`)
    if (editingId.value === u.id) resetForm()
  } catch (err: any) {
    loadError.value = message(err, 'Could not delete the user.')
  } finally {
    busy.value = false
    await load()
  }
}

async function resetTwoFactor(u: ConsoleUser) {
  const ok = await confirmDialog({
    tone: 'warning',
    title: 'Reset two-factor authentication?',
    message: 'They will need to set up a new authenticator app the next time they want to re-enable it. Use this if they lost their device.',
    details: [{ label: 'Username', value: u.username }, { label: 'Display name', value: u.displayName }],
    confirmText: 'Reset 2FA',
  })
  if (!ok) return
  busy.value = true
  try {
    await axios.post(`/api/users/${u.id}/reset-2fa`)
  } catch (err: any) {
    loadError.value = message(err, 'Could not reset two-factor authentication.')
  } finally {
    busy.value = false
    await load()
  }
}

onMounted(load)
</script>
