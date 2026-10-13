import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";
const source = ts.transpileModule(
  readFileSync(
    new URL("../src/utils/dashboardStatus.ts", import.meta.url),
    "utf8",
  ),
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  },
).outputText;
const { scheduleTone, runTone, inventoryTone, refreshController } =
  await import(
    "data:text/javascript;base64," + Buffer.from(source).toString("base64")
  );
const schedule = {
  enabled: true,
  live: true,
  intervalMinutes: 15,
  nextRunAt: null,
  schedulerOnline: true,
};
const now = Date.parse("2026-10-13T04:00:00Z"),
  fresh = "2026-10-13T03:50:00Z";
const coverage = {
  from: "2026-10-13",
  to: "2026-10-14",
  days: 2,
  missingDays: 0,
  includesToday: true,
};
test("failed requests are never represented as Off", () => {
  assert.equal(scheduleTone(null, false, true).label, "Unable to load");
  assert.equal(
    scheduleTone({ ...schedule, enabled: false }, false, false).label,
    "Off",
  );
});
test("schedule mode and failed/unfinished run health remain separate", () => {
  assert.equal(scheduleTone(schedule, false, false).label, "Live");
  assert.equal(
    runTone({ status: "error", error: "provider failed" }).label,
    "Last run failed",
  );
  assert.equal(
    runTone({ status: "running", error: null }).label,
    "Last run unfinished",
  );
  assert.equal(scheduleTone(schedule, true, false).label, "Running");
});
test("zero closure dates are green only with fresh complete coverage", () => {
  assert.equal(
    inventoryTone(0, fresh, coverage, false, now, 30).pill,
    "pill-ok",
  );
  assert.equal(
    inventoryTone(0, "2026-10-12T00:00:00Z", coverage, false, now, 30).label,
    "Stale inventory",
  );
  assert.equal(
    inventoryTone(0, fresh, null, false, now, 30).label,
    "No upcoming coverage",
  );
  assert.equal(
    inventoryTone(0, fresh, { ...coverage, missingDays: 1 }, false, now, 30)
      .label,
    "Incomplete coverage",
  );
  assert.equal(
    inventoryTone(
      0,
      fresh,
      { ...coverage, includesToday: false },
      false,
      now,
      30,
    ).label,
    "Incomplete coverage",
  );
  assert.equal(
    inventoryTone(0, fresh, coverage, true, now, 30).label,
    "Unable to load",
  );
});
test("missing timestamp and unknown counts cannot show Clear", () => {
  assert.equal(
    inventoryTone(0, null, coverage, false, now, 30).label,
    "Stale inventory",
  );
  assert.equal(
    inventoryTone(null, fresh, coverage, false, now, 30).label,
    "Unknown",
  );
});
test("refreshes are independent, deduplicated while pending and stop cleanly", async () => {
  const calls = [];
  let resolve;
  const blocked = new Promise((r) => (resolve = r));
  const c = refreshController(["pipeline", "sync", "stopSale"], async (key) => {
    calls.push(key);
    if (key === "pipeline") await blocked;
    if (key === "sync") throw Error("offline");
  });
  const first = c.refresh();
  await c.refresh();
  assert.deepEqual(calls, ["pipeline", "sync", "stopSale"]);
  resolve();
  await first;
  assert.equal(calls.filter((x) => x === "pipeline").length, 1);
  await c.refresh();
  assert.equal(calls.length, 6);
  c.stop();
  await c.refresh();
  assert.equal(calls.length, 6);
});
