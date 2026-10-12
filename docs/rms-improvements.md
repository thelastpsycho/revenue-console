# RMS decision workspace

The `/rms` page now provides Overview, Pace, PMS forecast, and Data & settings.
No RMS action changes prices or inventory in the PMS or D-EDGE.

## Operator workflow

1. Run an initial backfill in **Data & settings**, then a daily refresh. Existing
   installations retain their cache and migrate automatically.
2. Choose stay dates, room type, market, pickup window, and comparison; press
   **Apply**. The URL retains applied filters. Unapplied controls do not change
   displayed results, date drilldowns, or exports.
3. Review **Dates requiring attention**. Thresholds are configurable. Click a date
   for its curve, physical room availability, market segments and shared meeting note.
4. Select gross IDR or estimated net IDR revenue. Export the filtered pace table
   as CSV; notes, revenue basis, data-quality labels and source sync timestamp are
   included. Exported string fields are protected against spreadsheet formulas.
5. Enter monthly IDR revenue targets on the same gross/net basis. Monthly target
   comparisons are intentionally unavailable for partial months or filtered room
   types/markets. Required remaining revenue is the positive target gap divided
   by remaining calendar days, including today. It is not a demand forecast.

## History and coverage

`booking_versions` appends the normalized, PII-free reservation state whenever
its business fields change. Versions retain stay dates, status, rate, currency,
room type, market, RateType and (when supplied) RateId. Repeated imports do not
create duplicate versions. Existing `bookings` and `booking_nights` remain the
latest-state cache; upgrading seeds existing records as first observations.

As-of queries choose the last version observed by the requested hotel-local day.
The daily resolution represents the latest observation on that day, not the
exact time of the PMS amendment. Newly discovered old bookings cannot rewrite
an already observed date. Earlier queries use the first available version to
reconstruct history and are explicitly **estimated**. Cancellation date remains
a proxy based on the first observed cancelled row's UpdatedDate.

A backfill cannot recover earlier amendments, nightly rate changes, or every
cancellation/reinstatement that occurred between observations. “Observed” means
observed by this application, not a complete PMS audit trail. “Estimated” means
reconstructed from the earliest available version. As-of dates before the
completed backfill's booking-date coverage have null comparisons rather than
zero. Long-lead bookings created before that coverage can still be missing;
coverage is a booking-creation boundary, not a guarantee of complete historical
stay-date inventory. Use sufficient backfill depth for the chosen comparison.

Pickup is decomposed into new, cancelled and net amended room nights, with
`new - cancelled + amendments = net pickup`. Filter/date moves and reinstatements
are amendments; a late-discovered older booking is also an amendment to the
observed books. Historical breakdowns before observations began are estimates.
Future current-curve points are omitted and a Today marker is drawn.

## Refresh and definitions

Daily jobs refresh seven creation days **plus arrivals from 30 days ago through
365 days ahead**, extending the lookback to the earliest cached in-house arrival.
Weekly jobs additionally refresh 90 creation days. A booking moved outside all
these search windows can remain stale until a broader backfill; the PMS has no
verified modified-since feed in this integration. Runs begin after 04:00 Bali
time. A missing successful-sync timestamp or one older than 36 hours is stale.
A newly completed sync does not relabel an already displayed report as refreshed;
the page prompts the operator to Apply again.

IDR revenue and ADR exclude all other currencies. All currencies still count in
room nights. The IDR ADR coverage percentage makes this explicit. Estimated net
revenue defaults to `max(rate - 350000, 0) / 1.21`. Effective-date wildcard,
RateType and optional package RateId rules can override this. A RateId rule takes
precedence over a RateType rule, which takes precedence over the wildcard.
Changing rules restates estimated net calculations, not stored gross history.

RevPAR is explicitly the **IDR revenue component divided by room capacity** and
is unavailable when capacity is missing or a market filter is active. These are
booking positions, not audited actual room revenue. PMS forecast revenue/ADR use
the PMS report's definitions and are displayed separately. PMS RoomUsed semantics
are not fully verified; a reconciliation difference is a reason to check, not an
automatic assertion that either source is wrong.

Last-applied BAR reads the existing confirmed local apply record, labeled with
its file timestamp. It is not live rate verification or an IDR quote. Physical
availability uses AvailableRoomInventoryType, not channel allotments. Monthly
budgets are operator-entered because the documented PMS budget units remain
unverified. No unsupported PMS endpoint assumptions are introduced.

## Forecast cache and deployment

`rms_forecast_cache.db` stores hotel, market, room-type and physical-availability
sections independently by requested start/day count. Results are fresh for five
minutes. A GET immediately returns cached/empty sections and starts background
refreshes when stale. Polling shows sections as they complete. On error, the
previous payload and timestamp remain visible; explicit Refresh retries failures.
Database leases deduplicate concurrent refreshes of the same section. The PMS
room-type report is serialized using an OS file lock across requests/processes
because its server temp table cannot handle concurrent calls. Network operations
have connect/read timeouts. Forecast is capped at 90 days; pace at 366 days.

Keep the existing deployment's **one Gunicorn worker** requirement; pipeline and
booking-sync job progress still use process-local state. Both new persistent
state and the lock live under the existing runtime data directory/volume. Back
up booking_events.db before deployment as part of the normal DB backup procedure.
The migration is additive; no old bookings are deleted. Rolling back the code
leaves the new tables and settings harmlessly present.

## Verification

- `PYTHONPATH=backend python -m pytest -q backend/tests`
- `npm --prefix frontend test`
- `npm --prefix frontend run build`

Regression tests cover retained amendments, cancellations/reinstatements, late
old-booking discovery, idempotent PII-free versions, long in-house refreshes,
missing coverage, leap/custom comparisons, package deductions, currency isolation,
settings validation, CSRF, cache deduplication/failure retention, weighted ADR,
partial-month targets and CSV formula protection. No test uses live PMS data.

## Grouped reports

RMS navigation groups reports into Performance & Forecast, Pace & Pickup,
Booking Behaviour, Business Production, and Room Type & Inventory, alongside
Overview and Data & Settings. Existing forecast/data deep links retain their IDs.

`GET /api/rms/reports` reads existing booking versions. Production is grouped by
market ID, room-type code and RateId (falling back to RateType), with OTB nights,
IDR revenue, weighted IDR ADR, currency coverage, 1/7/30-day pickup, the selected
pickup decomposition and matched-period comparison. Missing market IDs remain
Unassigned. Group totals include comparison/prior-only groups so amendments and
cancellations remain visible. Drilldowns apply the segment or room type to the
existing pace page. The segment trend shows the top five groups plus Other.

Behaviour uses unique reservations rather than stay nights. Its own date-basis
selector switches between stays overlapping the selected dates and bookings
created within those dates; production continues to use stay dates. Lead time,
full-reservation length of stay, booking/arrival weekdays and current cancelled /
no-show counts are provided. Active behaviour distributions exclude cancelled
and no-show reservations. Cancellation percentages use all reservations in the
selected cohort, including cancelled/no-show rows; they are not event rates or
predictions of future cancellations. Negative lead times are disclosed and omitted
from lead-time buckets and averages.

Room inventory displays physical availability independently from segment/market
filters, with expected occupied / capacity and high-occupancy shading. Revenue
and historical-quality definitions are the same as existing pace. CSV exports
retain nulls and protect string values against spreadsheet formula execution.

Channel/company/nationality production, commission-based contribution, audited
actuals and forecast accuracy are visibly marked as needing additional verified
data. Rate-plan production does not claim to measure promotion attribution.
