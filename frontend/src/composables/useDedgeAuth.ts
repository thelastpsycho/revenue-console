import { ref, onMounted, onBeforeUnmount } from 'vue'
import axios from '../plugins/axios'

export interface DedgeAuthStatus {
  pending: boolean
  since: string | null
  deadline: string | null
  email_hint: string | null
  last_error: string | null
  last_verified_at: string | null
  check_running: boolean
  check_result: { ok: boolean; message: string; at: string } | null
}

// One shared poll for every component that shows D-EDGE device-code state
// (the global banner and the session card), so they never disagree.
const status = ref<DedgeAuthStatus | null>(null)
const pipelineActive = ref(false)
let users = 0
let timer: ReturnType<typeof setTimeout> | undefined

async function refresh() {
  try {
    const res = await axios.get('/api/dedge/auth/status')
    status.value = res.data.auth
    pipelineActive.value = res.data.pipelineActive
  } catch {
    // Keep the last known state; a transient failure shouldn't hide a prompt.
  }
}

function schedule() {
  // Poll fast while something is waiting on the user or in flight.
  const busy = status.value?.pending || status.value?.check_running
  timer = setTimeout(async () => {
    await refresh()
    if (users > 0) schedule()
  }, busy ? 3000 : 15000)
}

export function useDedgeAuth() {
  onMounted(() => {
    users += 1
    if (users === 1) {
      refresh().then(schedule)
    }
  })
  onBeforeUnmount(() => {
    users -= 1
    if (users === 0) clearTimeout(timer)
  })

  async function post(path: string, body?: unknown): Promise<string> {
    try {
      const res = await axios.post(path, body)
      return res.data.message
    } finally {
      await refresh()
    }
  }

  return {
    status,
    pipelineActive,
    refresh,
    submitCode: (code: string) => post('/api/dedge/auth/code', { code }),
    resendEmail: () => post('/api/dedge/auth/resend'),
    checkSession: () => post('/api/dedge/auth/check'),
  }
}
