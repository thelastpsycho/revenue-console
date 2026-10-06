<template>
  <!-- Mobile backdrop -->
  <transition
    enter-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    leave-active-class="transition-opacity duration-200"
    leave-to-class="opacity-0"
  >
    <div
      v-if="open"
      class="fixed inset-0 z-30 bg-slate-900/20 lg:hidden"
      @click="$emit('close')"
    />
  </transition>

  <aside
    :class="[
      'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform duration-200 ease-out lg:translate-x-0',
      open ? 'translate-x-0' : '-translate-x-full',
    ]"
  >
    <!-- Brand -->
    <div class="flex h-16 items-center gap-2.5 border-b border-slate-200 px-6">
      <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white">
        <ChartBarSquareIcon class="h-5 w-5" />
      </span>
      <div class="leading-tight">
        <p class="text-sm font-semibold tracking-tight text-slate-900">Revenue Console</p>
        <p class="text-xs text-slate-400">Yield &amp; Inventory</p>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 space-y-0.5 overflow-y-auto px-3 py-5">
      <p class="px-3 pb-2 text-[11px] font-medium uppercase tracking-widest text-slate-400">
        Pipeline
      </p>
      <router-link
        v-for="item in navigation"
        :key="item.name"
        :to="item.href"
        @click="$emit('close')"
        :class="[
          route.path === item.href
            ? 'bg-slate-100 text-slate-900'
            : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900',
          'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors cursor-pointer',
        ]"
      >
        <component
          :is="item.icon"
          :class="[
            route.path === item.href ? 'text-slate-900' : 'text-slate-400 group-hover:text-slate-600',
            'h-5 w-5 flex-shrink-0 transition-colors',
          ]"
        />
        <span>{{ item.name }}</span>
        <span
          v-if="item.href === SCHEDULE_PAGE && scheduleBadge"
          class="relative ml-auto flex h-2.5 w-2.5"
          :title="scheduleBadge.title"
          :aria-label="scheduleBadge.title"
        >
          <span
            v-if="scheduleBadge.blink"
            :class="['absolute inline-flex h-full w-full animate-ping rounded-full opacity-75', scheduleBadge.color]"
          />
          <span :class="['relative inline-flex h-2.5 w-2.5 rounded-full', scheduleBadge.color]" />
        </span>
      </router-link>
    </nav>

    <!-- Footer -->
    <div class="border-t border-slate-200 px-4 py-4">
      <div class="flex items-center gap-3 px-2">
        <span class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">
          RC
        </span>
        <div class="min-w-0 leading-tight">
          <p class="truncate text-xs font-medium text-slate-900">Local session</p>
          <p class="truncate text-[11px] text-slate-400">fo.hospitality.mykg.id</p>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import axios from '../plugins/axios'
import {
  HomeIcon,
  DocumentTextIcon,
  CircleStackIcon,
  ChartBarIcon,
  ArchiveBoxIcon,
  ChartBarSquareIcon,
  ReceiptPercentIcon,
  RocketLaunchIcon,
  BeakerIcon,
  BoltIcon,
  ClockIcon,
} from '@heroicons/vue/24/outline'

defineProps<{ open: boolean }>()
defineEmits<{ (e: 'close'): void }>()

const route = useRoute()

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Scraping', href: '/scraping', icon: DocumentTextIcon },
  { name: 'Data', href: '/data', icon: CircleStackIcon },
  { name: 'Yielder', href: '/yielder', icon: ChartBarIcon },
  { name: 'Allotment', href: '/allotment', icon: ArchiveBoxIcon },
  { name: 'BAR Calculator', href: '/bar-calculator', icon: ReceiptPercentIcon },
  { name: 'Pipeline', href: '/pipeline', icon: RocketLaunchIcon },
  { name: 'Fast API Pipeline', href: '/fast-api-pipeline', icon: BoltIcon },
  { name: 'Pipeline History', href: '/fast-pipeline-history', icon: ClockIcon },
  { name: 'PMS API Test', href: '/pms-api-test', icon: BeakerIcon },
]

// Schedule indicator on the Fast API Pipeline item: blinks while the
// UI-managed schedule is on and the scheduler container is checking in
// (red = live, green = preview); steady amber when it's on but the
// scheduler is offline, i.e. switched on but nothing will actually run.
const SCHEDULE_PAGE = '/fast-api-pipeline'
const SCHEDULE_POLL_MS = 15000

const schedule = ref<{
  enabled: boolean
  live: boolean
  intervalMinutes: number
  nextRunAt: string | null
  schedulerOnline: boolean
} | null>(null)
const runInProgress = ref(false)

async function loadSchedule() {
  try {
    const res = await axios.get('/api/fast-pipeline/schedule')
    schedule.value = res.data.schedule
    runInProgress.value = res.data.pipelineActive
  } catch {
    // Badge just keeps its last state; the page itself reports errors.
  }
}

let scheduleTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  loadSchedule()
  scheduleTimer = setInterval(loadSchedule, SCHEDULE_POLL_MS)
})
onBeforeUnmount(() => clearInterval(scheduleTimer))

const scheduleBadge = computed(() => {
  const s = schedule.value
  if (!s?.enabled) return null
  if (!s.schedulerOnline) {
    return { blink: false, color: 'bg-amber-500', title: 'Schedule is on, but the scheduler is offline - no runs will happen' }
  }
  const mode = s.live ? 'LIVE' : 'Preview'
  const every = s.intervalMinutes % 60 === 0 ? `${s.intervalMinutes / 60} h` : `${s.intervalMinutes} min`
  const next = s.nextRunAt
    ? new Date(s.nextRunAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    : 'soon'
  const status = runInProgress.value ? 'run in progress' : `next run ${next}`
  return {
    blink: true,
    color: s.live ? 'bg-rose-500' : 'bg-emerald-500',
    title: `Schedule on - ${mode}, every ${every} - ${status}`,
  }
})
</script>
