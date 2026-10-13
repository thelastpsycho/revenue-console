/** Explicit filters override saved RMS selections so briefing links reconcile. */
export function briefingReportLink(
  period: { start: string; end: string },
  tab: string,
  compareWith = "yoy",
) {
  return {
    path: "/rms",
    query: {
      start: period.start,
      end: period.end,
      tab,
      basis: "gross",
      pickupDays: "7",
      comparison: "calendar",
      compareWith,
      marketId: "",
      roomType: "",
      channels: "",
    },
  };
}
