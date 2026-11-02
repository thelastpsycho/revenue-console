<template>
  <div class="mx-auto w-full max-w-5xl space-y-8 p-4 pb-24 sm:p-6">
    <header>
      <h1 class="text-xl font-semibold">Documentation</h1>
      <p class="mt-1 text-sm text-slate-500">
        What Revenue Console does, how data moves through it, and where every
        setting lives. This page is a map, not a manual — it explains intent
        and flow so the rest of the app is easier to reason about.
      </p>
    </header>

    <!-- Search -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="relative min-w-[220px] max-w-sm flex-1">
        <MagnifyingGlassIcon
          class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
        />
        <input
          v-model="query"
          type="text"
          placeholder="Search documentation…"
          class="neu-input py-1.5 pl-9 text-sm"
        />
      </div>
      <button
        v-if="query"
        type="button"
        class="btn-flat px-3 py-1.5 text-xs"
        @click="query = ''"
      >
        Clear
      </button>
      <span v-if="query" class="text-xs text-slate-500">
        {{
          noMatches
            ? `No sections match “${query}”.`
            : `${matchCount} of ${sections.length} sections match.`
        }}
      </span>
    </div>

    <!-- On this page -->
    <nav class="seg !flex flex-wrap" aria-label="Documentation sections">
      <a
        v-for="s in sections"
        :key="s.id"
        :href="`#${s.id}`"
        class="seg-btn"
        :class="{ 'opacity-40': !sectionVisible(s.id) }"
        >{{ s.label }}</a
      >
    </nav>

    <!-- Overview -->
    <section
      id="overview"
      :ref="(el) => setSectionRef('overview', el)"
      v-show="sectionVisible('overview')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">What this app is</h2>
      <p class="text-sm text-slate-700">
        Revenue Console is the inventory and revenue-automation tool for The
        Anvaya Beach Resort Bali (79 rooms, Kuta). It reads room availability
        out of two systems the hotel already uses — the hospitality
        <strong>PMS</strong> (property management system) and
        <strong>D-EDGE</strong> (the channel manager that distributes rates
        and availability to OTAs) — combines those two views into one
        dataset, runs a yield engine to decide how many rooms each channel
        should be allowed to sell, and can push the result straight back into
        the PMS (allotment) and D-EDGE (BAR pricing). A separate revenue
        management workspace (RMS) turns the same underlying booking data
        into forecast, pace and pickup views for daily revenue decisions.
      </p>
      <p class="text-sm text-slate-700">
        Nothing happens silently: every automated push (allotment, BAR, stop
        sale emails) is either operator-triggered or an explicitly configured
        schedule, and every run is logged so it can be inspected after the
        fact.
      </p>
      <div class="grid gap-3 sm:grid-cols-2">
        <div class="neu-inset p-3 text-xs text-slate-600">
          <p class="field-label !mb-1">Backend</p>
          Flask API, Selenium browser automation, a reverse-engineered PMS
          JSON API client, and a set of SQLite databases — one per pipeline
          stage.
        </div>
        <div class="neu-inset p-3 text-xs text-slate-600">
          <p class="field-label !mb-1">Frontend</p>
          Vue 3 + TypeScript single-page app. Every routed page follows the
          <code>*View.vue</code> naming convention and talks to the backend
          over <code>/api/...</code>.
        </div>
      </div>
    </section>

    <!-- Architecture -->
    <section
      id="architecture"
      :ref="(el) => setSectionRef('architecture', el)"
      v-show="sectionVisible('architecture')"
      class="neu-card space-y-4 p-5"
    >
      <h2 class="font-semibold">Architecture at a glance</h2>
      <p class="text-sm text-slate-700">
        The backend is organized by responsibility rather than by endpoint:
      </p>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="neu-inset p-3 text-xs">
          <p class="font-semibold text-slate-800">integrations/</p>
          <p class="mt-1 text-slate-600">
            <code>pms/</code> — PMS scraping and allotment automation (both
            the Selenium path and the faster JSON API path).<br />
            <code>dedge/</code> — D-EDGE inventory scraping and BAR updates.
          </p>
        </div>
        <div class="neu-inset p-3 text-xs">
          <p class="font-semibold text-slate-800">inventory/</p>
          <p class="mt-1 text-slate-600">
            PMS/CM processing, combining the two sources, and persisting the
            yield engine's allocation decisions.
          </p>
        </div>
        <div class="neu-inset p-3 text-xs">
          <p class="font-semibold text-slate-800">revenue/</p>
          <p class="mt-1 text-slate-600">
            The yield engine, BAR-rate processing, and the entire RMS stack
            (forecast cache, booking events, settings).
          </p>
        </div>
        <div class="neu-inset p-3 text-xs">
          <p class="font-semibold text-slate-800">pipeline/</p>
          <p class="mt-1 text-slate-600">
            Orchestrates the full scrape-to-BAR workflow end to end, both the
            legacy Selenium version and the faster API-based version.
          </p>
        </div>
      </div>
      <p class="text-xs text-slate-500">
        Runtime data — every SQLite database, scrape screenshot and debug
        HTML artifact — lives on disk under
        <code>backend/app/scraper/data/</code> and is not tracked in git
        (except the Fast API Pipeline's default schedule config). A read-only
        MCP server exposes the same data to Claude as a thin HTTP client of
        the backend's own GET endpoints — it never opens the SQLite files
        directly.
      </p>
    </section>

    <!-- Pipeline / data flow -->
    <section
      id="pipeline"
      :ref="(el) => setSectionRef('pipeline', el)"
      v-show="sectionVisible('pipeline')"
      class="neu-card space-y-5 p-5"
    >
      <h2 class="font-semibold">Inventory pipeline &amp; database flow</h2>
      <p class="text-sm text-slate-700">
        This is the core data pipeline: two independent sources are scraped,
        processed into a common shape, combined, yielded, and — optionally —
        pushed back out. Every arrow below is a SQLite database file written
        by the step above it and read by the step below it.
      </p>

      <div class="overflow-x-auto">
        <div class="flow-diagram">
          <div class="flow-row">
            <div class="flow-box">
              <p class="flow-title">PMS scrape</p>
              <p class="flow-sub">
                Selenium drives the PMS UI, or the reverse-engineered JSON
                API client fetches the same data directly
              </p>
            </div>
            <div class="flow-box">
              <p class="flow-title">D-EDGE scrape</p>
              <p class="flow-sub">
                Selenium exports room planning data from the channel manager
              </p>
            </div>
          </div>
          <div class="flow-row">
            <div class="flow-arrow">↓ writes</div>
            <div class="flow-arrow">↓ exports</div>
          </div>
          <div class="flow-row">
            <div class="flow-db">pms_inventory_raw.db</div>
            <div class="flow-db flow-muted">room planning export</div>
          </div>
          <div class="flow-row">
            <div class="flow-arrow">↓ pms_processor.py</div>
            <div class="flow-arrow">↓ channel_manager_processor.py</div>
          </div>
          <div class="flow-row">
            <div class="flow-db">pms_inventory_processed.db</div>
            <div class="flow-db">cm_inventory_processed.db</div>
          </div>
          <div class="flow-merge">
            <span>↘</span><span class="flow-merge-label">inventory_combiner.py</span
            ><span>↙</span>
          </div>
          <div class="flow-row flow-row-single">
            <div class="flow-db flow-highlight">combined_inventory.db</div>
          </div>
          <div class="flow-row flow-row-single">
            <div class="flow-arrow">↓ yield_engine.py — applies the configured allocation strategy</div>
          </div>
          <div class="flow-row flow-row-single">
            <div class="flow-db flow-highlight">
              inventory_allocation.db
              <span class="flow-sub">table <code>daily_inventory_allocation</code></span>
            </div>
          </div>
          <div class="flow-row flow-row-single">
            <div class="flow-arrow">↓ verify — re-read what was just written before pushing anything</div>
          </div>
          <div class="flow-row">
            <div class="flow-box">
              <p class="flow-title">Push allotment</p>
              <p class="flow-sub">
                allotment_updater.py / other_room_allotment_updater.py write
                the calculated room counts back into the PMS
              </p>
            </div>
            <div class="flow-box">
              <p class="flow-title">Update BAR</p>
              <p class="flow-sub">
                bar_updater.py pushes BAR rate levels into D-EDGE; a
                checkpoint file lets a partial run resume instead of
                restarting
              </p>
            </div>
          </div>
        </div>
      </div>

      <p class="text-xs text-slate-500">
        <code>combined_inventory.db</code> is the one dataset most of the
        rest of the app reads from directly — Stop Sale, the Dashboard, and
        the Inventory Data Overview tables all read it rather than the raw or
        processed intermediates.
      </p>
    </section>

    <!-- Automation -->
    <section
      id="automation"
      :ref="(el) => setSectionRef('automation', el)"
      v-show="sectionVisible('automation')"
      class="neu-card space-y-4 p-5"
    >
      <h2 class="font-semibold">Automation &amp; scheduling</h2>
      <p class="text-sm text-slate-700">
        The pipeline above runs end to end in two different implementations:
      </p>
      <div class="grid gap-3 sm:grid-cols-2">
        <div class="neu-inset p-3 text-sm">
          <p class="font-semibold text-slate-800">
            Fast API Pipeline <span class="pill pill-ok ml-1">current</span>
          </p>
          <p class="mt-1 text-xs text-slate-600">
            The same workflow, but the two PMS stages call its JSON API
            directly instead of driving Chrome, and an extra
            <strong>verify allotment</strong> step re-checks the push against
            the PMS's own allotment grid. Eight steps in total: scrape PMS,
            scrape D-EDGE, combine, calculate yield, verify data, push
            allotment, verify allotment, update BAR. Can run on demand or on
            an interval schedule in either <strong>Preview</strong> (computes
            but does not push) or <strong>Live</strong> mode; every run is
            recorded in Fast Pipeline History with full step-by-step logs.
          </p>
        </div>
        <div class="neu-inset p-3 text-sm">
          <p class="font-semibold text-slate-800">
            Legacy Pipeline <span class="pill pill-muted ml-1">advanced</span>
          </p>
          <p class="mt-1 text-xs text-slate-600">
            The original seven-step Selenium-only workflow (PMS scrape →
            D-EDGE scrape → combine → yield → verify → PMS allotment →
            D-EDGE BAR). Still available under Administration → Advanced for
            comparison or fallback if the API client ever breaks.
          </p>
        </div>
      </div>
      <p class="text-sm text-slate-700">
        Both pipelines stream their progress live over Server-Sent Events
        (SSE) so the UI shows logs as they happen rather than only a final
        result — PMS scraping, allotment/BAR pushes, and the full pipeline
        each have their own log stream.
      </p>
      <p class="text-xs text-slate-500">
        The schedule, interval, Live/Preview mode and the yield configuration
        a scheduled run will use are all set from the Fast API Pipeline page
        itself and summarized there before the next run fires.
      </p>
    </section>

    <!-- RMS -->
    <section
      id="rms"
      :ref="(el) => setSectionRef('rms', el)"
      v-show="sectionVisible('rms')"
      class="neu-card space-y-4 p-5"
    >
      <h2 class="font-semibold">RMS — Revenue Management</h2>
      <p class="text-sm text-slate-700">
        RMS answers "how are we doing" day to day. It runs on a separate data
        path from the inventory pipeline above — it reads PMS report
        endpoints directly rather than the scraped/combined inventory
        databases.
      </p>
      <div class="flow-diagram">
        <div class="flow-row">
          <div class="flow-box">
            <p class="flow-title">PMS forecast reports</p>
            <p class="flow-sub">
              Occupancy, market segment and expected-occupancy endpoints,
              fetched independently of the main scrape
            </p>
          </div>
          <div class="flow-box">
            <p class="flow-title">PMS master folios</p>
            <p class="flow-sub">
              Every booking, polled for changes
            </p>
          </div>
        </div>
        <div class="flow-row">
          <div class="flow-arrow">↓ cached, stale-while-refresh</div>
          <div class="flow-arrow">↓ appended, never rewritten</div>
        </div>
        <div class="flow-row">
          <div class="flow-db">forecast cache</div>
          <div class="flow-db flow-highlight">booking_events.db</div>
        </div>
        <div class="flow-row flow-row-single">
          <div class="flow-arrow">
            ↓ forecast + pace + pickup + briefing endpoints, filtered by RMS settings
          </div>
        </div>
        <div class="flow-row flow-row-single">
          <div class="flow-box">
            RMS pages — Forecast &amp; Pace, Online Segment, Pickup by Month,
            Company Analytics, Daily Revenue Briefing
          </div>
        </div>
      </div>
      <p class="text-sm text-slate-700">
        <code>booking_events.db</code> is append-only: every row is a PII-free
        snapshot of a master folio at the moment it was observed (cancelled
        bookings are flagged, not deleted). History from before this cache
        existed is reconstructed and explicitly labeled
        <span class="pill pill-warn">estimated</span> rather than
        <span class="pill pill-ok">observed</span>, and every figure in the
        UI carries that quality flag so a stale or backfilled number is never
        mistaken for a live one. After the initial backfill, daily and weekly
        syncs revisit future and in-house arrivals to keep recent data
        observed rather than estimated.
      </p>
      <p class="text-sm text-slate-700">
        <strong>Pace</strong> compares on-the-books figures at the same lead
        time last year ("stly"); <strong>pickup</strong> shows what changed
        between two snapshots; <strong>forecast</strong> projects from the
        PMS's own forecast reports. Local notes and CSV/print exports support
        revenue meetings without needing a separate deck.
      </p>
    </section>

    <!-- Settings -->
    <section
      id="settings"
      :ref="(el) => setSectionRef('settings', el)"
      v-show="sectionVisible('settings')"
      class="neu-card space-y-4 p-5"
    >
      <h2 class="font-semibold">Settings — where every configuration lives</h2>
      <p class="text-sm text-slate-700">
        There is no single settings page; each area owns the configuration
        that affects only it. Administration → Settings links to all of
        them:
      </p>
      <div class="space-y-3">
        <div class="neu-inset p-3 text-sm">
          <p class="font-semibold text-slate-800">
            Revenue thresholds, deduction rules &amp; budgets
            <span class="text-xs font-normal text-slate-500">— RMS</span>
          </p>
          <ul class="mt-1 list-disc pl-5 text-xs text-slate-600 space-y-0.5">
            <li>
              <strong>Attention thresholds</strong> — occupancy % that counts
              as "full", a minimum pickup below which a date is flagged weak,
              and a rooms-behind-last-year gap that counts as "behind".
            </li>
            <li>
              <strong>Revenue rules</strong> — per rate-type breakfast
              deduction and tax/service % for converting gross to net
              revenue, by date range. A wildcard baseline must cover
              2000–2099 without gaps so every date always has a rule.
            </li>
            <li>
              <strong>Monthly budgets</strong> — one gross or net revenue
              target per month, entered by the operator (the PMS's own budget
              endpoint has unverified units, so this is hand-entered instead).
            </li>
            <li>
              <strong>USD/IDR rate</strong> — the mid rate used to convert
              USD-quoted bookings into IDR before they hit revenue/ADR
              figures.
            </li>
          </ul>
        </div>
        <div class="neu-inset p-3 text-sm">
          <p class="font-semibold text-slate-800">
            Automation schedule &amp; run configuration
            <span class="text-xs font-normal text-slate-500">— Fast API Pipeline</span>
          </p>
          <p class="mt-1 text-xs text-slate-600">
            Whether the schedule is on, how often it runs, Live vs Preview,
            which room types the allotment step pushes to (defaults to
            Deluxe + Premiere), and the yield configuration a scheduled run
            applies.
          </p>
        </div>
        <div class="neu-inset p-3 text-sm">
          <p class="font-semibold text-slate-800">
            Stop-sale rules &amp; recipients
            <span class="text-xs font-normal text-slate-500">— Stop Sale</span>
          </p>
          <p class="mt-1 text-xs text-slate-600">
            The occupancy % and per-room-type remaining-rooms thresholds that
            decide which dates need a stop sale, plus the recipient list and
            SMTP sending settings.
          </p>
        </div>
      </div>
      <p class="text-xs text-slate-500">
        Administration also exposes <strong>Data health</strong> (is each
        database fresh), <strong>Mappings</strong> (channel/company
        classification rules, read-only), <strong>Access</strong> (auth
        model and session length) and <strong>Backups</strong>.
      </p>
    </section>

    <!-- Stop sale -->
    <section
      id="stop-sale"
      :ref="(el) => setSectionRef('stop-sale', el)"
      v-show="sectionVisible('stop-sale')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">Stop sale emails</h2>
      <p class="text-sm text-slate-700">
        Reads <code>combined_inventory.db</code> and flags a date for stop
        sale when either the whole hotel's occupancy is at or above the
        configured threshold, or a single room type's remaining rooms drop to
        or below that room type's own threshold. Nothing sends
        automatically — the operator reviews the ticked dates and presses
        Send.
      </p>
      <p class="text-sm text-slate-700">
        Closures are recomputed server-side at send time (the browser only
        supplies which dates were ticked), one email per recipient with no
        CC, over SMTP. Every send — successful or failed — is written to
        <code>stop_sale.db</code> along with the recipients and rules used,
        so a failed send can be resent later without re-deriving which dates
        needed it.
      </p>
    </section>

    <!-- BAR / allotment / yield tools -->
    <section
      id="bar-pricing"
      :ref="(el) => setSectionRef('bar-pricing', el)"
      v-show="sectionVisible('bar-pricing')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">BAR Calculator, Allotment &amp; Yield tools</h2>
      <p class="text-sm text-slate-700">
        <strong>BAR Calculator</strong> is a standalone what-if tool: pick a
        BAR level and a discount %, and see the resulting rate for every room
        type — useful for sanity-checking a number before it goes live,
        without touching D-EDGE.
      </p>
      <p class="text-sm text-slate-700">
        <strong>Manual yielder</strong> and <strong>manual allotment</strong>
        (under Administration → Advanced) expose the same yield engine and
        PMS push used by the automated pipeline, but one step at a time —
        useful for testing a new allocation strategy or pushing a one-off
        correction without running the full pipeline.
      </p>
    </section>

    <!-- Data overview -->
    <section
      id="data"
      :ref="(el) => setSectionRef('data', el)"
      v-show="sectionVisible('data')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">Inventory Data Overview</h2>
      <p class="text-sm text-slate-700">
        Browses and exports every stage of the inventory pipeline directly —
        raw PMS scrape, processed PMS, processed channel manager, combined,
        and the yield engine's allocation output — as read-only tables. This
        is the fastest way to confirm what a pipeline run actually wrote,
        independent of any dashboard summary.
      </p>
    </section>

    <!-- Administration -->
    <section
      id="administration"
      :ref="(el) => setSectionRef('administration', el)"
      v-show="sectionVisible('administration')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">Administration</h2>
      <p class="text-sm text-slate-700">
        The operations home base: data freshness per database, the
        classification mappings that group channels and companies, links to
        every settings surface above, operator access/session info, backups,
        and — under <strong>Advanced</strong> — the manual/legacy tools
        (inventory tables, manual yielder, PMS API test, manual inventory
        collection, manual allotment, legacy pipeline) that exist for
        debugging and fallback rather than day-to-day use.
      </p>
    </section>

    <!-- Security -->
    <section
      id="security"
      :ref="(el) => setSectionRef('security', el)"
      v-show="sectionVisible('security')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">Security &amp; access</h2>
      <p class="text-sm text-slate-700">
        The whole UI is gated behind a 6-digit operator PIN
        (<code>APP_ACCESS_PIN</code>) and a signed session
        (<code>APP_SESSION_SECRET</code>); every write request carries a CSRF
        token issued at login. Authenticated endpoints simply don't exist
        until both are configured on the backend. Provider credentials (e.g.
        for any AI integration) are never passed through frontend-visible
        <code>VITE_*</code> variables.
      </p>
      <p class="text-xs text-slate-500">
        The MCP server that lets Claude query this data is strictly
        read-only: it logs in with the same operator PIN and calls the same
        GET endpoints the UI does — it has no path to write inventory,
        allotment, BAR, or stop-sale state.
      </p>
    </section>

    <!-- Glossary -->
    <section
      id="glossary"
      :ref="(el) => setSectionRef('glossary', el)"
      v-show="sectionVisible('glossary')"
      class="neu-card space-y-3 p-5"
    >
      <h2 class="font-semibold">Database glossary</h2>
      <div class="overflow-auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Written by</th>
              <th>Contains</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="whitespace-nowrap">pms_inventory_raw.db</td>
              <td>PMS scrape</td>
              <td>Raw room availability exactly as read from the PMS</td>
            </tr>
            <tr>
              <td class="whitespace-nowrap">pms_inventory_processed.db</td>
              <td>pms_processor.py</td>
              <td>PMS data normalized into the shared inventory shape</td>
            </tr>
            <tr>
              <td class="whitespace-nowrap">cm_inventory_processed.db</td>
              <td>channel_manager_processor.py</td>
              <td>D-EDGE room planning data normalized the same way</td>
            </tr>
            <tr>
              <td class="whitespace-nowrap">combined_inventory.db</td>
              <td>inventory_combiner.py</td>
              <td>
                PMS + channel manager merged into one dataset; read directly
                by Stop Sale, the Dashboard and Data Overview
              </td>
            </tr>
            <tr>
              <td class="whitespace-nowrap">inventory_allocation.db</td>
              <td>yield_engine.py</td>
              <td>
                Yield decisions, table <code>daily_inventory_allocation</code>
              </td>
            </tr>
            <tr>
              <td class="whitespace-nowrap">booking_events.db</td>
              <td>booking_events.py (RMS sync)</td>
              <td>
                Append-only, PII-free observed booking snapshots that drive
                pace/pickup
              </td>
            </tr>
            <tr>
              <td class="whitespace-nowrap">stop_sale.db</td>
              <td>Stop Sale routes</td>
              <td>Recipients, rule/email settings and send history</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs text-slate-500">
        All of these live under <code>backend/app/scraper/data/</code> and
        are inspected via Administration → Data health or the Inventory Data
        Overview page rather than opened directly.
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { MagnifyingGlassIcon } from "@heroicons/vue/24/outline";

const sections = [
  { id: "overview", label: "Overview" },
  { id: "architecture", label: "Architecture" },
  { id: "pipeline", label: "Pipeline & databases" },
  { id: "automation", label: "Automation" },
  { id: "rms", label: "RMS" },
  { id: "settings", label: "Settings" },
  { id: "stop-sale", label: "Stop sale" },
  { id: "bar-pricing", label: "BAR & yield tools" },
  { id: "data", label: "Data overview" },
  { id: "administration", label: "Administration" },
  { id: "security", label: "Security" },
  { id: "glossary", label: "Glossary" },
];

const query = ref("");
const sectionEls: Record<string, HTMLElement | null> = {};
function setSectionRef(id: string, el: unknown) {
  sectionEls[id] = (el as HTMLElement) ?? null;
}

// textContent (not innerText) so a section hidden by a previous search still
// reports its full text — innerText is render-aware and returns "" once an
// ancestor is display:none, which would make a hidden section unsearchable.
const matchedIds = computed<Set<string> | null>(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return null;
  const result = new Set<string>();
  for (const s of sections) {
    const text = sectionEls[s.id]?.textContent?.toLowerCase() ?? "";
    if (text.includes(q)) result.add(s.id);
  }
  return result;
});

