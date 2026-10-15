<template>
  <RmsCard
    title="Booking history"
    description="Daily refresh covers new bookings, arrivals in the next year and known in-house stays. Weekly refresh also revisits 90 days of booking creation. Versions can't recover amendments made before first observation."
    padded
  >
    <dl class="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
      <div>
        <dt class="field-label">Bookings</dt>
        <dd class="text-sm font-semibold tabular-nums">{{ num(sync?.bookings) }}</dd>
      </div>
      <div>
        <dt class="field-label">Coverage from</dt>
        <dd class="text-sm font-semibold">{{ sync?.coverageFrom || "—" }}</dd>
      </div>
      <div>
        <dt class="field-label">Last daily</dt>
        <dd class="text-sm font-semibold">{{ sync?.lastDaily || "—" }}</dd>
      </div>
      <div>
        <dt class="field-label">Last weekly</dt>
        <dd class="text-sm font-semibold">{{ sync?.lastWeekly || "—" }}</dd>
      </div>
    </dl>
    <div class="mt-4 flex flex-wrap items-end gap-2 border-t border-slate-100 pt-4">
      <label>
        <span class="field-label">Backfill years</span>
        <select v-model.number="backfillYears" class="neu-input">
          <option v-for="n in [1, 2, 3, 4, 5]" :key="n" :value="n">
            {{ n }}
          </option>
        </select>
      </label>
      <button
        v-for="kind in ['backfill', 'daily', 'weekly']"
        :key="kind"
        type="button"
        class="btn-flat capitalize"
        :disabled="sync?.job.running"
        @click="runSync(kind)"
      >
        Run {{ kind }}
      </button>
      <span v-if="sync?.job.running" class="pill pill-muted">
        {{ sync.job.kind }}: {{ sync.job.done }} / {{ sync.job.total }} windows ·
        {{ sync.job.rows }} rows
      </span>
    </div>
    <p v-if="sync?.job.error" class="alert-error mt-3">{{ sync.job.error }}</p>
  </RmsCard>

  <form v-if="settings" class="space-y-4" @submit.prevent="save">
    <RmsCard
      title="Review thresholds"
      description="When a stay date is flagged on Overview."
      padded
    >
      <div class="flex flex-wrap gap-3">
        <label>
          <span class="field-label">High occupancy %</span>
          <input
            v-model.number="settings.thresholds.occupancy"
            type="number"
            min="0"
            max="100"
            required
            class="neu-input w-36"
          />
        </label>
        <label>
          <span class="field-label">Weak pickup below</span>
          <input
            v-model.number="settings.thresholds.weakPickup"
            type="number"
            min="0"
            required
            class="neu-input w-36"
          />
        </label>
        <label>
          <span class="field-label">Behind LY by (rooms)</span>
          <input
            v-model.number="settings.thresholds.behindRooms"
            type="number"
            min="0"
            required
            class="neu-input w-36"
          />
        </label>
      </div>
    </RmsCard>

    <RmsCard
      title="Currency"
      description="USD-quoted bookings (~4% of volume) are converted to IDR at this mid rate before being added to revenue/ADR. Other currencies are still excluded."
      padded
    >
      <label>
        <span class="field-label">USD/IDR mid rate</span>
        <input
          v-model.number="settings.usdIdrRate"
          type="number"
          min="1000"
          max="100000"
          required
          class="neu-input w-36"
        />
      </label>
    </RmsCard>

    <RmsCard
      title="Estimated net revenue rules"
      description="Net = max(gross rate − breakfast, 0) / (1 + tax/service). A specific RateType overrides *; a package RateId overrides its type rule. Rules apply by stay date — keep a * rule covering all dates. 0.21 means 21%."
      padded
    >
      <template #actions>
        <button
          type="button"
          class="btn-flat px-2.5 py-1 text-xs"
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
          <PlusIcon class="h-3.5 w-3.5" /> Add rule
        </button>
      </template>
      <div class="space-y-3">
        <div
          v-for="(r, i) in settings.revenueRules"
          :key="i"
          class="flex flex-wrap items-end gap-2"
        >
          <label>
            <span class="field-label">RateType</span>
            <input v-model="r.rateType" required maxlength="40" class="neu-input w-24" />
          </label>
          <label>
            <span class="field-label">Package RateId</span>
            <input
              v-model="r.rateId"
              maxlength="80"
              placeholder="Optional"
              class="neu-input w-36"
            />
          </label>
          <label>
            <span class="field-label">From</span>
            <input v-model="r.from" type="date" required class="neu-input" />
          </label>
          <label>
            <span class="field-label">Through</span>
            <input v-model="r.to" type="date" required class="neu-input" />
          </label>
          <label>
            <span class="field-label">Breakfast IDR</span>
            <input
              v-model.number="r.breakfast"
              type="number"
              min="0"
              required
              class="neu-input w-32"
            />
          </label>
          <label>
            <span class="field-label">Tax/service</span>
            <input
              v-model.number="r.taxService"
              type="number"
              min="0"
              max="1"
              step=".001"
              required
              class="neu-input w-24"
            />
          </label>
          <button
            type="button"
            class="btn-icon"
            aria-label="Remove rule"
            title="Remove rule"
            @click="settings.revenueRules.splice(i, 1)"
          >
            <TrashIcon class="h-4 w-4" />
          </button>
        </div>
      </div>
    </RmsCard>

    <RmsCard
      title="Monthly IDR revenue targets"
      description="Enter targets on the same basis as the report. Foreign revenue is excluded. PMS budget figures aren't imported because their units are unverified."
      padded
    >
      <template #actions>
        <button
          type="button"
          class="btn-flat px-2.5 py-1 text-xs"
          @click="
            settings.budgets.push({
              month: today.slice(0, 7),
              basis: 'gross',
              revenue: 0,
            })
          "
        >
          <PlusIcon class="h-3.5 w-3.5" /> Add target
        </button>
      </template>
      <div class="space-y-3">
        <div
          v-for="(b, i) in settings.budgets"
          :key="i"
          class="flex flex-wrap items-end gap-2"
        >
          <label>
            <span class="field-label">Month</span>
            <input v-model="b.month" type="month" required class="neu-input" />
          </label>
          <label>
            <span class="field-label">Basis</span>
            <select v-model="b.basis" class="neu-input">
              <option value="gross">Gross IDR</option>
              <option value="net">Estimated net IDR</option>
            </select>
          </label>
          <label>
            <span class="field-label">Target IDR</span>
            <input
              v-model.number="b.revenue"
              type="number"
              min="0"
              required
              class="neu-input w-44"
            />
          </label>
          <button
            type="button"
            class="btn-icon"
            aria-label="Remove target"
            title="Remove target"
            @click="settings.budgets.splice(i, 1)"
          >
            <TrashIcon class="h-4 w-4" />
          </button>
        </div>
      </div>
    </RmsCard>

    <div
      class="neu-card sticky bottom-4 flex items-center gap-3 px-4 py-3 shadow-lg"
    >
      <button class="btn-primary" :disabled="settingsSaving">
        {{ settingsSaving ? "Saving…" : "Save settings" }}
      </button>
      <span class="text-xs text-slate-600" role="status">{{
        settingsMessage
      }}</span>
    </div>
  </form>
  <p v-else-if="settingsMessage" class="alert-error">{{ settingsMessage }}</p>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { PlusIcon, TrashIcon } from "@heroicons/vue/24/outline";
