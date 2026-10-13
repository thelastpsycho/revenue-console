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
      'group/sidebar fixed inset-y-0 left-0 z-40 flex w-64 flex-col overflow-hidden border-r border-slate-200 bg-white transition-[width] duration-200 ease-out lg:w-16 lg:translate-x-0 lg:hover:w-64',
      open ? 'translate-x-0' : '-translate-x-full',
    ]"
  >
    <!-- Brand -->
    <div class="flex h-16 items-center gap-2.5 border-b border-slate-200 px-6 lg:px-[18px] lg:group-hover/sidebar:px-6">
      <span class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
        <ChartBarSquareIcon class="h-5 w-5" />
      </span>
      <div class="min-w-0 whitespace-nowrap leading-tight lg:hidden lg:group-hover/sidebar:block">
        <p class="text-sm font-semibold tracking-tight text-slate-900">Revenue Console</p>
        <p class="text-xs text-slate-400">Yield &amp; Inventory</p>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden px-3 py-5">
      <p
        class="whitespace-nowrap px-3 pb-2 text-[11px] font-medium uppercase tracking-widest text-slate-400 lg:hidden lg:group-hover/sidebar:block"
      >
        Pipeline
      </p>
      <div v-for="item in navigation" :key="item.name">
        <div class="flex items-stretch gap-0.5">
          <router-link
            :to="item.href"
            :title="item.href === SCHEDULE_PAGE && scheduleBadge ? `${item.name} — ${scheduleBadge.title}` : item.name"
            @click="$emit('close')"
            :class="[
              route.path === item.href
                ? 'bg-slate-100 text-slate-900'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900',
              'group flex flex-1 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors cursor-pointer',
            ]"
          >
            <component
              :is="item.icon"
              :class="[
                item.href === SCHEDULE_PAGE && scheduleBadge
                  ? SCHEDULE_ICON_CLASSES[scheduleBadge.tone]
                  : route.path === item.href ? 'text-slate-900' : 'text-slate-400 group-hover:text-slate-600',
                'h-5 w-5 flex-shrink-0 transition-colors',
              ]"
              :aria-label="item.href === SCHEDULE_PAGE && scheduleBadge ? scheduleBadge.title : undefined"
            />
            <span class="whitespace-nowrap lg:hidden lg:group-hover/sidebar:inline">{{ item.name }}</span>
          </router-link>
          <button
            v-if="item.children"
            type="button"
            class="hidden w-7 flex-shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-50 hover:text-slate-600 lg:group-hover/sidebar:flex"
            :aria-expanded="isExpanded(item)"
            :aria-label="`${isExpanded(item) ? 'Collapse' : 'Expand'} ${item.name}`"
            @click="toggleExpanded(item)"
          >
            <ChevronRightIcon
              :class="['h-4 w-4 transition-transform', isExpanded(item) && 'rotate-90']"
            />
          </button>
        </div>
        <div
          v-if="item.children && isExpanded(item)"
          class="ml-6 mt-0.5 space-y-0.5 border-l border-slate-200 pl-3 lg:hidden lg:group-hover/sidebar:block"
        >
          <router-link
            v-for="child in item.children"
            :key="child.name"
            :to="child.href"
            @click="$emit('close')"
            :class="[
              route.path === child.href
                ? 'bg-slate-100 text-slate-900'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900',
              'flex items-center whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer',
            ]"
          >
            {{ child.name }}
          </router-link>
        </div>
      </div>
    </nav>

    <!-- Footer -->
    <div class="border-t border-slate-200 px-4 py-4">
      <div class="flex items-center gap-3 px-2">
        <span class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">
          RC
        </span>
        <div class="min-w-0 whitespace-nowrap leading-tight lg:hidden lg:group-hover/sidebar:block">
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
  CircleStackIcon,
  ChartBarIcon,
  ChartBarSquareIcon,
  ChevronRightIcon,
  ReceiptPercentIcon,
  BeakerIcon,
  BoltIcon,
  ClockIcon,
  EnvelopeIcon,
  PresentationChartLineIcon,
} from '@heroicons/vue/24/outline'

defineProps<{ open: boolean }>()
defineEmits<{ (e: 'close'): void }>()

const route = useRoute()

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Data', href: '/data', icon: CircleStackIcon },
  { name: 'Yielder', href: '/yielder', icon: ChartBarIcon },
  { name: 'BAR Calculator', href: '/bar-calculator', icon: ReceiptPercentIcon },
  { name: 'Fast API Pipeline', href: '/fast-api-pipeline', icon: BoltIcon },
  { name: 'Pipeline History', href: '/fast-pipeline-history', icon: ClockIcon },
  { name: 'Stop Sale', href: '/stop-sale', icon: EnvelopeIcon },
  {
    name: 'RMS',
    href: '/rms',
    icon: PresentationChartLineIcon,
    children: [{ name: 'Online', href: '/rms/online' }],
  },
  { name: 'PMS API Test', href: '/pms-api-test', icon: BeakerIcon },
]
const expanded = ref<Record<string, boolean>>({})
function isExpanded(item: { name: string; children?: unknown[] }) {
  return expanded.value[item.name] ?? route.path.startsWith('/rms')
}
function toggleExpanded(item: { name: string }) {
  expanded.value[item.name] = !isExpanded(item)
}

// Schedule indicator on the Fast API Pipeline item: the icon itself turns
// color and pulses while the UI-managed schedule is on and the scheduler
// container is checking in (red = live, green = preview); steady amber
// when it's on but the scheduler is offline, i.e. switched on but nothing
// will actually run. Driving the icon (rather than a separate dot) means
// it still reads correctly when the sidebar is collapsed to an icon rail.
const SCHEDULE_PAGE = '/fast-api-pipeline'
const SCHEDULE_POLL_MS = 15000
const SCHEDULE_ICON_CLASSES: Record<string, string> = {
  live: 'text-rose-500 animate-pulse',
  preview: 'text-emerald-500 animate-pulse',
  offline: 'text-amber-500',
}

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
    return { tone: 'offline', title: 'Schedule is on, but the scheduler is offline - no runs will happen' }
  }
  const mode = s.live ? 'LIVE' : 'Preview'
  const every = s.intervalMinutes % 60 === 0 ? `${s.intervalMinutes / 60} h` : `${s.intervalMinutes} min`
  const next = s.nextRunAt
    ? new Date(s.nextRunAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    : 'soon'
  const status = runInProgress.value ? 'run in progress' : `next run ${next}`
  return {
    tone: s.live ? 'live' : 'preview',
    title: `Schedule on - ${mode}, every ${every} - ${status}`,
  }
})
</script>
