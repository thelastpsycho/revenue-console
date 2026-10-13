# Daily briefing, performance and navigation

The home Overview shows whole-hotel positions for today through the next 7 and
30 calendar days, using Bali-local dates. It provides OTB room occupancy, gross
quoted IDR room-rate revenue, IDR ADR, 7-day net room-night pickup, the imported
gross-IDR daily budget gap, and demand flags. Each figure links to RMS with the
exact date window and explicit whole-hotel filters, overriding saved selections.
Attention dates link to a one-day RMS overview. Thresholds reuse RMS settings.

Room-night positions include all currencies; IDR revenue/ADR exclude other
currencies and show the coverage percentage. Occupancy is OTB room nights divided
by PMS room capacity for the same dates, weighted across the window. Missing
capacity or incomplete budget-date coverage produces Unavailable, never zero.
Budget gaps compare imported pro-rated daily targets, not a flat monthly target
or audited actuals. Comparisons use the same calendar date last year and retain
estimated/unavailable historical quality. Source sync/capacity timestamps and
warnings remain visible when data is missing or stale.

The briefing only asks for the hotel forecast cache section; it does not trigger
market, room-type or physical-availability report calls. It polls briefly while
hotel capacity refreshes, otherwise once per minute, and pauses while hidden.
Failed refreshes retain data with an explicit warning. Existing status cards
continue their independent 15-second refresh.

## Navigation

- Revenue Insights: Overview, RMS, Online segment.
- Distribution Operations: Automation, Run history, Stop sale, BAR.
- Administration: Data health, Mappings, Settings, Access, Backups.
- Advanced under Administration: inventory tables, manual yielder, PMS API test,
  manual inventory collection, manual allotment and the legacy pipeline.

All existing URLs continue to work. Every route loads its view dynamically.
Administration is a read-only hub with current configured mapping values, file
availability/timestamps, report timings and links to existing settings. Access
reports the current shared-operator authentication model and supports sign-out;
this change does not add individual accounts or roles. Backups explicitly say
that no managed backup service or verified external-backup timestamp is available.
It provides guidance, not a new backup/restore implementation. No credentials or
runtime filesystem paths are returned by the administration API.

## Report performance

Pace tables/curves, grouped reports, room/rate breakdown and Online source/direct
share calculations use a bounded, process-local 60-second cache (64 entries).
Keys include all function arguments and the Bali-local date. Booking/settings
and budget file identity, size and nanosecond modification times (including WAL
files if present) invalidate cached values. Concurrent identical calculations
are deduplicated. A source mutation during calculation prevents that result from
being cached; failures are never cached. Returned data is copied so callers
cannot corrupt subsequent responses. Current sync metadata is assembled outside
the calculation cache. Initial creation/migration of a source database can cause
an additional cache miss; subsequent stable requests hit the cache.

RMS responses expose Server-Timing and X-Report-Cache. Administration > Advanced
shows median/p95 timings over the last 200 requests per endpoint in this server
process, including cache hits. Metrics and calculation caches reset on restart;
the existing deployment still requires one Gunicorn worker.

Reproduce the local synthetic calculation benchmark:

```bash
PYTHONPATH=backend python scripts/benchmark_rms_reports.py
```

The fixture uses 12,000 bookings in a temporary directory and no live PMS calls.
Before this change: pace30 ~295 ms, reports30 ~699 ms. With the cache, one run
measured pace30 cold ~456 ms, first repeat ~358 ms (initial budget DB creation),
then ~0.5 ms; reports30 cold ~732 ms, repeats ~0.8 ms. These measure Python
calculations, not HTTP serialization, network latency or production workloads.
The entry JS bundle decreased from ~954 KB (~306 KB gzip) to ~167 KB (~63 KB
gzip); page and shared chart/spreadsheet chunks are requested separately.

Validation includes period/currency/budget calculations, unavailable states,
source invalidation, non-mutating cache reads, failed-calculation behavior,
admin credential omission, briefing filter-reset links, backend regression tests,
frontend tests and production typecheck/build. Live PMS/browser verification is
outside these local checks.
