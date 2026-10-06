<template>
  <div class="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Scraping"
      subtitle="Log into the PMS and capture room availability, then process and combine inventory."
    />

    <div class="grid grid-cols-1 gap-6 xl:grid-cols-3">

      <!-- Left Column: Actions -->
      <section class="space-y-6 xl:col-span-2">
        <!-- Main Scraping Card -->
        <div class="neu-card p-6">
          <h2 class="text-base font-semibold text-app-tertiary">Start a new scraping task</h2>
          <p class="mt-1 text-sm text-slate-500">Select a start date and enter your PMS credentials to begin.</p>

          <div class="mt-5">
            <label for="startDate" class="mb-1.5 block text-sm font-semibold text-slate-600">Start date</label>
            <input
              type="date"
              id="startDate"
              v-model="startDate"
              class="neu-input"
            />
          </div>

          <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label for="pmsUsername" class="mb-1.5 block text-sm font-semibold text-slate-600">PMS username</label>
              <input
                type="text"
                id="pmsUsername"
                v-model="username"
                autocomplete="username"
                placeholder="Username"
                class="neu-input"
              />
            </div>
            <div>
              <label for="pmsPassword" class="mb-1.5 block text-sm font-semibold text-slate-600">PMS password</label>
              <input
                type="password"
                id="pmsPassword"
                v-model="password"
                autocomplete="current-password"
                placeholder="Password"
                class="neu-input"
              />
            </div>
          </div>

          <button
            @click="startScraping"
            :disabled="isScraping"
            class="btn-primary mt-5 w-full px-5 py-3"
          >
            <svg v-if="isScraping" class="h-5 w-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <BoltIcon v-else class="h-5 w-5" />
            {{ isScraping ? 'Scraping in progress…' : 'Start scraping now' }}
          </button>
        </div>

        <!-- Other Actions Card -->
        <div class="neu-card p-6">
          <h2 class="text-base font-semibold text-app-tertiary">Additional tools</h2>
          <p class="mt-1 text-sm text-slate-500">Run the downstream processing stages after scraping.</p>
          <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <button @click="openModal" :disabled="loadingProcessCM" class="group flex flex-col items-start gap-3 rounded-xl bg-app-primary p-4 text-left shadow-neu-sm transition-all duration-200 active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer">
              <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-app-primary text-app-accent shadow-neu-sm">
                <DocumentTextIcon class="h-5 w-5" />
              </span>
              <span class="text-sm font-semibold text-app-tertiary">Process CM</span>
            </button>
            <button @click="triggerScrapeCM" :disabled="isScrapingCM" class="group flex flex-col items-start gap-3 rounded-xl bg-app-primary p-4 text-left shadow-neu-sm transition-all duration-200 active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer">
              <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-app-primary text-app-accent shadow-neu-sm">
                <span v-if="isScrapingCM" class="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent"></span>
                <CloudArrowDownIcon v-else class="h-5 w-5" />
              </span>
              <span class="text-sm font-semibold text-app-tertiary">{{ isScrapingCM ? 'Scraping CM…' : 'Scrape CM' }}</span>
            </button>
            <button @click="triggerCombine" :disabled="loadingCombine" class="group flex flex-col items-start gap-3 rounded-xl bg-app-primary p-4 text-left shadow-neu-sm transition-all duration-200 active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer">
              <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-app-primary text-app-accent shadow-neu-sm">
                <ArrowsRightLeftIcon class="h-5 w-5" />
              </span>
              <span class="text-sm font-semibold text-app-tertiary">Combine inventory</span>
            </button>
            <button @click="triggerYield" :disabled="loadingYield" class="group flex flex-col items-start gap-3 rounded-xl bg-app-primary p-4 text-left shadow-neu-sm transition-all duration-200 active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer">
              <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-app-primary text-app-accent shadow-neu-sm">
                <ChartBarIcon class="h-5 w-5" />
              </span>
              <span class="text-sm font-semibold text-app-tertiary">Calculate yield</span>
            </button>
          </div>
        </div>
      </section>

      <!-- Right Column: Status & Instructions -->
      <aside class="space-y-6 xl:col-span-1">
        <!-- Status Card -->
        <div class="neu-card p-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold text-app-tertiary">
            <InformationCircleIcon class="h-5 w-5 text-slate-400" />
            Status
          </h3>
          <div class="mt-3 space-y-2">
            <div v-if="message" :class="['rounded-lg px-3 py-2 text-xs font-medium', messageType === 'success' ? 'bg-app-primary text-emerald-700 shadow-neu-inset-sm' : 'bg-app-primary text-rose-700 shadow-neu-inset-sm']">
              {{ message }}
            </div>
            <div v-if="error" class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
              {{ error }}
            </div>
            <div v-if="success" class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-emerald-700 shadow-neu-inset-sm">
              {{ success }}
            </div>
            <div v-if="!message && !error && !success" class="text-sm text-slate-500">
              No new notifications. System is ready.
            </div>
          </div>
        </div>

        <!-- Instructions Card -->
        <div class="neu-card p-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold text-app-tertiary">
            <LightBulbIcon class="h-5 w-5 text-slate-400" />
            How it works
          </h3>
          <ul class="mt-3 space-y-2.5 text-sm text-slate-600">
            <li class="flex items-start gap-2">
              <CheckCircleIcon class="mt-0.5 h-4 w-4 flex-shrink-0 text-app-accent" />
              <span>Select a <strong class="font-medium text-app-tertiary">start date</strong> for the data scrape.</span>
            </li>
            <li class="flex items-start gap-2">
              <CheckCircleIcon class="mt-0.5 h-4 w-4 flex-shrink-0 text-app-accent" />
              <span>Click <strong class="font-medium text-app-tertiary">Start scraping</strong> to begin the process.</span>
            </li>
            <li class="flex items-start gap-2">
              <CheckCircleIcon class="mt-0.5 h-4 w-4 flex-shrink-0 text-app-accent" />
              <span>Use the <strong class="font-medium text-app-tertiary">additional tools</strong> for processing and analysis.</span>
            </li>
            <li class="flex items-start gap-2">
              <CheckCircleIcon class="mt-0.5 h-4 w-4 flex-shrink-0 text-app-accent" />
              <span>Monitor progress in the <strong class="font-medium text-app-tertiary">scraping modal</strong>.</span>
            </li>
          </ul>
        </div>
      </aside>

    </div>

    <!-- Modal for file upload -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-500/20 p-4 backdrop-blur-sm">
      <div class="relative w-full max-w-md rounded-xl bg-app-primary p-6 shadow-neu">
        <button @click="closeModal" class="btn-icon absolute right-4 top-4 !p-2">
          <XMarkIcon class="h-5 w-5" />
        </button>
        <h3 class="font-semibold text-base text-app-tertiary">Upload &amp; process CM file</h3>
        <p class="mt-1 text-sm text-slate-500">Upload the Channel Manager Excel export (.xlsx).</p>

        <div class="mt-4 rounded-xl bg-app-primary p-5 text-center shadow-neu-inset">
          <CloudArrowUpIcon class="mx-auto h-10 w-10 text-app-accent" />
          <input
            type="file"
            accept=".xlsx"
            @change="onFileChange"
            :disabled="uploading || processingCM"
            class="mt-3 block w-full text-xs text-slate-500 file:mr-3 file:rounded-full file:border-0 file:bg-app-accent file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white hover:file:brightness-110"
          />
        </div>

        <button
          @click="uploadAndProcessCM"
          :disabled="!selectedFile || uploading || processingCM"
          class="btn-primary mt-4 w-full px-4 py-2.5"
        >
          <span v-if="uploading || processingCM" class="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"></span>
          {{ uploading ? 'Uploading…' : (processingCM ? 'Processing…' : 'Upload & process') }}
        </button>
        <div v-if="modalStatus" :class="['mt-3 rounded-lg px-3 py-2 text-center text-xs font-semibold shadow-neu-inset-sm', modalStatusType === 'success' ? 'bg-app-primary text-emerald-700' : 'bg-app-primary text-rose-700']">
          {{ modalStatus }}
        </div>
      </div>
    </div>

    <!-- Scraping Process Modal -->
    <div v-if="isScraping" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-500/20 p-4 backdrop-blur-sm">
      <div class="relative w-full max-w-xl rounded-xl bg-app-primary p-6 shadow-neu">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="flex items-center gap-3 font-semibold text-base text-app-tertiary">
            <span class="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent"></span>
            Scraping in progress
          </h3>
          <button @click="closeScrapingModal" class="btn-icon !p-2">
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>

        <div class="mb-3 rounded-xl bg-app-primary p-3 shadow-neu-inset-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Current operation</p>
          <p class="mt-1 font-mono text-xs text-app-accent">{{ currentOperation }}</p>
        </div>

        <div ref="scrapingLogContainer" class="h-72 overflow-y-auto rounded-xl bg-app-primary p-3 shadow-neu-inset">
          <div v-for="(log, index) in scrapingLogs" :key="index" class="border-b border-slate-200 py-1 font-mono text-xs last:border-b-0">
            <span :class="{
              'text-emerald-700': typeof log === 'string' && (log.includes('successfully') || log.includes('completed')),
              'text-app-accent': typeof log === 'string' && (log.includes('Starting') || log.includes('Processing')),
              'text-slate-500': typeof log !== 'string' || (!log.includes('successfully') && !log.includes('completed') && !log.includes('Starting') && !log.includes('Processing'))
            }">
              {{ typeof log === 'object' ? JSON.stringify(log) : log }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- CM Scrape Process Modal -->
    <div v-if="isScrapingCM" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-500/20 p-4 backdrop-blur-sm">
      <div class="relative w-full max-w-xl rounded-xl bg-app-primary p-6 shadow-neu">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="flex items-center gap-3 font-semibold text-base text-app-tertiary">
            <span class="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent"></span>
            Scraping CM from D-EDGE / Availpro
          </h3>
          <button @click="closeScrapeCMModal" class="btn-icon !p-2">
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>

        <p class="mb-3 text-xs text-slate-500">
          First run on a new device needs a code emailed by D-EDGE - if a Chrome window pops up asking for one, check the inbox and enter it there.
        </p>

        <div ref="cmLogContainer" class="h-72 overflow-y-auto rounded-xl bg-app-primary p-3 shadow-neu-inset">
          <div v-if="cmLogs.length === 0" class="py-8 text-center text-sm text-slate-500">
            Waiting for the scrape to start…
          </div>
          <div v-for="(entry, index) in cmLogs" :key="index" class="border-b border-slate-200 py-1 font-mono text-xs last:border-b-0">
            <span :class="{
              'text-emerald-700': entry.type === 'success',
              'text-rose-700': entry.type === 'error',
              'text-slate-500': entry.type === 'info'
            }">
              {{ entry.message }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import { todayLocalDateString } from '../utils/date'
import {
  BoltIcon,
  DocumentTextIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  InformationCircleIcon,
  LightBulbIcon,
  CheckCircleIcon,
  XMarkIcon,
  CloudArrowUpIcon,
  CloudArrowDownIcon,
} from '@heroicons/vue/24/outline'

const isScraping = ref(false)
const error = ref('')
const success = ref('')
const scrapingLogs = ref<(string | object)[]>([])
const scrapingLogContainer = ref<HTMLElement | null>(null)

// Keep the log pinned to the newest entry as lines stream in.
watch(
  () => scrapingLogs.value.length,
  () => {
    nextTick(() => {
      const el = scrapingLogContainer.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
)
const currentOperation = ref('')
let eventSource: EventSource | null = null
const loadingCombine = ref(false)
const loadingYield = ref(false)
const loadingProcessCM = ref(false)
const dedgeUsername = ref('')
const dedgePassword = ref('')
const isScrapingCM = ref(false)
const cmLogs = ref<Array<{ message: string; type: 'info' | 'success' | 'error' }>>([])
const cmLogContainer = ref<HTMLElement | null>(null)
let cmEventSource: EventSource | null = null

watch(
  () => cmLogs.value.length,
  () => {
    nextTick(() => {
      const el = cmLogContainer.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')
const startDate = ref(todayLocalDateString()) // Initialize with today's local date
const username = ref('')
const password = ref('')

const selectedFile = ref<File|null>(null)
const uploading = ref(false)

// Modal state
const showModal = ref(false)
const processingCM = ref(false)
const modalStatus = ref('')
const modalStatusType = ref<'success'|'error'>('success')

const startScraping = async () => {
  // Blank username/password falls back to PMS_USERNAME / PMS_PASSWORD on the backend.
  isScraping.value = true
  error.value = ''
  success.value = ''
  scrapingLogs.value = []
  currentOperation.value = 'Starting scraping process...'

  try {
    // First make a POST request to start the scraping with date + credentials
    console.log('Starting scraping process...')
    const response = await axios.post('/api/scrape', {
      startDate: startDate.value, // Use the selected date
      username: username.value,
      password: password.value
    })
    console.log('Scraping start response:', response.data)
    
    if (response.data.status !== 'success') {
      throw new Error(response.data.message || 'Failed to start scraping')
    }
    
    // Then create EventSource for Server-Sent Events
    console.log('Establishing SSE connection...')
    eventSource = new EventSource('/api/scrape/stream')
    
    // Add connection opened handler
    eventSource.onopen = () => {
      console.log('SSE connection opened')
      scrapingLogs.value.push('Connected to server...')
    }
    
    eventSource.onmessage = (event) => {
      console.log('Received message:', event.data)
      
      // Make sure scraping state is true
      isScraping.value = true
      
      if (event.data === '[DONE]') {
        console.log('Scraping completed')
        eventSource?.close()
        success.value = 'Scraping completed successfully!'
        currentOperation.value = 'Scraping completed!'
      }
      
      if (event.data.startsWith('Error:')) {
        console.error('Scraping error:', event.data)
        error.value = event.data
        eventSource?.close()
        return
      }
      
      // Parse and handle message data
      try {
        const messageData = JSON.parse(event.data);
        
        // Handle pending status specially
        if (messageData.status === "pending") {
          // Skip adding repetitive pending messages to the logs
          return;
        }
        
        // For complete or success status, update currentOperation
        if (messageData.status === "success" || messageData.status === "complete") {
          currentOperation.value = messageData.message || 'Operation completed';
        }

        scrapingLogs.value.push(messageData);

        // "complete" is always the final event the backend sends before closing
        // the stream, so treat it as the signal to stop and close the modal.
        if (messageData.status === "complete") {
          success.value = messageData.message || 'Scraping completed successfully!';
          eventSource?.close();
          isScraping.value = false;
          return;
        }
      } catch (e) {
        // Not JSON or parsing failed, treat as regular message
        // Update the current operation text for meaningful string messages
        if (typeof event.data === 'string' && 
            !event.data.includes('{') && 
            !event.data.includes('pending')) {
          currentOperation.value = event.data;
        }
        
        scrapingLogs.value.push(event.data);
      }
    }
    
    eventSource.onerror = (err) => {
      console.error('EventSource error:', err)
      // Only show error if we're still in scraping state
      // This prevents showing error when connection closes normally after completion
      if (isScraping.value) {
        error.value = 'Connection to server lost. Please try again.'
        eventSource?.close()
      }
    }
  } catch (err: any) {
    console.error('Error during scraping:', err)
    error.value = err.response?.data?.message || 'Failed to start scraping. Please try again.'
    setTimeout(() => {
      isScraping.value = false
    }, 3000)
  }
}

function onFileChange(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files && files.length > 0) {
    selectedFile.value = files[0]
  }
}

function openModal() {
  showModal.value = true
  selectedFile.value = null
  modalStatus.value = ''
}

function closeModal() {
  showModal.value = false
  selectedFile.value = null
  modalStatus.value = ''
}

async function uploadAndProcessCM() {
  if (!selectedFile.value) return
  uploading.value = true
  modalStatus.value = ''
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const uploadRes = await axios.post('/api/upload-cm-excel', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    modalStatus.value = uploadRes.data.message || 'File uploaded successfully.'
    modalStatusType.value = 'success'
    // Now trigger process CM
    processingCM.value = true
    const processRes = await axios.post('/api/process-cm')
    modalStatus.value = processRes.data.message || 'Process CM completed.'
    modalStatusType.value = 'success'
  } catch (err: any) {
    modalStatus.value = err?.response?.data?.message || 'Failed to upload or process CM.'
    modalStatusType.value = 'error'
  } finally {
    uploading.value = false
    processingCM.value = false
  }
}

async function triggerScrapeCM() {
  isScrapingCM.value = true
  cmLogs.value = []
  message.value = ''

  // Open the stream before starting the job so no early log lines are missed.
  cmEventSource = new EventSource('/api/scrape-cm/stream')

  cmEventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)
    cmLogs.value.push({ message: data.message, type: data.type })

    if (data.type === 'success' || data.type === 'error') {
      cmEventSource?.close()
      isScrapingCM.value = false
      message.value = data.message
      messageType.value = data.type === 'success' ? 'success' : 'error'
    }
  }

  cmEventSource.onerror = () => {
    cmLogs.value.push({ message: 'Connection to server lost.', type: 'error' })
    cmEventSource?.close()
    isScrapingCM.value = false
  }

  try {
    await axios.post('/api/scrape-cm', {
      startDate: startDate.value,
      dedgeUsername: dedgeUsername.value || undefined,
      dedgePassword: dedgePassword.value || undefined,
    })
  } catch (err: any) {
    cmEventSource?.close()
    isScrapingCM.value = false
    message.value = err?.response?.data?.message || 'Failed to start CM scrape.'
    messageType.value = 'error'
  }
}

function closeScrapeCMModal() {
  cmEventSource?.close()
  isScrapingCM.value = false
}

async function triggerCombine() {
  loadingCombine.value = true
  message.value = ''
  try {
    console.log('Starting combine inventory process...')
    const res = await axios.post('/api/combine-inventory')
    console.log('Combine inventory response:', res.data)
    message.value = res.data.message || 'Combine inventory completed.'
    messageType.value = 'success'
  } catch (err: any) {
    console.error('Error in combine inventory:', err)
    message.value = err?.response?.data?.message || 'Failed to combine inventory. Please check the console for details.'
    messageType.value = 'error'
  } finally {
    loadingCombine.value = false
  }
}

async function triggerYield() {
  loadingYield.value = true
  message.value = ''
  try {
    console.log('Starting yield calculation process...')
    const res = await axios.post('/api/yield')
    console.log('Yield calculation response:', res.data)
    message.value = res.data.message || 'Yield calculation completed.'
    messageType.value = 'success'
  } catch (err: any) {
    console.error('Error in yield calculation:', err)
    message.value = err?.response?.data?.message || 'Failed to calculate yield. Please check the console for details.'
    messageType.value = 'error'
  } finally {
    loadingYield.value = false
  }
}

function closeScrapingModal() {
  if (eventSource) {
    eventSource.close();
  }
  isScraping.value = false;
}
</script>