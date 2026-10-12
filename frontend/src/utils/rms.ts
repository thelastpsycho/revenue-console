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
export function monthlySummary(
  rows: PaceRow[],
  basis: "gross" | "net",
  budgets: Budget[],
  capacities: Record<string, number>,
  today: string,
  filtered: boolean,
) {
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
