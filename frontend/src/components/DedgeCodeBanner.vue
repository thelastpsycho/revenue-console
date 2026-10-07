<template>
  <div
    v-if="status?.pending"
    class="border-b border-amber-200 bg-amber-50 px-4 py-3 sm:px-6 lg:px-8"
    role="alert"
  >
    <div class="mx-auto flex w-full max-w-7xl flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="flex min-w-0 items-start gap-2 text-sm text-amber-900">
        <ShieldExclamationIcon class="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div class="min-w-0">
          <p class="font-semibold">D-EDGE needs a device code</p>
          <p class="text-xs text-amber-800">
            D-EDGE emailed a code to <span class="font-semibold">{{ status.email_hint || 'the hotel mailbox' }}</span>.
            The run is paused until you enter it{{ remaining ? ` (${remaining} left)` : '' }}.
          </p>
          <p v-if="message" :class="['mt-1 text-xs font-semibold', messageIsError ? 'text-rose-700' : 'text-emerald-700']">
            {{ message }}
          </p>
        </div>
      </div>

      <form class="flex flex-wrap items-center gap-2" @submit.prevent="submit">
        <input
          v-model="code"
          type="text"
          inputmode="text"
          autocomplete="one-time-code"
          maxlength="6"
          placeholder="Code"
          aria-label="D-EDGE device code"
          class="w-28 rounded-lg border border-amber-300 bg-white px-3 py-1.5 font-mono text-sm uppercase tracking-widest text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
        />
        <button
          type="submit"
          :disabled="busy || !code.trim()"
          class="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Submit
        </button>
        <button
          type="button"
          :disabled="busy"
          @click="resend"
          class="rounded-lg px-2 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
        >
          Resend email
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ShieldExclamationIcon } from '@heroicons/vue/24/outline'
import { useDedgeAuth } from '../composables/useDedgeAuth'

const { status, submitCode, resendEmail } = useDedgeAuth()

const code = ref('')
const busy = ref(false)
const message = ref('')
const messageIsError = ref(false)

// Surface D-EDGE's verdict on the last code (set by the waiting session).
watch(() => status.value?.last_error, (err) => {
  if (err && status.value?.pending) {
    message.value = err
    messageIsError.value = true
    busy.value = false
  }
})
watch(() => status.value?.pending, (pending) => {
  if (!pending) {
    code.value = ''
    message.value = ''
    busy.value = false
  }
})

async function submit() {
  busy.value = true
  message.value = ''
  try {
    message.value = await submitCode(code.value.trim().toUpperCase())
    messageIsError.value = false
    code.value = ''
  } catch (err: any) {
    message.value = err?.response?.data?.message || 'Could not send the code.'
    messageIsError.value = true
    busy.value = false
  }
  // On success, stay busy until the session reports back (pending clears or last_error is set).
}

async function resend() {
  busy.value = true
  try {
    message.value = await resendEmail()
    messageIsError.value = false
  } catch (err: any) {
    message.value = err?.response?.data?.message || 'Could not ask D-EDGE to resend.'
    messageIsError.value = true
  } finally {
    busy.value = false
  }
}

const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | undefined
onMounted(() => { clock = setInterval(() => { now.value = Date.now() }, 1000) })
onBeforeUnmount(() => clearInterval(clock))

const remaining = computed(() => {
  const deadline = status.value?.deadline
  if (!deadline) return ''
  const secs = Math.max(0, Math.round((new Date(deadline).getTime() - now.value) / 1000))
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`
})
</script>
