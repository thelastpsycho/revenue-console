<template>
  <div class="flex h-[calc(100dvh-4rem)] flex-col p-4 sm:p-6 lg:h-screen lg:p-8">
    <div class="flex h-full w-full flex-col overflow-hidden rounded-xl bg-app-primary shadow-neu">
      <!-- Loading state -->
      <div v-if="loading" class="flex flex-1 flex-col items-center justify-center">
        <div class="h-10 w-10 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent"></div>
        <p class="mt-4 text-sm font-semibold text-slate-500">Loading data…</p>
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="p-6">
        <div class="rounded-xl bg-app-primary p-4 text-rose-700 shadow-neu-inset-sm" role="alert">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <svg class="h-5 w-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
              </svg>
            </div>
            <div class="ml-3">
              <p class="font-medium">{{ error }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Data Content -->
      <template v-else>
        <!-- Compact Header & Tabs -->
        <div class="flex-shrink-0 border-b border-slate-200 p-4 sm:px-6">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 class="font-semibold text-lg text-app-tertiary">Data overview</h1>
              <p class="text-sm text-slate-500">Explore your scraped and processed inventory data.</p>
            </div>
            <div class="flex space-x-1.5 rounded-xl bg-app-primary p-1.5 shadow-neu-inset-sm">
              <button
                v-for="tab in tabs"
                :key="tab.id"
                @click="activeTab = tab.id"
                :class="[
                  activeTab === tab.id
                    ? 'bg-app-primary text-app-accent shadow-neu-sm'
                    : 'text-slate-500 hover:text-app-tertiary',
                  'flex items-center whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200 cursor-pointer'
                ]"
              >
                <component :is="tab.icon" class="mr-1.5 h-4 w-4" />
                <span>{{ tab.name }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Tab content -->
        <div class="flex flex-1 flex-col overflow-hidden p-4 sm:p-6">
          <div v-for="tab in tabs" :key="`${tab.id}-content`" class="h-full">
            <div v-if="activeTab === tab.id" class="flex h-full flex-col">
              <div class="mb-4 flex flex-shrink-0 flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 class="font-semibold text-base text-app-tertiary">{{ tab.name }}</h3>
                  <p class="text-sm text-slate-500">{{ tab.description }}</p>
                  <p class="mt-1 text-xs text-slate-400">Updated on {{ formatUpdatedAt(tabUpdatedAt[tab.id]) }}</p>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold text-slate-500">Export</span>
                  <button @click="exportData(tab.id, 'csv')" class="btn-icon" title="Export CSV">
                    <DocumentArrowDownIcon class="h-5 w-5" />
                  </button>
                  <button @click="exportData(tab.id, 'excel')" class="btn-icon" title="Export Excel">
                    <TableCellsIcon class="h-5 w-5" />
                  </button>
                  <button @click="exportData(tab.id, 'json')" class="btn-icon" title="Export JSON">
                    <CodeBracketIcon class="h-5 w-5" />
                  </button>
                </div>
              </div>

              <div v-if="getDataForTab(tab.id).length === 0" class="flex flex-1 flex-col items-center justify-center text-center text-slate-500">
                <span class="flex h-16 w-16 items-center justify-center rounded-xl bg-app-primary text-slate-400 shadow-neu-inset">
                  <CircleStackIcon class="h-8 w-8" />
                </span>
                <p class="mt-4 text-sm font-semibold text-slate-600">No data available for this view.</p>
                <p class="text-sm">Please ensure the required data processing steps have been completed.</p>
              </div>

              <div v-else class="flex-1 overflow-auto rounded-xl bg-app-primary p-1 shadow-neu-inset">
                <table class="min-w-full divide-y divide-slate-200" :class="tab.id === 'allocation' || tab.id === 'combined' ? 'text-xs' : 'text-sm'">
                  <thead class="bg-app-primary sticky top-0 z-10">
                    <tr>
                      <th
                        v-for="header in getHeadersForTab(tab.id)"
                        :key="header"
                        scope="col"
                        class="py-3.5 px-4 text-left font-bold uppercase tracking-wider text-[11px] text-slate-500 cursor-pointer hover:text-app-accent group"
                        :class="getStickyClass(tab.id, header, true) || getRoomColorClass(tab.id, header, true)"
                        :style="getStickyStyle(tab.id, header)"
                        @click="sortTab(tab.id, header)"
                      >
                        <div class="flex items-center space-x-2">
                          <span>{{ header.replace(/_/g, ' ') }}</span>
                          <span v-if="sortColumn === header" class="text-app-accent">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-200">
                    <tr v-for="(row, index) in getDataForTab(tab.id)" :key="index" class="group hover:bg-app-secondary/50 transition-colors">
                      <td
                        v-for="header in getHeadersForTab(tab.id)"
                        :key="header"
                        class="whitespace-nowrap px-4 py-3 font-mono transition"
                        :class="[getCellClass(row[header]), getStickyClass(tab.id, header, false) || getRoomColorClass(tab.id, header, false), getOnlineInventoryClass(tab.id, header, row[header])]"
                        :style="getStickyStyle(tab.id, header)"
                      >
                        {{ getDisplayValue(tab.id, row, header) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from '../plugins/axios'
import * as XLSX from 'xlsx'
import {
  TableCellsIcon,
  AdjustmentsHorizontalIcon,
  ArrowsRightLeftIcon,
  CalculatorIcon,
  DocumentArrowDownIcon,
  CodeBracketIcon,
  CircleStackIcon,
  CloudArrowDownIcon,
} from '@heroicons/vue/24/outline'

// Data refs
const pmsRawData = ref<any[]>([])
const pmsProcessedData = ref<any[]>([])
const combinedData = ref<any[]>([])
const allocationData = ref<any[]>([])
const cmRawData = ref<any[]>([])

// Headers refs
const pmsRawHeaders = ref<string[]>([])
const pmsProcessedHeaders = ref<string[]>([])
const combinedHeaders = ref<string[]>([])
const allocationHeaders = ref<string[]>([])
const cmRawHeaders = ref<string[]>([])

// Last-modified timestamp (ISO string) per tab, as returned by each /api/db/* endpoint
const tabUpdatedAt = ref<Record<string, string | null>>({})

// Loading and error states
const loading = ref(true)
const error = ref('')

// Tab management
const tabs = [
  { id: 'pms-raw', name: 'PMS Raw', icon: TableCellsIcon, description: 'Raw inventory data from the PMS system.' },
  { id: 'pms-processed', name: 'PMS Processed', icon: AdjustmentsHorizontalIcon, description: 'Processed and cleaned inventory data from the PMS system.' },
  { id: 'cm-raw', name: 'CM Raw', icon: CloudArrowDownIcon, description: 'Raw Channel Manager export data, as scraped from D-EDGE or manually uploaded.' },
  { id: 'combined', name: 'Combined', icon: ArrowsRightLeftIcon, description: 'Combined inventory from all available sources.' },
  { id: 'allocation', name: 'Allocation', icon: CalculatorIcon, description: 'Calculated daily inventory allocation and BAR rates.' }
]
const activeTab = ref('pms-raw')

// Sorting refs
const sortColumn = ref('')
const sortDirection = ref<'asc' | 'desc'>('asc')


// Shared full-name -> short-code abbreviations for room types (Combined + Allocation tabs).
// The Allocation table's columns are built from yielder.py's output, which renames
// 'Deluxe Room'/'Premiere Room' down to just 'Deluxe'/'Premiere' - both spellings are
// mapped here so this table works against either source.
const roomTypeAbbreviations: Record<string, string> = {
  'Deluxe Room': 'DLX',
  'Deluxe': 'DLX',
  'Premiere Room': 'PRE',
  'Premiere': 'PRE',
  'Deluxe Pool Access': 'DLP',
  'Premiere Room Lagoon Access': 'PKL',
  'Family Premiere Room': 'FPK',
  'Deluxe Suite Room': 'DLS',
  'Premiere Suite Room': 'PRS',
  'The Anvaya Suite No Pool': 'AVS',
  'The Anvaya Suite Whirpool': 'ASW',
  'Beach Front Private Suite Room': 'BFS',
  'The Anvaya Suite With Pool': 'ASP',
  'The Anvaya Residence': 'AVR',
  'The Anvaya Villa': 'AVP',
}

// Display order for room-type column groups (Allocation tab)
const roomTypeOrder = ['DLX', 'PRE', 'DLP', 'PKL', 'FPK', 'DLS', 'PRS', 'AVS', 'ASW', 'BFS', 'ASP', 'AVR', 'AVP']

// One distinct pastel color per room-type abbreviation, applied to its header + cells
const roomTypeColors: Record<string, { header: string; cell: string }> = {
  DLX: { header: 'bg-blue-200/60 text-blue-700', cell: 'bg-blue-100/40' },
  PRE: { header: 'bg-purple-200/60 text-purple-700', cell: 'bg-purple-100/40' },
  DLP: { header: 'bg-cyan-200/60 text-cyan-700', cell: 'bg-cyan-100/40' },
  PKL: { header: 'bg-teal-200/60 text-teal-700', cell: 'bg-teal-100/40' },
  FPK: { header: 'bg-pink-200/60 text-pink-700', cell: 'bg-pink-100/40' },
  DLS: { header: 'bg-indigo-200/60 text-indigo-700', cell: 'bg-indigo-100/40' },
  PRS: { header: 'bg-violet-200/60 text-violet-700', cell: 'bg-violet-100/40' },
  AVS: { header: 'bg-amber-200/60 text-amber-700', cell: 'bg-amber-100/40' },
  ASW: { header: 'bg-sky-200/60 text-sky-700', cell: 'bg-sky-100/40' },
  BFS: { header: 'bg-emerald-200/60 text-emerald-700', cell: 'bg-emerald-100/40' },
  ASP: { header: 'bg-lime-200/60 text-lime-700', cell: 'bg-lime-100/40' },
  AVR: { header: 'bg-rose-200/60 text-rose-700', cell: 'bg-rose-100/40' },
  AVP: { header: 'bg-orange-200/60 text-orange-700', cell: 'bg-orange-100/40' },
  'DLX+Pre': { header: 'bg-slate-300/70 text-slate-700', cell: 'bg-slate-200/50' },
}

// On the Allocation tab, Date and Season/Demand are pinned to the left (in this order) so
// they stay visible while scrolling horizontally. Fixed pixel widths are required so the
// second sticky column's offset lines up exactly with the first column's rendered width.
const STICKY_COLUMN_WIDTHS: Record<string, number> = {
  'Date': 170,
  'Season/Demand': 150,
}
const STICKY_COLUMN_ORDER = Object.keys(STICKY_COLUMN_WIDTHS)

const getStickyOffset = (header: string) => {
  const index = STICKY_COLUMN_ORDER.indexOf(header)
  if (index <= 0) return 0
  return STICKY_COLUMN_ORDER.slice(0, index).reduce((sum, h) => sum + STICKY_COLUMN_WIDTHS[h], 0)
}

const getStickyStyle = (tabId: string, header: string) => {
  if (tabId !== 'allocation' || !(header in STICKY_COLUMN_WIDTHS)) return {}
  const width = `${STICKY_COLUMN_WIDTHS[header]}px`
  return { left: `${getStickyOffset(header)}px`, width, minWidth: width, maxWidth: width }
}

const getStickyClass = (tabId: string, header: string, isHeader: boolean) => {
  if (tabId !== 'allocation' || !(header in STICKY_COLUMN_WIDTHS)) return ''
  const bg = 'bg-app-primary'
  const z = isHeader ? 'z-20' : 'z-10'
  return `sticky ${z} ${bg} overflow-hidden text-ellipsis`
}

// Merges Date + occupancy into one cell, e.g. "08Aug / 98.37%" (day+month, no year, plus
// occupancy). Used by both the Allocation and Combined tabs. On the Combined tab, also
// appends the total remaining inventory (sum of every room type's own remaining count) so
// that stays compacted into the same cell instead of needing its own column.
const getDateWithOccupancyDisplay = (tabId: string, row: Record<string, any>) => {
  const d = new Date(row['Date'])
  let dateLabel = row['Date']
  if (!isNaN(d.getTime())) {
    const day = d.getDate().toString().padStart(2, '0')
    const month = d.toLocaleString('en-US', { month: 'short' })
    dateLabel = `${day}${month}`
  }
  const occ = row['Occ%']
  let display = occ === undefined || occ === null ? dateLabel : `${dateLabel} / ${occ}%`
  if (tabId === 'combined') {
    const remaining = roomTypeOrder.reduce((sum, code) => sum + (Number(row[code]) || 0), 0)
    display += ` / ${remaining}`
  }
  return display
}

// Renders a cell's display value, handling the Allocation tab's virtual merged columns
// (Date+Occupancy, Season+Demand) before falling back to the generic formatValue
const getDisplayValue = (tabId: string, row: Record<string, any>, header: string) => {
  if ((tabId === 'allocation' || tabId === 'combined') && header === 'Date') {
    return getDateWithOccupancyDisplay(tabId, row)
  }
  if (tabId === 'allocation' && header === 'Season/Demand') {
    return `${row['Season'] ?? '-'}/${row['Demand'] ?? '-'}`
  }
  return formatValue(row[header], header)
}

// On the Allocation and Combined tabs, looks up a header's room-type abbreviation (its
// first word, e.g. "DLX" from "DLX Rem", or just "DLX" on Combined) and returns the
// matching background color class. Scoped to these two tabs only - the PMS Raw/Processed
// tabs' raw column names (e.g. "ASP"/"AVR"/"BFS") can coincidentally collide with these
// abbreviations without actually being related.
const getRoomColorClass = (tabId: string, header: string, isHeader: boolean) => {
  if (tabId !== 'allocation' && tabId !== 'combined') return ''
  const abbrev = header.split(' ')[0]
  const colors = roomTypeColors[abbrev]
  if (!colors) return ''
  return isHeader ? colors.header : colors.cell
}

// On the Allocation tab, flag any Online Inventory cell (columns renamed with the
// ' On' suffix, e.g. "DLX On") that has dropped below 1 with a red highlight.
// Uses ! utilities so it overrides the room-type tint and generic cell text color.
const getOnlineInventoryClass = (tabId: string, header: string, value: any) => {
  if (tabId !== 'allocation' || !header.endsWith(' On')) return ''
  const num = Number(value)
  if (isNaN(num) || num >= 1) return ''
  return '!bg-red-100 !text-red-700 !font-semibold'
}

// Data Accessors
const getDataForTab = (tabId: string) => {
  switch (tabId) {
    case 'pms-raw': return pmsRawData.value;
    case 'pms-processed': return pmsProcessedData.value;
    case 'cm-raw': return cmRawData.value;
    case 'combined': return combinedData.value;
    case 'allocation': return allocationData.value;
    default: return [];
  }
}

const getHeadersForTab = (tabId: string) => {
  switch (tabId) {
    case 'pms-raw': return pmsRawHeaders.value;
    case 'pms-processed': return pmsProcessedHeaders.value;
    case 'cm-raw': return cmRawHeaders.value;
    case 'combined': return combinedHeaders.value;
    case 'allocation': return allocationHeaders.value;
    default: return [];
  }
}

// Formats an ISO timestamp (from each /api/db/* endpoint's updated_at) for display;
// falls back to a placeholder when the source data hasn't been generated yet.
const formatUpdatedAt = (iso: string | null | undefined) => {
  if (!iso) return 'unknown'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return 'unknown'
  return d.toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

// Formatting functions
const formatValue = (value: any, key: string) => {
  if (value === null || value === undefined) return '-'
  if (key && key.toLowerCase().includes('date')) {
    const d = new Date(value)
    if (isNaN(d.getTime())) return value
    const day = d.getDate().toString().padStart(2, '0')
    const month = d.toLocaleString('en-US', { month: 'short' })
    const year = d.getFullYear().toString().slice(-2)
    return `${day}-${month}-${year}`
  }
  return value
}

const getCellClass = (value: any) => {
  const num = Number(value)
  if (isNaN(num)) return 'text-slate-600'

  if (num < 0) return 'text-rose-600 font-bold'
  if (num === 0) return 'text-orange-600 font-semibold'
  if (num >= 1 && num <= 5) return 'text-amber-600 font-semibold'

  return 'text-slate-700'
}

// Sorting logic
const sortTab = (tabId: string, column: string) => {
  if (sortColumn.value === column) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column
    sortDirection.value = 'asc'
  }

  const sortable = getDataForTab(tabId);
  sortable.sort((a, b) => {
    let valA = a[column];
    let valB = b[column];

    if (column.toLowerCase().includes('date')) {
      valA = new Date(valA).getTime();
      valB = new Date(valB).getTime();
    }

    const numA = Number(valA);
    const numB = Number(valB);
    if (!isNaN(numA) && !isNaN(numB)) {
      valA = numA;
      valB = numB;
    }

    if (valA < valB) return sortDirection.value === 'asc' ? -1 : 1;
    if (valA > valB) return sortDirection.value === 'asc' ? 1 : -1;
    return 0;
  });
}

// Fetch data from APIs
const fetchData = async () => {
  loading.value = true
  error.value = ''
  try {
    const responses = await Promise.allSettled([
      axios.get('/api/db/pms-inventory-raw'),
      axios.get('/api/db/pms-inventory-processed'),
      axios.get('/api/db/combined-inventory'),
      axios.get('/api/db/inventory-allocation'),
      axios.get('/api/db/cm-inventory-raw')
    ]);

    const tabIdsByResponseIndex = ['pms-raw', 'pms-processed', 'combined', 'allocation', 'cm-raw'];
    responses.forEach((res, i) => {
      if (res.status === 'fulfilled' && res.value.data.status === 'success') {
        tabUpdatedAt.value[tabIdsByResponseIndex[i]] = res.value.data.updated_at ?? null;
      }
    });

    if (responses[0].status === 'fulfilled' && responses[0].value.data.status === 'success') {
      pmsRawData.value = responses[0].value.data.data;
      if (pmsRawData.value.length > 0) pmsRawHeaders.value = Object.keys(pmsRawData.value[0]);
    }

    if (responses[1].status === 'fulfilled' && responses[1].value.data.status === 'success') {
      pmsProcessedData.value = responses[1].value.data.data;
      if (pmsProcessedData.value.length > 0) pmsProcessedHeaders.value = Object.keys(pmsProcessedData.value[0]);
    }

    if (responses[4].status === 'fulfilled' && responses[4].value.data.status === 'success') {
      cmRawData.value = responses[4].value.data.data;
      if (cmRawData.value.length > 0) cmRawHeaders.value = Object.keys(cmRawData.value[0]);
    }

    if (responses[2].status === 'fulfilled' && responses[2].value.data.status === 'success') {
      const rawData = responses[2].value.data.data;
      const roomMappings: Record<string, string> = {
        'Occupancy': 'Occ%', 'occupancy': 'Occ%', 'OCCUPANCY': 'Occ%',
        'The Anvaya Villa': 'AVP', 'The Anvaya Suite Whirpool': 'ASW',
        'The Anvaya Suite With Pool': 'ASP', 'The Anvaya Suite No Pool': 'AVS',
        'The Anvaya Residence': 'AVR', 'Beach Front Private Suite Room': 'BFS',
        'Deluxe Room': 'DLX', 'Deluxe Pool Access': 'DLP', 'Deluxe Suite Room': 'DLS',
        'Premiere Room': 'PRE', 'Premiere Room Lagoon Access': 'PKL',
        'Premiere Suite Room': 'PRS', 'Family Premiere Room': 'FPK'
      };

      const processedData = rawData.map((row: Record<string, any>) => {
        const newRow: Record<string, any> = {};
        for (const key in row) {
          const newKey = roomMappings[key] || key;
          newRow[newKey] = row[key];
        }
        if (newRow['DLX'] !== undefined && newRow['PRE'] !== undefined) {
          newRow['DLX+Pre'] = (Number(newRow['DLX']) || 0) + (Number(newRow['PRE']) || 0);
        }
        return newRow;
      });
      
      combinedData.value = processedData;

      if (processedData.length > 0) {
        // 'Occ%' is intentionally omitted - it's merged into the Date column (see
        // getDateWithOccupancyDisplay). The value still lives in each row for that display.
        const columnOrder = [
          'Date', 'DLX', 'PRE', 'DLX+Pre', 'DLP', 'PKL', 'FPK',
          'DLS', 'PRS', 'AVS', 'ASW', 'BFS', 'ASP', 'AVR', 'AVP'
        ];
        const firstRowKeys = Object.keys(processedData[0]);
        combinedHeaders.value = columnOrder.filter(header => firstRowKeys.includes(header));
      } else {
        combinedHeaders.value = [];
      }
    }

    if (responses[3].status === 'fulfilled' && responses[3].value.data.status === 'success') {
      const rawData = responses[3].value.data.data;

      const baseColumnRenames: Record<string, string> = {
        'Occupancy': 'Occ%',
        'DemandLevel': 'Demand',
      };
      const suffixRenames: [string, string][] = [
        [' Remaining Inventory', ' Rem'],
        [' Online Inventory', ' On'],
        [' BAR Rate', ' BAR'],
      ];

      const renameAllocationColumn = (key: string): string => {
        if (baseColumnRenames[key]) return baseColumnRenames[key];
        for (const [fullSuffix, shortSuffix] of suffixRenames) {
          if (key.endsWith(fullSuffix)) {
            const roomTypeName = key.slice(0, -fullSuffix.length);
            const abbrev = roomTypeAbbreviations[roomTypeName];
            if (abbrev) return `${abbrev}${shortSuffix}`;
          }
        }
        return key;
      };

      const processedData = rawData.map((row: Record<string, any>) => {
        const newRow: Record<string, any> = {};
        for (const key in row) {
          if (key === 'DayOfWeek') continue; // redundant with Date, drop from display
          newRow[renameAllocationColumn(key)] = row[key];
        }
        return newRow;
      });

      allocationData.value = processedData;

      if (processedData.length > 0) {
        // 'Season/Demand' and Date's occupancy suffix are virtual, computed columns (see
        // getDisplayValue) - Season/Demand isn't a literal row key, so it needs its own
        // availability check rather than the plain firstRowKeys.includes(header) below.
        const columnOrder = [
          'Date', 'Season/Demand',
          ...roomTypeOrder.flatMap(code => [`${code} Rem`, `${code} On`, `${code} BAR`])
        ];
        const firstRowKeys = Object.keys(processedData[0]);
        const isColumnAvailable = (header: string) => {
          if (header === 'Season/Demand') return firstRowKeys.includes('Season') && firstRowKeys.includes('Demand');
          return firstRowKeys.includes(header);
        };
        allocationHeaders.value = columnOrder.filter(isColumnAvailable);
      } else {
        allocationHeaders.value = [];
      }
    }

  } catch (err: any) {
    console.error('Error fetching data:', err)
    error.value = 'Failed to fetch data. Please make sure the backend server is running.'
  } finally {
    loading.value = false
  }
}

// Export functionality
const formatExportTimestamp = () => {
  const now = new Date()
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

const exportData = async (type: string, format: 'csv' | 'excel' | 'json') => {
  let data: any[] = getDataForTab(type);
  const filename = `${type.replace(/-/g, '_')}_${formatExportTimestamp()}`;

  if (data.length === 0) {
    alert('No data available to export');
    return;
  }

  try {
    switch (format) {
      case 'csv':
        const csvHeaders = Object.keys(data[0]).join(',');
        const csvContent = data.map(row => Object.values(row).map(value => typeof value === 'string' ? `"${value}"` : value).join(',')).join('\n');
        const csv = `${csvHeaders}\n${csvContent}`;
        const csvBlob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const csvUrl = URL.createObjectURL(csvBlob);
        const csvLink = document.createElement('a');
        csvLink.href = csvUrl;
        csvLink.download = `${filename}.csv`;
        csvLink.click();
        URL.revokeObjectURL(csvUrl);
        break;

      case 'excel':
        const worksheet = XLSX.utils.json_to_sheet(data);
        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, worksheet, 'Data');
        XLSX.writeFile(workbook, `${filename}.xlsx`);
        break;

      case 'json':
        const jsonContent = JSON.stringify(data, null, 2);
        const jsonBlob = new Blob([jsonContent], { type: 'application/json' });
        const jsonUrl = URL.createObjectURL(jsonBlob);
        const jsonLink = document.createElement('a');
        jsonLink.href = jsonUrl;
        jsonLink.download = `${filename}.json`;
        jsonLink.click();
        URL.revokeObjectURL(jsonUrl);
        break;
    }
  } catch (error) {
    console.error('Error exporting data:', error);
    alert('Error exporting data. Please try again.');
  }
}

onMounted(() => {
  fetchData();
});
</script>