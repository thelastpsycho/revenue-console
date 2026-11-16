<template>
  <div v-if="auth.loading" class="flex min-h-screen items-center justify-center bg-slate-100 text-slate-700">
    Checking access…
  </div>
  <div v-else-if="!auth.authenticated" class="flex min-h-screen items-center justify-center bg-slate-100 p-5">
    <form class="w-full max-w-sm space-y-5 rounded-2xl bg-white p-7 shadow-xl" @submit.prevent="login">
      <h1 class="text-xl font-semibold text-slate-900">Revenue Console</h1>
      <p v-if="!auth.configured" class="text-sm text-amber-800" role="alert">
        API authentication is not configured. Set APP_SESSION_SECRET on the backend, then run
        backend/scripts/bootstrap_admin.py to create the first account.
      </p>
      <template v-else>
        <div>
          <label for="username" class="block text-sm font-medium text-slate-700">Username</label>
          <input id="username" v-model="username" type="text" autocomplete="username" required
            class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" />
        </div>
        <div>
          <label for="password" class="block text-sm font-medium text-slate-700">Password</label>
          <input id="password" v-model="password" type="password" autocomplete="current-password" required
            class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" />
        </div>
        <p v-if="auth.error" class="text-sm text-red-700" role="alert">{{ auth.error }}</p>
        <button type="submit" :disabled="!username || !password || submitting"
          class="rounded-lg bg-slate-900 px-4 py-2 text-white disabled:opacity-50">
          {{ submitting ? 'Signing in…' : 'Sign in' }}
        </button>
      </template>
    </form>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const submitting = ref(false)
const username = ref('')
const password = ref('')

function expireSession() {
  auth.expireSession()
}

async function login() {
  if (!username.value || !password.value || submitting.value) return
  submitting.value = true
  try {
    await auth.login(username.value, password.value)
    username.value = ''
    password.value = ''
  } catch {
    auth.setError('Could not sign in. Check your username and password.')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  window.addEventListener('operator-session-expired', expireSession)
  void auth.refresh()
})
onUnmounted(() => window.removeEventListener('operator-session-expired', expireSession))
</script>
