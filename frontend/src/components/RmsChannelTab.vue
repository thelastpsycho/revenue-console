<template>
  <RmsCard
    title="OTA / channel mix"
    description="Hotel-wide production per OTA/online channel, as reported by the PMS. MTD/YTD as of today - date, room type and market filters don't apply here."
    scroll
  >
    <template #actions>
      <span v-if="channel?.error" class="pill pill-warn">{{ channel.error }}</span>
      <span v-else-if="channel" class="pill pill-muted" :title="`Last refreshed ${timestamp(channel.fetchedAt)}`">
        {{ channel.refreshing ? "Refreshing…" : channel.stale ? "Stale" : "Up to date" }}
      </span>
      <button type="button" class="pill pill-muted cursor-pointer hover:border-slate-300" :disabled="channelBusy" @click="$emit('refresh')">
        <ArrowPathIcon :class="['h-3 w-3', channelBusy && 'animate-spin']" />
        Refresh
      </button>
    </template>
    <table v-if="ota.length" class="data-table">
      <thead>
        <tr>
          <th>Channel</th>
          <th class="num">Room nights MTD</th>
          <th class="num">Revenue MTD</th>
          <th class="num">ADR MTD</th>
          <th class="num">MTD vs last year</th>
          <th class="num">Revenue YTD</th>
          <th class="num">YTD vs last year</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in ota" :key="r.companyId ?? r.company ?? 'unassigned'">
          <td class="font-semibold text-slate-900">{{ r.company || "Unassigned" }}</td>
          <td class="num">{{ num(r.roomsMtd) }}</td>
          <td class="num" :title="money(r.revenueMtd)">{{ moneyShort(r.revenueMtd) }}</td>
          <td class="num" :title="money(r.adrMtd)">{{ moneyShort(r.adrMtd) }}</td>
          <td class="num" :class="signClass(pctDiff(r.revenueMtd, r.revenueMtdLy))">
            {{ pctLabel(pctDiff(r.revenueMtd, r.revenueMtdLy)) }}
          </td>
          <td class="num" :title="money(r.revenueYtd)">{{ moneyShort(r.revenueYtd) }}</td>
          <td class="num" :class="signClass(pctDiff(r.revenueYtd, r.revenueYtdLy))">
            {{ pctLabel(pctDiff(r.revenueYtd, r.revenueYtdLy)) }}
          </td>
        </tr>
      </tbody>
    </table>
    <template v-if="!ota.length" #empty>
      {{ channelBusy ? "Channel mix is loading…" : "No channel mix available." }}
    </template>
  </RmsCard>

  <RmsCard
    title="Segment mix"
    description="Hotel-wide production per market segment, MTD/YTD as reported by the PMS. Not the same filters as the Pace/Production tabs' market selector."
  >
    <div class="overflow-x-auto">
      <table v-if="segments.length" class="data-table">
        <thead>
          <tr>
            <th>Segment</th>
            <th class="num">Room nights MTD</th>
            <th class="num">Revenue MTD</th>
            <th class="num">Share of MTD</th>
            <th class="num">Revenue YTD</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in segments" :key="g.marketId ?? g.market ?? 'unassigned'">
            <td class="font-semibold text-slate-900">{{ g.market || "Unassigned" }}</td>
            <td class="num">{{ num(g.roomsMtd) }}</td>
            <td class="num" :title="money(g.revenueMtd)">{{ moneyShort(g.revenueMtd) }}</td>
            <td class="num">{{ percent(shareOf(g.revenueMtd, segmentMtdTotal)) }}</td>
            <td class="num" :title="money(g.revenueYtd)">{{ moneyShort(g.revenueYtd) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <template v-if="!segments.length" #empty>
      {{ channelBusy ? "Segment mix is loading…" : "No segment mix available." }}
    </template>
  </RmsCard>

  <RmsCard
    title="Reservation source"
    description="How reservations were taken (email, phone, walk-in, online, ...), MTD/YTD as reported by the PMS."
  >
    <div class="overflow-x-auto">
      <table v-if="sources.length" class="data-table">
        <thead>
          <tr>
            <th>Source</th>
            <th class="num">Room nights MTD</th>
            <th class="num">Revenue MTD</th>
            <th class="num">Share of MTD</th>
            <th class="num">Revenue YTD</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sources" :key="s.id ?? s.description ?? 'unknown'">
            <td class="font-semibold text-slate-900">{{ s.description || "Unknown" }}</td>
            <td class="num">{{ num(s.roomsMtd) }}</td>
            <td class="num" :title="money(s.revenueMtd)">{{ moneyShort(s.revenueMtd) }}</td>
            <td class="num">{{ percent(shareOf(s.revenueMtd, sourceMtdTotal)) }}</td>
            <td class="num" :title="money(s.revenueYtd)">{{ moneyShort(s.revenueYtd) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <template v-if="!sources.length" #empty>
      {{ channelBusy ? "Sources are loading…" : "No reservation-source data available." }}
    </template>
  </RmsCard>
</template>
<script setup lang="ts">
import { computed } from "vue";
import { ArrowPathIcon } from "@heroicons/vue/24/outline";
import RmsCard from "./RmsCard.vue";
import {
  num,
  money,
  moneyShort,
  percent,
  pctDiff,
  pctLabel,
  signClass,
  timestamp,
  ratio,
} from "../utils/rms";
import type { ChannelMix } from "../utils/rms";

const props = defineProps<{
  channel: ChannelMix | null;
  channelBusy: boolean;
}>();
defineEmits<{ refresh: [] }>();

const ota = computed(() => props.channel?.ota ?? []);
const sources = computed(() => props.channel?.sources ?? []);
const segments = computed(() => props.channel?.segments ?? []);
const sourceMtdTotal = computed(() =>
  sources.value.reduce((sum, s) => sum + (s.revenueMtd || 0), 0),
);
const segmentMtdTotal = computed(() =>
  segments.value.reduce((sum, g) => sum + (g.revenueMtd || 0), 0),
);
function shareOf(value: number | null, total: number) {
  const r = ratio(value, total);
  return r == null ? null : r * 100;
}
</script>
