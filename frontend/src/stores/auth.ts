import { defineStore } from 'pinia'
import axios, { setCsrfToken } from '../plugins/axios'

export interface AuthUser {
  id: number
  username: string
  displayName: string
  permissions: string[]
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    loading: true,
    authenticated: false,
    configured: false,
    user: null as AuthUser | null,
    error: '',
  }),
  getters: {
    hasPermission(state) {
      return (key: string) => !!state.user?.permissions.includes(key)
    },
  },
  actions: {
    async refresh() {
      try {
        const { data } = await axios.get('/api/auth/status')
        this.configured = !!data.configured || !!data.dev_mode
        this.authenticated = !!data.authenticated
        this.user = data.user || null
        setCsrfToken(data.csrf_token || null)
        this.error = ''
      } catch {
        this.configured = false
        this.authenticated = false
        this.user = null
        this.error = 'Cannot reach the backend.'
      } finally {
        this.loading = false
      }
    },
    async login(username: string, password: string) {
      const { data } = await axios.post('/api/auth/login', { username, password })
      setCsrfToken(data.csrf_token)
      this.authenticated = true
      this.user = data.user
      this.error = ''
    },
    async logout() {
      try {
        await axios.post('/api/auth/logout')
      } finally {
        this.expireSession('')
      }
    },
    async changePassword(currentPassword: string, newPassword: string) {
      await axios.post('/api/auth/change-password', { currentPassword, newPassword })
    },
    setError(message: string) {
      this.error = message
    },
    expireSession(message = 'Your session expired. Please sign in again.') {
      this.authenticated = false
      this.user = null
      setCsrfToken(null)
      this.error = message
    },
  },
})
