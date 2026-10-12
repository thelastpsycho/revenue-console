# PMS data API (`api5b.hospitality.citiskg.com`)

This is the **actual per-hotel business-data API** - the host
`backend/app/integrations/pms/api_client.py` already talks to (bearer JWT
from the `fo.hospitality.mykg.id` login form, then `POST /api/{path}`). Not
to be confused with the ops/admin gateway documented in
[pms-api-gateway.md](pms-api-gateway.md) (`api.hospitality.mykg.id`), which
is a different host entirely.

Endpoints already implemented in `api_client.py`: `AvailableRoomInventoryType`
(`get_available_room_inventory`), `AllotmentRoomInventory`
(`get_allotment_room_inventory`), `allotment` (`save_allotment`). This file
tracks endpoints found by probing beyond those.

## `POST api/AvailableRoomInventory`

**Description:** returns physical room availability for a date range,
pivoted by room type/metric (one row per type, one column per date) -
equivalent to the pivot-table view of the Room Availability page, as
opposed to `AvailableRoomInventoryType`'s per-date list view of the same
underlying numbers.

Same auth/shape convention as `AvailableRoomInventoryType` - body:

```json
{ "TrxDate": "2026-10-08", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA" }
```

**Quirk confirmed, matches `AvailableRoomInventoryType`:** `Days` values
below 7 are silently ignored; the response always covers at least a 7-day
window starting at `TrxDate`. `Days: 14` correctly returns 14 date columns.

**Shape is the transpose of `AvailableRoomInventoryType`:** instead of one
row per date with room types as columns, this returns one row per
type/metric with *dates* as columns (`"10-08"`, `"10-09"`, ... `MM-DD`
keys). 26 rows total - 19 real room-type codes plus 7 summary pseudo-rows:

```
DLK, DLKP, DLT, DLTP, DLS, PRKG, PRKL, PRKP, PRTG, PRTL, PRTP, PSU, FAM,
BFS, AVS, ASW, ASP, AVR, AVP,
OCCUPANCY %, TOTAL ROOM, AVAILABLE, DEFINTE, TENTATIVE, ALLOTMENT,
OUT OF ORDER
```

