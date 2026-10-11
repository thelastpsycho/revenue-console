<template>
  <Teleport to="body">
    <transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      leave-active-class="transition duration-100 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-if="dialogState.open"
        class="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-4 sm:items-center"
        @mousedown.self="closeDialog(false)"
      >
        <div
          ref="panel"
          role="alertdialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="dialogState.message ? messageId : undefined"
          class="w-full max-w-md overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
          @keydown.esc.prevent="closeDialog(false)"
          @keydown.tab="trapFocus"
        >
          <div class="flex gap-3 p-5">
            <span :class="['flex h-9 w-9 shrink-0 items-center justify-center rounded-full', tone.badge]">
              <component :is="tone.icon" class="h-5 w-5" />
            </span>
            <div class="min-w-0 flex-1 space-y-3">
              <h2 :id="titleId" class="text-base font-semibold text-slate-900">{{ dialogState.title }}</h2>
              <p v-if="dialogState.message" :id="messageId" class="whitespace-pre-line text-sm text-slate-600">
                {{ dialogState.message }}
              </p>
              <dl v-if="dialogState.details?.length" class="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
                <div v-for="row in dialogState.details" :key="row.label" class="flex justify-between gap-4 px-3 py-1.5">
                  <dt class="shrink-0 text-slate-500">{{ row.label }}</dt>
                  <dd class="min-w-0 break-words text-right font-semibold text-slate-800">{{ row.value }}</dd>
                </div>
              </dl>
              <ul v-if="dialogState.items?.length" class="max-h-40 space-y-0.5 overflow-auto rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
                <li v-for="item in dialogState.items" :key="item" class="break-words">{{ item }}</li>
              </ul>
            </div>
          </div>
          <div class="flex flex-col-reverse gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3 sm:flex-row sm:justify-end">
            <button
              v-if="dialogState.kind === 'confirm'"
              ref="cancelButton"
              type="button"
              class="btn-flat"
              @click="closeDialog(false)"
            >
              {{ dialogState.cancelText || 'Cancel' }}
            </button>
            <button
              ref="confirmButton"
              type="button"
              :class="['btn-primary', tone.button]"
              @click="closeDialog(true)"
            >
              {{ dialogState.confirmText || (dialogState.kind === 'alert' ? 'OK' : 'Confirm') }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  PaperAirplaneIcon,
} from '@heroicons/vue/24/outline'
import { closeDialog, dialogState } from '../composables/useDialog'

const titleId = 'app-dialog-title'
const messageId = 'app-dialog-message'
const panel = ref<HTMLElement | null>(null)
const cancelButton = ref<HTMLButtonElement | null>(null)
const confirmButton = ref<HTMLButtonElement | null>(null)

const TONES = {
  default: { icon: InformationCircleIcon, badge: 'bg-slate-100 text-slate-700', button: '' },
  danger: { icon: PaperAirplaneIcon, badge: 'bg-rose-50 text-rose-700', button: 'bg-rose-700 hover:bg-rose-800' },
  warning: { icon: ExclamationTriangleIcon, badge: 'bg-amber-50 text-amber-700', button: 'bg-amber-600 hover:bg-amber-700' },
  success: { icon: CheckCircleIcon, badge: 'bg-emerald-50 text-emerald-700', button: 'bg-emerald-700 hover:bg-emerald-800' },
}
const tone = computed(() => TONES[dialogState.tone || 'default'])

// Focus the safe choice first for confirmations (Cancel), the only button for
// alerts, and give focus back to whatever had it when the dialog closes.
let returnFocus: HTMLElement | null = null
watch(() => dialogState.open, async open => {
  if (open) {
    returnFocus = document.activeElement as HTMLElement | null
    await nextTick()
    ;(cancelButton.value || confirmButton.value)?.focus()
  } else {
    returnFocus?.focus?.()
    returnFocus = null
  }
})

function trapFocus(event: KeyboardEvent) {
  const buttons = [cancelButton.value, confirmButton.value].filter(Boolean) as HTMLButtonElement[]
  if (buttons.length < 2) {
    event.preventDefault()
    return
  }
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  const next = event.shiftKey ? (index <= 0 ? buttons.length - 1 : index - 1) : (index + 1) % buttons.length
  event.preventDefault()
  buttons[next].focus()
}
</script>
