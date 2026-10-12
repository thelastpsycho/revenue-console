<template>
  <Teleport to="body">
    <transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      leave-active-class="transition duration-100 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-if="selectedDate"
        class="fixed inset-0 z-40 flex justify-end bg-slate-900/30"
        @mousedown.self="$emit('close')"
      >
        <aside
          ref="panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rms-day-title"
          tabindex="-1"
          class="flex h-full w-full max-w-2xl flex-col overflow-hidden border-l border-slate-200 bg-white shadow-xl outline-none"
          @keydown.esc.prevent="$emit('close')"
        >
          <header
            class="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4"
          >
            <div>
              <p class="field-label !mb-0">Stay date</p>
              <h2 id="rms-day-title" class="text-base font-semibold text-slate-900">
                {{ dayLabel(selectedDate) }}
              </h2>
              <p class="text-[11px] text-slate-500">
                Compared with {{ curve?.lyDate ? dayLabel(curve.lyDate) : "—" }}
              </p>
            </div>
            <button
              type="button"
              class="btn-icon"
              aria-label="Close"
              @click="$emit('close')"
            >
              <XMarkIcon class="h-4 w-4" />
            </button>
          </header>

          <div class="flex-1 space-y-5 overflow-y-auto px-5 py-4">
            <section>
              <h3 class="text-sm font-semibold text-slate-900">Booking curve</h3>
              <p class="mt-0.5 text-[11px] text-slate-500">
                Current curve stops at today. Earlier reconstructed history is
                estimated; gaps mean unavailable.
              </p>
              <p v-if="curveLoading" class="mt-2 text-xs text-slate-500">
                Loading booking curve…
              </p>
              <p v-if="curveError" role="alert" class="alert-error mt-2">
                {{ curveError }}
              </p>
              <div class="mt-2 h-60">
                <Chart
                  type="line"
                  :data="curveData"
                  :options="curveOptions"
                  :plugins="[todayMarker]"
                />
              </div>
            </section>

            <section>
              <h3 class="text-sm font-semibold text-slate-900">
                Physical availability
              </h3>
              <p
                v-if="!selectedAvailability.length"
                class="mt-1 text-xs text-slate-500"
              >
                Unavailable for this date.
              </p>
              <dl v-else class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                <div
                  v-for="r in selectedAvailability"
                  :key="r.type"
                  class="rounded-lg border border-slate-200 px-3 py-2"
                >
                  <dt class="truncate text-[11px] text-slate-500">
                    {{ label(r.type) }}
                  </dt>
                  <dd
                    :class="[
                      'text-sm font-semibold tabular-nums',
                      r.rooms < 0 ? 'text-rose-700' : 'text-slate-900',
                    ]"
                  >
                    {{ num(r.rooms) }}
                  </dd>
                </div>
              </dl>
            </section>

            <section>
              <h3 class="text-sm font-semibold text-slate-900">
                PMS segment breakdown
              </h3>
              <p
                v-if="!selectedSegments.length"
                class="mt-1 text-xs text-slate-500"
              >
                Unavailable for this date.
              </p>
              <table v-else class="data-table mt-1">
                <thead>
                  <tr>
                    <th>Segment</th>
                    <th class="num">Nights</th>
                    <th class="num">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in selectedSegments" :key="s.marketId">
                    <td>{{ s.market }}</td>
                    <td class="num">{{ num(s.rooms) }}</td>
                    <td class="num" :title="money(s.revenue)">
                      {{ moneyShort(s.revenue) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </section>
          </div>

          <footer class="space-y-2 border-t border-slate-200 bg-slate-50 px-5 py-4">
            <label class="block">
              <span class="field-label">Meeting note — no guest details</span>
              <textarea
                v-model="noteDraft"
                maxlength="2000"
                rows="3"
                class="neu-input"
              />
            </label>
            <div class="flex items-center gap-3">
              <button
                type="button"
                class="btn-primary"
                :disabled="noteSaving"
                @click="$emit('saveNote')"
              >
                {{ noteSaving ? "Saving…" : "Save note" }}
              </button>
              <span v-if="savedNote" class="text-[11px] text-slate-500"
                >Saved {{ timestamp(savedNote.updatedAt) }}</span
              >
            </div>
          </footer>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>
<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { Chart } from "vue-chartjs";
import type { ChartOptions, ChartTypeRegistry } from "chart.js";
import { XMarkIcon } from "@heroicons/vue/24/outline";
import { num, money, moneyShort, timestamp, dayLabel } from "../utils/rms";
import type { Curve } from "../utils/rms";

const props = defineProps<{
  selectedDate: string;
  curve: Curve | null;
  curveLoading: boolean;
  curveError: string;
  curveData: any;
  curveOptions: ChartOptions<keyof ChartTypeRegistry>;
  todayMarker: any;
  selectedAvailability: { type: string; rooms: number }[];
  selectedSegments: { marketId: number; market: string; rooms: number; revenue: number }[];
  savedNote: { text: string; updatedAt: string } | undefined;
  noteSaving: boolean;
  label: (code: string) => string;
}>();
defineEmits<{ close: []; saveNote: [] }>();
const noteDraft = defineModel<string>("noteDraft", { required: true });

// Focus the drawer when it opens so Esc closes it straight away.
const panel = ref<HTMLElement | null>(null);
watch(
  () => props.selectedDate,
  async (d) => {
    if (!d) return;
    await nextTick();
    panel.value?.focus();
  },
);
</script>