(Note the vendor's own typo: `DEFINTE`, not `DEFINITE`.)

Example row:

```json
{
  "ROW_ID": 1,
  "HotelId": 103,
  "TypeId": "DLK",
  "10-08": 1.0,
  "10-09": 0.0,
  "10-10": 0.0,
  "10-11": 0.0,
  "10-12": 1.0,
  "10-13": 0.0,
  "10-14": 0.0,
  "StartDate": "2026-10-08T00:00:00",
  "EndDate": "2026-10-14T00:00:00"
}
```

Cross-checked against `AvailableRoomInventoryType` for the same date/hotel:
`DLK` on `10-08` is `1` in both - confirms this is the same physical
availability data as the existing endpoint, just pivoted (room
type/metric as rows, dates as columns) rather than one row per date. This
is presumably what backs the Room Availability page's pivot-table view, as
opposed to the per-date list view `AvailableRoomInventoryType` backs.

Likely not needed for anything the app doesn't already get from
`get_available_room_inventory` - same underlying numbers, just transposed -
but noting it here since it was explicitly probed.

## `POST api/ForecastOccupancyList`

**Description:** returns a revenue-management forecast - projected room
nights, room revenue, and average room rate broken out by market segment,
for every day of the calendar month containing `TrxDate`. This is
reservation/booking-pace data (forward-looking demand by segment), not
physical room availability like the two endpoints above.

Body - same field names as the other endpoints, but behaves differently:

```json
{ "TrxDate": "2026-10-08", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA" }
```

**Quirk (different from the other two endpoints): `Days` is ignored
entirely**, and `TrxDate`'s day-of-month is ignored too - the response
always covers the **whole calendar month** that `TrxDate` falls in
(confirmed: `TrxDate=2026-10-15, Days=3` still returned Oct 1-31;
`TrxDate=2026-11-01` returned all of November; `TrxDate=2026-01-01` returned
all of January).

Shape: one row per `(Date, Market Segment)` combination that has data - not
a dense grid, rows for segments/dates with nothing booked are simply
omitted (row count varies: 263 rows for October, 203 for November, 240 for
January). 10 market segments observed: `Unique, Corporate, FIT, Government,
Group - AdHoc, Group - IT Series, Meeting, Online, Package, Travel Agent`.

Example row:

```json
{
  "HotelId": 103,
  "Date": "2026-10-01T00:00:00",
  "Hotel Name": "The ANVAYA Beach Resort Bali",
  "Market Id": "2",
  "Market Segment": "Corporate",
  "Room Night": 15,
  "Room Revenue": 27066116.0,
  "Average Room Rate": 1804408.0
}
```

`Room Revenue`/`Average Room Rate` are in IDR (no currency field - inferred
from magnitude). `Market Id` is a numeric string that maps 1:1 to `Market
Segment` (not independently verified against a lookup table).

## `POST api/ReportForecastOccupancy`

**Description:** daily occupancy forecast at the whole-hotel level - rooms
used, room count, room revenue, ADR, occupancy %, plus comp/house-use room
counts and a same-weekday-last-year transient comparison. This is the
hotel-wide version of `ReportForecastOccupancyMarketSegment` below (no
market-segment breakdown).

Body: `{ "TrxDate": "2026-10-08", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA" }`

**Quirk: `Days` is ignored entirely** - always returns exactly 7 rows (one
per day) starting at `TrxDate`, regardless of whether `Days` is 1, 3, or 14.

Example row:

```json
{
  "HotelId": 103,
  "TrxDate": "2026-10-08T00:00:00",
  "DayName": "Thursday",
  "Complimentary": 0,
  "HouseUse": 1,
  "RoomUsed": 395,
  "RoomUsed2": 443,
  "RoomCount": 493,
  "RoomRevenue": 625921809.4959,
  "AverageRoomRate": 1588634.0,
  "Occupancy": 80.12,
  "LastYearTransient": 446
}
```

`RoomUsed` vs `RoomUsed2` differ (395 vs 443) - not confirmed which is
"rooms sold" vs "rooms occupied incl. complimentary/house-use/day-use" etc;
didn't dig further.

## `POST api/ReportForecastOccupancyMarketSegment`

**Description:** same daily forecast, broken out by market segment instead
of hotel-wide totals - on-hand reservation count, house-use count,
complimentary count, and revenue, per segment per day.

Body: same shape as above.

**Quirk: `Days` is respected exactly** (unlike every other endpoint on this
page) - `Days: 1` returns exactly 1 day's rows, `Days: 14` returns exactly
14 days, no silent clamping to a 7-day minimum.

Example row:

```json
{
  "HotelId": 103,
  "TrxDate": "2026-10-08T00:00:00",
  "MarketId": 2,
  "MarketDescription": "Corporate",
  "OnhandReservation": 1,
  "OnhandHouseUse": 0,
  "OnhandCompliment": 0,
  "OnhandRevenue": 1942148.7603,
  "DayName": "Thursday"
}
```

## `POST api/ReportForecastOccupancySummary`

**Description:** two-row month-to-date / year-to-date summary (room
revenue, ADR, occupancy %) for the hotel.

Body: same shape, but **`Days` is ignored entirely and `HotelId` is the
only thing besides `TrxDate`'s month/year that matters.**

```json
[
  { "HotelId": 103, "Period": "MonthToDate", "RoomRevenue": 21338323555.5841, "AverageRoomRate": 1627141.0, "Occupancy": 86.07 },
  { "HotelId": 103, "Period": "YearToDate",  "RoomRevenue": 184714801209.5841, "AverageRoomRate": 1636817.0, "Occupancy": 76.13 }
]
```

`TrxDate`'s month/year selects the MTD/YTD window - e.g. `TrxDate:
2026-01-01` makes `MonthToDate` and `YearToDate` identical (January 1 is
both the start of its month and the start of the year).

## `POST api/ReportReservationByMarketSegment`

**Description:** raw reservation-level detail (not aggregated) for every
reservation arriving on `TrxDate` - essentially an arrivals list with full
guest/company/rate/market-segment detail.

Body: same shape, but **`Days` is ignored** - only `TrxDate` matters, and
it's treated as a single **arrival date**, not a range start. A past date
(before the live system's current date) returned 0 rows in testing, so this
looks like an "on the books" report rather than a historical query.

**Contains substantial guest PII** - full name, email address, mobile
phone, national ID number (`IdentityNo`), a guest photo path
(`ImageLocation`), free-text remarks that can contain further personal
details, nationality, and audit fields (who created/updated/verified the
reservation). Redacted/placeholder example below - do **not** commit real
rows from this endpoint to the repo:

```json
{
  "HotelId": 103,
  "ReservationId": 100606,
  "ReservationBy": "Front Desk Staff",
  "ReservationDate": "2026-09-07T00:00:00",
  "ArrivalDate": "2026-10-08T00:00:00",
  "DepartureDate": "2026-10-09T00:00:00",
  "Nights": 1,
  "ReservationStatus": "D",
  "CompanyId": 121751,
  "CompanyName": "Example Company Pte Ltd",
  "TypeId": "DLT",
  "RateType": "BAR",
  "RateId": "BAR2619",
  "Person": 2,
  "Pax": 2,
  "Currency": "IDR",
  "RoomRate": 1251736.0,
  "GuestId": 6968027,
  "GuestName": "<redacted - guest full name>",
  "EmailAddress": "<redacted>",
  "MobilePhone": "<redacted>",
  "IdentityNo": "<redacted>",
  "ImageLocation": "<redacted - path to guest photo>",
  "MarketId": 3,
  "MarketDescription": "FIT",
  "NationalityDescription": "Russia",
  "GuestStatusDescription": "Honeymooner",
  "SourceDescription": "Direct Reservation At Hotel",
  "CreatedBy": "STAFF-NAME",
  "UpdatedBy": "STAFF-NAME",
  "Revenue": 0.0
}
```

Given the PII density, this endpoint should be treated like the production
guest database it effectively is - no caching/logging of raw responses to
disk or git, and any future app feature built on it should pull fields
on-demand rather than persisting guest contact/identity data.

## `POST api/ManagerReport`

**Description:** the daily night-audit "flash" report - the actuals
counterpart to the forecast endpoints above. Single day, hotel-wide:
occupancy/room counts (`OccupiedRoom`, `VaccantRoom`, `OORoom`), arrivals/
departures/cancellations/no-shows, group arrivals, guest counts, and a full
revenue breakdown (`RoomRevenue`, `FBRevenue`, service/tax amounts, package
revenue split by food/beverage/laundry/other).

Body: `{ "TrxDate": "2026-10-07", "HotelId": 103, "UserId": "KRISNATHA" }`

**Quirk: `Days` is accepted but ignored** - always returns a single object
(not a list) for exactly `TrxDate`, identical whether `Days` is omitted, 1,
or 7.

```json
{
  "HotelId": 103,
  "TrxDate": "2026-10-07T00:00:00",
  "TotalRoom": 493,
  "RoomAvailable": 492,
  "OccupiedRoom": 379,
  "VaccantRoom": 114,
  "Arrival": 98,
  "Departure": 203,
  "NoShowReservation": 0,
  "CancelledReservation": 14,
  "RoomRevenue": 586098008.0,
  "FBRevenue": 120209153.0,
  "AverageRoomRate": 0.0,
  "ServiceAmount": 70630727.0,
  "TaxAmount": 77693904.0
}
```

This is the single most important endpoint found so far for a revenue-
actuals feed: everything else on this page is forward-looking forecast or
point-in-time snapshot; this is the only one giving a closed day's true
numbers. Note `AverageRoomRate` was `0.0` in this sample despite non-zero
`RoomRevenue`/`OccupiedRoom` - looked like a data quirk for this
particular date rather than a param issue (worth sanity-checking ADR here
against `RoomRevenue / OccupiedRoom` before trusting the field itself).

## `POST api/RevenueMarketSegmentList`

Tried `{TrxDate, Days, HotelId, UserId}` (several `Days`/date combinations)
and a `{StartDate, EndDate, HotelId, UserId}` variant - every attempt
returned `[]`. Didn't find the right parameter shape. This would be the
natural "revenue actuals by market segment over time" complement to
`ManagerReport` (hotel-wide) and `ReportForecastOccupancyMarketSegment`
(segment-level but forecast, not actuals) - worth revisiting if a real need
for segment-level revenue trend comes up, but not pursued further here.

## `POST api/ReportReservationStatus` - **the real pace/pickup source**

**Resolved on a second pass** (found by watching the network tab behind the
PMS UI's own "Reservation" report, not by guessing params): the standard
`{TrxDate, Days, HotelId, UserId}` body always returned `[]` because this
endpoint needs a completely different shape - date range instead of `Days`,
slash-separated dates, and two fields neither of the other endpoints use:

```json
{
  "HotelId": "103",
  "UserId": "KRISNATHA",
  "TrxDate": "2026/09/12",
  "TrxDate2": "2026/10/11",
  "ReservationStatus": "D,T,Q,I,O",
  "ReservationSource": "",
  "Mode": "RESERVATION_DATE"
}
```

- `TrxDate`/`TrxDate2` are a real **date range** (`YYYY/MM/DD`, slashes not
  dashes) - confirmed a 30-day range returns reservation-level rows spanning
  all 30 days, not clamped to one day or one week like most of this file.
- `ReservationStatus` is a comma-joined list of status codes (`D` Definite,
  `T` Tentative, `Q` Waiting list/Queue, `I` In House, `O` presumably
  Checked Out) - the UI's own default, used as-is. **Cancelled is `L`, not
  the `C` originally guessed** - confirmed via the UI's separate
  "Cancelled Reservation" report (`/listreport/index` → Reservation Report
  → Cancelled Reservation), see the dedicated cancellation mode below.
  `N` (no-show) still unconfirmed.
- **`Mode` is the important part - it changes what the date range filters
  on, not just the output shape:**
  - `"ARRIVAL_DATE"` - matches the already-documented single-arrival-date
    behavior of `ReportReservationByMarketSegment`: rows are reservations
    *arriving* in the range, each carrying its own (often much earlier)
    `ReservationDate`. This is a forward/current view - "who's arriving."
  - `"RESERVATION_DATE"` - **the one that matters for pace.** Rows are
    reservations *created* in the range, each carrying its own `ArrivalDate`
    (observed spanning from the creation date out to over a year in the
    future). This is a booking **transaction log**, not a snapshot - it
    answers "what bookings came in on day X, and for which future dates,"
    which is exactly the pickup signal nothing else in this file provides.

Confirmed with a 30-day `RESERVATION_DATE` range (`2026-09-12` to
`2026-10-11`): 4,454 rows, 30 distinct `ReservationDate` values (one per
day in the range, as expected), 322 distinct `ArrivalDate` values spanning
out to 2028. A single day in that mode (`2026-09-15`) returned 110 rows -
all bookings made that one day, landing on 43 different future arrival
dates.

**Why this changes the pace conclusion in [rms-plan.md](rms-plan.md):**
previously the plan was "snapshot a forecast endpoint going forward and
diff our own history later." This endpoint's `RESERVATION_DATE` mode is a
transaction log that already exists for the **past** - a single wide-range
call can backfill "how many room-nights for arrival date X existed as of
each day it was booked," reconstructing pace retroactively, without having
been snapshotting anything in advance.

### Cancellations - `Mode: "CancelDate"`

Found the same way (watching the UI's "Cancelled Reservation" report,
which has a "Search By: Arrival Date / Cancelled Date" toggle - setting it
to "Cancelled Date" sends a third `Mode` value). Body:

```json
{ "HotelId": "103", "UserId": "KRISNATHA", "TrxDate": "2026/10/11", "TrxDate2": "2026/10/11", "ReservationStatus": "L", "Mode": "CancelDate" }
```

No `ReservationSource` field needed here (unlike the two modes above).
Every row returned has its `UpdatedDate` falling inside the queried
`TrxDate`/`TrxDate2` range - **confirms `UpdatedDate` is the right
cancel-date proxy**, and this mode filters on it directly server-side
rather than us having to infer it client-side. Response also carries
`CancelReason` and `Remark2` populated (both are always empty in every
other endpoint that surfaces them, e.g. `ReportGroupInformation`) -
e.g. `"Guest Change Plan"`, `"Cancel as per update RL"`.

This closes the one open gap from the original pace write-up: pull
`ReservationStatus: "L"`, `Mode: "CancelDate"` over the same rolling
windows as the `RESERVATION_DATE` pulls, and mark any `ReservationId`
that shows up there as dropped-off-the-books as of its `UpdatedDate`.

**Contains full guest PII** - same fields as `ReportReservationByMarketSegment`
(`GuestName`, `EmailAddress`, `MobilePhone`, `IdentityNo`, `ImageLocation`),
plus free-text `Note`/`Remark` fields that can carry further personal/
payment detail (e.g. partial card numbers typed into notes by staff). Redact
per the usual policy - this is the richest and highest-row-count PII surface
found in this file, precisely because it's a transaction log rather than a
point-in-time report.

```json
{
  "HotelId": 103,
  "ReservationId": 106023,
  "ReservationBy": "<redacted>",
  "ReservationDate": "2026-10-11T00:00:00",
  "ArrivalDate": "2026-10-12T00:00:00",
  "DepartureDate": "2026-10-13T00:00:00",
  "ReservationStatus": "D",
  "TypeId": "PSU",
  "RateType": "BAR",
  "RateId": "BAR2607",
  "RoomRate": 5916750.0,
  "CompanyName": "Personal Account",
  "MarketDescription": "FIT",
  "GuestName": "<redacted>",
  "EmailAddress": "<redacted>",
  "IdentityNo": "<redacted>",
  "CreatedBy": "AYU-YULI",
  "CreatedDate": "2026-10-11T05:13:24.329Z"
}
```

## The `api/Reservation` family - **read-only ones only, by design**

`DELETE api/Reservation`, `POST api/Reservation`, `PUT api/Reservation`,
`POST api/Reservation/CheckIn`, and `POST api/Reservation/CheckOut` were
**deliberately not called**. This is a live production PMS for an
operating hotel with real guests currently in-house - creating, editing,
deleting a reservation, or checking a real guest in/out are exactly the
kind of destructive, hard-to-reverse actions that must not be fired just to
see what the response shape looks like. If/when there's a real need to
exercise these (e.g. against a disposable test reservation created and
torn down in a controlled way, with the property's sign-off), that's a
separate, explicitly-scoped task - not something to probe opportunistically.

Only the GET (read) endpoints in this family were tested:

**Auth quirk, different from the report endpoints above:** these need
`HotelId`/`UserId` as **query-string params**, not JSON body fields.
Without them: `GET api/Reservation` and `GET api/Reservation/Inhouse` both
403 with `"You do not have access to this hotel '0'"`; `GET
api/Reservation/{id}` without them 428s with a raw `"Object reference not
set to an instance of an object"` (an unhandled null-ref leaking through as
an HTTP error - a backend bug, not something query-param tuning fixes
cleanly, just noting it happens).

