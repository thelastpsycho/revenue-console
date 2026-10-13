import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";
const source = ts.transpileModule(
  readFileSync(new URL("../src/utils/briefing.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  },
).outputText;
const { briefingReportLink } = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);
test("briefing links preserve the period and clear persisted market/room/channel filters", () => {
  const r = briefingReportLink(
    { start: "2026-10-13", end: "2026-10-19" },
    "pace",
  );
  assert.equal(r.query.start, "2026-10-13");
  assert.equal(r.query.end, "2026-10-19");
  assert.equal(r.query.marketId, "");
  assert.equal(r.query.roomType, "");
  assert.equal(r.query.channels, "");
  assert.equal(r.query.basis, "gross");
  assert.equal(r.query.pickupDays, "7");
});
test("budget links explicitly select budget comparison", () => {
  assert.equal(
    briefingReportLink(
      { start: "2026-10-13", end: "2026-11-11" },
      "pace",
      "budget",
    ).query.compareWith,
    "budget",
  );
});
