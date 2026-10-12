<template>
  <div class="neu-card space-y-3 p-4">
    <h2 class="font-semibold">Booking history</h2>
    <p class="text-xs text-slate-500">
      Daily refresh includes new bookings, arrivals in the next year and known
      in-house stays. Weekly refresh also revisits 90 days of booking
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
  <form v-if="settings" class="neu-card space-y-4 p-4" @submit.prevent="save">
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
      Net = max(gross rate − breakfast, 0) / (1 + tax/service). A specific PMS
      RateType overrides *; an optional package RateId overrides the type
      rule. Rules apply by stay date. Keep a * rule covering all report dates.
      0.21 means 21%. Changing rules restates estimated net figures; gross
      booking history is retained.
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
    ><button class="btn-primary px-3 py-2 text-xs" :disabled="settingsSaving">
      {{ settingsSaving ? "Saving…" : "Save settings" }}</button
    ><span class="ml-3 text-xs" role="status">{{ settingsMessage }}</span>
  </form>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import axios from "../plugins/axios";
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