### `GET api/Reservation?HotelId={id}&UserId={user}`

Returns a flat list of reservations - **2000 rows observed, no date-range
query param found that narrows it**, so this reads like "all reservations"
(or a backend-side cap at 2000) rather than anything scoped to `TrxDate`.
Field set is reservation-summary-level (no guest contact PII like email/
phone/ID number - just `GuestName`, `CompanyName`, room/rate/date fields,
status flags). Didn't find a way to paginate or filter by date; left as-is
rather than guessing at undocumented query params.

### `GET api/Reservation/Inhouse?HotelId={id}&UserId={user}`

Returns every currently in-house guest/room (606 rows at test time) -
adds room-assignment and billing-folio fields on top of the `Reservation`
list shape (`FolioToCharge`, `IsCheckIn`, `BackColor`/`ForeColor` for the
PMS's room-rack UI, `ReligionId`/`ReligionDescription`, group/booking
fields). Same PII level as the plain list (`GuestName` but no email/phone/
ID number).

### `GET api/Reservation/{reservationId}?hotelId={id}&userId={user}`

Single full reservation record - this is the richest shape seen on this
host: everything from the list endpoints plus full guest PII
(`EmailAddress`, `PhoneNo`, `IdentityNo`), billing/payment fields
(`PaymentType`, `CreditLimit`, `CardNumber`, `CardName`), and operational
detail (`WakeUpCall`/`WakeUpCallTime`, `SpecialRequest`, `Message1`/`Message2`
guest-facing messages, `VerifiedBy`, `CheckInBy`). Same PII-handling caution
as `ReportReservationByMarketSegment` above applies here, more so - this
includes payment card fields (`CardNumber`, `CardName`, `CardId`) which,
depending on what's actually stored there (full PAN vs. masked/tokenized),
could be a PCI-relevant exposure. Not confirmed either way from the field
name alone - worth checking with whoever owns PMS vendor compliance before
this endpoint is used for anything beyond ad-hoc lookups.

