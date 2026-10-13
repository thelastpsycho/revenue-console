<template>
  <div class="mx-auto w-full max-w-6xl space-y-5 p-4 sm:p-6">
    <header class="flex flex-wrap justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold">Administration</h1>
        <p class="text-xs text-slate-500">
          Data health, mappings, settings and access
        </p>
      </div>
      <button
        class="btn-flat px-3 py-2 text-xs"
        :disabled="loading"
        @click="load"
      >
        {{ loading ? "Loading…" : "Refresh" }}
      </button>
    </header>
    <nav class="seg !flex flex-wrap" aria-label="Administration sections">
      <router-link
        v-for="s in sections"
        :key="s.id"
        :to="{ path: '/administration', query: { section: s.id } }"
        class="seg-btn"
        :aria-current="section === s.id ? 'page' : undefined"
        >{{ s.label }}</router-link
      >
    </nav>
    <p v-if="error" role="alert" class="text-sm text-rose-700">{{ error }}</p>
    <template v-if="data">
      <section v-if="section === 'health'" class="neu-card overflow-hidden">
        <h2 class="p-4 font-semibold">Data health</h2>
        <p class="px-4 pb-3 text-xs text-slate-500">
          File timestamps show stored-file changes, not proof of a successful
          data collection. Check the source sync and pipeline history for
          operational freshness.
        </p>
        <div class="overflow-auto">
          <table class="data-table">
            <thead>
              <tr>
                <th>Dataset</th>
                <th>State</th>
                <th>File updated</th>
                <th>Age (minutes)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in data.dataHealth" :key="r.name">
                <td>{{ r.name }}</td>
                <td>
                  {{ r.available ? "Available" : "Not collected / missing" }}
                </td>
                <td>{{ timestamp(r.updatedAt) }}</td>
                <td>{{ r.ageMinutes ?? "Unavailable" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex gap-4 p-4 text-xs">
          <router-link to="/data" class="underline">Inspect tables</router-link
          ><router-link to="/fast-pipeline-history" class="underline"
            >Collection history</router-link
          >
        </div>
      </section>
      <section v-if="section === 'mappings'" class="space-y-4">
        <div
          v-for="mapping in mappingRows"
          :key="mapping.key"
          class="neu-card overflow-hidden"
        >
          <h2 class="p-4 font-semibold">
            {{ mappingNames[mapping.key] || mapping.key }}
          </h2>
          <p
            v-if="mapping.key === 'channelGroups'"
            class="px-4 pb-3 text-xs text-slate-500"
          >
            Company names are classified by configured string rules; these
            groups are not a verified commission model.
          </p>
          <table class="data-table">
            <tbody>
              <tr v-for="r in mapping.rows" :key="r.id">
                <td>{{ r.id }}</td>
                <td>{{ r.label }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-xs text-slate-500">
          Mappings are shown for inspection; changing them requires a reviewed
          configuration change.
        </p>
      </section>
      <section v-if="section === 'settings'" class="neu-card space-y-3 p-4">
        <h2 class="font-semibold">Settings</h2>
        <router-link to="/rms?tab=data" class="block text-sm underline"
          >Revenue thresholds, deduction rules & budgets</router-link
        ><router-link to="/fast-api-pipeline" class="block text-sm underline"
          >Automation schedule & run configuration</router-link
        ><router-link to="/stop-sale" class="block text-sm underline"
          >Stop-sale rules & recipients</router-link
        >
      </section>
      <section v-if="section === 'access'" class="neu-card space-y-3 p-4">
        <h2 class="font-semibold">Access</h2>
        <p class="text-sm">
          {{ data.access.model }} · {{ data.access.sessionHours }}-hour session
        </p>
        <p class="text-sm">
          {{
            data.access.developmentMode
              ? "Development access mode"
              : data.access.configured
                ? "Operator authentication configured"
                : "Authentication not configured"
          }}
        </p>
        <p class="text-xs text-slate-500">
          Individual accounts and roles are not configured. Ask your system
          administrator to change the shared access credentials.
        </p>
        <button class="btn-flat px-3 py-2 text-xs" @click="logout">
          Sign out
        </button>
      </section>
      <section v-if="section === 'backups'" class="neu-card space-y-3 p-4">
        <h2 class="font-semibold">Backups</h2>
        <p class="text-sm">{{ data.backups.message }}</p>
        <p class="text-xs text-slate-500">
          Ask your system administrator to confirm the last successful backup
          and restore test for booking history, revenue budgets, operator
          settings and automation records. No verified backup timestamp is
          available to this app.
        </p>
      </section>
      <section v-if="section === 'advanced'" class="space-y-4">
        <div class="neu-card p-4">
          <h2 class="font-semibold">Advanced tools</h2>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <router-link
              v-for="t in tools"
              :key="t.href"
              :to="t.href"
              class="text-sm underline"
              >{{ t.name }}</router-link
            >
          </div>
        </div>
        <div class="neu-card overflow-hidden">
          <h2 class="p-4 font-semibold">Report endpoint timings</h2>
          <p class="px-4 pb-3 text-xs text-slate-500">
            Up to the latest 200 requests per endpoint in this running server.
            Includes cache hits. Timings reset on restart; use browser
            Server-Timing and X-Report-Cache headers for individual requests.
          </p>
          <table class="data-table">
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Samples</th>
                <th>Median ms</th>
                <th>95th percentile ms</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in data.reportTimings" :key="r.endpoint">
                <td>{{ r.endpoint }}</td>
                <td>{{ r.samples }}</td>
                <td>{{ r.p50Ms }}</td>
                <td>{{ r.p95Ms }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import axios from "../plugins/axios";
import { timestamp } from "../utils/rms";
const route = useRoute(),
  data = ref<any>(null),
  loading = ref(false),
  error = ref("");
const sections = [
  { id: "health", label: "Data health" },
  { id: "mappings", label: "Mappings" },
  { id: "settings", label: "Settings" },
  { id: "access", label: "Access" },
  { id: "backups", label: "Backups" },
  { id: "advanced", label: "Advanced" },
];
const section = computed(() =>
  sections.some((s) => s.id === route.query.section)
    ? String(route.query.section)
    : "health",
);
const mappingRows = computed(() =>
  Object.entries(data.value?.mappings || {}).map(([key, values]) => ({
    key,
    rows: Array.isArray(values)
      ? values
      : Object.entries(values as Record<string, string | number>).map(
          ([id, label]) => ({ id, label }),
        ),
  })),
);
const mappingNames: Record<string, string> = {
  roomTypes: "PMS room-type labels",
  roomCapacities: "Yield room capacities",
  budgetSegments: "Budget segment IDs",
  channelGroups: "Channel groups",
};
const tools = [
  { name: "Inventory tables", href: "/data" },
  { name: "Manual yielder", href: "/yielder" },
  { name: "PMS API test", href: "/pms-api-test" },
  { name: "Manual inventory collection", href: "/scraping" },
  { name: "Manual allotment", href: "/allotment" },
  { name: "Legacy pipeline", href: "/pipeline" },
];
async function load() {
  loading.value = true;
  error.value = "";
  try {
    data.value = (await axios.get("/api/administration/overview")).data;
  } catch {
    error.value = "Administration data could not be loaded.";
  } finally {
    loading.value = false;
  }
}
async function logout() {
  try {
    await axios.post("/api/auth/logout");
    window.dispatchEvent(new Event("operator-session-expired"));
  } catch {
    error.value = "Could not sign out. Please retry.";
  }
}
onMounted(load);
</script>
