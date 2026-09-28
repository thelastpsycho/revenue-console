<template>
  <div class="flex h-[calc(100dvh-4rem)] flex-col p-4 sm:p-6 lg:h-screen lg:p-8">
    <div class="flex h-full w-full flex-col overflow-hidden rounded-xl bg-app-primary shadow-neu">
      <!-- Header & Controls -->
      <div class="flex-shrink-0 border-b border-slate-200 p-4 sm:px-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 class="font-semibold text-lg text-app-tertiary">Yield management</h1>
            <p class="text-sm text-slate-500">Run the demand matrix and tune allocation strategies.</p>
          </div>
          <div class="flex flex-shrink-0 items-center gap-2">
            <button
              @click="calculateYield"
              :disabled="isLoading"
              class="btn-primary px-4 py-2.5"
            >
              <svg v-if="isLoading" class="h-5 w-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <CalculatorIcon v-else class="h-5 w-5" />
              {{ isLoading ? 'Calculating…' : 'Calculate' }}
            </button>
            <button @click="showCustomConfig = !showCustomConfig" class="btn-icon" :class="{'!shadow-neu-inset-sm !text-app-accent': showCustomConfig}" title="Toggle configuration">
              <AdjustmentsHorizontalIcon class="h-5 w-5" />
            </button>
            <button @click="resetToDefault" v-if="showCustomConfig" class="btn-icon" title="Reset configuration">
              <ArrowPathIcon class="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      <!-- Configuration Form (Collapsible) -->
      <div v-if="showCustomConfig" class="flex-shrink-0 border-b border-slate-200 p-3">
        <div class="flex flex-wrap items-start gap-x-5 gap-y-2.5 rounded-xl bg-app-primary p-3 shadow-neu-inset-sm">
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Define how demand levels are calculated based on occupancy.">Demand bins</label>
            <input v-model="customConfig.demand_bins" type="text" class="neu-input mt-1 w-40 px-2.5 py-1.5 text-sm" placeholder="[0, 70, 85, 100]">
          </div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Define how demand levels are calculated based on occupancy.">Demand labels</label>
            <input v-model="customConfig.demand_labels" type="text" class="neu-input mt-1 w-44 px-2.5 py-1.5 text-sm" placeholder="['Low', 'Medium', 'High']">
          </div>
          <div class="my-1 h-8 w-px self-center bg-slate-200"></div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Percentage thresholds for low inventory warnings.">Very low %</label>
            <input v-model.number="customConfig.very_low_threshold_pct" type="number" step="0.01" class="neu-input mt-1 w-20 px-2.5 py-1.5 text-sm">
          </div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Percentage thresholds for low inventory warnings.">Low %</label>
            <input v-model.number="customConfig.low_threshold_pct" type="number" step="0.01" class="neu-input mt-1 w-20 px-2.5 py-1.5 text-sm">
          </div>
          <div class="my-1 h-8 w-px self-center bg-slate-200"></div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Shift the base BAR matrix N levels for Deluxe and Premiere Rooms, applied before scarcity escalation. Positive = more expensive (e.g. 1 turns base BAR5 into BAR4). Negative = cheaper (e.g. -1 turns base BAR5 into BAR6).">BAR shift</label>
            <input v-model.number="customConfig.bar_level_shift" type="number" step="1" class="neu-input mt-1 w-16 px-2.5 py-1.5 text-sm">
          </div>
          <div class="my-1 h-8 w-px self-center bg-slate-200"></div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Total rooms available for each type.">Deluxe cap</label>
            <input v-model.number="customConfig.room_caps['Deluxe Room']" type="number" class="neu-input mt-1 w-20 px-2.5 py-1.5 text-sm">
          </div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Total rooms available for each type.">Premiere cap</label>
            <input v-model.number="customConfig.room_caps['Premiere Room']" type="number" class="neu-input mt-1 w-20 px-2.5 py-1.5 text-sm">
          </div>
          <div class="my-1 h-8 w-px self-center bg-slate-200"></div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Rule to automatically adjust Deluxe inventory.">Override occ %</label>
            <input v-model.number="customConfig.deluxe_override_occupancy" type="number" class="neu-input mt-1 w-20 px-2.5 py-1.5 text-sm">
          </div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Rule to automatically adjust Deluxe inventory.">Premiere min</label>
            <input v-model.number="customConfig.deluxe_override_premiere" type="number" class="neu-input mt-1 w-20 px-2.5 py-1.5 text-sm">
          </div>
          <div class="flex flex-col">
            <label class="text-[10px] font-medium text-slate-500" title="Rule to automatically adjust Deluxe inventory.">Amount</label>
            <input v-model.number="customConfig.deluxe_override_amount" type="number" class="neu-input mt-1 w-16 px-2.5 py-1.5 text-sm">
          </div>
        </div>
      </div>

      <div class="flex-shrink-0 border-b border-slate-200 px-6 py-3">
        <label class="flex items-center gap-2 text-sm text-slate-700">
          <input v-model="includeOtherRooms" type="checkbox">
          Calculate allocations for all room categories
        </label>
        <p class="mt-1 text-xs text-slate-500">Reserves cover unassigned upgrades. Room assignments already reflected in the PMS are not deducted again. Publishing remains a separate action.</p>
      </div>

      <!-- Status/Error Message -->
      <div v-if="error" class="flex-shrink-0 p-4 sm:px-6">
        <div class="flex items-start gap-2 rounded-xl bg-app-primary p-3 text-sm font-semibold text-rose-700 shadow-neu-inset-sm">
          <ExclamationTriangleIcon class="h-5 w-5 flex-shrink-0" />
          <span>{{ error }}</span>
        </div>
      </div>

      <!-- Data Table -->
      <div class="flex flex-1 flex-col overflow-hidden p-4 sm:p-6">
        <div v-if="allocationData.length > 0" class="flex h-full flex-col">
          <div class="mb-4 flex flex-shrink-0 flex-wrap items-center justify-between gap-4">
            <div>
              <h3 class="text-base font-semibold text-app-tertiary">Inventory allocation</h3>
              <p class="text-sm text-slate-500">Results from the yield calculation.</p>
              <p v-if="blockedDays" class="mt-1 text-sm font-semibold text-rose-700">{{ blockedDays }} date(s) have uncovered upgrades. Proposed online inventory is zero on those dates; review upgrade routes and capacity.</p>
              <label class="mt-2 block text-sm text-slate-600">Show category
                <select v-model="selectedRoom" class="neu-input mt-1">
                  <option v-for="room in roomTypes" :key="room" :value="room">{{ room }}</option>
                </select>
              </label>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-slate-400">Export</span>
              <button @click="exportData('csv')" class="btn-icon" title="Export CSV">
                <DocumentArrowDownIcon class="h-5 w-5" />
              </button>
              <button @click="exportData('excel')" class="btn-icon" title="Export Excel">
                <TableCellsIcon class="h-5 w-5" />
              </button>
              <button @click="exportData('json')" class="btn-icon" title="Export JSON">
                <CodeBracketIcon class="h-5 w-5" />
              </button>
            </div>
          </div>
          <div class="flex-1 overflow-y-auto rounded-xl bg-app-primary p-1 shadow-neu-inset">
            <table class="min-w-full divide-y divide-slate-200">
              <thead class="bg-app-primary sticky top-0 z-10">
                <tr>
                  <th v-for="header in tableHeaders" :key="header.key" scope="col" class="py-3.5 pl-6 pr-3 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500 cursor-pointer hover:text-app-accent group" @click="allocationData = sortData(allocationData, header.key)">
                    <div class="flex items-center space-x-2">
                      <component :is="header.icon" class="h-4 w-4 text-slate-400 group-hover:text-app-accent" />
                      <span>{{ header.label }}</span>
                      <span v-if="sortColumn === header.key" class="text-xs text-app-accent">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-200">
                <tr v-for="(row, index) in allocationData" :key="index" class="hover:bg-app-secondary/50 transition-colors duration-150">
                  <td v-for="header in tableHeaders" :key="header.key" class="whitespace-nowrap py-4 pl-6 pr-3 text-sm" :class="getCellStyle(row[header.key], header.key)">
                    {{ formatValue(row[header.key], header.key) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else-if="!isLoading" class="flex flex-1 flex-col items-center justify-center text-center text-slate-500">
          <span class="flex h-16 w-16 items-center justify-center rounded-xl bg-app-primary text-slate-400 shadow-neu-inset">
            <DocumentMagnifyingGlassIcon class="h-8 w-8" />
          </span>
          <h3 class="mt-4 text-sm font-semibold text-slate-600">No data available</h3>
          <p class="mt-1 text-sm">Click <span class="font-semibold text-app-accent">Calculate</span> to generate inventory allocation data.</p>
        </div>
        <div v-if="isLoading" class="flex flex-1 flex-col items-center justify-center">
          <div class="h-9 w-9 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent"></div>
          <p class="mt-4 text-sm text-slate-500">Calculating yield, please wait…</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from '../plugins/axios'
import * as XLSX from 'xlsx'
import {
  CalculatorIcon,
  ArrowPathIcon,
  AdjustmentsHorizontalIcon,
  ExclamationTriangleIcon,
  DocumentArrowDownIcon,
  TableCellsIcon,
  CodeBracketIcon,
  DocumentMagnifyingGlassIcon,
  CalendarDaysIcon,
  ChartPieIcon,
  SignalIcon,
  BuildingOfficeIcon,
  BuildingStorefrontIcon,
  BanknotesIcon,
} from '@heroicons/vue/24/outline'

const isLoading = ref(false)
const error = ref<string | null>(null)
const allocationData = ref<any[]>([])
const showCustomConfig = ref(false)
const includeOtherRooms = ref(false)
const selectedRoom = ref('Premiere Room')

interface CustomConfig {
  demand_bins: number[] | string;
  demand_labels: string[] | string;
  very_low_threshold_pct: number;
  low_threshold_pct: number;
  room_caps: {
    'Deluxe Room': number;
    'Premiere Room': number;
  };
  deluxe_override_occupancy: number;
  deluxe_override_premiere: number;
  deluxe_override_amount: number;
  bar_level_shift: number;
}

const defaultConfig: CustomConfig = {
  demand_bins: [0, 70, 85, 100],
  demand_labels: ['Low', 'Medium', 'High'],
  very_low_threshold_pct: 5,
  low_threshold_pct: 20,
  room_caps: {
    'Deluxe Room': 160,
    'Premiere Room': 260
  },
  deluxe_override_occupancy: 70,
  deluxe_override_premiere: 61,
  deluxe_override_amount: 2,
  bar_level_shift: 0
}

const customConfig = ref<CustomConfig>({ ...defaultConfig })

const roomTypes = [
  'Deluxe Room', 'Premiere Room', 'Deluxe Pool Access', 'Premiere Room Lagoon Access',
  'Premiere Suite Room', 'Deluxe Suite Room', 'Family Premiere Room',
  'Beach Front Private Suite Room', 'The Anvaya Suite Whirpool',
  'The Anvaya Suite No Pool', 'The Anvaya Suite With Pool', 'The Anvaya Residence', 'The Anvaya Villa'
]
const blockedDays = computed(() => allocationData.value.filter(row => row['Unresolved Upgrade Rooms'] > 0).length)
const tableHeaders = computed(() => {
  const room = selectedRoom.value
  const prefix = room === 'Deluxe Room' ? 'Deluxe' : room === 'Premiere Room' ? 'Premiere' : room
  const columns = [
    { key: 'Date', label: 'Date', icon: CalendarDaysIcon },
    { key: 'Occupancy', label: 'Occupancy', icon: ChartPieIcon },
    { key: 'Allocation Status', label: 'Status', icon: SignalIcon },
    { key: 'Unresolved Upgrade Rooms', label: 'Uncovered upgrades (hotel)', icon: ExclamationTriangleIcon },
    { key: `${prefix} Remaining Inventory`, label: 'Remaining', icon: BuildingOfficeIcon },
    { key: `${room} Upgrade Reserve`, label: 'Existing upgrades', icon: BuildingOfficeIcon },
    { key: `${room} Override Reserve`, label: 'New override sales', icon: BuildingOfficeIcon },
    { key: `${room} Operational Hold`, label: 'Buffer / holds', icon: BuildingOfficeIcon },
    { key: `${room} Safe Inventory`, label: 'After reserves', icon: BuildingOfficeIcon },
    { key: `${prefix} Online Inventory`, label: 'Proposed online', icon: BuildingStorefrontIcon },
  ]
  if (room === 'Deluxe Room' || room === 'Premiere Room') {
    columns.push({ key: `${prefix} BAR Rate`, label: 'BAR', icon: BanknotesIcon })
  }
  return columns
})

const calculateYield = async () => {
  isLoading.value = true
  error.value = null

  try {
    let parsedConfig;
    try {
      const parseArrayInput = (input: string | any[]): any[] => {
        if (Array.isArray(input)) return input
        const str = input.toString().trim()
        try {
          return JSON.parse(str.replace(/'/g, '"'))
        } catch {
          return str.split(',').map(item => item.trim())
        }
      }

      const roomCaps = customConfig.value.room_caps
      if (!roomCaps['Deluxe Room'] || !roomCaps['Premiere Room']) {
        throw new Error('Room capacities must be specified for both Deluxe Room and Premiere Room')
      }

      parsedConfig = {
        ...customConfig.value,
        demand_bins: parseArrayInput(customConfig.value.demand_bins).map(Number),
        demand_labels: parseArrayInput(customConfig.value.demand_labels),
        room_caps: {
          'Deluxe Room': Number(roomCaps['Deluxe Room']),
          'Premiere Room': Number(roomCaps['Premiere Room'])
        }
      }

      if (isNaN(parsedConfig.very_low_threshold_pct) || 
          isNaN(parsedConfig.low_threshold_pct) || 
          isNaN(parsedConfig.deluxe_override_occupancy) || 
          isNaN(parsedConfig.deluxe_override_premiere) || 
          isNaN(parsedConfig.deluxe_override_amount) ||
          isNaN(parsedConfig.bar_level_shift)) {
        throw new Error('All numeric values must be valid numbers')
      }
    } catch (parseError) {
      error.value = parseError instanceof Error ? parseError.message : 'Invalid configuration format'
      return
    }

    await axios.post('/api/custom-yield', { ...parsedConfig, include_simple_rooms: includeOtherRooms.value })
    
    const dataResponse = await axios.get('/api/db/inventory-allocation')
    if (dataResponse.data.status === 'success' && Array.isArray(dataResponse.data.data)) {
      allocationData.value = dataResponse.data.data
    } else {
      error.value = 'Received data in unexpected format'
    }
  } catch (err: any) {
    const errorMessage = err.response?.data?.message || 'Failed to calculate yield'
    if (errorMessage.includes('Combined inventory database not found')) {
      error.value = 'Please run the "Combine Inventory" process first. This requires both PMS and CM inventory data to be processed.'
    } else if (errorMessage.includes('Failed to create inventory allocation database')) {
      error.value = 'Failed to create the inventory allocation database. Please check if you have write permissions in the data directory.'
    } else if (errorMessage.includes('No data was written')) {
      error.value = 'No data was written to the inventory allocation database. Please check if the combined inventory data is valid.'
    } else {
      error.value = errorMessage
    }
  } finally {
    isLoading.value = false
  }
}

const formatValue = (value: any, key: string) => {
  if (value === null || value === undefined) return '-'
  if (key.toLowerCase().includes('rate')) {
    // BAR rates are rate-plan labels (e.g. "BAR4"), not currency amounts.
    return value
  }
  if (typeof value === 'number') {
    if (key.toLowerCase().includes('occupancy')) return `${value.toFixed(1)}%`
    return value.toLocaleString()
  }
  if (key.toLowerCase().includes('date')) {
    const date = new Date(value)
    const day = date.getDate().toString().padStart(2, '0')
    const month = date.toLocaleString('en-US', { month: 'short' })
    return `${day} ${month}`
  }
  return value
}

const getCellStyle = (value: any, key: string) => {
  const styles: string[] = ['text-slate-700']
  if (typeof value === 'number') {
    if (key.toLowerCase().includes('occupancy')) {
      if (value >= 85) styles.push('text-emerald-700', 'font-semibold')
      else if (value >= 70) styles.push('text-amber-600', 'font-semibold')
      else styles.push('text-rose-600', 'font-semibold')
    }
    if (key.toLowerCase().includes('inventory')) {
      if (value > 10) styles.push('text-emerald-700')
      else if (value > 0) styles.push('text-amber-600')
      else styles.push('text-rose-600', 'font-bold')
    }
  }
  if (key.toLowerCase().includes('rate')) {
    styles.push('font-mono', 'text-sm', 'text-app-accent')
  }
  return styles.join(' ')
}

const resetToDefault = () => {
  customConfig.value = { ...defaultConfig };
}

onMounted(async () => {
  try {
    const response = await axios.get('/api/db/inventory-allocation')
    if (response.data.status === 'success' && Array.isArray(response.data.data)) {
      allocationData.value = response.data.data
    }
  } catch (err: any) {
    // Silently fail on mount, let user trigger calculation
  }
})

const sortColumn = ref('Date')
const sortDirection = ref<'asc' | 'desc'>('asc')

function sortData(data: any[], column: string) {
  if (sortColumn.value === column) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column
    sortDirection.value = 'asc'
  }

  return [...data].sort((a, b) => {
    let valueA = a[column]
    let valueB = b[column]

    if (column.toLowerCase().includes('date')) {
      valueA = new Date(valueA).getTime()
      valueB = new Date(valueB).getTime()
    }
    else if (!isNaN(Number(valueA)) && !isNaN(Number(valueB))) {
      valueA = Number(valueA)
      valueB = Number(valueB)
    }

    if (valueA < valueB) return sortDirection.value === 'asc' ? -1 : 1
    if (valueA > valueB) return sortDirection.value === 'asc' ? 1 : -1
    return 0
  })
}

const exportData = async (format: 'csv' | 'excel' | 'json') => {
  if (allocationData.value.length === 0) {
    alert('No data available to export')
    return
  }

  try {
    const exportHeaders = Object.keys(allocationData.value[0]);
    const orderedData = allocationData.value.map(row => {
      const orderedRow: Record<string, any> = {}
      exportHeaders.forEach(header => {
        orderedRow[header] = row[header]
      })
      return orderedRow
    })

    switch (format) {
      case 'csv':
        const csvContent = orderedData.map(row => 
          exportHeaders.map(header => {
            const value = row[header]
            return typeof value === 'string' ? `"${value.replace(/"/g, '""')}"` : value
          }).join(',')
        ).join('\n')
        const csvHeaders = exportHeaders.join(',')
        const csv = `${csvHeaders}\n${csvContent}`
        
        const csvBlob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
        const csvUrl = URL.createObjectURL(csvBlob)
        const csvLink = document.createElement('a')
        csvLink.href = csvUrl
        csvLink.download = 'inventory_allocation.csv'
        csvLink.click()
        URL.revokeObjectURL(csvUrl)
        break

      case 'excel':
        const worksheet = XLSX.utils.json_to_sheet(orderedData)
        const workbook = XLSX.utils.book_new()
        XLSX.utils.book_append_sheet(workbook, worksheet, 'Data')
        XLSX.writeFile(workbook, 'inventory_allocation.xlsx')
        break

      case 'json':
        const jsonContent = JSON.stringify(orderedData, null, 2)
        const jsonBlob = new Blob([jsonContent], { type: 'application/json' })
        const jsonUrl = URL.createObjectURL(jsonBlob)
        const jsonLink = document.createElement('a')
        jsonLink.href = jsonUrl
        jsonLink.download = 'inventory_allocation.json'
        jsonLink.click()
        URL.revokeObjectURL(jsonUrl)
        break
    }
  } catch (error) {
    alert('Error exporting data. Please try again.')
  }
}
</script>