---

# Everything below: pulled from the gateway's "APIs" catalog page

The gateway (`api.hospitality.mykg.id`, see
[pms-api-gateway.md](pms-api-gateway.md)) has a full controller/route
catalog listing 700+ `api/{Controller}` endpoints. The sections below were
selected from that catalog as relevant to a revenue/forecast/pace RMS and
tested against the live data host - everything else in the catalog
(guest-profile CRUD, device integration, PABX, POS, banquet, accounting
sync, etc.) was left untouched as out of scope. Endpoints that look like
write/mutating actions by name (`CheckIn`, `CheckOut`, `Cancel*`,
`NoShowReservation`, `Change*`, `Create*`, bare `Allotment`/`RoomRate`/
`RateStrategy`/`RatePromotion`, etc.) were deliberately never called.

## Revenue & statistics actuals

`ManagerReport` above gives hotel-wide daily actuals. These endpoints
answer whether that breaks down further by segment/company/room type.

### `POST api/StatisticMarketSegmentWithBudget`

**Description:** despite the name, this returns **actuals**, not budget -
a single day's room-nights/revenue by market segment, plus running
month-to-date and year-to-date totals. No budget figures are actually
present in the response. **This is the best find in this section** - it
fills the "actuals broken down by segment" gap next to `ManagerReport`'s
hotel-wide-only totals.

Body: `{ "TrxDate": "2026-10-07", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA" }`

`RoomNightsMtd`/`RoomRevenueMtd` are a true running total as of `TrxDate`
within its month (confirmed: `TrxDate: 2026-10-01` gave `RoomNightsMtd:
6.0`, `TrxDate: 2026-10-06` gave `36.0`). Returns all 10 market segments
every time.

```json
{
  "HotelId": 103,
  "MarketId": 2,
  "MarketDescription": "Corporate",
  "RoomNights": 6.0,
  "RoomRevenue": 8474993.0,
  "RoomNightsMtd": 36.0,
  "RoomRevenueMtd": 50849953.0,
  "RoomNightsYtd": 1580.0,
  "RoomRevenueYtd": 2915440311.0
}
```

### `POST api/StatisticRSRBaseOnRoomType`

**Description:** the room-type-level companion to the above - actual daily
revenue and room-status counts (`RoomTransient`, `RoomHouseUse`,
`RoomCompliment`, `OutOfOrder`, etc.) per room type (19 rows, same codes
as `AvailableRoomInventoryType`). **The only endpoint found giving actual
daily revenue broken down by room type** - `ManagerReport` and
`StatisticRoomSalesRecapitulation` are both hotel-wide only.

Body: same shape. **`Days` ignored entirely** - always exactly one day
(`TrxDate`).

```json
{
  "HotelId": 103,
  "TrxDate": "2026-10-07T00:00:00",
  "TypeId": "ASW",
  "RoomRevenue": 4903581.0,
  "TotalRoom": 4,
  "RoomTransient": 2,
  "PaxTransient": 4,
  "RoomHouseUse": 0,
  "RoomCompliment": 0,
  "RoomDayUse": 0,
  "OutOfOrder": 0,
  "OutOfService": 0
}
```

### `POST api/StatisticRoomSalesRecapitulation`

**Description:** the hotel's "flash report" - 22 rows, one per metric
(`Id`/`Description`: room counts, guest movement, revenue), each with
`Today`/`MonthToDate`/`YearToDate` columns. Overlaps heavily with
`ManagerReport` (same facts, different shape) but has MTD/YTD built in
without a second call.

Body: same shape. **`Days` ignored.**

```json
{ "TrxDate": "2026-10-07T00:00:00", "Id": 10, "Description": "Total Room", "Today": 493.0, "MonthToDate": 3451.0, "YearToDate": 138040.0, "Flag": 0 }
```

### `POST api/StatisticCompanyByMonth` / `POST api/StatisticCompanyProduction`

**Description:** company-level analogue of the market-segment-by-month
endpoints below - 12-month `{Mon}Revenue`/`{Mon}RoomNights` columns, one
row per company. `StatisticCompanyByMonth` returns **890 rows** (every
company with any history) in one call, no filter needed.
`StatisticCompanyProduction` is the same data pivoted to row-per-metric
for **one** company, but **requires an explicit `CompanyId` in the body**
- without it, returns `[]`.

Body (`StatisticCompanyProduction`): `{ "TrxDate": "2026-10-07", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA", "CompanyId": 206214 }`

Company names are business/travel-trade entities, not guest PII - safe
verbatim.

```json
{ "CompanyId": 206214, "CompanyName": "Travelbliss Bali Dmc", "JanRevenue": 0.0, "JunRevenue": 3595041.0, "OctRevenue": 8925620.0, "JanRoomNights": 0, "JunRoomNights": 3, "OctRoomNights": 4 }
```

Useful for company drill-down; `StatisticMarketSegmentWithBudget` above is
the better fit for a top-level segment view given the row count here.

### `POST api/StatisticMarketSegmentByMonth` - pace, not actuals

Same 12-month-by-segment shape as above, but **the current month is a
live on-the-books figure, not a closed actual** - confirmed: querying
October with `TrxDate: 2026-10-01` gave `OctRevenue: 50,743,803`; the same
October queried with `TrxDate: 2026-10-07` gave `OctRevenue: 196,074,387`.
Only 5 of 10 market segments ever appear in this endpoint's output
(`Corporate`, `FIT`, `Travel Agent`, `Government`, `Online`) - don't use
this for "final" monthly numbers; use `StatisticMarketSegmentWithBudget`
for actuals instead.

### `POST api/StatisticMarketSegmentBudgetByMonth` - budget, not actuals

Same shape again, but these are **budget/target** figures - Oct/Nov/Dec
revenue and room-nights are implausibly large for a 493-room hotel (e.g.
`OctRoomNights: 150,696` for one segment - impossible as an actual in a
31-day month). Returns all 10 segments. Useful only as an actual-vs-budget
comparison baseline, not an actuals source itself.

### Unresolved in this section

- `StatisticMarketSegmentReservation` - consistent `428` error
  (`"The input string '' was not in a correct format."`) across every
  variant tried; some other required field wasn't guessed.
