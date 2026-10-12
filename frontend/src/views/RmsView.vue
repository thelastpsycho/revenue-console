<template>
  <div class="mx-auto w-full max-w-screen-2xl space-y-4 p-4 sm:p-6">
    <div class="flex flex-wrap justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold">Revenue management</h1>
        <p class="text-xs text-slate-500">
          Daily decisions · {{ today }} · Bali time
        </p>
      </div>
      <nav class="flex flex-wrap gap-1" aria-label="RMS sections">
        <button
          v-for="t in tabs"
          :key="t.id"
          :class="[
            'rounded-lg px-3 py-2 text-sm',
            tab === t.id ? 'bg-slate-800 text-white' : 'bg-slate-100',
          ]"
          :aria-current="tab === t.id ? 'page' : undefined"
          @click="selectTab(t.id)"
        >
          {{ t.label }}
        </button>
      </nav>
    </div>
    <p
      v-if="error"
      role="alert"
      class="rounded bg-rose-50 p-3 text-sm text-rose-800"
    >
      {{ error }}
    </p>
    <div
      v-if="sync"
      :class="[
        'rounded-lg border p-3 text-xs',
        sync.stale ? 'border-amber-200 bg-amber-50' : 'border-slate-200',
      ]"
    >
      <strong>{{
        sync.stale ? "Booking data needs refresh." : "Booking data updated."
      }}</strong>
      Last successful sync: {{ timestamp(sync.lastSuccessfulSync) }}.
      Booking-date coverage:
      {{ sync.coverageFrom || "Unavailable — run backfill" }}.
      <p class="mt-1">
        Observed history records what each sync saw. Earlier history is
        reconstructed and estimated; missing coverage is unavailable. No
        currency conversion is applied.
      </p>
    </div>
    <template v-if="tab !== 'data'">
      <form
        class="neu-card flex flex-wrap items-end gap-3 p-4 text-xs"
        @submit.prevent="loadAll"
      >
        <label
          >From<input
            v-model="filters.start"
            type="date"
            required
            class="neu-input mt-1 block" /></label
        ><label
          >Through<input
            v-model="filters.end"
            type="date"
            required
            class="neu-input mt-1 block"
        /></label>
        <label
          >Room type<select
            v-model="filters.roomType"
            class="neu-input mt-1 block"
          >
            <option value="">All</option>
            <option v-for="r in dims.roomTypes" :key="r" :value="r">
              {{ label(r) }}
            </option>
          </select></label
        >
        <label
          >Market<select
            v-model="filters.marketId"
            class="neu-input mt-1 block"
          >
            <option value="">All</option>
            <option v-for="m in dims.markets" :key="m.id" :value="String(m.id)">
              {{ m.name }}
            </option>
          </select></label
        >
        <label
          >Pickup<select
            v-model.number="filters.pickupDays"
            class="neu-input mt-1 block"
          >
            <option v-for="d in [1, 3, 7, 14, 30]" :key="d" :value="d">
              {{ d }} days
            </option>
          </select></label
        >
        <label
          >Compare with<select
            v-model="filters.comparison"
            class="neu-input mt-1 block"
          >
            <option value="weekday">Same weekday last year</option>
            <option value="calendar">Same calendar date last year</option>
            <option value="custom">Matched event / holiday</option>
          </select></label
        >
        <label v-if="filters.comparison === 'custom'"
          >Comparison begins<input
            v-model="filters.comparisonStart"
            type="date"
            required
            class="neu-input mt-1 block"
        /></label>
        <label
          >Revenue basis<select v-model="basis" class="neu-input mt-1 block">
            <option value="gross">Gross IDR rate</option>
            <option value="net">Estimated net IDR rate</option>
          </select></label
        >
        <button class="btn-primary px-3 py-2" :disabled="loading">
          {{ loading ? "Loading…" : "Apply" }}</button
        ><button type="button" class="btn-flat px-3 py-2" @click="thisMonth">
          This month</button
        ><button
          type="button"
          class="btn-flat px-3 py-2"
          :disabled="!rows.length"
          @click="exportCsv"
        >
          Export CSV
        </button>
      </form>
      <p v-if="dirty" class="text-xs text-amber-800">
        Filters changed. Press Apply. Displayed data and exports still use the
        previous selection.
      </p>
      <p v-if="loaded" class="text-xs text-slate-500">
        Showing {{ loaded.start }}–{{ loaded.end }} ·
        {{ loaded.roomType ? label(loaded.roomType) : "All room types" }} ·
        {{ loaded.marketId ? marketName(loaded.marketId) : "All markets" }} ·
        {{ comparisonLabel }} · {{ loaded.pickupDays }}-day pickup.
      </p>
      <div v-if="forecast" class="flex flex-wrap gap-3 text-xs text-slate-500">
        <span v-for="(s, k) in forecast.sections" :key="k"
          >{{ k }}:
          {{
            s.refreshing
              ? "refreshing…"
              : s.error
                ? "failed"
                : s.stale
                  ? "stale"
                  : "ready"
          }}
          · {{ timestamp(s.fetchedAt)
          }}<span v-if="s.error" class="text-rose-700">
            {{ s.error }}</span
          ></span
        ><button
          class="underline"
          :disabled="forecastBusy"
          @click="refreshForecast"
        >
          Refresh PMS reports
        </button>
      </div>
      <p v-if="loaded" class="text-xs text-slate-500">
        Displayed booking data from sync:
        {{ timestamp(reportSync?.lastSuccessfulSync) }}.
        {{
          reportSync?.lastSuccessfulSync !== sync?.lastSuccessfulSync
            ? "New data is available — press Apply."
            : ""
        }}
      </p>
      <p class="text-xs text-slate-500">
        PMS reports cover the first 90 selected days; pace covers up to 366. PMS
        forecast revenue uses the PMS definition and is not combined with
        booking-rate revenue.
      </p>
      <template v-if="tab === 'overview'">
        <dl class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div v-for="t in tiles" :key="t.label" class="neu-card p-4">
            <dt class="text-xs text-slate-500">{{ t.label }}</dt>
            <dd class="mt-1 text-lg font-semibold tabular-nums">
              {{ t.value }}
            </dd>
          </div>
        </dl>
        <div class="neu-card overflow-hidden">
          <div class="flex flex-wrap justify-between gap-2 p-4">
            <h2 class="font-semibold">Dates requiring attention</h2>
            <label class="text-xs"
              ><input v-model="onlyAttention" type="checkbox" /> Only flagged
              dates</label
            >
          </div>
          <p class="px-4 pb-3 text-xs text-slate-500">
            Flags never change rates. Availability is physical PMS inventory;
            last-applied BAR levels may differ from live prices. BAR record
            updated: {{ timestamp(bar.updatedAt) }}.
          </p>
          <div class="max-h-[55vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 bg-white">
                <tr>
                  <th
                    v-for="h in [
                      'Stay date',
                      'OTB',
                      'OTB occ.',
                      'Pickup',
                      'Comparison gap',
                      'Available',
                      'Last applied BAR',
                      'PMS room difference',
                      'Review reason',
                    ]"
                    :key="h"
                    class="whitespace-nowrap p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in attentionRows"
                  :key="r.date"
                  class="border-t border-slate-100 hover:bg-slate-50"
                >
                  <td class="whitespace-nowrap p-3">
                    <button
                      class="font-semibold underline"
                      @click="openDay(r.date)"
                    >
                      {{ dayLabel(r.date) }}
                    </button>
                  </td>
                  <td class="p-3">{{ num(r.otb) }}</td>
                  <td class="p-3">{{ percent(r.occupancy) }}</td>
                  <td class="p-3">{{ signed(r.pickupRooms) }}</td>
                  <td class="p-3">{{ signed(r.gap) }}</td>
                  <td class="p-3">{{ num(r.available) }}</td>
                  <td class="max-w-48 p-3">{{ r.bar || "Unavailable" }}</td>
                  <td class="p-3">{{ signed(r.reconciliation) }}</td>
                  <td class="min-w-44 p-3">
                    {{ r.reasons.join(" · ") || "No flags"
                    }}<span
                      v-if="notes[r.date]?.text"
                      class="block text-slate-500"
                      >Note saved</span
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!attentionRows.length" class="p-4 text-sm text-slate-500">
            {{
              rows.length
                ? "No dates match the attention filter."
                : "Apply a range to load data."
            }}
          </p>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">Monthly booking position & targets</h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            {{ basisLabel }}. ADR uses IDR nights only. RevPAR is the IDR
            revenue component / room capacity. Targets require complete,
            unfiltered months on the same basis. These are booking positions,
            not audited actuals.
          </p>
          <div class="overflow-x-auto">
            <table class="min-w-full text-xs">
              <thead>
                <tr>
                  <th
                    v-for="h in [
                      'Month',
                      'Room nights',
                      'Room revenue',
                      'ADR',
                      'RevPAR (IDR component)',
                      'Target',
                      'Target gap',
                      'Required revenue / remaining day',
                    ]"
                    :key="h"
                    class="p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in months"
                  :key="m.month"
                  class="border-t border-slate-100"
                >
                  <td class="p-3">
                    {{ m.month
                    }}<span v-if="!m.fullMonth" class="block text-amber-800"
                      >Partial month</span
                    ><span v-if="m.hasForeign" class="block text-slate-500"
                      >Foreign revenue excluded</span
                    >
                  </td>
                  <td class="p-3">{{ num(m.roomNights) }}</td>
                  <td class="p-3">{{ money(m.revenue) }}</td>
                  <td class="p-3">{{ money(m.adr) }}</td>
                  <td class="p-3">{{ money(m.revpar) }}</td>
                  <td class="p-3">{{ money(m.budget) }}</td>
                  <td class="p-3">{{ money(m.gap) }}</td>
                  <td class="p-3">{{ money(m.required) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <template v-if="tab === 'pace'">
        <div class="neu-card p-4">
          <div class="flex justify-between">
            <h2 class="font-semibold">Room nights & ADR</h2>
            <select
              v-model="chartView"
              aria-label="Chart grouping"
              class="neu-input text-xs"
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
          <p class="my-2 text-xs text-slate-500">
            {{ basisLabel }}. IDR ADR coverage: {{ percent(idrCoverage) }} of
            room nights. Comparison history may be estimated.
          </p>
          <div class="h-72">
            <Chart type="bar" :data="chartData" :options="chartOptions" />
          </div>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">Pickup by stay date</h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            New − cancellations + net amendments = net pickup, in room nights.
            Amendments include date/segment moves and reinstatements.
            Pre-observation breakdowns are estimates.
          </p>
          <div class="max-h-[60vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 bg-white">
                <tr>
                  <th
                    v-for="h in [
                      'Date',
                      'OTB',
                      'Revenue',
                      'New',
                      'Cancelled',
                      'Amendments',
                      'Net pickup',
                      'Comparison',
                      'Gap',
                      'LY / matched final',
                      'Quality',
                    ]"
                    :key="h"
                    class="whitespace-nowrap p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in rows"
                  :key="r.date"
                  class="border-t border-slate-100"
                >
                  <td class="whitespace-nowrap p-3">
                    <button class="underline" @click="openDay(r.date)">
                      {{ dayLabel(r.date) }}
                    </button>
                  </td>
                  <td class="p-3">{{ num(currentRooms(r)) }}</td>
                  <td class="p-3">
                    {{ money(currentRooms(r) == null ? null : revenue(r)) }}
                  </td>
                  <td class="p-3">{{ num(r.newRooms) }}</td>
                  <td class="p-3">{{ num(r.cancelledRooms) }}</td>
                  <td class="p-3">{{ signed(r.amendedRooms) }}</td>
                  <td class="p-3">{{ signed(r.pickupRooms) }}</td>
                  <td class="p-3">{{ num(r.stlyRooms) }}</td>
                  <td class="p-3">
                    {{ signed(difference(currentRooms(r), r.stlyRooms)) }}
                  </td>
                  <td class="p-3">{{ num(r.lyFinalRooms) }}</td>
                  <td class="p-3">
                    Comparison: {{ r.comparisonQuality }}<br />Pickup:
                    {{ r.pickupQuality }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <template v-if="tab === 'forecast'">
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">PMS hotel forecast — whole hotel</h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            RoomUsed and revenue are reported by PMS. Room-type/market filters
            apply to pace; this table remains hotel-wide.
          </p>
          <div class="max-h-[60vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 bg-white">
                <tr>
                  <th
                    v-for="h in [
                      'Date',
                      'Occupancy',
                      'RoomUsed / capacity',
                      'PMS revenue',
                      'PMS ADR',
                      'Comp / house use',
                    ]"
                    :key="h"
                    class="p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in forecast?.hotel || []"
                  :key="r.date"
                  class="border-t border-slate-100"
                >
                  <td class="p-3">{{ dayLabel(r.date) }}</td>
                  <td class="p-3">{{ percent(r.occupancy) }}</td>
                  <td class="p-3">
                    {{ num(r.roomsSold) }} / {{ num(r.roomCount) }}
                  </td>
                  <td class="p-3">{{ money(r.revenue) }}</td>
                  <td class="p-3">{{ money(r.adr) }}</td>
                  <td class="p-3">
                    {{ num(r.complimentary) }} / {{ num(r.houseUse) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!forecast?.hotel.length" class="p-4 text-sm">
            {{
              forecastBusy
                ? "Hotel totals are loading independently…"
                : "No hotel forecast available."
            }}
          </p>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">
            Market segments — whole forecast window
          </h2>
          <div class="overflow-x-auto">
            <table class="min-w-full text-xs">
              <thead>
                <tr>
                  <th
                    v-for="h in [
                      'Segment',
                      'Room nights',
                      'PMS revenue',
                      'PMS revenue / night',
                    ]"
                    :key="h"
                    class="p-3 text-left"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="s in segmentTotals"
                  :key="s.market"
                  class="border-t border-slate-100"
                >
                  <td class="p-3">{{ s.market }}</td>
                  <td class="p-3">{{ num(s.rooms) }}</td>
                  <td class="p-3">{{ money(s.revenue) }}</td>
                  <td class="p-3">{{ money(ratio(s.revenue, s.rooms)) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">Expected occupied by room type</h2>
          <div class="max-h-[50vh] overflow-auto">
            <table class="min-w-full text-xs">
              <thead class="sticky top-0 bg-white">
                <tr>
                  <th class="sticky left-0 bg-white p-3 text-left">
                    Room type
                  </th>
                  <th
                    v-for="d in matrix.dates"
                    :key="d"
                    class="whitespace-nowrap p-2"
                  >
                    {{ d.slice(5) }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in matrix.types"
                  :key="r.typeId"
                  class="border-t border-slate-100"
                >
                  <td class="sticky left-0 whitespace-nowrap bg-white p-3">
                    {{ label(r.typeId) }}
                  </td>
                  <td
                    v-for="d in matrix.dates"
                    :key="d"
                    :class="[
                      'p-2 text-right',
                      r.capacity && r.values[d] >= r.capacity * 0.9
                        ? 'bg-amber-50'
                        : '',
                    ]"
                  >
                    {{ num(r.values[d]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <section
        v-if="selectedDate"
        ref="detailElement"
        class="neu-card space-y-3 p-4"
        aria-label="Stay date detail"
      >
        <div class="flex justify-between">
          <h2 class="font-semibold">
            {{ dayLabel(selectedDate) }} — booking curve & review
          </h2>
          <button class="text-xs underline" @click="closeDay">Close</button>
        </div>
        <p v-if="curveLoading" class="text-xs">Loading booking curve…</p>
        <p v-if="curveError" role="alert" class="text-xs text-rose-700">
          {{ curveError }}
        </p>
        <p class="text-xs text-slate-500">
          Current curve stops at today. Earlier reconstructed history is
          estimated; gaps mean unavailable. Comparison: {{ curve?.lyDate }}.
        </p>
        <div class="h-60">
          <Chart
            type="line"
            :data="curveData"
            :options="curveOptions"
            :plugins="[todayMarker]"
          />
        </div>
        <div class="grid gap-4 md:grid-cols-2">
          <div>
            <h3 class="text-sm font-semibold">Physical availability</h3>
            <p v-if="!selectedAvailability.length" class="text-xs">
              Unavailable for this date.
            </p>
            <div class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="r in selectedAvailability"
                :key="r.type"
                class="rounded bg-slate-50 p-2 text-xs"
                >{{ label(r.type) }}: {{ num(r.rooms) }}</span
              >
            </div>
          </div>
          <div>
            <h3 class="text-sm font-semibold">PMS segment breakdown</h3>
            <p v-if="!selectedSegments.length" class="text-xs">
              Unavailable for this date.
            </p>
            <p
              v-for="s in selectedSegments"
              :key="s.marketId"
              class="mt-1 text-xs"
            >
              {{ s.market }}: {{ num(s.rooms) }} nights · {{ money(s.revenue) }}
            </p>
          </div>
        </div>
        <label class="block text-xs font-semibold"
          >Meeting note — do not enter guest details<textarea
            v-model="noteDraft"
            maxlength="2000"
            rows="3"
            class="neu-input mt-1 w-full"
          /></label
        ><button
          class="btn-primary px-3 py-2 text-xs"
          :disabled="noteSaving"
          @click="saveNote"
        >
          {{ noteSaving ? "Saving…" : "Save note" }}</button
        ><span v-if="notes[selectedDate]" class="ml-3 text-xs"
          >Saved {{ timestamp(notes[selectedDate].updatedAt) }}</span
        >
      </section>
    </template>
    <template v-else>
      <div class="neu-card space-y-3 p-4">
        <h2 class="font-semibold">Booking history</h2>
        <p class="text-xs text-slate-500">
          Daily refresh includes new bookings, arrivals in the next year and
          known in-house stays. Weekly refresh also revisits 90 days of booking
          creation. Versions cannot recover amendments before first observation.
        </p>
        <p class="text-sm">
          {{ num(sync?.bookings) }} bookings · Last daily:
          {{ sync?.lastDaily || "Unavailable" }} · Last weekly:
          {{ sync?.lastWeekly || "Unavailable" }}
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <label class="text-xs"
            >Backfill years
            <select v-model.number="backfillYears" class="neu-input">
              <option v-for="n in [1, 2, 3, 4, 5]" :key="n" :value="n">
                {{ n }}
              </option>
            </select></label
          ><button
            v-for="kind in ['backfill', 'daily', 'weekly']"
            :key="kind"
            class="btn-flat px-3 py-2 text-xs"
            :disabled="sync?.job.running"
            @click="runSync(kind)"
          >
            Run {{ kind }}
          </button>
        </div>
        <p v-if="sync?.job.running" class="text-xs">
          {{ sync.job.kind }}: {{ sync.job.done }} /
          {{ sync.job.total }} windows · {{ sync.job.rows }} rows
        </p>
        <p v-if="sync?.job.error" class="text-xs text-rose-700">
          {{ sync.job.error }}
        </p>
      </div>
      <form
        v-if="settings"
        class="neu-card space-y-4 p-4"
        @submit.prevent="saveSettings"
      >
        <h2 class="font-semibold">Review thresholds</h2>
        <div class="flex flex-wrap gap-4 text-xs">
          <label
            >High occupancy %<input
              v-model.number="settings.thresholds.occupancy"
              type="number"
              min="0"
              max="100"
              required
              class="neu-input mt-1 block" /></label
          ><label
            >Weak pickup below<input
              v-model.number="settings.thresholds.weakPickup"
              type="number"
              min="0"
              required
              class="neu-input mt-1 block" /></label
          ><label
            >Behind comparison by (rooms)<input
              v-model.number="settings.thresholds.behindRooms"
              type="number"
              min="0"
              required
              class="neu-input mt-1 block"
          /></label>
        </div>
        <h2 class="font-semibold">Estimated net revenue rules</h2>
        <p class="text-xs text-slate-500">
          Net = max(gross rate − breakfast, 0) / (1 + tax/service). A specific
          PMS RateType overrides *; an optional package RateId overrides the
          type rule. Rules apply by stay date. Keep a * rule covering all report
          dates. 0.21 means 21%. Changing rules restates estimated net figures;
          gross booking history is retained.
        </p>
        <div
          v-for="(r, i) in settings.revenueRules"
          :key="i"
          class="flex flex-wrap items-end gap-2 text-xs"
        >
          <label
            >RateType<input
              v-model="r.rateType"
              required
              maxlength="40"
              class="neu-input mt-1 block w-24" /></label
          ><label
            >Package RateId (optional)<input
              v-model="r.rateId"
              maxlength="80"
              class="neu-input mt-1 block w-36" /></label
          ><label
            >From<input
              v-model="r.from"
              type="date"
              required
              class="neu-input mt-1 block" /></label
          ><label
            >Through<input
              v-model="r.to"
              type="date"
              required
              class="neu-input mt-1 block" /></label
          ><label
            >Breakfast IDR<input
              v-model.number="r.breakfast"
              type="number"
              min="0"
              required
              class="neu-input mt-1 block w-36" /></label
          ><label
            >Tax/service<input
              v-model.number="r.taxService"
              type="number"
              min="0"
              max="1"
              step=".001"
              required
              class="neu-input mt-1 block w-28" /></label
          ><button
            type="button"
            class="p-2 underline"
            @click="settings.revenueRules.splice(i, 1)"
          >
            Remove
          </button>
        </div>
        <button
          type="button"
          class="text-xs underline"
          @click="
            settings.revenueRules.push({
              rateType: '',
              rateId: '',
              from: today,
              to: '2099-12-31',
              breakfast: 0,
              taxService: 0.21,
            })
          "
        >
          Add rate-type rule
        </button>
        <h2 class="font-semibold">Monthly IDR booking revenue targets</h2>
        <p class="text-xs text-slate-500">
          Enter targets on the same basis as the report. Foreign revenue is
          excluded. PMS budget figures are not imported because their units are
          unverified.
        </p>
        <div
          v-for="(b, i) in settings.budgets"
          :key="i"
          class="flex flex-wrap items-end gap-2 text-xs"
        >
          <label
            >Month<input
              v-model="b.month"
              type="month"
              required
              class="neu-input mt-1 block" /></label
          ><label
            >Basis<select v-model="b.basis" class="neu-input mt-1 block">
              <option value="gross">Gross IDR</option>
              <option value="net">Estimated net IDR</option>
            </select></label
          ><label
            >Target IDR<input
              v-model.number="b.revenue"
              type="number"
              min="0"
              required
              class="neu-input mt-1 block" /></label
          ><button
            type="button"
            class="p-2 underline"
            @click="settings.budgets.splice(i, 1)"
          >
            Remove
          </button>
        </div>
        <button
          type="button"
          class="block text-xs underline"
          @click="
            settings.budgets.push({
              month: today.slice(0, 7),
              basis: 'gross',
              revenue: 0,
            })
          "
        >
          Add monthly target</button
        ><button
          class="btn-primary px-3 py-2 text-xs"
          :disabled="settingsSaving"
        >
          {{ settingsSaving ? "Saving…" : "Save settings" }}</button
        ><span class="ml-3 text-xs" role="status">{{ settingsMessage }}</span>
      </form>
    </template>
  </div>
</template>
<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { Chart } from "vue-chartjs";
import {
  Chart as ChartJS,
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartTypeRegistry,
} from "chart.js";
import axios from "../plugins/axios";
import {
  addDays,
  hotelToday,
  difference,
  ratio,
  sumKnown,
  monthlySummary,
  csvText,
  type PaceRow,
  type Budget,
} from "../utils/rms";
ChartJS.register(
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
);
interface Settings {
  thresholds: { occupancy: number; weakPickup: number; behindRooms: number };
  revenueRules: {
    rateType: string;
    rateId?: string;
    from: string;
    to: string;
    breakfast: number;
    taxService: number;
  }[];
  budgets: Budget[];
}
interface Sync {
  stale: boolean;
  coverageFrom: string | null;
  lastSuccessfulSync: string | null;
  bookings: number;
  lastDaily: string | null;
  lastWeekly: string | null;
  job: {
    running: boolean;
    kind: string;
    done: number;
    total: number;
    rows: number;
    error: string | null;
  };
}
interface Hotel {
  date: string;
  roomsSold: number | null;
  roomCount: number | null;
  occupancy: number | null;
  revenue: number | null;
  adr: number | null;
  complimentary: number | null;
  houseUse: number | null;
}
interface Segment {
  date: string;
  marketId: number;
  market: string;
  rooms: number;
  revenue: number;
}
interface Forecast {
  start: string;
  end: string;
  hotel: Hotel[];
  segments: Segment[];
  roomTypes: {
    date: string;
    typeId: string;
    rooms: number;
    roomCount: number;
  }[];
  availability: { date: string; values: Record<string, number> }[];
  sections: Record<
    string,
    {
      loaded: boolean;
      refreshing: boolean;
      stale: boolean;
      fetchedAt: string | null;
      error: string | null;
    }
  >;
}
interface Filters {
  start: string;
  end: string;
  roomType: string;
  marketId: string;
  pickupDays: number;
  comparison: string;
  comparisonStart: string;
}
interface CurvePoint {
  lead: number;
  rooms: number | null;
  quality: string;
}
interface Curve {
  date: string;
  lyDate: string;
  todayLead: number;
  maxLead: number;
  current: CurvePoint[];
  lastYear: CurvePoint[];
}
const today = hotelToday(),
  route = useRoute(),
  router = useRouter();
const tabs = [
  { id: "overview", label: "Overview" },
  { id: "pace", label: "Pace" },
  { id: "forecast", label: "PMS forecast" },
  { id: "data", label: "Data & settings" },
];
const query = (k: string, f = "") =>
  typeof route.query[k] === "string" ? String(route.query[k]) : f;
const tab = ref(
    tabs.some((t) => t.id === query("tab")) ? query("tab") : "overview",
  ),
  basis = ref<"gross" | "net">(query("basis") === "net" ? "net" : "gross");
const filters = reactive<Filters>({
  start: query("start", today),
  end: query("end", addDays(today, 29)),
  roomType: query("roomType"),
  marketId: query("marketId"),
  pickupDays: Number(query("pickupDays", "7")),
  comparison: query("comparison", "weekday"),
  comparisonStart: query("comparisonStart"),
});
const reportSync = ref<Sync | null>(null);
const loaded = ref<Filters | null>(null),
  rows = ref<PaceRow[]>([]),
  forecast = ref<Forecast | null>(null);
const dims = reactive<{
  roomTypes: string[];
  markets: { id: number; name: string }[];
  labels: Record<string, string>;
}>({ roomTypes: [], markets: [], labels: {} });
const sync = ref<Sync | null>(null),
  settings = ref<Settings | null>(null),
  appliedSettings = ref<Settings | null>(null);
const notes = ref<Record<string, { text: string; updatedAt: string }>>({}),
  bar = ref<{
    byDate: Record<string, Record<string, string>>;
    updatedAt: string | null;
  }>({ byDate: {}, updatedAt: null });
const loading = ref(false),
  error = ref(""),
  onlyAttention = ref(true),
  chartView = ref("monthly"),
  settingsSaving = ref(false),
  settingsMessage = ref(""),
  backfillYears = ref(3);
const selectedDate = ref(""),
  curve = ref<Curve | null>(null),
  curveLoading = ref(false),
  curveError = ref(""),
  noteDraft = ref(""),
  noteSaving = ref(false),
  detailElement = ref<HTMLElement | null>(null);
let requestId = 0,
  curveId = 0,
  forecastTimer: ReturnType<typeof setTimeout> | undefined,
  syncTimer: ReturnType<typeof setTimeout> | undefined,
  disposed = false;
const label = (code: string) => dims.labels[code] || code,
  marketName = (id: string) =>
    dims.markets.find((m) => String(m.id) === id)?.name || id;
const num = (v: number | null | undefined) =>
  v == null
    ? "Unavailable"
    : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const money = (v: number | null | undefined) =>
  v == null ? "Unavailable" : `IDR ${Math.round(v).toLocaleString("en-US")}`;
const signed = (v: number | null) =>
    v == null ? "Unavailable" : `${v > 0 ? "+" : ""}${num(v)}`,
  percent = (v: number | null) =>
    v == null ? "Unavailable" : `${v.toFixed(1)}%`;
const timestamp = (v: string | null | undefined) =>
  v
    ? new Date(v).toLocaleString("en-GB", {
        timeZone: "Asia/Makassar",
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Unavailable";
const dayLabel = (v: string) =>
  new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const message = (e: any) =>
  e?.response?.data?.message || e?.message || "Request failed";
const basisLabel = computed(() =>
  basis.value === "gross"
    ? "Gross quoted room-rate revenue (IDR only)"
    : "Estimated room-rate revenue net of breakfast and tax/service (IDR only)",
);
const revenue = (r: PaceRow) =>
    basis.value === "gross" ? r.revenue : r.netRevenue,
  currentRooms = (r: PaceRow) =>
    r.currentQuality === "unavailable" ? null : r.rooms;
const dirty = computed(
  () =>
    loaded.value && JSON.stringify(filters) !== JSON.stringify(loaded.value),
);
const comparisonLabel = computed(() =>
  loaded.value?.comparison === "custom"
    ? `Matched period from ${loaded.value.comparisonStart}`
    : loaded.value?.comparison === "calendar"
      ? "Same calendar date last year"
      : "Same weekday last year",
);
const forecastBusy = computed(() =>
  Object.values(forecast.value?.sections || {}).some((s) => s.refreshing),
);
function saveUrl() {
  router.replace({
    query: { ...(loaded.value || filters), tab: tab.value, basis: basis.value },
  });
}
function selectTab(id: string) {
  tab.value = id;
  saveUrl();
  if (id !== "data" && !loaded.value && !loading.value) void loadAll();
}
watch(basis, saveUrl);
function thisMonth() {
  filters.start = `${today.slice(0, 7)}-01`;
  filters.end = addDays(
    new Date(Date.UTC(Number(today.slice(0, 4)), Number(today.slice(5, 7)), 1))
      .toISOString()
      .slice(0, 10),
    -1,
  );
  void loadAll();
}
async function loadAll() {
  if (
    !filters.start ||
    !filters.end ||
    filters.end < filters.start ||
    (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000 >= 366
  ) {
    error.value = "Choose a valid range of at most 366 days.";
    return;
  }
  if (filters.comparison === "custom" && !filters.comparisonStart) {
    error.value = "Choose a comparison start date.";
    return;
  }
  const id = ++requestId,
    f = { ...filters };
  loading.value = true;
  error.value = "";
  clearTimeout(forecastTimer);
  try {
    const r = await axios.get("/api/rms/pace", { params: f, timeout: 120000 });
    if (disposed || id !== requestId) return;
    rows.value = r.data.rows;
    loaded.value = f;
    sync.value = r.data.sync;
    reportSync.value = r.data.sync;
    settings.value = r.data.settings;
    appliedSettings.value = JSON.parse(JSON.stringify(r.data.settings));
    notes.value = r.data.notes;
    bar.value = r.data.bar;
    closeDay();
    forecast.value = null;
    saveUrl();
    void loadForecast(id, f);
  } catch (e) {
    if (id === requestId) error.value = message(e);
  } finally {
    if (id === requestId) loading.value = false;
  }
}
async function loadForecast(id: number, f: Filters, refresh = false) {
  clearTimeout(forecastTimer);
  try {
    const days = Math.min(
      90,
      Math.round((Date.parse(f.end) - Date.parse(f.start)) / 86400000) + 1,
    );
    const r = await axios.get("/api/rms/forecast", {
      params: { start: f.start, days, refresh: refresh ? "1" : undefined },
    });
    if (disposed || id !== requestId) return;
    forecast.value = r.data;
    if (forecastBusy.value)
      forecastTimer = setTimeout(() => loadForecast(id, f), 2000);
  } catch (e) {
    if (id === requestId && !disposed) error.value = message(e);
  }
}
function refreshForecast() {
  if (loaded.value) void loadForecast(requestId, loaded.value, true);
}
async function pollSync() {
  try {
    const r = await axios.get("/api/rms/sync");
    if (disposed) return;
    sync.value = r.data;
  } catch (e) {
    if (!disposed) error.value = message(e);
  }
  if (!disposed)
    syncTimer = setTimeout(pollSync, sync.value?.job.running ? 2000 : 30000);
}
async function runSync(kind: string) {
  try {
    const r = await axios.post("/api/rms/sync", {
      kind,
      backfillDays: backfillYears.value * 365,
    });
    sync.value = r.data;
    clearTimeout(syncTimer);
    void pollSync();
  } catch (e) {
    error.value = message(e);
  }
}
async function saveSettings() {
  settingsSaving.value = true;
  settingsMessage.value = "";
  try {
    const r = await axios.put("/api/rms/settings", settings.value);
    settings.value = r.data.settings;
    settingsMessage.value = "Saved. Apply the report to recalculate.";
  } catch (e) {
    error.value = message(e);
  } finally {
    settingsSaving.value = false;
  }
}
function closeDay() {
  selectedDate.value = "";
  curve.value = null;
  ++curveId;
}
async function openDay(day: string) {
  const id = ++curveId;
  selectedDate.value = day;
  noteDraft.value = notes.value[day]?.text || "";
  curve.value = null;
  curveLoading.value = true;
  curveError.value = "";
  await nextTick();
  detailElement.value?.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const r = await axios.get("/api/rms/pace/curve", {
      params: { ...loaded.value, date: day, maxLead: 180 },
      timeout: 120000,
    });
    if (id === curveId && !disposed) curve.value = r.data;
  } catch (e) {
    if (id === curveId) curveError.value = message(e);
  } finally {
    if (id === curveId) curveLoading.value = false;
  }
}
async function saveNote() {
  const day = selectedDate.value,
    text = noteDraft.value;
  noteSaving.value = true;
  try {
    const r = await axios.put(`/api/rms/notes/${day}`, { text });
    notes.value[day] = r.data.note;
  } catch (e) {
    error.value = message(e);
  } finally {
    noteSaving.value = false;
  }
}
const idrCoverage = computed(() => {
  const r = ratio(
    rows.value.reduce((s, r) => s + r.idrRooms, 0),
    rows.value.reduce((s, r) => s + r.rooms, 0),
  );
  return r == null ? null : r * 100;
});
const hotelMap = computed(() =>
    Object.fromEntries((forecast.value?.hotel || []).map((r) => [r.date, r])),
  ),
  availabilityMap = computed(() =>
    Object.fromEntries(
      (forecast.value?.availability || []).map((r) => [r.date, r.values]),
    ),
  );
const capacities = computed(() => {
  const m: Record<string, number> = {};
  if (loaded.value?.roomType) {
    for (const r of forecast.value?.roomTypes || [])
      if (r.typeId === loaded.value.roomType) m[r.date] = r.roomCount;
  } else
    for (const r of forecast.value?.hotel || [])
      if (r.roomCount != null) m[r.date] = r.roomCount;
  return m;
});
const attention = computed(() =>
  rows.value.map((r) => {
    const h = hotelMap.value[r.date],
      a = availabilityMap.value[r.date],
      otb = currentRooms(r),
      occ = ratio(otb, capacities.value[r.date] ?? null),
      occupancy = occ == null ? null : occ * 100,
      gap = difference(otb, r.stlyRooms),
      t = appliedSettings.value?.thresholds,
      reasons: string[] = [];
    if (otb == null) reasons.push("Booking coverage unavailable");
    if (reportSync.value?.stale) reasons.push("Stale booking data");
    if (reportSync.value?.lastSuccessfulSync !== sync.value?.lastSuccessfulSync)
      reasons.push("Booking data changed — apply again");
    if (t && occupancy != null && occupancy >= t.occupancy)
      reasons.push("High occupancy");
    if (
      t &&
      gap != null &&
      gap <= -t.behindRooms &&
      r.pickupRooms != null &&
      r.pickupRooms < t.weakPickup
    )
      reasons.push("Behind pace; weak pickup");
    const available = a?.[loaded.value?.roomType || "RoomAvailable"] ?? null;
    if (available != null && available < 0)
      reasons.push("Negative physical availability");
    const reconciliation =
      !loaded.value?.roomType && !loaded.value?.marketId && h
        ? difference(otb, h.roomsSold)
        : null;
    if (reconciliation != null && reconciliation !== 0)
      reasons.push("Check booking/PMS room difference");
    if (r.comparisonQuality === "unavailable")
      reasons.push("Comparison unavailable");
    return {
      ...r,
      otb,
      occupancy,
      gap,
      available,
      reconciliation,
      reasons,
      bar: Object.entries(bar.value.byDate[r.date] || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join("; "),
    };
  }),
);
const attentionRows = computed(() =>
  attention.value.filter((r) => !onlyAttention.value || r.reasons.length),
);
const months = computed(() =>
  monthlySummary(
    rows.value,
    basis.value,
    appliedSettings.value?.budgets || [],
    loaded.value?.marketId ? {} : capacities.value,
    today,
    !!loaded.value?.roomType || !!loaded.value?.marketId,
  ),
);
const tiles = computed(() => {
  const known =
    rows.value.length &&
    rows.value.every((r) => r.currentQuality !== "unavailable");
  return [
    {
      label: "OTB room nights",
      value: num(known ? rows.value.reduce((s, r) => s + r.rooms, 0) : null),
    },
    {
      label:
        basis.value === "gross"
          ? "Gross IDR revenue"
          : "Estimated net IDR revenue",
      value: money(
        known ? rows.value.reduce((s, r) => s + revenue(r), 0) : null,
      ),
    },
    {
      label: `Net pickup (${loaded.value?.pickupDays || 7}d)`,
      value: signed(
        rows.value.length
          ? sumKnown(rows.value.map((r) => r.pickupRooms))
          : null,
      ),
    },
    {
      label: "IDR ADR coverage",
      value: percent(known ? idrCoverage.value : null),
    },
  ];
});
const segmentTotals = computed(() => {
  const m = new Map<
    string,
    { market: string; rooms: number; revenue: number }
  >();
  for (const s of forecast.value?.segments || []) {
    const r = m.get(s.market) || { market: s.market, rooms: 0, revenue: 0 };
    r.rooms += s.rooms || 0;
    r.revenue += s.revenue || 0;
    m.set(s.market, r);
  }
  return [...m.values()].sort((a, b) => b.rooms - a.rooms);
});
const matrix = computed(() => {
  const types = new Map<
    string,
    { typeId: string; capacity: number; values: Record<string, number> }
  >();
  for (const r of forecast.value?.roomTypes || []) {
    const t = types.get(r.typeId) || {
      typeId: r.typeId,
      capacity: r.roomCount,
      values: {},
    };
    t.values[r.date] = r.rooms;
    types.set(r.typeId, t);
  }
  return {
    dates: [
      ...new Set((forecast.value?.roomTypes || []).map((r) => r.date)),
    ].sort(),
    types: [...types.values()],
  };
});
const selectedAvailability = computed(() =>
    Object.entries(availabilityMap.value[selectedDate.value] || {})
      .filter(([k]) => k in dims.labels || dims.roomTypes.includes(k))
      .map(([type, rooms]) => ({ type, rooms })),
  ),
  selectedSegments = computed(() =>
    (forecast.value?.segments || []).filter(
      (r) => r.date === selectedDate.value,
    ),
  );
const buckets = computed(() => {
  const m = new Map<string, PaceRow[]>();
  for (const r of rows.value) {
    let key = r.date;
    if (chartView.value === "monthly") key = key.slice(0, 7);
    if (chartView.value === "weekly")
      key = addDays(key, -((new Date(`${key}T00:00:00Z`).getUTCDay() + 6) % 7));
    m.set(key, [...(m.get(key) || []), r]);
  }
  return [...m].map(([key, rs]) => ({
    key,
    rooms: sumKnown(rs.map(currentRooms)),
    comparison: sumKnown(rs.map((r) => r.stlyRooms)),
    adr: ratio(
      sumKnown(rs.map((r) => (currentRooms(r) == null ? null : revenue(r)))),
      rs.reduce((s, r) => s + r.idrRooms, 0),
    ),
    comparisonAdr: ratio(
      sumKnown(
        rs.map((r) =>
          basis.value === "gross" ? r.stlyRevenue : r.stlyNetRevenue,
        ),
      ),
      sumKnown(rs.map((r) => r.stlyIdrRooms)),
    ),
  }));
});
const chartData = computed(() => ({
  labels: buckets.value.map((b) => b.key),
  datasets: [
    {
      type: "bar" as const,
      label: "OTB room nights",
      data: buckets.value.map((b) => b.rooms),
      backgroundColor: "#334155",
      yAxisID: "rooms",
      order: 2,
    },
    {
      type: "bar" as const,
      label: "Comparison nights",
      data: buckets.value.map((b) => b.comparison),
      backgroundColor: "#cbd5e1",
      yAxisID: "rooms",
      order: 2,
    },
    {
      type: "line" as const,
      label: "IDR ADR",
      data: buckets.value.map((b) => b.adr),
      borderColor: "#0f766e",
      yAxisID: "adr",
      order: 1,
    },
    {
      type: "line" as const,
      label: "Comparison ADR",
      data: buckets.value.map((b) => b.comparisonAdr),
      borderColor: "#64748b",
      borderDash: [4, 4],
      yAxisID: "adr",
      order: 1,
    },
  ],
}));
const chartOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    rooms: {
      position: "left",
      beginAtZero: true,
      title: { display: true, text: "Room nights" },
    },
    adr: {
      position: "right",
      grid: { drawOnChartArea: false },
      title: { display: true, text: "ADR (IDR)" },
    },
  },
};
const curveData = computed(() => {
  const c = curve.value,
    leads = Array.from(
      { length: (c?.maxLead || 180) + 1 },
      (_, i) => (c?.maxLead || 180) - i,
    ),
    point = (pts: CurvePoint[], lead: number) =>
      pts.find((p) => p.lead === lead)?.rooms ?? null;
  return {
    labels: leads.map((l) => (l === c?.todayLead ? `${l} · Today` : String(l))),
    datasets: [
      {
        label: "Current observed / reconstructed",
        data: leads.map((l) => point(c?.current || [], l)),
        borderColor: "#0f766e",
        pointRadius: 0,
        spanGaps: false,
      },
      {
        label: "Comparison observed / reconstructed",
        data: leads.map((l) => point(c?.lastYear || [], l)),
        borderColor: "#94a3b8",
        borderDash: [4, 4],
        pointRadius: 0,
        spanGaps: false,
      },
    ],
  };
});
const todayMarker = {
  id: "rms-today",
  afterDraw(chart: ChartJS) {
    const c = curve.value;
    if (!c || c.todayLead < 0 || c.todayLead > c.maxLead) return;
    const x = chart.scales.x.getPixelForValue(c.maxLead - c.todayLead);
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = "#0f766e";
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.stroke();
    ctx.fillStyle = "#0f766e";
    ctx.textAlign = x > chartArea.right - 50 ? "right" : "left";
    ctx.fillText("Today", x, chartArea.top + 12);
    ctx.restore();
  },
};
const curveOptions: ChartOptions<keyof ChartTypeRegistry> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  scales: {
    x: {
      title: { display: true, text: "Days before stay date" },
      ticks: { maxTicksLimit: 10 },
    },
    y: { beginAtZero: true, title: { display: true, text: "Room nights" } },
  },
};
function exportCsv() {
  const out: unknown[][] = [
    [
      "Stay date",
      "Comparison date",
      "Room type",
      "Market",
      "Revenue basis",
      "OTB rooms",
      "IDR revenue",
      "IDR ADR",
      "New rooms",
      "Cancelled rooms",
      "Amended rooms",
      "Net pickup",
      "Comparison rooms",
      "Current quality",
      "Comparison quality",
      "Pickup quality",
      "Last successful sync",
      "Note",
    ],
  ];
  for (const r of rows.value)
    out.push([
      r.date,
      r.lyDate,
      loaded.value?.roomType || "All",
      loaded.value?.marketId || "All",
      basisLabel.value,
      currentRooms(r),
      currentRooms(r) == null ? null : revenue(r),
      currentRooms(r) == null ? null : ratio(revenue(r), r.idrRooms),
      r.newRooms,
      r.cancelledRooms,
      r.amendedRooms,
      r.pickupRooms,
      r.stlyRooms,
      r.currentQuality,
      r.comparisonQuality,
      r.pickupQuality,
      reportSync.value?.lastSuccessfulSync,
      notes.value[r.date]?.text || "",
    ]);
  const url = URL.createObjectURL(
      new Blob([csvText(out)], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = `rms-${loaded.value?.start}-${loaded.value?.end}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
onMounted(async () => {
  void pollSync();
  try {
    const [d, s] = await Promise.all([
      axios.get("/api/rms/room-types"),
      axios.get("/api/rms/settings"),
    ]);
    if (disposed) return;
    Object.assign(dims, d.data);
    settings.value = s.data.settings;
    appliedSettings.value = JSON.parse(JSON.stringify(s.data.settings));
  } catch (e) {
    error.value = message(e);
  }
  if (!disposed && tab.value !== "data") void loadAll();
});
onBeforeUnmount(() => {
  disposed = true;
  ++requestId;
  ++curveId;
  clearTimeout(forecastTimer);
  clearTimeout(syncTimer);
});
</script>
