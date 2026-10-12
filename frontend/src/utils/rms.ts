export interface PaceRow {
  date: string;
  lyDate: string;
  rooms: number;
  idrRooms: number;
  revenue: number;
  netRevenue: number;
  revenueUsd: number;
  pickupRooms: number | null;
  pickupRevenue: number | null;
  newRooms: number | null;
  cancelledRooms: number | null;
  amendedRooms: number | null;
  stlyRooms: number | null;
  stlyRevenue: number | null;
  stlyIdrRooms: number | null;
  stlyNetRevenue: number | null;
  lyFinalRooms: number | null;
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
    const budget =
      !filtered && fullMonth
        ? (budgets.find((b) => b.month === month && b.basis === basis)
            ?.revenue ?? null)
        : null;
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
export const num = (v: number | null | undefined) =>
  v == null
    ? "Unavailable"
    : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
export const money = (v: number | null | undefined) =>
  v == null ? "Unavailable" : `IDR ${Math.round(v).toLocaleString("en-US")}`;
export const signed = (v: number | null) =>
  v == null ? "Unavailable" : `${v > 0 ? "+" : ""}${num(v)}`;
export const percent = (v: number | null) =>
  v == null ? "Unavailable" : `${v.toFixed(1)}%`;
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
  v == null ? "Unavailable" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
export const currentRooms = (r: PaceRow) =>
  r.currentQuality === "unavailable" ? null : r.rooms;
export const revenueFor = (r: PaceRow, basis: "gross" | "net") =>
  basis === "gross" ? r.revenue : r.netRevenue;
export const breakdownRevenue = (
  m: { revenue: number; netRevenue: number },
  basis: "gross" | "net",
) => (basis === "gross" ? m.revenue : m.netRevenue);
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