- `RevenueCompanyList`, `NightAuditSummary`, `NightAuditSummaryReport`,
  `NightAuditSummaryRevenue`, `OutletRevenueList`, `FoodBeverageRevenueList`
  - all consistently return `[]` with no error, across several
  date/range/`CompanyId` variations (including dates with confirmed
  non-zero F&B revenue via `ManagerReport`). `OutletRevenueList`/
  `FoodBeverageRevenueList` are the most disappointing misses - outlet/F&B
  actuals would nicely complement `ManagerReport`'s single `FBRevenue`
  total, but no working param shape was found (likely needs an `OutletId`
  or similar, symmetric with `StatisticCompanyProduction` needing
  `CompanyId`).

## Channel mix & demand quality

General pattern across almost this entire section: **`Days` is silently
ignored** - results are anchored purely to `TrxDate` (Today/MTD/YTD, or a
single arrival date for the group endpoints), confirmed via explicit
`Days=1` vs `Days=7`/`14` A/B tests, not just inferred from other
endpoints' behavior.

### `POST api/StatisticOnlineTravelAgentDistribution`

**Description:** per-OTA/online-channel company breakdown - room nights,
revenue, and ADR, split MTD/YTD plus MTD-last-year/YTD-last-year for
built-in year-over-year comparison. **The best channel-mix endpoint
found** - exactly "where is online demand coming from," with `CompanyName`
already resolved (e.g. "Booking.com", "Santika Online Reservation").

Body: `{ "TrxDate": "2026-10-07", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA" }`

21 rows returned.

```json
{
  "HotelId": 103,
  "CompanyId": 11647,
  "CompanyName": "Booking.com",
  "RoomNightsMtd": 334,
  "RevenueMtd": 775063435.0,
  "AverageRoomRateMtd": 2320549.2065,
  "RoomNightsYtd": 11735,
  "RevenueYtd": 25330524935.0,
  "AverageRoomRateYtd": 2158544.9454,
  "RoomNightsMtdLy": 282,
  "RevenueMtdLy": 577653915.0,
  "RoomNightsYtdLy": 5054,
  "RevenueYtdLy": 11989460592.0
}
```

### `POST api/StatisticSourceOfReservation`

**Description:** coarser channel split than the above - reservation
source (Email, Phone, Walk-in, etc.) with Today/MTD/YTD room-nights,
person count, revenue. 11 source rows observed. OTA volume is presumably
folded into whichever source bucket the PMS assigns it to - not
independently confirmed which.

```json
{ "HotelId": 103, "TrxDate": "2026-10-07T00:00:00", "Id": 3, "Description": "Email", "RoomNights": 168, "RoomRevenue": 220075330.0, "RoomNightsMtd": 1305, "RoomRevenueMtd": 1786449789.0, "RoomNightsYtd": 34468, "RoomRevenueYtd": 49958625413.0 }
```

### `POST api/StatisticNationality` / `StatisticRegion` / `StatisticCity` / `StatisticGeographicalOrigin`

**Description:** a nested geography hierarchy - country → province/region
→ city - each with Today/MTD/YTD room-nights/person/revenue.
`StatisticGeographicalOrigin` additionally bundles MTD/YTD-last-year
columns (like the OTA endpoint above). All are dense lookup-table style
(every country/region/city returned, zero-filled if inactive - 140/158/
575/427 rows respectively). No guest PII - aggregate counts only.

```json
{ "HotelId": 103, "TrxDate": "2026-10-07T00:00:00", "Id": 1, "Description": "Afghanistan", "RoomNights": 1, "RoomRevenue": 1442149.0, "RoomNightsMtd": 1, "RoomRevenueMtd": 1442149.0, "RoomNightsYtd": 12, "RoomRevenueYtd": 30917568.0 }
```

`StatisticRegion`'s added value over `StatisticNationality` is the
sub-national province breakdown for domestic Indonesian demand.
`StatisticCity`'s row order was observed to be unstable between identical
calls (same 575 rows, different order) - sort client-side if consumed.
Note the vendor's own field typos on `StatisticGeographicalOrigin`:
`CityDesciption`/`CountryDesciption` (missing the "r").

### `POST api/StatisticPromotion`

**Description:** an **annual** (not date-range) promo-performance report -
one row per `(PromoId, RateType, RowDescription)`, with `January`..
`December` monthly revenue/room-night columns (`RowDescription` alternates
`"Room Revenue"`/`"Room Night"` per promo). 1044 rows. Some promo
descriptions map directly to an OTA (e.g. `"Fenced MOD Expedia"`), making
this channel-mix-adjacent.

```json
{ "HotelId": 103, "PromoId": 5021, "RateType": "BAR", "January": 55922530.0, "October": 0.0, "RowDescription": "Room Revenue", "Description": "Fenced MOD Expedia" }
```

### `POST api/StatisticMethodOfCheckIn` / `POST api/StatisticVoucherPayment`

Minor finds: `StatisticMethodOfCheckIn` gives a 2-row Reservation-vs-
Walk-In split with Today/MTD/YTD (walk-ins are a tiny fraction at this
property); `StatisticVoucherPayment` is a voucher-redemption ledger
(3 rows), only tangentially related to channel/demand quality.

### `POST api/ReportGroupProduction` / `POST api/ReportGroupInformation`

**Description:** group-arrivals reporting for a single `TrxDate` (treated
as one arrival date, not a range, despite accepting `Days`).
`ReportGroupProduction` is aggregated (one row per group: room count,
room-nights, market segment, company); `ReportGroupInformation` is the
per-room/reservation detail behind it (one row per room in the group).

```json
{ "HotelId": 103, "GroupPairId": 1219, "ArrivalDate": "2026-10-07T00:00:00", "GroupDescription": "OJK DIMB (06 - 09 Oct 2026)", "MarketDescription": "Government", "CompanyName": "Otoritas Jasa Keuangan (OJK)", "Rooms": 7, "RoomNights": 14 }
```

**`ReportGroupInformation` contains guest PII** (name, email, phone,
national ID, photo path) - same handling caution as
`ReportReservationByMarketSegment`. It also carries a `CancelReason`
field (empty in every sampled row) that may be the closest accessible
cancellation-reason signal given the permission gaps below.

### Unresolved in this section - 403 permission, not a shape issue

`StatisticCancelReservationMarketSegment`, `StatisticCancelReservationNationality`,
`StatisticExtraBed` - all three return the identical `"You don't have
access to this report."` across every body variation tried (standard,
`Days=1`, `StartDate`/`EndDate`). This is a real gap for "cancellations by
segment/nationality" - the logged-in API user's role isn't entitled to
these specific reports; no request-shape change will fix it.

## Rate & yield pricing

### `POST api/RatePromotionList`

**Description:** master list of promotion *rules* (not tied to a date) -
discount type/amount, day-of-week applicability bitmask, validity window
- per `RateType`. **Requires `RateType` (`BAR`/`TRA`/`COR`) in the body** -
without it, returns a single placeholder row. `TrxDate`/`Days` are
ignored once `RateType` is set.

