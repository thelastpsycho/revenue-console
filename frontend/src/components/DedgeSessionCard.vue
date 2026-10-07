<template>
  <div class="neu-card p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 class="flex items-center gap-1.5 text-sm font-semibold text-app-tertiary">
        <ShieldCheckIcon class="h-4 w-4" />
        D-EDGE session
      </h2>
      <span
        :class="[
          'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-app-primary px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm',
          pill.text,
        ]"
      >
        <span :class="['h-1.5 w-1.5 rounded-full', pill.dot]" />
        {{ pill.label }}
      </span>
    </div>

    <div class="mt-3 space-y-2 text-xs text-slate-600">
      <p v-if="status?.pending" class="rounded-lg bg-app-primary px-3 py-2 font-semibold text-amber-700 shadow-neu-inset-sm">
        D-EDGE is waiting for the emailed device code - enter it in the banner at the top of the page.
      </p>
      <p>
        Last verified:
        <span class="font-semibold">{{ lastVerifiedText }}</span>
      </p>
      <p v-if="status?.check_result" :class="status.check_result.ok ? 'text-emerald-700' : 'font-semibold text-rose-700'">
        {{ status.check_result.message }} ({{ formatTime(status.check_result.at) }})
      </p>
      <p class="text-slate-500">
        If D-EDGE stops trusting this machine, it emails a code to the hotel mailbox and the run pauses;
        a banner appears at the top of every page to enter it. A check does the same login a run does,
        so you can re-authorize before the next scheduled run.
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          :disabled="checkDisabled"
          @click="runCheck"
          class="rounded-lg bg-app-primary px-2 py-1 font-semibold text-app-accent shadow-neu-sm active:shadow-neu-inset-sm disabled:cursor-not-allowed disabled:opacity-50"
          :title="pipelineActive && !status?.check_running ? 'A pipeline run is in progress - it checks the session itself' : ''"
        >
          {{ status?.check_running ? 'Checking...' : 'Check session now' }}
        </button>
        <span v-if="actionError" class="font-semibold text-rose-700">{{ actionError }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ShieldCheckIcon } from '@heroicons/vue/24/outline'
import { useDedgeAuth } from '../composables/useDedgeAuth'

const { status, pipelineActive, checkSession } = useDedgeAuth()
const actionError = ref('')

function formatTime(iso: string | null | undefined) {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const lastVerifiedText = computed(() =>
  status.value?.last_verified_at ? formatTime(status.value.last_verified_at) : 'not since the backend started')

const pill = computed(() => {
  const s = status.value
  if (s?.pending) return { label: 'Code needed', text: 'text-amber-700', dot: 'bg-amber-500' }
  if (s?.check_running) return { label: 'Checking', text: 'text-slate-600', dot: 'bg-slate-400' }
  if (s?.check_result && !s.check_result.ok) return { label: 'Check failed', text: 'text-rose-700', dot: 'bg-rose-500' }
  if (s?.last_verified_at) return { label: 'Verified', text: 'text-emerald-700', dot: 'bg-emerald-500' }
  return { label: 'Not checked', text: 'text-slate-500', dot: 'bg-slate-400' }
})

const checkDisabled = computed(() => !!status.value?.check_running || !!status.value?.pending || pipelineActive.value)

async function runCheck() {
  actionError.value = ''
  try {
    await checkSession()
  } catch (err: any) {
    actionError.value = err?.response?.data?.message || 'Could not start the check.'
  }
}
</script>