import axios from "../plugins/axios";
import RmsCard from "./RmsCard.vue";
import { num, type Settings, type Sync } from "../utils/rms";

defineProps<{ today: string }>();
const emit = defineEmits<{ synced: [] }>();
const sync = defineModel<Sync | null>("sync", {
  required: true,
});

const settings = ref<Settings | null>(null),
  settingsSaving = ref(false),
  settingsMessage = ref(""),
  backfillYears = ref(3);

const message = (e: any) =>
  e?.response?.data?.message || e?.message || "Request failed";

async function save() {
  settingsSaving.value = true;
  settingsMessage.value = "";
  try {
    const r = await axios.put("/api/rms/settings", settings.value);
    settings.value = r.data.settings;
    settingsMessage.value = "Saved. Apply the report to recalculate.";
  } catch (e) {
    settingsMessage.value = message(e);
  } finally {
    settingsSaving.value = false;
  }
}
async function runSync(kind: string) {
  try {
    const r = await axios.post("/api/rms/sync", {
      kind,
      backfillDays: backfillYears.value * 365,
    });
    sync.value = r.data;
    emit("synced");
  } catch (e) {
    settingsMessage.value = message(e);
  }
}
onMounted(async () => {
  try {
    const r = await axios.get("/api/rms/settings");
    settings.value = r.data.settings;
  } catch (e) {
    settingsMessage.value = message(e);
  }
});
</script>
