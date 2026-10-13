export interface Schedule {
  enabled: boolean;
  live: boolean;
  intervalMinutes: number;
  nextRunAt: string | null;
  schedulerOnline: boolean;
}
export interface Run {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  error: string | null;
}
export interface Coverage {
  from: string | null;
  to: string | null;
  days: number;
  missingDays: number;
  includesToday: boolean;
}
export const tone = (
  label: string,
  level: "ok" | "warn" | "bad" | "muted",
) => ({ label, pill: `pill-${level}` });
export function scheduleTone(
  schedule: Schedule | null,
  active: boolean,
  error: boolean,
) {
  if (error) return tone("Unable to load", "bad");
  if (!schedule) return tone("Unknown", "muted");
  if (active) return tone("Running", "warn");
  if (!schedule.enabled) return tone("Off", "muted");
  if (!schedule.schedulerOnline) return tone("Scheduler offline", "warn");
  return tone(
    schedule.live ? "Live" : "Preview",
    schedule.live ? "warn" : "ok",
  );
}
export function runTone(run: Run | null) {
  if (!run) return tone("No scheduled runs", "muted");
  if (run.status === "error" || run.error)
    return tone("Last run failed", "bad");
  if (run.status === "running") return tone("Last run unfinished", "warn");
  if (run.status === "success") return tone("Last run succeeded", "ok");
  return tone("Last run status unknown", "muted");
}
export function inventoryTone(
  count: number | null,
  updatedAt: string | null,
  coverage: Coverage | null,
  error: boolean,
  now: number,
  thresholdMinutes: number,
) {
  if (error) return tone("Unable to load", "bad");
  if (!coverage?.days) return tone("No upcoming coverage", "muted");
  const updated = updatedAt ? Date.parse(updatedAt) : NaN;
  if (!Number.isFinite(updated) || now - updated > thresholdMinutes * 60000)
    return tone("Stale inventory", "warn");
  if (!coverage.includesToday || coverage.missingDays)
    return tone("Incomplete coverage", "warn");
  if (count == null) return tone("Unknown", "muted");
  return count === 0
    ? tone("Clear in checked range", "ok")
    : tone(`${count} closure date${count === 1 ? "" : "s"}`, "warn");
}
/** Independent in-flight guards: failure in one card never blocks another. */
export function refreshController(
  keys: string[],
  fetchCard: (key: string) => Promise<void>,
) {
  const pending = new Set<string>();
  let stopped = false;
  return {
    async refresh(key?: string) {
      if (stopped) return;
      await Promise.allSettled(
        (key ? [key] : keys).map(async (k) => {
          if (pending.has(k)) return;
          pending.add(k);
          try {
            await fetchCard(k);
          } finally {
            pending.delete(k);
          }
        }),
      );
    },
    stop() {
      stopped = true;
    },
  };
}
