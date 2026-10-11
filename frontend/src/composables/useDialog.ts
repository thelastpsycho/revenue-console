import { reactive } from 'vue'

/** In-app replacement for window.confirm / window.alert, rendered once by
 * AppDialog.vue (mounted in App.vue). Only one dialog shows at a time; opening
 * another while one is up cancels the first. */

export type DialogTone = 'default' | 'danger' | 'success' | 'warning'

export interface DialogOptions {
  title: string
  message?: string
  /** Label/value rows shown as a summary table, e.g. what is about to be sent. */
  details?: { label: string; value: string }[]
  /** Bullet list under the summary, e.g. failed addresses. */
  items?: string[]
  confirmText?: string
  cancelText?: string
  tone?: DialogTone
}

interface DialogState extends DialogOptions {
  open: boolean
  kind: 'confirm' | 'alert'
}

export const dialogState = reactive<DialogState>({ open: false, kind: 'confirm', title: '' })

let resolver: ((ok: boolean) => void) | null = null

function show(kind: DialogState['kind'], options: DialogOptions) {
  resolver?.(false)
  Object.assign(dialogState, {
    message: undefined, details: undefined, items: undefined,
    confirmText: undefined, cancelText: undefined, tone: 'default',
    ...options, kind, open: true,
  })
  return new Promise<boolean>(resolve => { resolver = resolve })
}

export function closeDialog(ok: boolean) {
  dialogState.open = false
  const resolve = resolver
  resolver = null
  resolve?.(ok)
}

/** Resolves true when the operator confirms, false on cancel / Esc / backdrop. */
export function confirmDialog(options: DialogOptions) {
  return show('confirm', options)
}

/** Resolves when the operator dismisses it. */
export async function alertDialog(options: DialogOptions) {
  await show('alert', options)
}
