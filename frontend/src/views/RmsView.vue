<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="RMS"
      subtitle="Forecast is read live from the PMS. Pace is rebuilt from the booking history cached locally, so it can compare against the same time last year. Room revenue only."
    />

    <div class="flex max-w-full gap-1.5 overflow-x-auto rounded-xl bg-app-primary p-1.5 shadow-neu-inset-sm sm:w-fit" role="tablist">
      <button
        v-for="tab in TABS"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.id"
        @click="selectTab(tab.id)"
        :class="[
          activeTab === tab.id ? 'bg-app-primary text-app-accent shadow-neu-sm' : 'text-slate-500 hover:text-app-tertiary',
          'flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200',
        ]"
      >
        <component :is="tab.icon" class="h-4 w-4" />
        {{ tab.name }}
      </button>
    </div>

    <!-- ===== Forecast ===== -->
    <div v-show="activeTab === 'forecast'" class="space-y-4">
      <div class="neu-card flex flex-wrap items-end gap-3 p-4 text-xs">
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">From</span>
          <input v-model="fc.start" type="date" class="neu-input py-1.5 text-xs" />
        </label>
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">Days</span>
          <select v-model.number="fc.days" class="neu-input py-1.5 text-xs">
            <option v-for="d in [7, 14, 30, 60, 90]" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <button type="button" class="btn-primary px-3 py-1.5 text-xs" :disabled="fc.loading" @click="loadForecast">
          <ArrowPathIcon :class="['h-4 w-4', fc.loading && 'animate-spin']" />
          {{ fc.loading ? 'Loading from PMS…' : 'Load forecast' }}
        </button>
        <p class="text-[11px] text-slate-500">Read live from the PMS - takes 20-45 seconds.</p>
      </div>

      <p v-if="fc.error" class="neu-card p-4 text-xs font-semibold text-rose-700">{{ fc.error }}</p>

      <template v-if="forecast">
        <dl class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div v-for="tile in forecastTiles" :key="tile.label" class="neu-card p-3">
            <dt class="text-[11px] text-slate-500">{{ tile.label }}</dt>
            <dd class="mt-1 text-lg font-semibold tabular-nums text-slate-900">{{ tile.value }}</dd>
          </div>
        </dl>

        <div class="neu-card overflow-hidden">
          <h2 class="border-b border-slate-200 p-4 text-sm font-semibold text-app-tertiary">Hotel forecast</h2>
          <div class="max-h-[60vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 z-10 bg-white shadow-[0_1px_0_rgb(226_232_240)]">
                <tr>
                  <th v-for="h in ['Date', 'Occ.', 'Rooms sold', 'Room revenue', 'ADR', 'Comp / HU', 'LY transient']" :key="h"
                      :class="['px-3 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500', h === 'Date' ? 'text-left' : 'text-right']">{{ h }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="r in forecast.hotel" :key="r.date" class="hover:bg-slate-50">
                  <td class="whitespace-nowrap px-3 py-2 font-semibold text-slate-700">{{ formatDay(r.date) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums">
                    <span :class="['rounded-full px-2 py-0.5 font-semibold', occClass(r.occupancy)]">{{ r.occupancy?.toFixed(1) }}%</span>
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ r.roomsSold }} / {{ r.roomCount }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ millions(r.revenue) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ thousands(r.adr) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ r.complimentary }} / {{ r.houseUse }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ r.lastYear }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div class="neu-card overflow-hidden xl:col-span-5">
            <h2 class="border-b border-slate-200 p-4 text-sm font-semibold text-app-tertiary">By market segment <span class="font-normal text-slate-500">(whole window)</span></h2>
            <div class="overflow-x-auto">
              <table class="min-w-full text-xs">
                <thead>
                  <tr>
                    <th v-for="h in ['Segment', 'Room nights', 'Share', 'Revenue', 'ADR']" :key="h"
                        :class="['px-3 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500', h === 'Segment' ? 'text-left' : 'text-right']">{{ h }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="s in segmentTotals" :key="s.market">
                    <td class="px-3 py-2 font-semibold text-slate-700">{{ s.market }}</td>
                    <td class="px-3 py-2 text-right tabular-nums">{{ s.rooms }}</td>
                    <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ s.share.toFixed(1) }}%</td>
                    <td class="px-3 py-2 text-right tabular-nums">{{ millions(s.revenue) }}</td>
                    <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ s.rooms ? thousands(s.revenue / s.rooms) : '–' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="neu-card overflow-hidden xl:col-span-7">
            <h2 class="border-b border-slate-200 p-4 text-sm font-semibold text-app-tertiary">Expected occupied by room type</h2>
            <div class="max-h-[60vh] overflow-auto">
              <table class="min-w-full text-xs">
                <thead class="sticky top-0 z-10 bg-white shadow-[0_1px_0_rgb(226_232_240)]">
                  <tr>
                    <th class="sticky left-0 bg-white px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Room type</th>
                    <th v-for="d in roomMatrix.dates" :key="d" class="whitespace-nowrap px-2 py-2.5 text-right text-[11px] font-bold text-slate-500">{{ shortDay(d) }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="t in roomMatrix.types" :key="t.typeId">
                    <td class="sticky left-0 whitespace-nowrap bg-white px-3 py-1.5 font-semibold text-slate-700" :title="t.typeId">
                      {{ roomLabel(t.typeId) }} <span class="font-normal text-slate-400">{{ t.roomCount }}</span>
                    </td>
                    <td v-for="d in roomMatrix.dates" :key="d"
                        :class="['px-2 py-1.5 text-right tabular-nums', cellClass(t.cells[d], t.roomCount)]">
                      {{ t.cells[d] ?? '' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ===== Pace ===== -->
    <div v-show="activeTab === 'pace'" class="space-y-4">
      <p v-if="sync && !sync.coverageFrom" class="neu-card bg-amber-50 p-4 text-xs font-semibold text-amber-800">
        No booking history yet. Run the backfill in the Booking data tab first. Until then, pace and same-time-last-year are empty.
      </p>

      <div class="neu-card flex flex-wrap items-end gap-3 p-4 text-xs">
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">Stay from</span>
          <input v-model="pc.start" type="date" class="neu-input py-1.5 text-xs" />
        </label>
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">To</span>
          <input v-model="pc.end" type="date" class="neu-input py-1.5 text-xs" />
        </label>
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">Room type</span>
          <select v-model="pc.roomType" class="neu-input py-1.5 text-xs">
            <option value="">All</option>
            <option v-for="t in dims.roomTypes" :key="t" :value="t">{{ roomLabel(t) }}</option>
          </select>
        </label>
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">Market</span>
          <select v-model="pc.marketId" class="neu-input py-1.5 text-xs">
            <option value="">All</option>
            <option v-for="m in dims.markets" :key="m.id" :value="String(m.id)">{{ m.name }}</option>
          </select>
        </label>
        <label class="space-y-1">
          <span class="font-semibold text-slate-600">Pickup over</span>
          <select v-model.number="pc.pickupDays" class="neu-input py-1.5 text-xs">
            <option v-for="d in [1, 3, 7, 14, 30]" :key="d" :value="d">{{ d }} day{{ d > 1 ? 's' : '' }}</option>
          </select>
        </label>
        <button type="button" class="btn-primary px-3 py-1.5 text-xs" :disabled="pc.loading" @click="loadPace">
          <ArrowPathIcon :class="['h-4 w-4', pc.loading && 'animate-spin']" />
          Load pace
        </button>
      </div>

      <p v-if="pc.error" class="neu-card p-4 text-xs font-semibold text-rose-700">{{ pc.error }}</p>

      <div v-if="paceRows.length" class="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div class="neu-card overflow-hidden xl:col-span-7">
          <div class="border-b border-slate-200 p-4">
            <h2 class="text-sm font-semibold text-app-tertiary">On the books by stay date</h2>
            <p class="mt-0.5 text-[11px] text-slate-500">
              STLY = same weekday last year, as of the same days before arrival. Click a date for its booking curve.
              <template v-if="usdBookings"> USD-priced bookings count in room nights but not in IDR revenue.</template>
            </p>
          </div>
          <div class="max-h-[65vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 z-10 bg-white shadow-[0_1px_0_rgb(226_232_240)]">
                <tr>
                  <th class="px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">Date</th>
                  <th class="px-3 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">OTB</th>
                  <th class="px-3 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">Revenue</th>
                  <th class="px-3 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">Pickup {{ loadedPickupDays }}d</th>
                  <th class="px-3 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">STLY</th>
                  <th class="px-3 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">vs STLY</th>
                  <th class="px-3 py-2.5 text-right text-[11px] font-bold uppercase tracking-wider text-slate-500">LY final</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="r in paceRows" :key="r.date"
                    :class="['cursor-pointer hover:bg-slate-50', curve?.date === r.date && 'bg-slate-100']"
                    @click="loadCurve(r.date)">
                  <td class="whitespace-nowrap px-3 py-2 font-semibold text-slate-700">{{ formatDay(r.date) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-900">{{ r.rooms }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-700">{{ millions(r.revenue) }}</td>
                  <td :class="['px-3 py-2 text-right tabular-nums', signClass(r.pickupRooms)]">{{ signed(r.pickupRooms) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ r.stlyRooms }}</td>
                  <td :class="['px-3 py-2 text-right tabular-nums font-semibold', signClass(r.rooms - r.stlyRooms)]">{{ signed(r.rooms - r.stlyRooms) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ r.lyFinalRooms ?? '–' }}</td>
                </tr>
              </tbody>
              <tfoot class="sticky bottom-0 bg-slate-50 font-semibold">
                <tr>
                  <td class="px-3 py-2 text-slate-700">Total</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ paceTotals.rooms }}</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ millions(paceTotals.revenue) }}</td>
                  <td :class="['px-3 py-2 text-right tabular-nums', signClass(paceTotals.pickup)]">{{ signed(paceTotals.pickup) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ paceTotals.stly }}</td>
                  <td :class="['px-3 py-2 text-right tabular-nums', signClass(paceTotals.rooms - paceTotals.stly)]">{{ signed(paceTotals.rooms - paceTotals.stly) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ paceTotals.lyFinal ?? '–' }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div class="neu-card p-4 xl:col-span-5">
          <h2 class="text-sm font-semibold text-app-tertiary">Booking curve</h2>
          <p v-if="!curve" class="mt-2 text-xs text-slate-500">Click a stay date to see how its bookings built up.</p>
          <template v-else>
            <p class="mt-0.5 text-[11px] text-slate-500">
              {{ formatDay(curve.date) }} vs {{ formatDay(curve.lyDate) }}. Rooms on the books by days before arrival.
            </p>
            <svg :viewBox="`0 0 ${CW} ${CH}`" class="mt-3 w-full" role="img" :aria-label="`Booking curve for ${curve.date}`">
              <g class="text-slate-200" stroke="currentColor">
                <line v-for="t in curveChart.yTicks" :key="t.v" :x1="PAD_L" :x2="CW - PAD_R" :y1="t.y" :y2="t.y" />
              </g>
              <g class="fill-slate-400 text-[10px]">
                <text v-for="t in curveChart.yTicks" :key="`y${t.v}`" :x="PAD_L - 6" :y="t.y + 3" text-anchor="end">{{ t.v }}</text>
                <text v-for="t in curveChart.xTicks" :key="`x${t.v}`" :x="t.x" :y="CH - 6" text-anchor="middle">{{ t.v }}</text>
              </g>
              <polyline :points="curveChart.ly" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="4 3" />
              <polyline :points="curveChart.cur" fill="none" stroke="#0f172a" stroke-width="2" />
            </svg>
            <div class="mt-2 flex gap-4 text-[11px] text-slate-600">
              <span class="flex items-center gap-1.5"><span class="h-0.5 w-4 bg-slate-900" /> This year</span>
              <span class="flex items-center gap-1.5"><span class="h-0.5 w-4 border-t-2 border-dashed border-slate-400" /> Last year</span>
            </div>
          </template>
        </div>
      </div>
      <p v-else-if="pc.loaded && !pc.error" class="neu-card p-4 text-xs text-slate-500">No bookings on the books for this range.</p>
    </div>

    <!-- ===== Booking data ===== -->
    <div v-show="activeTab === 'sync'" class="grid grid-cols-1 gap-4 xl:grid-cols-12">
      <div class="neu-card space-y-3 p-4 text-xs xl:col-span-5">
        <h2 class="text-sm font-semibold text-app-tertiary">Booking history cache</h2>
        <p class="text-slate-500">
          Pace reads bookings from a local copy of the PMS reservation log. Guest details are never stored.
          Once the backfill has run, the scheduler keeps it current: a 7-day pull daily after 04:00, and a deeper resync weekly
          (last 90 days of bookings plus every arrival in the next year, to catch cancellations).
        </p>
        <dl v-if="sync" class="grid grid-cols-2 gap-2">
          <div class="rounded-lg bg-slate-50 p-2">
            <dt class="text-[11px] text-slate-500">Bookings cached</dt>
            <dd class="text-lg font-semibold tabular-nums text-slate-900">{{ sync.bookings.toLocaleString() }}</dd>
          </div>
          <div class="rounded-lg bg-slate-50 p-2">
            <dt class="text-[11px] text-slate-500">Complete from</dt>
            <dd class="text-lg font-semibold text-slate-900">{{ sync.coverageFrom ? formatDay(sync.coverageFrom) : '–' }}</dd>
          </div>
          <div class="rounded-lg bg-slate-50 p-2">
            <dt class="text-[11px] text-slate-500">Last daily sync</dt>
            <dd class="font-semibold text-slate-900">{{ sync.lastDaily ? formatDay(sync.lastDaily) : '–' }}</dd>
          </div>
          <div class="rounded-lg bg-slate-50 p-2">
            <dt class="text-[11px] text-slate-500">Last weekly resync</dt>
            <dd class="font-semibold text-slate-900">{{ sync.lastWeekly ? formatDay(sync.lastWeekly) : '–' }}</dd>
          </div>
        </dl>

        <div v-if="sync?.job.running" class="space-y-1 rounded-lg bg-slate-50 p-3">
          <p class="font-semibold text-slate-700">
            {{ KIND_LABEL[sync.job.kind ?? ''] }} running - {{ sync.job.done }} / {{ sync.job.total }} windows, {{ sync.job.rows.toLocaleString() }} rows
          </p>
          <div class="h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div class="h-full bg-slate-900 transition-all" :style="{ width: `${(sync.job.done / Math.max(1, sync.job.total)) * 100}%` }" />
          </div>
        </div>
        <p v-else-if="sync?.job.error" class="rounded-lg bg-rose-50 px-3 py-2 font-semibold text-rose-700">
          Last {{ KIND_LABEL[sync.job.kind ?? ''] }} failed: {{ sync.job.error }}
        </p>

        <div class="flex flex-wrap items-end gap-2 border-t border-slate-200 pt-3">
          <label class="space-y-1">
            <span class="font-semibold text-slate-600">Backfill depth</span>
            <select v-model.number="backfillYears" class="neu-input py-1.5 text-xs">
              <option v-for="y in [1, 2, 3, 4, 5]" :key="y" :value="y">{{ y }} year{{ y > 1 ? 's' : '' }}</option>
            </select>
          </label>
          <button type="button" class="btn-primary px-3 py-1.5 text-xs" :disabled="sync?.job.running" @click="runSync('backfill')">Run backfill</button>
          <button type="button" class="btn-flat px-3 py-1.5 text-xs" :disabled="sync?.job.running" @click="runSync('daily')">Sync last 7 days</button>
          <button type="button" class="btn-flat px-3 py-1.5 text-xs" :disabled="sync?.job.running" @click="runSync('weekly')">Full resync</button>
        </div>
        <p class="text-[11px] text-slate-500">A 3-year backfill takes about 4 minutes. Same-time-last-year needs at least 2 years.</p>
      </div>

      <div class="neu-card overflow-hidden xl:col-span-7">
        <h2 class="border-b border-slate-200 p-4 text-sm font-semibold text-app-tertiary">Recent syncs</h2>
        <p v-if="!sync?.runs.length" class="p-4 text-xs text-slate-500">No syncs yet.</p>
        <table v-else class="min-w-full text-xs">
          <thead>
            <tr>
              <th v-for="h in ['Started', 'Kind', 'Rows', 'Result']" :key="h"
                  class="px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">{{ h }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="run in sync.runs" :key="run.id">
              <td class="whitespace-nowrap px-3 py-2 text-slate-700">{{ formatDateTime(run.started_at) }}</td>
              <td class="px-3 py-2 text-slate-700">{{ KIND_LABEL[run.kind] }}</td>
              <td class="px-3 py-2 tabular-nums text-slate-700">{{ run.rows.toLocaleString() }}</td>
              <td class="px-3 py-2">
                <span v-if="!run.finished_at" class="font-semibold text-slate-500">Running</span>
                <span v-else-if="run.error" class="font-semibold text-rose-700" :title="run.error">Failed</span>
                <span v-else class="font-semibold text-emerald-700">OK</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import { todayLocalDateString } from '../utils/date'
import { alertDialog } from '../composables/useDialog'
import { ArrowPathIcon, PresentationChartLineIcon, ArrowTrendingUpIcon, CircleStackIcon } from '@heroicons/vue/24/outline'

interface HotelRow { date: string; roomsSold: number; roomCount: number; occupancy: number; revenue: number; adr: number; complimentary: number; houseUse: number; lastYear: number }
interface SegmentRow { date: string; marketId: number; market: string; rooms: number; revenue: number }
interface RoomTypeRow { date: string; typeId: string; rooms: number; roomCount: number }
interface Forecast { start: string; end: string; hotel: HotelRow[]; segments: SegmentRow[]; roomTypes: RoomTypeRow[] }
interface PaceRow {
  date: string; lyDate: string; rooms: number; revenue: number; revenueUsd: number
  pickupRooms: number; pickupRevenue: number; stlyRooms: number; stlyRevenue: number
  lyFinalRooms: number | null; lyFinalRevenue: number | null
}
interface CurvePoint { lead: number; rooms: number }
interface Curve { date: string; lyDate: string; current: CurvePoint[]; lastYear: CurvePoint[] }
interface SyncRun { id: number; kind: string; started_at: string; finished_at: string | null; rows: number; error: string | null }
interface SyncStatus {
  job: { running: boolean; kind: string | null; done: number; total: number; rows: number; error: string | null }
  bookings: number; coverageFrom: string | null; lastDaily: string | null; lastWeekly: string | null; runs: SyncRun[]
}

type TabId = 'forecast' | 'pace' | 'sync'
const TABS: { id: TabId; name: string; icon: Component }[] = [
  { id: 'forecast', name: 'Forecast', icon: PresentationChartLineIcon },
  { id: 'pace', name: 'Pace', icon: ArrowTrendingUpIcon },
  { id: 'sync', name: 'Booking data', icon: CircleStackIcon },
]
const KIND_LABEL: Record<string, string> = { backfill: 'Backfill', daily: 'Daily sync', weekly: 'Full resync' }

const route = useRoute()
const router = useRouter()
const activeTab = ref<TabId>(TABS.some(t => t.id === route.query.tab) ? route.query.tab as TabId : 'forecast')
function selectTab(id: TabId) {
  activeTab.value = id
  router.replace({ query: { ...route.query, tab: id === 'forecast' ? undefined : id } })
}

function errorMessage(err: any, fallback: string) {
  return err?.response?.data?.message || err?.message || fallback
}

// ---------------------------------------------------------------- formatting
function addDays(iso: string, n: number) {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const formatDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const shortDay = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
const formatDateTime = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const millions = (v: number | null | undefined) => (v == null ? '–' : `${(v / 1e6).toLocaleString(undefined, { maximumFractionDigits: 1 })} M`)
const thousands = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v / 1e3).toLocaleString()} K`)
const signed = (v: number) => (v > 0 ? `+${v}` : `${v}`)
const signClass = (v: number) => (v > 0 ? 'text-emerald-700' : v < 0 ? 'text-rose-700' : 'text-slate-500')
const occClass = (occ: number) =>
  occ >= 90 ? 'bg-rose-50 text-rose-700' : occ >= 75 ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-700'
function cellClass(rooms: number | undefined, capacity: number) {
  if (rooms == null || !capacity) return 'text-slate-400'
  const ratio = rooms / capacity
  return ratio >= 1 ? 'bg-rose-50 font-semibold text-rose-700' : ratio >= 0.85 ? 'bg-amber-50 text-amber-800' : 'text-slate-600'
}

const roomLabels = ref<Record<string, string>>({})
const roomLabel = (code: string) => roomLabels.value[code] || code
const dims = reactive<{ roomTypes: string[]; markets: { id: number; name: string }[] }>({ roomTypes: [], markets: [] })

async function loadDimensions() {
  try {
    const res = await axios.get('/api/rms/room-types')
    roomLabels.value = res.data.labels
    dims.roomTypes = res.data.roomTypes
    dims.markets = res.data.markets
  } catch {
    // Filters just stay at "All"; the tables report their own errors.
  }
}

// ------------------------------------------------------------------ forecast
const fc = reactive({ start: todayLocalDateString(), days: 14, loading: false, error: '' })
const forecast = ref<Forecast | null>(null)

async function loadForecast() {
  fc.loading = true
  fc.error = ''
  try {
    const res = await axios.get('/api/rms/forecast', { params: { start: fc.start, days: fc.days }, timeout: 120000 })
    forecast.value = res.data
  } catch (err) {
    fc.error = errorMessage(err, 'Could not load the forecast from the PMS')
  } finally {
    fc.loading = false
  }
}

const forecastTiles = computed(() => {
  const rows = forecast.value?.hotel ?? []
  const sold = rows.reduce((s, r) => s + (r.roomsSold || 0), 0)
  const capacity = rows.reduce((s, r) => s + (r.roomCount || 0), 0)
  const revenue = rows.reduce((s, r) => s + (r.revenue || 0), 0)
  return [
    { label: 'Avg occupancy', value: capacity ? `${((sold / capacity) * 100).toFixed(1)}%` : '–' },
    { label: 'Room nights', value: sold.toLocaleString() },
    { label: 'Room revenue', value: millions(revenue) },
    { label: 'ADR', value: sold ? thousands(revenue / sold) : '–' },
  ]
})

const segmentTotals = computed(() => {
  const totals = new Map<string, { market: string; rooms: number; revenue: number }>()
  for (const s of forecast.value?.segments ?? []) {
    const t = totals.get(s.market) ?? { market: s.market, rooms: 0, revenue: 0 }
    t.rooms += s.rooms || 0
    t.revenue += s.revenue || 0
    totals.set(s.market, t)
  }
  const all = [...totals.values()].filter(t => t.rooms || t.revenue)
  const sum = all.reduce((s, t) => s + t.rooms, 0)
  return all.map(t => ({ ...t, share: sum ? (t.rooms / sum) * 100 : 0 })).sort((a, b) => b.rooms - a.rooms)
})

const roomMatrix = computed(() => {
  const rows = forecast.value?.roomTypes ?? []
  const dates = [...new Set(rows.map(r => r.date))].sort()
  const types = new Map<string, { typeId: string; roomCount: number; cells: Record<string, number> }>()
  for (const r of rows) {
    const t = types.get(r.typeId) ?? { typeId: r.typeId, roomCount: r.roomCount, cells: {} }
    t.cells[r.date] = r.rooms
    types.set(r.typeId, t)
  }
  return { dates, types: [...types.values()].sort((a, b) => b.roomCount - a.roomCount) }
})

// ---------------------------------------------------------------------- pace
const pc = reactive({
  start: todayLocalDateString(), end: addDays(todayLocalDateString(), 29),
  roomType: '', marketId: '', pickupDays: 7, loading: false, loaded: false, error: '',
})
const paceRows = ref<PaceRow[]>([])
const loadedPickupDays = ref(7)
const curve = ref<Curve | null>(null)

async function loadPace() {
  pc.loading = true
  pc.error = ''
  try {
    const res = await axios.get('/api/rms/pace', {
      params: { start: pc.start, end: pc.end, roomType: pc.roomType || undefined, marketId: pc.marketId || undefined, pickupDays: pc.pickupDays },
    })
    paceRows.value = res.data.rows
    loadedPickupDays.value = pc.pickupDays
    sync.value = res.data.sync
    if (curve.value) loadCurve(curve.value.date)
  } catch (err) {
    pc.error = errorMessage(err, 'Could not load pace')
  } finally {
    pc.loading = false
    pc.loaded = true
  }
}

async function loadCurve(date: string) {
  try {
    const res = await axios.get('/api/rms/pace/curve', {
      params: { date, maxLead: 120, roomType: pc.roomType || undefined, marketId: pc.marketId || undefined },
    })
    curve.value = res.data
  } catch (err) {
    pc.error = errorMessage(err, 'Could not load the booking curve')
  }
}

const usdBookings = computed(() => paceRows.value.some(r => r.revenueUsd))
const paceTotals = computed(() => {
  const rows = paceRows.value
  const sum = (f: (r: PaceRow) => number) => rows.reduce((s, r) => s + f(r), 0)
  const finals = rows.filter(r => r.lyFinalRooms != null)
  return {
    rooms: sum(r => r.rooms), revenue: sum(r => r.revenue), pickup: sum(r => r.pickupRooms), stly: sum(r => r.stlyRooms),
    lyFinal: finals.length === rows.length ? sum(r => r.lyFinalRooms ?? 0) : null,
  }
})

const CW = 480, CH = 240, PAD_L = 36, PAD_R = 8, PAD_T = 8, PAD_B = 22
const curveChart = computed(() => {
  const c = curve.value
  if (!c) return { cur: '', ly: '', yTicks: [], xTicks: [] }
  const maxLead = Math.max(...c.current.map(p => p.lead))
  const maxRooms = Math.max(1, ...c.current.map(p => p.rooms), ...c.lastYear.map(p => p.rooms))
  const step = Math.max(1, Math.ceil(maxRooms / 4 / 10) * 10)
  const top = Math.ceil(maxRooms / step) * step
  const x = (lead: number) => PAD_L + ((maxLead - lead) / maxLead) * (CW - PAD_L - PAD_R)
  const y = (v: number) => PAD_T + (1 - v / top) * (CH - PAD_T - PAD_B)
  const line = (pts: CurvePoint[]) => pts.map(p => `${x(p.lead).toFixed(1)},${y(p.rooms).toFixed(1)}`).join(' ')
  const yTicks = Array.from({ length: Math.floor(top / step) + 1 }, (_, i) => ({ v: i * step, y: y(i * step) }))
  const xTicks = [maxLead, 90, 60, 30, 14, 0].filter(l => l <= maxLead).map(l => ({ v: l, x: x(l) }))
  return { cur: line(c.current), ly: line(c.lastYear), yTicks, xTicks }
})

// ---------------------------------------------------------------------- sync
const sync = ref<SyncStatus | null>(null)
const backfillYears = ref(3)
let syncTimer: ReturnType<typeof setTimeout> | undefined

async function loadSync() {
  clearTimeout(syncTimer)
  try {
    const res = await axios.get('/api/rms/sync')
    const wasRunning = sync.value?.job.running
    sync.value = res.data
    if (wasRunning && !res.data.job.running) loadDimensions()
  } catch {
    // Keep the last status; it's re-polled below.
  }
  syncTimer = setTimeout(loadSync, sync.value?.job.running ? 2000 : 30000)
}

async function runSync(kind: 'backfill' | 'daily' | 'weekly') {
  try {
    const res = await axios.post('/api/rms/sync', { kind, backfillDays: backfillYears.value * 365 })
    sync.value = res.data
  } catch (err) {
    alertDialog({ title: 'Sync not started', message: errorMessage(err, 'Could not start the sync'), tone: 'danger' })
  }
  loadSync()
}

onMounted(() => {
  loadDimensions()
  loadSync()
  loadPace()
})
onBeforeUnmount(() => clearTimeout(syncTimer))
</script>
