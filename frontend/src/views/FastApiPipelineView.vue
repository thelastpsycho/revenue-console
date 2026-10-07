<template>
  <div class="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
    <PageHeader
      title="Fast API Pipeline"
      subtitle="Same scrape-to-BAR-pricing pipeline, but PMS steps call its JSON API directly instead of driving a browser. D-EDGE steps still use Chrome (no D-EDGE API)."
    />

    <!-- Tabs. Panels use v-show so switching never loses unsaved input
         (schedule edits, a half-picked hold range) or the live log. -->
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
        <span v-if="tab.id === 'run' && isRunning" class="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" title="Run in progress" />
        <span v-if="tab.id === 'automation' && dedgeAuth?.pending" class="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" title="D-EDGE needs a device code" />
      </button>
    </div>

    <!-- ===== Run ===== -->
    <div v-show="activeTab === 'run'" class="grid grid-cols-1 gap-4 xl:grid-cols-12">
      <!-- Setup -->
      <div class="neu-card divide-y divide-slate-100 xl:col-span-5">
        <section class="p-4">
          <h2 class="text-sm font-semibold text-app-tertiary">Steps</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">Untick a step to skip it this run.</p>
          <div class="mt-3 grid grid-cols-2 gap-1.5">
            <label
              v-for="step in stepStates"
              :key="step.id"
              :class="['flex cursor-pointer items-center gap-2 rounded-lg bg-app-primary px-2.5 py-1.5 text-xs shadow-neu-inset-sm', !stepEnabled[step.id] && 'opacity-50']"
            >
              <input
                type="checkbox"
                class="h-3 w-3 cursor-pointer accent-app-accent disabled:cursor-not-allowed"
                :checked="stepEnabled[step.id]"
                :disabled="isRunning"
                @change="toggleStep(step.id)"
              />
              <span class="font-semibold text-slate-600">{{ step.label }}</span>
            </label>
          </div>
        </section>

        <section class="grid grid-cols-2 items-end gap-3 p-4">
          <div>
            <label for="fp-start-date" class="mb-1 block text-xs font-semibold text-slate-600">Start date</label>
            <input id="fp-start-date" v-model="startDate" type="date" class="neu-input disabled:opacity-60" :disabled="isRunning" />
          </div>
          <label class="inline-flex cursor-pointer items-center gap-2 pb-2 text-xs font-semibold text-slate-500" title="Only affects the D-EDGE Chrome steps - PMS steps never open a browser. Always headless in Docker.">
            <button
              type="button"
              role="switch"
              :aria-checked="headless"
              :disabled="isRunning"
              @click="headless = !headless"
              :class="[
                'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full shadow-neu-inset-sm transition-colors disabled:opacity-50',
                headless ? 'bg-app-accent' : 'bg-app-primary',
              ]"
            >
              <span :class="['inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-neu-sm transition-transform', headless ? 'translate-x-[20px]' : 'translate-x-0.5']" />
            </button>
            Headless (D-EDGE)
          </label>
        </section>

        <!-- Allotment push -->
        <section v-if="stepEnabled.allotment" class="space-y-3 p-4 text-xs text-slate-600">
          <h2 class="text-sm font-semibold text-app-tertiary">Allotment push</h2>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div class="inline-flex rounded-lg bg-app-primary p-0.5 shadow-neu-inset-sm">
              <button
                type="button"
                title="Builds every payload and logs in, but never calls the PMS save endpoint."
                :disabled="isRunning"
                @click="allotmentDryRun = true"
                :class="['rounded-md px-3 py-1 font-semibold transition-all disabled:opacity-50', allotmentDryRun ? 'bg-app-primary text-app-accent shadow-neu-sm' : 'text-slate-500']"
              >
                Dry run
              </button>
              <button
                type="button"
                title="Actually writes allotment changes to the live PMS."
                :disabled="isRunning"
                @click="allotmentDryRun = false"
                :class="['rounded-md px-3 py-1 font-semibold transition-all disabled:opacity-50', !allotmentDryRun ? 'bg-rose-600 text-white shadow-neu-sm' : 'text-slate-500']"
              >
                Live
              </button>
            </div>
            <label class="inline-flex cursor-pointer items-center gap-1.5" title="Compares against the current channel-manager value and skips dates that already match, instead of always pushing every date.">
              <input type="checkbox" v-model="skipUnchanged" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Skip unchanged dates
            </label>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="mb-1 block font-semibold">Concurrency</span>
              <input v-model.number="allotmentConcurrency" type="number" min="1" max="20" :disabled="isRunning" class="neu-input py-1 disabled:opacity-60" />
            </label>
            <label class="block">
              <span class="mb-1 block font-semibold">Company ID</span>
              <input v-model.number="companyId" type="number" :disabled="isRunning" class="neu-input py-1 disabled:opacity-60" />
            </label>
          </div>
          <div>
            <div class="flex items-center justify-between gap-2">
              <span class="font-semibold">Room types <span class="font-normal text-slate-500">({{ allotmentRoomTypes.length }}/{{ roomTypeConfig.length }})</span></span>
              <span class="flex gap-1">
                <button type="button" @click="setAllRoomTypes(true)" :disabled="isRunning" class="rounded px-1.5 py-0.5 font-semibold text-app-accent hover:bg-slate-100 disabled:opacity-50">All</button>
                <button type="button" @click="setAllRoomTypes(false)" :disabled="isRunning" class="rounded px-1.5 py-0.5 font-semibold text-slate-500 hover:bg-slate-100 disabled:opacity-50">None</button>
              </span>
            </div>
            <div class="mt-1.5 grid grid-cols-1 gap-x-3 gap-y-1 rounded-lg bg-app-primary p-2.5 shadow-neu-inset-sm sm:grid-cols-2">
              <label v-for="rt in roomTypeConfig" :key="rt.key" class="inline-flex cursor-pointer items-center gap-1.5 text-[11px]">
                <input type="checkbox" :value="rt.key" v-model="allotmentRoomTypes" :disabled="isRunning" class="h-3 w-3 accent-app-accent" />
                {{ rt.label }}
              </label>
            </div>
          </div>
          <p v-if="allotmentNeedsAllRoomYield && stepEnabled.yield && !includeAllRoomTypes" class="rounded-lg bg-app-primary px-3 py-2 font-semibold text-amber-700 shadow-neu-inset-sm">
            You've selected a room type beyond Deluxe/Premiere, but "Calculate allocations for all room categories" is off in Settings → Yield configuration - those types will have no Online Inventory to push.
          </p>
          <p v-if="!allotmentDryRun" class="rounded-lg bg-app-primary px-3 py-2 font-semibold text-rose-700 shadow-neu-inset-sm">
            Live mode pushes real allotment changes to the PMS for every {{ allotmentRoomLabels.join(', ') || '(no room types selected)' }} date range that differs from the channel manager.
          </p>
        </section>

        <!-- BAR pricing -->
        <section v-if="stepEnabled.bar" class="space-y-2 p-4 text-xs text-slate-600">
          <h2 class="text-sm font-semibold text-app-tertiary">BAR pricing (D-EDGE)</h2>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span class="font-semibold">Rooms</span>
            <label class="inline-flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" v-model="barRooms.deluxe" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Deluxe
            </label>
            <label class="inline-flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" v-model="barRooms.premiere" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Premiere
            </label>
            <label class="inline-flex cursor-pointer items-center gap-1.5" title="Compares against the BAR level we last successfully pushed and skips dates that already match, instead of always pushing every date.">
              <input type="checkbox" v-model="barSkipUnchanged" :disabled="isRunning" class="h-3 w-3 accent-app-accent" /> Skip unchanged dates
            </label>
          </div>
          <p class="text-[11px] text-slate-500">
            BAR always pushes live - there is no dry run. Dates on hold are skipped;
            <button type="button" class="font-semibold text-app-accent underline-offset-2 hover:underline" @click="selectTab('automation')">manage hold dates</button>.
          </p>
          <label class="inline-flex items-start gap-2 text-amber-800">
            <input v-model="resetCheckpoint" type="checkbox" :disabled="isRunning" class="mt-0.5 accent-app-accent" />
            <span>Start a fresh BAR batch (discard partial-run checkpoint). Check existing D-EDGE changes before selecting.</span>
          </label>
        </section>

        <section class="p-4">
          <button @click="openStartConfirm" :disabled="isRunning" class="btn-primary w-full px-5 py-2.5">
            <svg v-if="isRunning" class="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <BoltIcon v-else class="h-4 w-4" />
            {{ isRunning ? 'Pipeline running…' : (stepEnabled.allotment && !allotmentDryRun ? 'Start pipeline (LIVE allotment push)' : 'Start pipeline') }}
          </button>
          <div v-if="configError" class="mt-3 rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
            {{ configError }}
          </div>
        </section>
      </div>

      <!-- Progress + log -->
      <div class="neu-card flex flex-col p-4 xl:col-span-7">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold text-app-tertiary">Progress</h2>
            <p class="mt-0.5 text-xs text-slate-500">{{ progressLabel }}</p>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex items-center gap-2">
              <div class="h-1.5 w-24 overflow-hidden rounded-full bg-app-primary shadow-neu-inset-sm">
                <div class="h-full rounded-full transition-all" :class="progressBarColor" :style="{ width: progressPercent + '%' }" />
              </div>
              <span class="text-[11px] font-semibold text-slate-500">{{ progressPercent }}%</span>
            </div>
            <button
              v-if="isRunning"
              type="button"
              @click="requestStop"
              :disabled="stopping"
              title="Best-effort - it only interrupts between steps (not mid-scrape or mid-push)."
              class="rounded-lg bg-app-primary px-2.5 py-1 text-xs font-semibold text-rose-600 shadow-neu-sm transition-all hover:text-rose-700 active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer"
            >
              Stop
            </button>
            <span
              :class="[
                'inline-flex items-center gap-1.5 rounded-full bg-app-primary px-2.5 py-1 text-[11px] font-semibold shadow-neu-inset-sm',
                isRunning ? 'text-amber-700' : overallError ? 'text-rose-700' : overallSuccess ? 'text-emerald-700' : 'text-slate-500',
              ]"
            >
              <span :class="['h-1.5 w-1.5 rounded-full', isRunning ? 'bg-amber-500 animate-pulse' : overallError ? 'bg-rose-500' : overallSuccess ? 'bg-emerald-500' : 'bg-slate-400']" />
              {{ isRunning ? 'Running' : overallError ? 'Failed' : overallSuccess ? 'Success' : 'Ready' }}
            </span>
          </div>
        </div>

        <!-- Read-only stepper: status of each step this run -->
        <div class="mt-3 flex flex-wrap items-center gap-1.5">
          <template v-for="(step, index) in stepStates" :key="step.id">
            <span
              class="flex items-center gap-1.5 rounded-full bg-app-primary py-1 pl-1.5 pr-2.5 shadow-neu-inset-sm"
              :class="{ 'ring-1 ring-app-accent/40': step.status === 'running', 'opacity-40': !stepEnabled[step.id] }"
              :title="stepEnabled[step.id] ? step.label : `${step.label} (skipped)`"
            >
              <span v-if="step.status === 'running'" class="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-200 border-t-app-accent" />
              <CheckCircleIcon v-else-if="step.status === 'success'" class="h-3.5 w-3.5 shrink-0 text-emerald-600" />
              <MinusCircleIcon v-else-if="step.status === 'skipped'" class="h-3.5 w-3.5 shrink-0 text-slate-400" />
              <XCircleIcon v-else-if="step.status === 'error'" class="h-3.5 w-3.5 shrink-0 text-rose-600" />
              <span v-else class="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-300" />
              <span class="text-[11px] font-semibold text-slate-600">{{ step.label }}</span>
            </span>
            <span v-if="index < stepStates.length - 1" class="h-px w-2 shrink-0 bg-slate-300" />
          </template>
        </div>

        <div class="mb-2 mt-4 flex items-center justify-between">
          <h3 class="text-xs font-semibold text-slate-600">Process log</h3>
          <button
            @click="clearLogs"
            :disabled="isRunning"
            class="rounded-lg bg-app-primary px-2.5 py-1 text-xs font-semibold text-slate-500 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm disabled:opacity-50 cursor-pointer"
          >
            Clear logs
          </button>
        </div>
        <div ref="logContainer" class="h-96 overflow-y-auto rounded-xl bg-app-primary p-4 shadow-neu-inset xl:h-auto xl:min-h-[28rem] xl:flex-1">
          <div v-if="logs.length === 0" class="py-8 text-center text-sm text-slate-500">
            No logs yet. Start the pipeline to see live progress. Scheduled runs log to
            <router-link to="/fast-pipeline-history" class="font-semibold text-app-accent hover:underline">Pipeline History</router-link>.
          </div>
          <div v-else class="space-y-1.5">
            <div
              v-for="(log, index) in logs"
              :key="index"
              class="flex items-start gap-2 font-mono text-xs"
              :class="{
                'text-app-accent': log.type === 'info',
                'text-emerald-700': log.type === 'success',
                'text-rose-600': log.type === 'error',
                'text-slate-400': log.type === 'skipped',
              }"
            >
              <span class="text-slate-500">{{ formatTime(log.timestamp) }}</span>
              <span v-if="log.step" class="shrink-0 rounded bg-app-primary px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 shadow-neu-inset-sm">{{ stepLabel(log.step) }}</span>
              <span class="flex-1 whitespace-pre-wrap break-words">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== Automation ===== -->
    <div v-show="activeTab === 'automation'" class="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
      <PipelineScheduleCard :page-config="buildScheduleConfig" :step-label="stepLabel" />
      <div class="space-y-4">
        <DedgeSessionCard />
        <BarHoldDatesCard />
      </div>
    </div>

    <!-- ===== Settings ===== -->
    <div v-show="activeTab === 'settings'" class="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
      <div class="neu-card p-4">
        <h2 class="text-sm font-semibold text-app-tertiary">Credentials</h2>
        <p class="mt-0.5 text-[11px] text-slate-500">For manual runs. Leave blank to use the credentials saved on the server (scheduled runs always use those).</p>
        <div class="mt-3 space-y-3">
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="mb-1 block text-xs font-semibold text-slate-600">PMS username</label>
              <input v-model="pmsUsername" type="text" autocomplete="username" class="neu-input disabled:opacity-60" :disabled="isRunning" />
            </div>
            <div>
              <label class="mb-1 block text-xs font-semibold text-slate-600">PMS password</label>
              <input v-model="pmsPassword" type="password" autocomplete="current-password" class="neu-input disabled:opacity-60" :disabled="isRunning" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="mb-1 block text-xs font-semibold text-slate-600">D-EDGE username</label>
              <input v-model="dedgeUsername" type="text" autocomplete="off" class="neu-input disabled:opacity-60" :disabled="isRunning" />
            </div>
            <div>
              <label class="mb-1 block text-xs font-semibold text-slate-600">D-EDGE password</label>
              <input v-model="dedgePassword" type="password" autocomplete="off" class="neu-input disabled:opacity-60" :disabled="isRunning" />
            </div>
          </div>
        </div>
      </div>

      <div class="neu-card p-4">
        <h2 class="text-sm font-semibold text-app-tertiary">
          Yield configuration
          <span class="ml-1 text-xs font-normal text-slate-500">(same as Yield Management page)</span>
        </h2>
        <div class="mt-3 space-y-3">
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>
              <label class="block text-xs font-semibold text-slate-600">Demand bins</label>
              <input v-model="yieldForm.demand_bins" type="text" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" placeholder="[0, 70, 85, 100]" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600">Demand labels</label>
              <input v-model="yieldForm.demand_labels" type="text" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" placeholder="['Low', 'Medium', 'High']" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-xs font-semibold text-slate-600">Very low (%)</label>
              <input v-model.number="yieldForm.very_low_threshold_pct" type="number" step="0.01" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600">Low (%)</label>
              <input v-model.number="yieldForm.low_threshold_pct" type="number" step="0.01" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-xs font-semibold text-slate-600">Deluxe rooms</label>
              <input v-model.number="yieldForm.room_caps['Deluxe Room']" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600">Premiere rooms</label>
              <input v-model.number="yieldForm.room_caps['Premiere Room']" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
            </div>
          </div>
          <div>
            <p class="text-xs font-semibold text-slate-600">Deluxe override</p>
            <div class="mt-1 grid grid-cols-3 gap-2">
              <div>
                <label class="block text-[11px] text-slate-500">Occupancy (%)</label>
                <input v-model.number="yieldForm.deluxe_override_occupancy" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="block text-[11px] text-slate-500">Premiere min</label>
                <input v-model.number="yieldForm.deluxe_override_premiere" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
              <div>
                <label class="block text-[11px] text-slate-500">Amount</label>
                <input v-model.number="yieldForm.deluxe_override_amount" type="number" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
              </div>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-xs font-semibold text-slate-600">BAR shift levels</label>
              <input v-model.number="yieldForm.bar_level_shift" type="number" step="1" class="neu-input mt-1 disabled:opacity-60" :disabled="isRunning" />
            </div>
          </div>
          <label class="flex items-start gap-2 text-xs text-slate-600">
            <input v-model="includeAllRoomTypes" type="checkbox" :disabled="isRunning" class="mt-0.5 accent-app-accent" />
            <span>
              Calculate allocations for all room categories
              <span class="block text-[11px] font-normal text-slate-500">Required for the allotment step to push anything beyond Deluxe/Premiere - without this, the other room types' Online Inventory won't be written and their allotment jobs will be empty.</span>
            </span>
          </label>
        </div>
      </div>
    </div>

    <!-- Confirm-before-start modal, same overlay pattern as InventoryCollectionView.vue -->
    <div v-if="showStartConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-500/20 p-4 backdrop-blur-sm">
      <div class="relative flex max-h-[85vh] w-full max-w-lg flex-col rounded-xl bg-app-primary p-6 shadow-neu">
        <button @click="showStartConfirm = false" class="btn-icon absolute right-4 top-4 !p-2">
          <XMarkIcon class="h-5 w-5" />
        </button>
        <h3 class="flex shrink-0 items-center gap-2 font-semibold text-base text-app-tertiary">
          <ExclamationTriangleIcon v-if="confirmIsLive" class="h-5 w-5 shrink-0 text-amber-600" />
          Confirm this pipeline run
        </h3>
        <p class="mt-1 shrink-0 text-sm text-slate-500">Check the scope below before it starts — this can't be recalled once live steps begin.</p>

        <div class="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
          <div class="space-y-2.5 rounded-xl bg-app-primary p-4 text-sm shadow-neu-inset">
            <p><span class="font-semibold text-slate-600">Date range:</span> {{ confirmDateRangeText }}</p>
            <p v-if="confirmAllotmentLine" :class="stepEnabled.allotment && !allotmentDryRun && allotmentRoomTypes.length ? 'font-semibold text-rose-700' : 'text-slate-600'">
              {{ confirmAllotmentLine }}
            </p>
            <p v-else class="text-slate-500">Allotment: step is off — no PMS allotment changes.</p>

            <div v-if="stepEnabled.allotment && allotmentRoomTypes.length" class="rounded-lg bg-app-primary p-3 text-xs shadow-neu-inset-sm">
              <div v-if="allotmentPlanLoading" class="flex items-center gap-2 text-slate-500">
                <span class="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-app-accent"></span>
                Building batch preview from the current inventory_allocation.db…
              </div>
              <div v-else-if="allotmentPlanError" class="text-slate-500">{{ allotmentPlanError }}</div>
              <div v-else-if="allotmentPlanPreview">
                <p class="font-semibold text-slate-600">
                  Batch preview: {{ allotmentPlanPreview.totalJobs }} job(s) — one PMS call per contiguous date range
                  <span v-if="allotmentPlanPreview.skippedRanges">, {{ allotmentPlanPreview.skippedRanges }} range(s) skipped (already match CM)</span>
                </p>
                <p v-if="upstreamStepsWillRecalculate" class="mt-1 text-[11px] text-amber-700">
                  Scrape/combine/yield will run first and can change these counts — this preview is from the last calculation, not this run's.
                </p>
                <ul class="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-600 sm:grid-cols-3">
                  <li v-for="(info, key) in allotmentPlanPreview.byRoomType" :key="key" class="flex justify-between gap-2">
                    <span>{{ info.label }}</span>
                    <span class="font-semibold">{{ info.job_count }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <p v-if="confirmBarLine" :class="confirmBarRoomLabels.length ? 'font-semibold text-rose-700' : 'text-slate-600'">
              {{ confirmBarLine }}
            </p>
            <p v-else class="text-slate-500">BAR pricing: step is off — no D-EDGE price changes.</p>
          </div>

          <p v-if="confirmIsLive" class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-rose-700 shadow-neu-inset-sm">
            This will make LIVE changes to the PMS and/or D-EDGE. Double-check the room types and date range above before continuing.
          </p>
          <p v-else class="rounded-lg bg-app-primary px-3 py-2 text-xs font-semibold text-emerald-700 shadow-neu-inset-sm">
            No live PMS or D-EDGE changes will be sent by this run.
          </p>
        </div>

        <div class="mt-5 flex shrink-0 gap-3">
          <button
            @click="showStartConfirm = false"
            class="flex-1 rounded-xl bg-app-primary px-4 py-2.5 text-sm font-semibold text-slate-600 shadow-neu-sm transition-all hover:text-app-accent active:shadow-neu-inset-sm"
          >
            Cancel
          </button>
          <button
            @click="confirmAndStartPipeline"
            :class="confirmIsLive ? 'bg-rose-600 hover:bg-rose-700' : 'bg-app-accent hover:brightness-110'"
            class="flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-neu-sm transition-colors"
          >
            {{ confirmIsLive ? 'Yes, start LIVE run' : 'Start pipeline' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from '../plugins/axios'
import PageHeader from '../components/PageHeader.vue'
import PipelineScheduleCard, { type ScheduleRunConfig } from '../components/PipelineScheduleCard.vue'
import DedgeSessionCard from '../components/DedgeSessionCard.vue'
import BarHoldDatesCard from '../components/BarHoldDatesCard.vue'
import { useDedgeAuth } from '../composables/useDedgeAuth'
import { usePipelineStream, type PipelineStepDef } from '../composables/usePipelineStream'
import { todayLocalDateString } from '../utils/date'
import {
  BoltIcon,
  CheckCircleIcon,
  XCircleIcon,
  MinusCircleIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
  PlayIcon,
  ClockIcon,
  Cog6ToothIcon,
} from '@heroicons/vue/24/outline'

// Run = set up and start a manual run; Automation = what happens without
// anyone here (schedule, BAR holds, D-EDGE session); Settings = rarely
// changed inputs. The tab is kept in ?tab= so it survives a reload.
type TabId = 'run' | 'automation' | 'settings'
const TABS: { id: TabId; name: string; icon: Component }[] = [
  { id: 'run', name: 'Run', icon: PlayIcon },
  { id: 'automation', name: 'Automation', icon: ClockIcon },
  { id: 'settings', name: 'Settings', icon: Cog6ToothIcon },
]
const route = useRoute()
const router = useRouter()
const activeTab = ref<TabId>(TABS.some(t => t.id === route.query.tab) ? route.query.tab as TabId : 'run')
function selectTab(id: TabId) {
  activeTab.value = id
  router.replace({ query: { ...route.query, tab: id === 'run' ? undefined : id } })
}
const { status: dedgeAuth } = useDedgeAuth()

const PIPELINE_STEPS: PipelineStepDef[] = [
  { id: 'scrape_pms', label: 'Scrape PMS (API)' },
  { id: 'scrape_cm', label: 'Scrape CM' },
  { id: 'combine', label: 'Combine' },
  { id: 'yield', label: 'Yield' },
  { id: 'verify', label: 'Verify' },
  { id: 'allotment', label: 'Allotment (API)' },
  { id: 'verify_allotment', label: 'Verify push' },
  { id: 'bar', label: 'BAR' },
]
const STEP_LABEL_BY_ID = Object.fromEntries(PIPELINE_STEPS.map(s => [s.id, s.label]))
const stepLabel = (id: string) => STEP_LABEL_BY_ID[id] || id

const { stepStates, logs, isRunning, overallError, overallSuccess, start } = usePipelineStream(PIPELINE_STEPS)

const stepEnabled = ref<Record<string, boolean>>(
  Object.fromEntries(PIPELINE_STEPS.map(s => [s.id, true]))
)
function toggleStep(id: string) {
  if (isRunning.value) return
  stepEnabled.value[id] = !stepEnabled.value[id]
}

const allotmentDryRun = ref(true)
const allotmentConcurrency = ref(4)
const companyId = ref(1001)
const barRooms = ref({ deluxe: true, premiere: true })
const resetCheckpoint = ref(false)
const skipUnchanged = ref(true)
const barSkipUnchanged = ref(true)

// Room types available for the allotment push, fetched from the same config
// the PMS API test page uses so this list can't drift from the backend's
// FULL_ROOM_TYPE_CONFIG. Defaults to all 13 selected; unchecking any lets you
// skip that category for this run.
const roomTypeConfig = ref<{ key: string; label: string; checkboxValue: string }[]>([])
const allotmentRoomTypes = ref<string[]>([])
onMounted(async () => {
  try {
    const res = await axios.get('/api/pms-fast/room-type-config')
    roomTypeConfig.value = res.data.roomTypes
    allotmentRoomTypes.value = roomTypeConfig.value.map(rt => rt.key)
  } catch {
    // Falls back to the two types the backend defaults to when the field is
    // omitted, so the page still works if this lookup fails.
    roomTypeConfig.value = [
      { key: 'deluxe', label: 'Deluxe', checkboxValue: 'DLT' },
      { key: 'premiere', label: 'Premiere', checkboxValue: 'PRKG' },
    ]
    allotmentRoomTypes.value = ['deluxe', 'premiere']
  }
})
const allotmentRoomLabels = computed(() =>
  roomTypeConfig.value.filter(rt => allotmentRoomTypes.value.includes(rt.key)).map(rt => rt.label)
)
function setAllRoomTypes(selected: boolean) {
  allotmentRoomTypes.value = selected ? roomTypeConfig.value.map(rt => rt.key) : []
}
const allotmentNeedsAllRoomYield = computed(() =>
  allotmentRoomTypes.value.some(key => key !== 'deluxe' && key !== 'premiere')
)

const pmsUsername = ref('')
const pmsPassword = ref('')
const dedgeUsername = ref('')
const dedgePassword = ref('')
const startDate = ref(todayLocalDateString())
const headless = ref(false)
const configError = ref('')
const stopping = ref(false)
const logContainer = ref<HTMLElement | null>(null)

const formatTime = (date: Date) => date.toLocaleTimeString()

watch(
  () => logs.value.length,
  () => {
    nextTick(() => {
      const el = logContainer.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
)

function clearLogs() {
  logs.value = []
}

interface YieldConfigForm {
  demand_bins: number[] | string
  demand_labels: string[] | string
  very_low_threshold_pct: number
  low_threshold_pct: number
  room_caps: {
    'Deluxe Room': number
    'Premiere Room': number
  }
  deluxe_override_occupancy: number
  deluxe_override_premiere: number
  deluxe_override_amount: number
  bar_level_shift: number
}

const defaultYieldConfig: YieldConfigForm = {
  demand_bins: [0, 70, 85, 100],
  demand_labels: ['Low', 'Medium', 'High'],
  very_low_threshold_pct: 5,
  low_threshold_pct: 20,
  room_caps: {
    'Deluxe Room': 160,
    'Premiere Room': 260,
  },
  deluxe_override_occupancy: 70,
  deluxe_override_premiere: 61,
  deluxe_override_amount: 2,
  bar_level_shift: 0,
}

const yieldForm = ref<YieldConfigForm>({
  ...defaultYieldConfig,
  room_caps: { ...defaultYieldConfig.room_caps },
})
const includeAllRoomTypes = ref(true)

function parseArrayInput(input: string | any[]): any[] {
  if (Array.isArray(input)) return input
  const str = input.toString().trim()
  try {
    return JSON.parse(str.replace(/'/g, '"'))
  } catch {
    return str.split(',').map(item => item.trim())
  }
}

function buildYieldConfig() {
  const roomCaps = yieldForm.value.room_caps
  if (!roomCaps['Deluxe Room'] || !roomCaps['Premiere Room']) {
    throw new Error('Room capacities must be specified for both Deluxe Room and Premiere Room')
  }

  const parsed = {
    ...yieldForm.value,
    demand_bins: parseArrayInput(yieldForm.value.demand_bins).map(Number),
    demand_labels: parseArrayInput(yieldForm.value.demand_labels),
    room_caps: {
      'Deluxe Room': Number(roomCaps['Deluxe Room']),
      'Premiere Room': Number(roomCaps['Premiere Room']),
    },
    include_simple_rooms: includeAllRoomTypes.value,
  }

  if (
    isNaN(parsed.very_low_threshold_pct) ||
    isNaN(parsed.low_threshold_pct) ||
    isNaN(parsed.deluxe_override_occupancy) ||
    isNaN(parsed.deluxe_override_premiere) ||
    isNaN(parsed.deluxe_override_amount) ||
    isNaN(parsed.bar_level_shift)
  ) {
    throw new Error('All numeric values must be valid numbers')
  }

  return parsed
}

// Snapshot for the Schedule panel's "Use this page's settings". Credentials,
// start date, headless and the BAR checkpoint reset are per-run decisions the
// backend makes for scheduled runs, so they're deliberately left out.
function buildScheduleConfig(): ScheduleRunConfig {
  return {
    steps: { ...stepEnabled.value },
    barRooms: Object.entries(barRooms.value).filter(([, v]) => v).map(([k]) => k),
    allotmentRoomTypes: [...allotmentRoomTypes.value],
    yieldConfig: buildYieldConfig(),
    skipUnchanged: skipUnchanged.value,
    barSkipUnchanged: barSkipUnchanged.value,
    allotmentConcurrency: allotmentConcurrency.value,
    companyId: companyId.value,
  }
}

// PMS API step fetches a fixed 100-day window from startDate
// (fast_inventory_scraper.fetch_room_inventory's `days` argument in
// fast_runner.py) - shown in the confirm dialog so the date range is never a surprise.
const PMS_FETCH_DAYS = 100

function formatConfirmDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

const confirmDateRangeText = computed(() => {
  const start = new Date(`${startDate.value}T00:00:00`)
  if (isNaN(start.getTime())) return startDate.value
  const end = new Date(start)
  end.setDate(end.getDate() + PMS_FETCH_DAYS - 1)
  return `${formatConfirmDate(startDate.value)} → ${end.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })} (${PMS_FETCH_DAYS} nights)`
})

const confirmBarRoomLabels = computed(() =>
  Object.entries(barRooms.value).filter(([, v]) => v).map(([k]) => (k === 'deluxe' ? 'Deluxe' : 'Premiere'))
)

const confirmAllotmentLine = computed(() => {
  if (!stepEnabled.value.allotment) return null
  if (allotmentRoomTypes.value.length === 0) return 'Allotment: no room types selected — this step will be skipped.'
  const mode = allotmentDryRun.value ? 'DRY RUN — payloads built, nothing sent' : 'LIVE — will write to the PMS'
  return `Allotment (${mode}): ${allotmentRoomLabels.value.join(', ')}`
})

const confirmBarLine = computed(() => {
  if (!stepEnabled.value.bar) return null
  if (confirmBarRoomLabels.value.length === 0) return 'BAR pricing: no room types selected — this step will be skipped.'
  return `BAR pricing (LIVE — no dry-run mode for this step): ${confirmBarRoomLabels.value.join(', ')}, based on the yield matrix calculation`
})

const confirmIsLive = computed(() =>
  (stepEnabled.value.allotment && !allotmentDryRun.value && allotmentRoomTypes.value.length > 0) ||
  (stepEnabled.value.bar && confirmBarRoomLabels.value.length > 0)
)

const showStartConfirm = ref(false)
const pendingYieldConfig = ref<ReturnType<typeof buildYieldConfig> | null>(null)

// Batch preview for the allotment step: reads the *existing*
// inventory_allocation.db via the same local, network-free planner the PMS
// API test page uses (/api/pms-fast/allotment-bulk/plan - no PMS login, no
// side effects). If scrape/combine/yield are also enabled for this run, this
// preview reflects the last calculation, not what this run will produce -
// flagged explicitly in the modal rather than silently shown as exact.
const allotmentPlanPreview = ref<{
  totalJobs: number
  skippedRanges: number
  byRoomType: Record<string, { label: string; job_count: number }>
} | null>(null)
const allotmentPlanLoading = ref(false)
const allotmentPlanError = ref('')

async function loadAllotmentPlanPreview() {
  allotmentPlanPreview.value = null
  allotmentPlanError.value = ''
  if (!stepEnabled.value.allotment || allotmentRoomTypes.value.length === 0) return
  allotmentPlanLoading.value = true
  try {
    const res = await axios.post('/api/pms-fast/allotment-bulk/plan', {
      roomTypes: allotmentRoomTypes.value,
      skipUnchanged: skipUnchanged.value,
    })
    allotmentPlanPreview.value = {
      totalJobs: res.data.totalJobs,
      skippedRanges: res.data.skippedRanges,
      byRoomType: res.data.byRoomType,
    }
  } catch (err: any) {
    allotmentPlanError.value = err?.response?.data?.message || 'Could not preview the allotment batch (no inventory_allocation.db yet?)'
  } finally {
    allotmentPlanLoading.value = false
  }
}

const upstreamStepsWillRecalculate = computed(() =>
  stepEnabled.value.scrape_pms || stepEnabled.value.scrape_cm || stepEnabled.value.combine || stepEnabled.value.yield
)

function openStartConfirm() {
  configError.value = ''
  try {
    pendingYieldConfig.value = buildYieldConfig()
  } catch (err: any) {
    configError.value = err instanceof Error ? err.message : 'Invalid yield configuration'
    return
  }
  showStartConfirm.value = true
  loadAllotmentPlanPreview()
}

async function confirmAndStartPipeline() {
  showStartConfirm.value = false
  const yieldConfig = pendingYieldConfig.value
  if (!yieldConfig) return

  const barRoomTypes = Object.entries(barRooms.value).filter(([, v]) => v).map(([k]) => k)

  try {
    await start('/api/fast-pipeline/start', {
      pmsUsername: pmsUsername.value,
      pmsPassword: pmsPassword.value,
      dedgeUsername: dedgeUsername.value,
      dedgePassword: dedgePassword.value,
      startDate: startDate.value,
      headless: headless.value,
      yieldConfig,
      steps: stepEnabled.value,
      barRooms: barRoomTypes,
      resetCheckpoint: resetCheckpoint.value,
      skipUnchanged: skipUnchanged.value,
      barSkipUnchanged: barSkipUnchanged.value,
      allotmentDryRun: allotmentDryRun.value,
      allotmentRoomTypes: allotmentRoomTypes.value,
      allotmentConcurrency: allotmentConcurrency.value,
      companyId: companyId.value,
    }, '/api/fast-pipeline/stream')
  } catch {
    // overallError is already surfaced reactively by the composable
  }
}

async function requestStop() {
  stopping.value = true
  try {
    await axios.post('/api/fast-pipeline/stop')
  } catch {
    // best-effort; ignore failures here, the stream will report the actual outcome
  } finally {
    stopping.value = false
  }
}

const completedCount = computed(() => stepStates.filter(s => s.status === 'success' || s.status === 'skipped').length)
const progressPercent = computed(() => Math.round((completedCount.value / stepStates.length) * 100))
const progressLabel = computed(() => `${completedCount.value} of ${stepStates.length} steps complete`)
const progressBarColor = computed(() => {
  if (overallError.value) return 'bg-rose-500'
  if (overallSuccess.value) return 'bg-emerald-500'
  return 'bg-app-accent'
})
</script>