function sectionVisible(id: string) {
  return matchedIds.value === null || matchedIds.value.has(id);
}
const matchCount = computed(() => matchedIds.value?.size ?? sections.length);
const noMatches = computed(
  () => matchedIds.value !== null && matchedIds.value.size === 0,
);
</script>

<style scoped>
.flow-diagram {
  display: flex;
  min-width: 640px;
  flex-direction: column;
  align-items: stretch;
  gap: 0.375rem;
}
.flow-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
.flow-row-single {
  grid-template-columns: 1fr;
}
.flow-box {
  @apply rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-center;
}
.flow-title {
  @apply text-xs font-semibold text-slate-800;
}
.flow-sub {
  @apply mt-0.5 block text-[11px] font-normal leading-snug text-slate-500;
}
.flow-arrow {
  @apply px-2 text-center text-[11px] font-medium text-slate-400;
}
.flow-db {
  @apply rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-center font-mono text-[11px] text-slate-600;
}
.flow-muted {
  @apply border-slate-200 bg-white text-slate-400;
}
.flow-highlight {
  @apply border-slate-400 bg-slate-100 font-semibold text-slate-800;
}
.flow-merge {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: #94a3b8;
  font-size: 0.875rem;
}
.flow-merge-label {
  @apply rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-slate-500;
}
</style>
