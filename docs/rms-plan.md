# Simple RMS - Phase 1: Pace & Forecast

**Status: phase 1 built (2026-10-11).** Forecast + pace are live on the
`/rms` page. See "As built" below for where the build diverged from this
sketch after live probing; the rest of this doc is the original plan.

## As built (2026-10-11)

- Code: `revenue/rms_forecast.py` (live forecast), `revenue/booking_events.py`
  (cache, sync jobs, pace queries), `routes/rms_routes.py` (`/api/rms/*`),
  `RmsView.vue` (`/rms`: Forecast / Pace / Booking data tabs).
- **Cancelled is `L`, not `C`** - `C` returns nothing. `L` rows carry
  `CancelReason`; the first `UpdatedDate` seen while `L` (converted to local
  date via the row's `TimeZone`) is stored as the cancel date. `N` is valid.
  Status filter used: `D,T,Q,I,O,L,N`.
- **Rows repeat per folio** - one `ReservationId` appears once per folio with
  identical fields; only the `IsMasterFolio` row is kept (exactly one each).
- **`Mode: "ARRIVAL_DATE"` works** and returns every booking for those
  arrivals regardless of when it was made, so the weekly resync is trailing
  90 days by reservation date **plus** the next 365 days by arrival date -
  that's what catches late cancellations/amendments of future stays.
- Pace counts **stay nights** (`booking_nights`, arrival <= night < departure),
  not just arrival date. STLY = same weekday (364 days back), as of the same
  number of days before. Verified: on-the-books for future dates matched
  `ReportForecastOccupancy` rooms sold exactly.
- ~4% of bookings are USD-priced; they count in room nights but USD revenue
  is summed separately, never converted.
- Forecast endpoints: `ReportForecastOccupancy` and `ReportExpectedRoomOccupied`
  ignore `Days` (always 7) but honour any `TrxDate`, so they're chunked.
  `ReportExpectedRoomOccupied` uses a server temp table named by
  hotel+timestamp - **concurrent calls fail** (`Invalid object name
  'xtempRoomAvail_...'`), so its chunks run serially. Segment calls are slow
  (~27 s / 30 days), so they're chunked in parallel; 90 days loads in ~45 s.
- Scheduling: the scheduler container's 30 s tick
  (`/api/fast-pipeline/schedule/tick`) also starts the booking sync when
  due - weekly resync, otherwise the daily 7-day pull, after 04:00 local.
  Nothing scheduled runs until the operator has run the backfill once
  (Booking data tab, or `python -m app.revenue.booking_events backfill`).
- Not built yet: the drill-down forecast cuts (`Company`, `Nationality`,
  `Detail`, `Summary`, `Promotion`, `ExpectedAllotmentRoomOccupied`).

**Phase 1 scope is deliberately narrowed to two things: forecast and
pace.** Actuals, rate/yield detail, channel mix, and competitor
benchmarking are real findings from the API probing (see
[pms-data-api.md](pms-data-api.md)) but are explicitly **deferred to a
later phase** - see "Out of scope for this phase" at the bottom. Room
revenue only, no F&B/outlet revenue, for the whole project regardless of
phase.

## Goal

Answer two questions for any future date: **"what's forecast to happen"**
(occupancy/revenue projection, as the PMS currently sees it) and **"how did
the booking volume for this date build up over time"** (pace/pickup,
reconstructed from our own booking-transaction history). Per room type and
market segment where the underlying endpoint supports it.

## Forecast - live API calls, no local storage needed

All forecast endpoints are called live and rendered directly - they're
cheap, single-digit-row-count calls, no reason to cache them for phase 1.
All via the existing `PMSApiClient` (`backend/app/integrations/pms/api_client.py`)
pattern - bearer JWT login, `POST api/{Name}`. Full quirks (exact `Days`
behavior, response shape, sample rows) are documented in
[pms-data-api.md](pms-data-api.md); this table is purpose-only.

| Endpoint | Purpose | Cut |
|---|---|---|
| `ReportForecastOccupancy` | Hotel-wide 7-day forecast - rooms used, revenue, ADR, occupancy % | None (hotel-wide) |
| `ReportForecastOccupancyMarketSegment` | Same forecast, by market segment. **Only endpoint that respects `Days` exactly** - use this when a custom window matters | Market segment |
| `ReportForecastOccupancyCompany` | Same forecast, by company | Company |
| `ReportForecastOccupancyNationality` | Same forecast, by nationality | Nationality |
| `ReportForecastOccupancyDetail` | Richer hotel-wide forecast (adds comp/house-use/definite-group/pax breakdown). Fixed 16-day window, `Days` ignored | None (hotel-wide, richer fields) |
| `ReportForecastOccupancySummary` | MTD/YTD forecast summary, two rows | None |
| `ReportForecastPromotion` | Forward promo revenue by month, with promo validity window attached | Per promotion |
| `ReportExpectedRoomOccupied` | 7-day-ahead occupancy, pivoted by room type (date columns) | Room type |
| `ReportExpectedAllotmentRoomOccupied` | Same pivot, by allotment-holding company/channel instead | Company/channel |

**Core for a v1 forecast view:** `ReportForecastOccupancy` (headline),
`ReportForecastOccupancyMarketSegment` (segment breakdown, flexible
window), `ReportExpectedRoomOccupied` (room-type pivot). The rest
(`Company`/`Nationality`/`Detail`/`Promotion`/`ExpectedAllotment`) are
drill-down cuts to add once the core view works, not launch blockers.

## Pace - the one endpoint that needs a local pipeline

