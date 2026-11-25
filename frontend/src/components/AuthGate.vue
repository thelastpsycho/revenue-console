<template>
  <div v-if="auth.loading" class="flex min-h-screen items-center justify-center bg-slate-100 text-sm text-slate-600">
    Checking access…
  </div>
  <div v-else-if="!auth.authenticated || auth.user?.twoFactorSetupRequired"
    class="flex min-h-screen flex-col items-center justify-center gap-7 bg-slate-100 px-5 py-12 text-slate-900">
    <div class="flex items-center gap-3">
      <div class="flex h-10 w-10 items-center justify-center rounded-[10px] bg-slate-900">
        <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-5 4 4 8-9" /><path d="M15 7h5v5" /></svg>
      </div>
      <div class="flex flex-col leading-tight">
        <span class="text-[17px] font-bold tracking-tight">Revenue Console</span>
        <span class="text-xs text-slate-600">The Anvaya Beach Resort Bali</span>
      </div>
    </div>

    <!-- Sign in / two-step verification -->
    <form v-if="!auth.authenticated" class="auth-card" @submit.prevent="login">
      <p v-if="!auth.configured" class="text-sm text-amber-800" role="alert">
        API authentication is not configured. Set APP_SESSION_SECRET on the backend, then run
        backend/scripts/bootstrap_admin.py to create the first account.
      </p>

      <template v-else-if="totpPending">
        <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100">
          <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0f172a" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" /><path d="M9 12l2 2 4-4" /></svg>
        </div>
        <div class="space-y-1.5">
          <h1 class="text-[22px] font-bold tracking-tight">Two-step verification</h1>
          <p class="text-sm text-slate-600">Enter the 6-digit code from your authenticator app for Revenue Console.</p>
        </div>
        <fieldset class="space-y-2">
          <legend class="mb-2 text-[13px] font-bold text-slate-700">Authenticator code</legend>
          <div class="flex items-center gap-2">
            <template v-for="(_, i) in digits" :key="i">
              <input :ref="(el) => setOtpRef(el, i)" :value="digits[i]" type="text" inputmode="numeric" pattern="[0-9]*"
                :autocomplete="i === 0 ? 'one-time-code' : 'off'" :aria-label="`Digit ${i + 1}`"
                class="otp-box" @input="onDigitInput(i, $event)" @keydown="onDigitKeydown(i, $event)"
                @paste="onDigitPaste(i, $event)" @focus="($event.target as HTMLInputElement).select()" />
              <span v-if="i === 2" aria-hidden="true" class="h-0.5 w-2.5 bg-slate-300" />
            </template>
          </div>
          <p class="text-xs text-slate-600">Codes refresh every 30 seconds. You can also paste the whole code.</p>
        </fieldset>
        <p v-if="auth.error" class="text-sm font-semibold text-red-700" role="alert">{{ auth.error }}</p>
        <label class="flex cursor-pointer items-center gap-2.5 text-sm text-slate-700">
          <input v-model="rememberDevice" type="checkbox" class="h-[18px] w-[18px] accent-slate-900" />
          Remember this device for 7 days
        </label>
        <div class="flex flex-col gap-3">
          <button type="submit" :disabled="totpCode.length !== 6 || submitting" class="auth-btn">
            {{ submitting ? 'Verifying…' : 'Verify' }}
          </button>
          <button type="button" class="h-10 rounded-lg text-sm font-bold text-slate-700 hover:text-slate-900"
            @click="backToPassword">
            Back to sign in
          </button>
        </div>
      </template>

      <template v-else>
        <div class="space-y-1.5">
          <h1 class="text-[22px] font-bold tracking-tight">Sign in</h1>
          <p class="text-sm text-slate-600">Use the account your admin created for you.</p>
        </div>
        <div class="space-y-1.5">
          <label for="username" class="block text-[13px] font-bold text-slate-700">Username</label>
          <input id="username" v-model="username" type="text" autocomplete="username" required class="auth-input" />
        </div>
        <div class="space-y-1.5">
          <label for="password" class="block text-[13px] font-bold text-slate-700">Password</label>
          <div class="relative flex">
            <input id="password" v-model="password" :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password" required class="auth-input pr-16" />
            <button type="button" class="absolute right-1 top-1 h-9 rounded-lg px-3 text-[13px] font-bold text-slate-700 hover:text-slate-900"
              :aria-pressed="showPassword" @click="showPassword = !showPassword">
              {{ showPassword ? 'Hide' : 'Show' }}
            </button>
          </div>
        </div>
        <p v-if="auth.error" class="text-sm font-semibold text-red-700" role="alert">{{ auth.error }}</p>
        <button type="submit" :disabled="!username || !password || submitting" class="auth-btn">
          {{ submitting ? 'Signing in…' : 'Sign in' }}
        </button>
      </template>
    </form>

    <!-- Admin requires 2FA before continuing -->
    <div v-else class="auth-card">
      <div class="space-y-1.5">
        <h1 class="text-[22px] font-bold tracking-tight">Set up two-step verification</h1>
        <p class="text-sm text-slate-600">
          An admin requires two-step verification on this account before you can continue.
        </p>
      </div>
      <TwoFactorSetup heading="" description="Set up an authenticator app to continue." />
      <button type="button" class="h-10 rounded-lg text-sm font-bold text-slate-700 hover:text-slate-900"
        @click="auth.logout()">
        Sign out instead
      </button>
    </div>

    <p class="text-center text-[13px] text-slate-600">
      <template v-if="totpPending">Lost your authenticator? Ask an admin to reset two-step verification.</template>
      <template v-else>Trouble signing in? Ask an admin to reset your access.</template>
    </p>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import TwoFactorSetup from './TwoFactorSetup.vue'

