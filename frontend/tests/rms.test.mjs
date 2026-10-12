import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";
const source = ts.transpileModule(
  readFileSync(new URL("../src/utils/rms.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  },
).outputText;
const { monthlySummary, csvText, addDays, sumKnown } = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);
const rows = Array.from({ length: 31 }, (_, i) => ({
  date: `2026-10-${String(i + 1).padStart(2, "0")}`,
  rooms: 3,
  idrRooms: 2,
  revenue: 200,
  netRevenue: 100,
  currentQuality: "observed",
}));
const capacities = Object.fromEntries(rows.map((r) => [r.date, 10]));
test("monthly ADR is weighted over IDR nights, not all currencies", () => {
  const [m] = monthlySummary(
    rows,
    "gross",
    [{ month: "2026-10", basis: "gross", revenue: 10000 }],
    capacities,
    "2026-10-12",
    false,
  );
  assert.equal(m.revenue, 6200);
  assert.equal(m.adr, 100);
  assert.equal(m.revpar, 20);
  assert.equal(m.gap, -3800);
  assert.equal(m.required, 190);
  assert.equal(m.hasForeign, true);
});
test("partial months, filtered reports and mismatched basis have no budget comparison", () => {
  const b = [{ month: "2026-10", basis: "net", revenue: 10000 }];
  assert.equal(
    monthlySummary(rows.slice(1), "net", b, capacities, "2026-10-12", false)[0]
      .budget,
    null,
  );
  assert.equal(
    monthlySummary(rows, "net", b, capacities, "2026-10-12", true)[0].budget,
    null,
  );
  assert.equal(
    monthlySummary(rows, "gross", b, capacities, "2026-10-12", false)[0].budget,
    null,
  );
});
test("missing capacity and history are unavailable, never fake zero", () => {
  assert.equal(
    monthlySummary(rows, "gross", [], {}, "2026-10-12", false)[0].revpar,
    null,
  );
  assert.equal(
    monthlySummary(
      [{ ...rows[0], currentQuality: "unavailable" }],
      "gross",
      [],
      capacities,
      "2026-10-12",
      false,
    )[0].revenue,
    null,
  );
  assert.equal(sumKnown([1, null]), null);
});
test("CSV protects formulas and correctly quotes commas, quotes and newlines", () => {
  const csv = csvText([['=HYPERLINK("bad")', "a,b", "a\nb", -2]]);
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert.ok(csv.includes('"a,b"'));
  assert.ok(csv.includes('"a\nb"'));
  assert.ok(csv.endsWith('"-2"'));
});
test("date arithmetic handles year and leap boundaries without local timezone", () => {
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2024-02-28", 1), "2024-02-29");
});