Body: `{ "TrxDate": "2026-10-08", "Days": 7, "HotelId": 103, "UserId": "KRISNATHA", "RateType": "BAR" }`

Row counts: `BAR` → 75, `TRA` → 112, `COR` → 9.

```json
{
  "HotelId": 103,
  "TrxId": 6940,
  "RateType": "BAR",
  "StartDate": "2025-12-06T00:00:00",
  "EndDate": "2026-12-31T00:00:00",
  "DiscountType": 0,
  "DiscountRate": 19.0,
  "Days": "1111111",
  "Description": "PROMO Fenced MOD ( 19% )"
}
```

Note: the response's `Days` field is a 7-char day-of-week bitmask, unrelated
to the request's date-range `Days` param - same name, different meaning on
each side of the request/response.

### `POST api/RatePromotionTimeLine`

**Description:** the richest pricing-history endpoint found - the full
promotion-to-rate-code mapping over time, one row per specific `RateId`
(e.g. `BAR2099`) the promotion was attached to, with start/end validity on
that code. **`TrxDate`/`Days` ignored entirely** - always the full
historical set: **63,696 rows**, no server-side date filtering (filter
client-side, e.g. `StartDate <= today <= EndDate`). Worth caching rather
than re-fetching live.

```json
{ "HotelId": 103, "RateType": "BAR", "RateId": "BAR2099", "StartDate": "2025-01-20T00:00:00", "EndDate": "2026-03-31T00:00:00", "DiscountRate": 10.0, "Description": "PROMO Fenced MOD Expedia ( 10% )" }
```

`RatePromotionByType` (700 rows) is a lighter, less detailed rollup of the
same underlying data - redundant given `RatePromotionTimeLine` is
strictly richer, unless the 63.7k row size becomes a performance problem.

### `POST api/ReportRateStrategy`

**Description:** per-reservation rate detail for a single day - original
vs. actually-charged rate, promo/discount applied, override/upgrade flags.
Queryable for any day, past or future (row count varies a lot: 25 rows for
today, 247 for a past date). **Contains guest PII** (`GuestName`,
`RoomNo`) - redact per the usual policy.

```json
{
  "HotelId": 103,
  "ReservationId": 81062,
  "EffectiveDate": "2026-10-08T00:00:00",
  "TypeId": "PRKP",
  "RateType": "PAC",
  "RateId": "PAC2608",
  "OriginalRate": 1930000.0,
  "RoomRate": 1930000.0,
  "IsUpgrade": true,
  "GuestName": "<redacted - guest full name>"
}
```

### `POST api/StatisticRoomRate` / `StatisticRoomRateTypeId` / `StatisticRoomTypeId`

**Description:** MTD/YTD production pace, respectively by rate code
(1,209 rows), rate code × room type (2,359 rows), and room type alone (17
rows - one per type). `Days` ignored everywhere; windows derive from
`TrxDate`'s month/year. `StatisticRoomTypeId` is the cleanest top-level
"pace by room type" view; the other two let you drill into which rate
codes/promos are driving it.

```json
{ "HotelId": 103, "TrxDate": "2026-10-08T00:00:00", "TypeId": "PRKG", "Description": "Premiere King Garden", "RoomNightsMtd": 944, "RoomRevenueMtd": 1632365897.0, "RoomNightsYtd": 28214, "RoomRevenueYtd": 47185757038.0 }
```

### `POST api/RoomAvailMonth` / `POST api/RoomAvailableList`

Lightweight hotel-wide pace summaries: `RoomAvailMonth` is a 2-row "this
month/next month" room-nights-available headline;
`RoomAvailableList` is a fixed 32-day daily grid (total/used/tentative/
definite/waiting-list/allotment rooms, hotel-wide). Both ignore `Days`.
Minor value given the existing per-room-type inventory endpoints, but
cheap single calls if only a headline number or a quick 32-day pace line
is needed.

### Unresolved in this section

- `AvailableRoomRate`, `AvailableRoomRateByDay` - always `[]`, no working
  param shape found (tried `+TypeId`, `+RoomTypeId`, `ArrivalDate`/
  `DepartureDate` variants).
- `AvailableRoomType` - not empty, but shape looks like a single-room-type
  booking-engine availability check (no price field at all), not a rate
  report - none of the tried params were reflected in the output.
- `ReportRoomRateDistribution`, `ReportRoomRatePromotion`,
  `ReportRoomRateRoom` - all three **403 "You don't have access to this
  report"** - permission-gated for this user's role, not a param issue.

## Competitor benchmarking & forward capacity/allotment

### `POST api/GetHotelCompetitor` / `POST api/GetHotelCompetitorMaster` / `POST api/StatisticHotelCompetitor`

**Description:** this PMS genuinely stores daily rate-shopping data,
staff-entered, for a tracked competitive set. `GetHotelCompetitorMaster`
is the 14-competitor lookup list (name + short code). `GetHotelCompetitor`
is the daily actuals (available/occupied rooms, occupancy %, average
rate) - only **5 of the 14** competitors actually get daily entries (Arya
Duta, Discovery Kartika Plaza, Bali Dynasty, Hard Rock, The Stones).
`StatisticHotelCompetitor` is the **most useful of the three** - an
MTD/YTD rollup per competitor in one call, no manual aggregation needed.

**Quirk shared by all three:** `Days` ignored; data lags by about a day
(querying today returns `[]`/zeroes for today specifically - same
"staff-entered actuals are T-1" pattern as `ManagerReport`). A fully-
elapsed month returns the complete month; a future month returns `[]`.

```json
{
  "CompetitorId": 1301,
  "CompetitorName": "Arya Duta",
  "MtdAvailableRoom": 1246,
  "MtdOccupiedRoom": 1230,
  "MtdOccupiedPercentage": 98.71714237758091,
  "MtdRoomRevenue": 971950645.0,
  "MtdAverageRate": 790624.1428,
  "YtdOccupiedPercentage": 72.53414255278452,
  "YtdRoomRevenue": 30145874582.0
}
```

`RevenueHotelCompetitorList` was tried as the natural "competitor revenue"
complement but stayed `[]` across every variation (standard body,
`{HotelId, UserId}`-only, wider `Days`) - unresolved, possibly needs a
`CompetitorId`.

### `POST api/ReportExpectedRoomOccupied` / `POST api/ReportExpectedAllotmentRoomOccupied`

**Description:** the genuine forward pace signals in this bucket.
`ReportExpectedRoomOccupied` is a forward occupancy forecast pivoted by
room type (19 rows, `MM-DD` date columns, like `AvailableRoomInventory`'s
shape) - "how full will each room type be over the coming weeks."
`ReportExpectedAllotmentRoomOccupied` is the same pivot but by
allotment-holding company (13-27 rows depending on window) - "how much
allotment is each channel/agent using, day by day."