const OTP_LENGTH = 6

const auth = useAuthStore()
const submitting = ref(false)
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const totpPending = ref(false)
const digits = ref<string[]>(Array(OTP_LENGTH).fill(''))
const totpCode = computed(() => digits.value.join(''))
const rememberDevice = ref(false)
const otpRefs: (HTMLInputElement | null)[] = []

function setOtpRef(el: unknown, i: number) {
  otpRefs[i] = (el as HTMLInputElement) || null
}

function focusDigit(i: number) {
  otpRefs[Math.max(0, Math.min(OTP_LENGTH - 1, i))]?.focus()
}

function resetDigits() {
  digits.value = Array(OTP_LENGTH).fill('')
}

function fillFrom(start: number, value: string) {
  const chars = value.replace(/\D/g, '').slice(0, OTP_LENGTH - start).split('')
  if (!chars.length) return
  const next = [...digits.value]
  chars.forEach((c, k) => { next[start + k] = c })
  digits.value = next
  focusDigit(start + chars.length)
}

function onDigitInput(i: number, e: Event) {
  const input = e.target as HTMLInputElement
  const value = input.value.replace(/\D/g, '')
  if (value.length > 1) {
    // Autofill (one-time-code) or fast typing into one box: spread across boxes.
    input.value = digits.value[i]
    fillFrom(i, value)
    return
  }
  const next = [...digits.value]
  next[i] = value
  digits.value = next
  input.value = value
  if (value && i < OTP_LENGTH - 1) focusDigit(i + 1)
}

function onDigitKeydown(i: number, e: KeyboardEvent) {
  if (e.key === 'Backspace' && !digits.value[i] && i > 0) {
    e.preventDefault()
    const next = [...digits.value]
    next[i - 1] = ''
    digits.value = next
    focusDigit(i - 1)
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    focusDigit(i - 1)
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    focusDigit(i + 1)
  }
}

function onDigitPaste(i: number, e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text') ?? ''
  if (!text) return
  e.preventDefault()
  fillFrom(i, text)
}

function expireSession() {
  auth.expireSession()
}

function backToPassword() {
  totpPending.value = false
  resetDigits()
  rememberDevice.value = false
  auth.setError('')
}

async function login() {
  if (submitting.value) return
  if (totpPending.value) return submitTotp()
  if (!username.value || !password.value) return
  submitting.value = true
  try {
    const result = await auth.login(username.value, password.value)
    if (result === 'totp_required') {
      totpPending.value = true
      await nextTick()
      focusDigit(0)
    } else {
      username.value = ''
      password.value = ''
      showPassword.value = false
    }
  } catch {
    auth.setError('Could not sign in. Check your username and password.')
  } finally {
    submitting.value = false
  }
}

async function submitTotp() {
  if (totpCode.value.length !== OTP_LENGTH) return
  submitting.value = true
  try {
    await auth.loginTotp(totpCode.value, rememberDevice.value)
    totpPending.value = false
    resetDigits()
    rememberDevice.value = false
    username.value = ''
    password.value = ''
    showPassword.value = false
  } catch (err: any) {
    if (err?.response?.data?.locked) {
      backToPassword()
      auth.setError('Too many attempts. Sign in again.')
    } else {
      auth.setError('Invalid code. Try again.')
      resetDigits()
      await nextTick()
      focusDigit(0)
    }
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

<style scoped>
.auth-card {
  @apply flex w-full max-w-[420px] flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-8;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 12px 32px rgba(15, 23, 42, 0.06);
}
.auth-input {
  @apply h-11 w-full rounded-[10px] border border-slate-300 bg-white px-3.5 text-[15px] text-slate-900 transition-colors focus:border-slate-900 focus:outline-none focus:ring-[3px] focus:ring-slate-900/10;
}
.auth-btn {
  @apply h-[46px] w-full cursor-pointer rounded-[10px] bg-slate-900 text-[15px] font-bold text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50;
}
.otp-box {
  @apply h-14 w-12 rounded-[10px] border border-slate-300 bg-white text-center text-[22px] font-bold text-slate-900 transition-colors focus:border-slate-900 focus:outline-none focus:ring-[3px] focus:ring-slate-900/10;
}
</style>
