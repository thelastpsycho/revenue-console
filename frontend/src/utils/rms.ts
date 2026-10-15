import type { ChartOptions, ChartTypeRegistry } from "chart.js";
// Remembers filters/tab across visits (private browsing or a full storage
// quota just means nothing persists - never worth surfacing as an error).
const STORAGE_PREFIX = "rc:";
export function loadStoredFilters(key: string): Record<string, string> | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
export function saveStoredFilters(key: string, value: Record<string, string | undefined>) {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
  } catch {
    // ignore
  }
}

export interface PaceRow {
  date: string;
  lyDate: string;
  rooms: number;
  idrRooms: number;
  revenue: number;
  netRevenue: number;
  pickupRooms: number | null;
  pickupRevenue: number | null;
  pickupNetRevenue: number | null;
  newRooms: number | null;
  cancelledRooms: number | null;
  amendedRooms: number | null;
  stlyRooms: number | null;
  stlyRevenue: number | null;
  stlyIdrRooms: number | null;
  stlyNetRevenue: number | null;
  lyFinalRooms: number | null;
  budgetRooms: number | null;
  budgetRevenue: number | null;
  currentQuality: string;
  comparisonQuality: string;
  pickupQuality: string;
}
export interface Budget {
  month: string;
  basis: string;
  revenue: number;
}
export interface BreakdownMetrics {
  rooms: number;
  idrRooms: number;
  revenue: number;
  netRevenue: number;
}
export interface Breakdown {
  roomTypes: (BreakdownMetrics & {
    id: string;
    ratePlans: (BreakdownMetrics & { id: string })[];
  })[];
  total: BreakdownMetrics;
}
export interface Settings {
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
  usdIdrRate: number;
}
export interface Sync {
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
export interface Filters {
  start: string;
  end: string;
  roomType: string;
  marketId: string;
  pickupDays: number;
  comparison: string;
  comparisonStart: string;
  // "comparison" always holds a valid YoY submode so it keeps working as the
  // backend's matching mode (pickup, LY-final, etc. depend on it even when
  // the operator is looking at budget); this picks which one is displayed.
  compareWith: "yoy" | "budget";
}
export interface CurvePoint {
  lead: number;
  rooms: number | null;
  quality: string;
}
export interface Curve {
  date: string;
  lyDate: string;
  todayLead: number;
  maxLead: number;
  current: CurvePoint[];
  lastYear: CurvePoint[];
}
export interface Hotel {
  date: string;
  roomsSold: number | null;
  roomCount: number | null;
  occupancy: number | null;
  revenue: number | null;
  adr: number | null;
  complimentary: number | null;
  houseUse: number | null;
}
export interface Segment {
  date: string;
  marketId: number;
  market: string;
  rooms: number;
  revenue: number;
}
export interface Forecast {
  start: string;
  end: string;
  hotel: Hotel[];
  segments: Segment[];
  roomTypes: { date: string; typeId: string; rooms: number; roomCount: number }[];
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
export interface OtaRow {
  companyId: number | null;
  company: string | null;
  roomsMtd: number | null;
  revenueMtd: number | null;
  adrMtd: number | null;
  roomsYtd: number | null;
  revenueYtd: number | null;
  adrYtd: number | null;
  roomsMtdLy: number | null;
  revenueMtdLy: number | null;
  roomsYtdLy: number | null;
  revenueYtdLy: number | null;
}
export interface SourceRow {
  id: number | null;
  description: string | null;
  rooms: number | null;
  revenue: number | null;
  roomsMtd: number | null;
  revenueMtd: number | null;
  roomsYtd: number | null;
  revenueYtd: number | null;
}
export interface SegmentMixRow {
  marketId: number | null;
  market: string | null;
  rooms: number | null;
  revenue: number | null;
  roomsMtd: number | null;
  revenueMtd: number | null;
  roomsYtd: number | null;
  revenueYtd: number | null;
}
export interface ChannelMix {
  ota: OtaRow[];
  sources: SourceRow[];
  segments: SegmentMixRow[];
  loaded: boolean;
  refreshing: boolean;
  stale: boolean;
  fetchedAt: string | null;
  error: string | null;
}
export interface CompanyRow {
  id: string;
  name: string;
  rooms: number;
  idrRooms: number;
  revenue: number;
  netRevenue: number;
}
export interface GroupPickupRow {
  id: string;
  name: string;
  rooms: number;
  idrRooms: number;
  revenue: number;
  netRevenue: number;
  pickupRooms: number;
  pickupRevenue: number;
  pickupNetRevenue: number;
}
export interface SourceBreakdown {
  start: string;
  end: string;
  companies: CompanyRow[];
  total: BreakdownMetrics;
}
export interface ChannelBucket {
  id: string;
  name: string;
  rooms: number;
  idrRooms: number;
  revenue: number;
  netRevenue: number;
}
export interface DirectShareSeriesPoint {
  date: string;
  [bucketId: string]: string | BreakdownMetrics;
}
export interface DirectShare {
  start: string;
  end: string;
  quality: string;
  buckets: ChannelBucket[];
  series: DirectShareSeriesPoint[];
  directSharePct: number | null;
}
export const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
export const hotelToday = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Makassar",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export const sumKnown = (values: (number | null)[]) =>
  values.some((v) => v == null)
    ? null
    : values.reduce<number>((s, v) => s + (v ?? 0), 0);
export const difference = (a: number | null, b: number | null) =>
  a == null || b == null ? null : a - b;
export const ratio = (a: number | null, b: number | null) =>
  a == null || !b ? null : a / b;
export interface MonthSummary {
  month: string;
  revenue: number | null;
  adr: number | null;
  revpar: number | null;
  budget: number | null;
  gap: number | null;
  required: number | null;
  fullMonth: boolean;
  hasForeign: boolean;
  roomNights: number | null;
}
export function monthlySummary(
  rows: PaceRow[],
  basis: "gross" | "net",
  budgets: Budget[],
  capacities: Record<string, number>,
  today: string,
  filtered: boolean,
): MonthSummary[] {
  return [...new Set(rows.map((r) => r.date.slice(0, 7)))].map((month) => {
    const days = rows.filter((r) => r.date.startsWith(month)),
      known = days.every((r) => r.currentQuality !== "unavailable");
    const revenue = known
      ? days.reduce(
          (s, r) => s + (basis === "gross" ? r.revenue : r.netRevenue),
          0,
        )
      : null;
    const rooms = known ? days.reduce((s, r) => s + r.idrRooms, 0) : null,
      capacity = sumKnown(days.map((r) => capacities[r.date] ?? null));
    const end = new Date(
      Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0),
    ).getUTCDate();
    const fullMonth = days.length === end && days[0]?.date === `${month}-01`;
    // Segment budget is per-day and market-aware, so it works for partial
    // ranges and market filters; fall back to the flat manual target where
    // it isn't available (net basis, room-type filters, or months with no
    // import - the imported workbook only carries gross figures).
    const segmentBudget =
      basis === "gross" ? sumKnown(days.map((r) => r.budgetRevenue)) : null;
    const flatBudget =
      !filtered && fullMonth
        ? (budgets.find((b) => b.month === month && b.basis === basis)
            ?.revenue ?? null)
        : null;
    const budget = segmentBudget ?? flatBudget;
    const gap = difference(revenue, budget),
      futureDays = days.filter((r) => r.date >= today).length;
    return {
      month,
      revenue,
      adr: ratio(revenue, rooms),
      revpar: ratio(revenue, capacity),
      budget,
      gap,
      required:
        gap == null || !futureDays ? null : Math.max(0, -gap) / futureDays,
      fullMonth,
      hasForeign: days.some((r) => r.rooms !== r.idrRooms),
      roomNights: known ? days.reduce((s, r) => s + r.rooms, 0) : null,
    };
  });
}
// Missing values render as an em dash; "About this data" explains it.
export const EMPTY = "—";
export const num = (v: number | null | undefined) =>
  v == null
    ? EMPTY
    : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
export const money = (v: number | null | undefined) =>
  v == null ? EMPTY : `IDR ${Math.round(v).toLocaleString("en-US")}`;
// Compact IDR for dense tables (6.3B, 2.17M, 850K); pair with money() as a title.
export const moneyShort = (v: number | null | undefined) => {
  if (v == null) return EMPTY;
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(a >= 1e10 ? 1 : 2)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(a >= 1e7 ? 1 : 2)}M`;
  if (a >= 1e3) return `${Math.round(v / 1e3)}K`;
  return String(Math.round(v));
};
export const signed = (v: number | null) =>
  v == null ? EMPTY : `${v > 0 ? "+" : ""}${num(v)}`;
export const percent = (v: number | null) =>
  v == null ? EMPTY : `${v.toFixed(1)}%`;
export const timestamp = (v: string | null | undefined) =>
  v
    ? new Date(v).toLocaleString("en-GB", {
        timeZone: "Asia/Makassar",
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Unavailable";
export const dayLabel = (v: string) =>
  new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
export const shortDayYear = (v: string) =>
  v
    ? new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", {
        timeZone: "UTC",
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "–";
export const pctDiff = (cur: number | null, prev: number | null) =>
  cur == null || prev == null || !prev ? null : ((cur - prev) / prev) * 100;
export const pctLabel = (v: number | null) =>
  v == null ? EMPTY : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
export const signClass = (v: number | null) =>
  v == null ? "" : v > 0 ? "text-emerald-700" : v < 0 ? "text-rose-700" : "";
export const currentRooms = (r: PaceRow) =>
  r.currentQuality === "unavailable" ? null : r.rooms;
export const revenueFor = (r: PaceRow, basis: "gross" | "net") =>
  basis === "gross" ? r.revenue : r.netRevenue;
export const pickupRevenueFor = (r: PaceRow, basis: "gross" | "net") =>
  basis === "gross" ? r.pickupRevenue : r.pickupNetRevenue;
export const groupRevenueFor = (r: GroupPickupRow, basis: "gross" | "net") =>
  basis === "gross" ? r.revenue : r.netRevenue;
export const groupPickupRevenueFor = (r: GroupPickupRow, basis: "gross" | "net") =>
  basis === "gross" ? r.pickupRevenue : r.pickupNetRevenue;
export const breakdownRevenue = (
  m: { revenue: number; netRevenue: number },
  basis: "gross" | "net",
) => (basis === "gross" ? m.revenue : m.netRevenue);
export interface PaceBucket {
  key: string;
  rooms: number | null;
  comparison: number | null;
  revenue: number | null;
  comparisonRevenue: number | null;
  adr: number | null;
  comparisonAdr: number | null;
  budgetRooms: number | null;
  budgetRevenue: number | null;
  budgetAdr: number | null;
}
// Shared daily/weekly/monthly bucketing + chart shaping for a pace table -
// used by both the main RMS page and any page reusing RmsPaceTab.vue.
export function paceBuckets(
  rows: PaceRow[],
  chartView: string,
  basis: "gross" | "net",
): PaceBucket[] {
  const m = new Map<string, PaceRow[]>();
  for (const r of rows) {
    let key = r.date;
    if (chartView === "monthly") key = key.slice(0, 7);
    if (chartView === "weekly")
      key = addDays(key, -((new Date(`${key}T00:00:00Z`).getUTCDay() + 6) % 7));
    m.set(key, [...(m.get(key) || []), r]);
  }
  return [...m].map(([key, rs]) => {
    const bucketRevenue = sumKnown(
        rs.map((r) => (currentRooms(r) == null ? null : revenueFor(r, basis))),
      ),
      bucketIdrRooms = rs.reduce((s, r) => s + r.idrRooms, 0),
      bucketComparisonRevenue = sumKnown(
        rs.map((r) => (basis === "gross" ? r.stlyRevenue : r.stlyNetRevenue)),
      ),
      bucketStlyIdrRooms = sumKnown(rs.map((r) => r.stlyIdrRooms)),
      bucketBudgetRooms = sumKnown(rs.map((r) => r.budgetRooms)),
      bucketBudgetRevenue = sumKnown(rs.map((r) => r.budgetRevenue));
    return {
      key,
      rooms: sumKnown(rs.map(currentRooms)),
      comparison: sumKnown(rs.map((r) => r.stlyRooms)),
      revenue: bucketRevenue,
      comparisonRevenue: bucketComparisonRevenue,
      adr: ratio(bucketRevenue, bucketIdrRooms),
      comparisonAdr: ratio(bucketComparisonRevenue, bucketStlyIdrRooms),
      budgetRooms: bucketBudgetRooms,
      budgetRevenue: bucketBudgetRevenue,
      budgetAdr: ratio(bucketBudgetRevenue, bucketBudgetRooms),
    };
  });
}
export function paceChartTable(buckets: PaceBucket[], rows: PaceRow[]) {
  const totalRevenue = sumKnown(buckets.map((x) => x.revenue)),
    totalComparisonRevenue = sumKnown(buckets.map((x) => x.comparisonRevenue)),
    totalIdrRooms = rows.reduce((s, r) => s + r.idrRooms, 0),
    totalStlyIdrRooms = sumKnown(rows.map((r) => r.stlyIdrRooms)),
    totalBudgetRooms = sumKnown(buckets.map((x) => x.budgetRooms)),
    totalBudgetRevenue = sumKnown(buckets.map((x) => x.budgetRevenue));
  return {
    buckets,
    totals: {
      rooms: sumKnown(buckets.map((x) => x.rooms)),
      comparison: sumKnown(buckets.map((x) => x.comparison)),
      revenue: totalRevenue,
      comparisonRevenue: totalComparisonRevenue,
      adr: ratio(totalRevenue, totalIdrRooms),
      comparisonAdr: ratio(totalComparisonRevenue, totalStlyIdrRooms),
      budgetRooms: totalBudgetRooms,
      budgetRevenue: totalBudgetRevenue,
      budgetAdr: ratio(totalBudgetRevenue, totalBudgetRooms),
    },
  };
}
export function paceChartData(buckets: PaceBucket[], compareWithBudget: boolean) {
  return {
    labels: buckets.map((b) => b.key),
    datasets: [
      {
        type: "bar" as const,
        label: "OTB room nights",
        data: buckets.map((b) => b.rooms),
        backgroundColor: "#334155",
        yAxisID: "rooms",
        order: 2,
      },
      compareWithBudget
        ? {
            type: "bar" as const,
            label: "Budget nights (gross)",
            data: buckets.map((b) => b.budgetRooms),
            backgroundColor: "#fcd34d",
            yAxisID: "rooms",
            order: 2,
          }
        : {
            type: "bar" as const,
            label: "Comparison nights",
            data: buckets.map((b) => b.comparison),
            backgroundColor: "#cbd5e1",
            yAxisID: "rooms",
            order: 2,
          },
      {
        type: "line" as const,
        label: "IDR ADR",
        data: buckets.map((b) => b.adr),
        borderColor: "#0f766e",
        yAxisID: "adr",
        order: 1,
      },
      compareWithBudget
        ? {
            type: "line" as const,
            label: "Budget ADR (gross)",
            data: buckets.map((b) => b.budgetAdr),
            borderColor: "#b45309",
            borderDash: [4, 4],
            yAxisID: "adr",
            order: 1,
          }
        : {
            type: "line" as const,
            label: "Comparison ADR",
            data: buckets.map((b) => b.comparisonAdr),
            borderColor: "#64748b",
            borderDash: [4, 4],
            yAxisID: "adr",
            order: 1,
          },
    ],
  };
}
export const PACE_CHART_OPTIONS: ChartOptions<keyof ChartTypeRegistry> = {
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
      min: 1000000,
      grid: { drawOnChartArea: false },
      title: { display: true, text: "ADR (IDR)" },
    },
  },
};
// Shared "value vs. a comparison figure" tile sub-line (used by stat tiles
// comparing against last year or budget).
export function vsLy(
  cur: number | null,
  comparison: number | null,
  fmt: (v: number | null) => string,
  label = "vs LY",
) {
  const d = pctDiff(cur, comparison);
  if (cur == null) return { text: `${label} \u2014` };
  return {
    text: `${pctLabel(d)} ${label} (${fmt(comparison)})`,
    tone: signClass(d) || undefined,
  };
}
export function csvText(rows: unknown[][]) {
  return (
    "\uFEFF" +
    rows
      .map((row) =>
        row
          .map((value) => {
            let s = value == null ? "" : String(value);
            if (typeof value === "string" && /^[\s]*[=+\-@]/.test(s))
              s = "'" + s;
            return '"' + s.replace(/"/g, '""') + '"';
          })
          .join(","),
      )
      .join("\r\n")
  );
}