**Correction from the first pass:** this isn't a fixed 7-day window -
`Days` is ignored, but there's a separate **`Mode` parameter (a string
day-count, not the boolean/enum it looks like) that controls the window
size**, found by watching the PMS UI's "Allotment - Forecast" report
(`/listreport/index` → Allotment Report → Allotment - Forecast) call this
exact endpoint with `"Mode": "30"`. Confirmed for both endpoints:
`Mode: "7"` → 7-day window, `"14"` → 14 days, `"30"` → 30 days, `"60"`/`"90"`
→ **clamped to 30 days**, the real max. Body:

```json
{ "HotelId": "103", "UserId": "KRISNATHA", "TrxDate": "2026/10/11", "Mode": "30" }
```

```json
{ "HotelId": 103, "TypeId": "DLT", "10-08": 119.0, "10-09": 138.0, "10-10": 140.0, "NoOfRooms": 138, "StartDate": "2026-10-08T00:00:00", "EndDate": "2026-10-14T00:00:00" }
```

### `POST api/ReportAllotmentList` / `POST api/ReportAllotmentSummary` / `POST api/ReportAllotmentTransaction`

**Description:** allotment utilization reporting. `ReportAllotmentList`
is per-company totals for one day (9 companies: Channel Manager + 8
agencies). `ReportAllotmentSummary` is the per-room-type drill-down of one
company - **requires `CompanyId` in the body** (standard body alone
returns `[]`; e.g. `CompanyId: 1001` for Channel Manager).
`ReportAllotmentTransaction` is an **audit log of every allotment change
made on a given day** - and it literally shows our own pipeline's writes
(`CreatedBy: "KRISNATHA"`, `Remark: "Updated from yield matrix - ..."`),
useful as a built-in change-audit feed. All three ignore `Days`.

```json
{ "AllotmentId": 1817447, "HotelId": 103, "AllotmentDate": "2026-10-08T00:00:00", "CompanyId": 1001, "StartDate": "2026-10-09T00:00:00", "TypeId": "ASP", "NoOfRoom": 1, "Remark": "Updated from yield matrix - The Anvaya Suite With Pool Online Inventory 1", "CreatedBy": "KRISNATHA" }
```

### `POST api/ProjectedRoomOccupied` / `POST api/ReportProjectedRoomOccupied`

Single-day whole-hotel capacity snapshot (available/occupied rooms,
expected arrivals/departures, expected revenue, allotment total).
`ProjectedRoomOccupied` is a flat object (nicer to consume
programmatically); `ReportProjectedRoomOccupied` is the same data exploded
to a 20-row "flash sheet" shape with display metadata (`RowId`, `Flag`).
Both ignore `Days`.

```json
{ "HotelId": 103, "TrxDate": "2026-10-08T00:00:00", "RoomAvailable": 493, "OccupiedRoom": 380, "ExpectedArrival": 16, "ExpectedRoomRevenue": 899084287.95, "Alloment": 48 }
```