**`POST api/ReportReservationStatus`, `Mode: "RESERVATION_DATE"`** - this
is the only pace-relevant endpoint, and the only one needing infrastructure
beyond a direct API call. Full discovery notes, confirmed behavior, and a
redacted example response are in
[pms-data-api.md](pms-data-api.md#post-apireportreservationstatus---the-real-pacepickup-source).

**Why this endpoint, not a forecast endpoint:** every forecast endpoint
above is "what does the PMS currently project" - a live snapshot. Pace
needs "how did that projection build up" - a time series we can only get
by reconstructing it from the booking **transaction log**
(`ReservationDate` = when a booking was made, independent of
`ArrivalDate` = what date it's for). No other endpoint in the whole
catalog (see the second-pass `Report*` sweep in `pms-data-api.md`) carries
both dates on the same row.

### Storage: SQLite (`booking_events.db`)

No MySQL - volume doesn't justify it (~150 reservations/day observed, so
even a 3-year backfill is ~150-270k rows), and it matches the
single-writer-batch-job pattern every other db in this repo already uses
(`pms_inventory_raw.db`, `combined_inventory.db`, `inventory_allocation.db`).

**What gets persisted per row** - PII dropped at ingest, never written to
disk: `ReservationId`, `ReservationDate`, `ArrivalDate`, `DepartureDate`,
`Nights`, `RoomRate`, `TypeId`, `RateType`, `MarketId`, `ReservationStatus`.
`GuestName`/`EmailAddress`/`MobilePhone`/`IdentityNo`/`ImageLocation`/
`Note`/`Remark` are present in the API response but must never be written
to our table.

### Pull cadence - one endpoint, three jobs, differing only in date window

```json
{"HotelId": "103", "UserId": "KRISNATHA", "TrxDate": "<start>", "TrxDate2": "<end>", "ReservationStatus": "D,T,Q,I,O,C,N", "ReservationSource": "", "Mode": "RESERVATION_DATE"}
```

1. **One-time historical backfill** - loop backward in 30-day chunks from
   today to however far back we want (2-3 years, for YoY). Runs once.
2. **Daily incremental** - trailing 7-day window, run every day, upsert by
   `ReservationId`.
3. **Weekly wider resync** - trailing 90-day window, run weekly, to catch
   cancellations/amendments made after a booking's original creation date
   (this endpoint filters by creation date, not last-modified date, so a
   booking that changes status 40 days after it was made won't reappear in
   the daily 7-day pull).

**Not yet confirmed:** whether `C` (cancelled) and `N` (no-show) are valid
`ReservationStatus` codes - the PMS UI's own default only sends
`D,T,Q,I,O`. Needs a quick live test (same read-only pattern as everything
else probed so far) before the real backfill runs, since without `C`/`N`
visibility, cancellations can't be detected at all and pace would be
systematically overstated.

### Computing pace from the local table

Once `booking_events.db` exists, pace is a local query, no further API
calls:

- Lead time per booking = `ArrivalDate - ReservationDate`.
- Pace curve for a given arrival date = cumulative room-nights/revenue
  bucketed by lead time.
- "On the books as of day X for arrival date Y" = sum of rows where
  `ReservationDate <= X` and `ArrivalDate = Y` and not cancelled as of X
  (requires the `C`/`N` status + a cancel-date proxy, likely `UpdatedDate`
  - not yet tested).
- Same-date-last-year comparison = filter `ArrivalDate` one year back.

## Rough shape (to revisit before building)

- `backend/app/revenue/rms_reports.py` (or similar) - thin wrapper over
  `PMSApiClient` for the forecast endpoint set, returning normalized
  room-revenue rows (no F&B fields). Pure live pass-through, no storage.
- `booking_events.db` + a backfill script + a scheduled incremental-sync
  job (daily 7-day / weekly 90-day) - the one new piece of infrastructure
  this phase actually needs.
- `routes/rms_routes.py` (same pattern as `pms_fast_routes.py`) - exposing
  forecast (live) and pace (queried from `booking_events.db`) to the
  frontend, read-only.
- `RmsView.vue` wired into `router.ts`, following the existing
  routed-component convention - likely two sections/tabs, Forecast and
  Pace.

## Out of scope for this phase (revisit later)

Real findings from the API probing, deliberately not pulled into phase 1
so pace+forecast can ship first:

- **Actuals** - `ManagerReport`, `StatisticMarketSegmentWithBudget`,
  `StatisticRSRBaseOnRoomType`, `StatisticRoomSalesRecapitulation`,
  `StatisticCompanyByMonth`/`StatisticCompanyProduction`.
- **Rate/yield pricing detail** - `RatePromotionList`/`RatePromotionTimeLine`,
  `ReportRateStrategy`, `StatisticRoomRate`/`StatisticRoomRateTypeId`/
  `StatisticRoomTypeId`.
- **Channel mix** - `StatisticOnlineTravelAgentDistribution`,
  `StatisticSourceOfReservation`, the geography stats
  (`StatisticNationality`/`Region`/`City`/`GeographicalOrigin`),
  `StatisticPromotion`.
- **Competitor benchmarking** - `GetHotelCompetitor`/`GetHotelCompetitorMaster`/
  `StatisticHotelCompetitor`.
- **Budget comparisons** - `StatisticMarketSegmentBudgetByMonth`.
- **Commission/net-rate detail** - `ReportCommission` (found in the
  second-pass sweep, not pursued for phase 1).

Current inventory/allotment (`AvailableRoomInventoryType`,
`AllotmentRoomInventory`) and BAR/rate context (`DashboardHotelStatus`)
are already implemented elsewhere in the codebase and can be surfaced
alongside pace/forecast later without new API work.

None of this is scheduled - revisit scope/order when actually starting.