(Vendor's own typo: `Alloment` for `Allotment`.)

### `POST api/ReportExpectedArrival` / `POST api/RoomCountSheet`

Both carry guest PII. `ReportExpectedArrival` is a single-day arrivals
list, overlapping with the already-documented
`ReportReservationByMarketSegment` but with a different field set
(`ArrivalTime`, `SpecialRequestDescription`, `VisitId`). `RoomCountSheet`
is the in-house folio/room-charge ledger for a day - granular
revenue-recognition detail per currently-occupied room (380 rows, matching
the hotel's exact in-house count). Both ignore `Days`; redact guest name/
contact fields as with the other reservation-touching endpoints.

### `POST api/RoomSummary` / `POST api/DashboardRoomAvailability` / `POST api/DashboardHotelStatus`

Simple dashboard-tile endpoints, all ignoring `Days`:
`RoomSummary` is a 3-row room-status tally (`OD`/`OS`/`VD` counts).
`DashboardRoomAvailability` is a room-type availability tile set - **the
only endpoint across both probing sessions that resolves room-type codes
to full human-readable names** (e.g. `DLT` → "Deluxe Twin"), useful as a
lookup table. `DashboardHotelStatus` is a single-row "hotel at a glance"
header: booked/blocked/vacant counts, two occupancy % figures, current BAR
rate, and forecast room revenue, all in one call.

```json
{ "SystemDate": "2026-10-08T00:00:00", "RoomAvailable": 49, "RoomBooked": 16, "Allotment": 48, "TotalInHouse": 380, "OccupancyPct": 90.06, "RateId": "BAR2601", "RoomRate": 5850000.0, "ForecastRoomRevenue": 627863958.2562 }
```

## Second pass: the rest of the gateway's `Report*` controller list

The gateway catalog's "APIs" page groups a `Report` controller family separately
from the `Statistic*`/`Dashboard*` ones above. Cross-checked that full list
against what's already documented here and tested the remainder that look
room-revenue-relevant. Skipped as out of scope for this RMS pass (not
revenue-bearing, or guest-admin/PII-only with no revenue angle):
`ReportBillGuestName`, `ReportCheckInGuestList`, `ReportCheckOutGuestList`,
`ReportDepositMutation(Detail)`, `ReportDepositStatus`,
`ReportDiscrepancy*`, `ReportEarly*`, `ReportExtendRoomList`,
`ReportExtrabedHistories`, `ReportGuestBirthday`, `ReportGuestBlackList`,
`ReportGuestPurposeVisit`, `ReportGuestVerified`, `ReportInhouse*`,
`ReportKeyCardInventory`, `ReportLongStayingGuestList`,
`ReportMeetingRoomGenerated`, `ReportOverCreditLimit`, `ReportPayment`,
`ReportRegistrationCard`, `ReportRepeaterGuest`, `ReportRepeaterInformation`,
`ReportRoomMaintenanceShedule`, `ReportReservationByMembership`,
`ReportChangeStatus` (ambiguous name, didn't probe - see note below).

### `POST api/ReportForecastOccupancyCompany` / `ReportForecastOccupancyNationality`

**Description:** the same daily forecast as `ReportForecastOccupancyMarketSegment`,
but cut by company (336 rows for a 7-day window) or nationality (220 rows)
instead of market segment. Same field shape (`OnhandReservation`,
`OnhandHouseUse`, `OnhandCompliment`, `OnhandRevenue`) with `CompanyName` or
`NationalityDescription` added. No guest PII - company/country names only.

```json
{ "TrxDate": "2026-10-07T00:00:00", "CompanyId": 2, "OnhandReservation": 17.0, "OnhandHouseUse": 0.0, "OnhandCompliment": 0.0, "OnhandRevenue": 25326138.0, "CompanyName": "Hotelbeds - B2B Dynamic", "DayName": "Wednesday" }
```

### `POST api/ReportForecastOccupancyDetail`

**Description:** a richer hotel-wide daily forecast than
`ReportForecastOccupancy` - adds `ComplimentaryRoom`, `HouseUseRoom`,
`OORoom`, `DefiniteFit`, `DefiniteGroup`, `TentativeArrival`, `Adult`,
`Child` counts on top of the room/revenue/ADR/occupancy fields already
in `ReportForecastOccupancy`.

**Quirk: `Days` is ignored entirely, fixed 16-day window** - confirmed
`Days: 1`, `7`, and `14` all returned the identical 16 rows/16 distinct
dates starting at `TrxDate`. Different fixed window than
`ReportForecastOccupancy`'s 7 days.

```json
{ "HotelId": 103, "TrxDate": "2026-10-07T00:00:00", "DayName": "Wednesday", "ComplimentaryRoom": 0, "HouseUseRoom": 1, "RoomUsed": 379, "OORoom": 0, "RoomCount": 492, "RoomRevenue": 586098008.0, "AverageRoomRate": 1546433.0, "Occupancy": 77.03, "RoomTransient": 378, "Departure": 203, "NoOfGuest": 722, "DefiniteFit": 0, "DefiniteGroup": 0, "TentativeArrival": 0, "Adult": 706, "Child": 16 }
```

### `POST api/ReportForecastPromotion`

**Description:** the forward-looking counterpart to `StatisticPromotion` -
same annual `(PromoId, RateType, RowDescription)` shape with
January..December columns, but also carries the promo's own validity
window (`TrxDate1`/`TrxDate2`) and `DiscountRate` inline, so a single row
tells you both "how much forecast revenue is this promo driving this
month" and "is it still active." 345 rows.

```json
{ "HotelId": 103, "PromoId": 5153, "RateType": "TRA", "October": 244250000.0, "November": 946200393.0, "December": 556700000.0, "RowId": 0, "PromotionType": 0, "DiscountRate": 50.0, "TrxDate1": "2025-09-08T00:00:00", "TrxDate2": "2026-12-31T00:00:00", "RowDescription": "Room Revenue", "Description": "Rainbow" }
```

### `POST api/ReportReservationByRateType`

**Description:** reservation-level detail (richer field set than
`ReportReservationByMarketSegment` - adds `ArrivalTime`/`DepartureTime`,
`RoomNo`, `ReservationSource`, `ExtraBedCharge`) filtered to one
`RateType`. **Requires `RateType` (`BAR`/`TRA`/`COR`/etc.) in the body -
without it, returns `[]`** regardless of `Days`. With `RateType: "BAR"`,
returned 65 rows (open + recently-closed reservations, not scoped tightly
to `TrxDate` as a single arrival date - mixed arrival dates observed in
the sample, unlike `ReportReservationByMarketSegment`).

**Contains guest PII** (`GuestName`, plus presumably contact fields in the
full row) - same redaction policy as the other reservation-detail
endpoints.

```json
{ "HotelId": 103, "ReservationId": 60968, "ReservationBy": "<redacted>", "ArrivalDate": "2026-09-24T00:00:00", "DepartureDate": "2026-10-07T00:00:00", "Nights": 13, "ReservationStatus": "O", "TypeId": "DLTP", "RoomNo": "6121", "RateType": "BAR", "ReservationSource": "ONLINE", "RateId": "SPOT-NR", "RoomRate": 1971131.0, "GuestName": "<redacted>" }
```

### `POST api/ReportCommission`

**Description:** per-reservation **net rate after commission** - this is
the revenue-net-of-channel-cost figure the RMS actually needs for true
channel profitability, which nothing else on this page provides directly
(`StatisticOnlineTravelAgentDistribution` gives gross revenue per OTA,
not net). Returns `RoomRate` (gross) alongside `NetRoomRate`, the
`DiscountRate`/`DiscountRateOriginal` applied, and `CompanyName` (the
booking channel). 50 rows for the standard body.

**Contains guest PII** (`GuestName`) - redact per policy. `UpdatedBy` is a
staff username, not PII.

```json
{ "HotelId": 103, "ReservationId": 55075, "RoomNo": "2107", "ArrivalDate": "2026-10-07T00:00:00", "DepartureDate": "2026-10-09T00:00:00", "ReservationStatus": "O", "TrxType": "ROOM_CHARGE", "RateId": "SPOT-NR", "RateType": "BAR", "DiscountRate": 17.76, "RoomRate": 2475899.8054, "NetRoomRate": 2036180.0, "SharedPct": 100.0, "CompanyId": 4400, "CompanyName": "Agoda.com", "UpdatedBy": "WAYAN-ANDI", "GuestName": "<redacted>" }
```

### `POST api/ReportHouseStatus`

**Description:** per-room status snapshot - every room (493 rows), with
`StatusId` (`OD`/`OS`/`VD`/etc. housekeeping codes), room type, current
guest, stay dates, and company/group. This is the granular per-room
version of `RoomSummary`'s 3-row tally - more detail than an RMS needs for
revenue/pace, but confirms `RoomSummary`'s aggregate counts are derived
from exactly this per-room data.

**Contains guest PII** (`GuestName`) - redact per policy.

```json
{ "HotelId": 103, "RoomNo": "1101", "TypeId": "PRKG", "StatusId": "OD", "MaxExtraBed": 2, "MaxPerson": 2, "Pax": 2, "GuestName": "<redacted>", "ArrivalDate": "2026-10-09T00:00:00", "DepartureDate": "2026-10-12T00:00:00", "CompanyName": "Bank Rakyat Indonesia (BRI) Corporate University - Jakarta", "GroupDescription": "BRI Corporate Univ 9 - 12 Oct", "Remark": "NA AUTO CHANGE", "UpdatedBy": "<redacted - staff or system account>" }
```

### Unresolved / out of scope in this second pass

- `GET api/Report/CRM/ReservationStatus` - a different path than the
  already-documented `POST api/ReportReservationStatus`, tried as a
  plausible alternate shape for the same report; also returned `[]`
  (`HotelId`/`UserId` as query params, matching the `Reservation` family's
  GET convention). Same conclusion as the POST version: right endpoint
  name, wrong/unfound param shape, not pursued further.
- `ReportComplimentaryRoom`, `ReportComplimentaryRate`, `ReportDayUse`,
  `ReportOtherCharge`, `ReportAdditionalRoomCharge`,
  `ReportAdditionalRoomCharge2` - all six return the identical 403
  `"You don't have access to this report."` - permission-gated for this
  API user's role, same pattern as the `StatisticCancelReservation*`/
  `ReportRoomRate*` 403s already documented above. Would have been useful
  (comp-room revenue leakage, day-use revenue, ancillary room charges) but
  not accessible with current credentials.
- `ReportChangeStatus` - name is ambiguous between "a report of status
  changes" (read, like `ReportAllotmentTransaction`) and "change the
  status" (a mutation despite the `Report` prefix). Not probed, to stay on
  the safe side of the live-production write boundary - if this is ever
  needed, confirm with the PMS vendor/docs what it does before calling it.
