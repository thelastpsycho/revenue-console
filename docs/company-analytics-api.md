# Company Analytics API (for external consumers)

Reference for a **separate web app** that wants to pull the same data behind
the Revenue Console's Company Analytics page
(`frontend/src/views/RmsCompanyAnalyticsView.vue`, route `/rms/company-analytics`).
That page isn't backed by one endpoint — it's three calls to the existing
read-only `/api/rms/*` API, filtered by `companyIds`. Nothing company-specific
exists server-side; `companyIds` is just one of several filter dimensions
these endpoints already accept (alongside `roomType`, `marketId`,
`nationalityIds`, `channels`, `group`).

All data ultimately comes from `booking_events.db` (an append-only cache of
PMS master folios) and `rms_workspace`-stored settings. See the RMS section
of the root `CLAUDE.md` for the data-quality model (`observed` /
`estimated` / `unavailable`) this API surfaces throughout.

## Before you integrate: two blockers for a truly external app

1. **CORS is locked down.** `backend/app/__init__.py` only allows origins
   `http://localhost:5173`, `http://127.0.0.1:5173`, `http://10.201.59.16:5173`
   (the dev Vite server). A browser-based app on any other origin will have
   its requests blocked by CORS regardless of auth. This only affects
   browser JS — a server-to-server client (another backend, a script) is
   unaffected, since CORS is a browser-enforced policy. If the other app
   needs to call this from its own frontend JS, its origin has to be added
   to that `CORS(...)` origins list first.
2. **Session cookie is `SameSite=Strict`.** Even if CORS allowed the origin,
   a browser won't attach the session cookie on a cross-site request under
   `Strict`. Again, only a problem for browser-to-browser cross-origin
   calls — a server-side client just replays the `Set-Cookie` value itself.

If the "other web app" is itself server-rendered or has its own backend,
have *that* backend call these endpoints server-to-server; don't call them
directly from the other app's frontend JS unless you loosen CORS/SameSite.

## Auth

Every `/api/*` route except `/api/health`, `/api/auth/status`, and
`/api/auth/login` requires an authenticated session
(`backend/app/security.py`). There's no API key / bearer token option today
— it's PIN login → session cookie.

**Login:**

```
POST /api/auth/login
Content-Type: application/json

{ "pin": "<6-digit APP_ACCESS_PIN>" }
```

- `200 { "status": "success", "csrf_token": "<token>" }` + `Set-Cookie: session=...`
- `401 { "status": "error", "message": "Invalid PIN" }`
- `503 { "status": "error", "message": "API authentication is not configured" }` — backend has no `APP_ACCESS_PIN`/`APP_SESSION_SECRET` set.

Persist the `Set-Cookie` (cookie jar / `requests.Session()` / axios with a
cookie jar) and send it on every later request. The session lasts 8 hours
(`PERMANENT_SESSION_LIFETIME`).

`csrf_token` only matters for state-changing calls (`X-CSRF-Token` header on
POST/PUT/PATCH/DELETE). **None of the three endpoints below are
state-changing — no CSRF token needed for this integration.**

Optional: `GET /api/auth/status` (no auth needed) returns
`{ "configured": bool, "dev_mode": bool, "authenticated": bool }` to check
state before logging in.

## 1. `GET /api/rms/room-types`

Lookup/dimension data — call once, cache client-side (it only changes when
new room types, companies, markets, or nationalities appear in the PMS).

**Params:** none.

**Response:**

```json
{
  "status": "success",
  "labels": { "<roomTypeCode>": "<Human Label>", ... },
  "roomTypes": ["DLK", "DLKP", "PRKG", ...],
  "markets": [{ "id": 2, "name": "Corporate" }, ...],
  "channels": [{ "id": "ota", "name": "OTA" }, ...],
  "companies": [{ "id": 206214, "name": "Travelbliss Bali Dmc" }, ...],
  "nationalities": [{ "id": 103, "name": "Indonesia" }, ...]
}
```

- `companies[].id` is what you pass as `companyIds` below.
- `nationalities` excludes `id: 0` (PMS "not specified" sentinel).
- `roomTypes` is the raw set of `type_id` values seen in bookings — not
  necessarily identical to `labels`'s key set (some booking-side variant
  codes get aliased to a representative sellable code elsewhere; this
  endpoint doesn't apply that aliasing).

## 2. `GET /api/rms/pace`

Day-by-day pace/pickup table for a date range, filtered by company (or any
other dimension).

**Params** (all optional unless noted):

| Param | Type | Default | Notes |
|---|---|---|---|
| `start` | `YYYY-MM-DD` | today | |
| `end` | `YYYY-MM-DD` | `start + 29d` | must be `>= start`, range `< 366` days |
| `pickupDays` | int | `7` | silently clamped to `[1, 90]` |
| `asOf` | `YYYY-MM-DD` | today | pins "now" for the pickup comparison |
| `roomType` | string | — | exact match on raw `type_id` |
| `marketId` | int | — | |
| `companyIds` | comma-joined ints, e.g. `206214,11647` | — | |
| `nationalityIds` | comma-joined ints | — | |
| `channels` | comma-joined strings | — | |
| `group` | `fit` \| `group` | — | anything else → 400 |
| `comparison` | `weekday` \| `calendar` \| `custom` | `weekday` | |
| `comparisonStart` | `YYYY-MM-DD` | — | **required** if `comparison=custom` |

**Response:**

```json
{
  "status": "success",
  "rows": [ { "date": "2026-11-06", ... }, ... ],
  "sync": { "lastSuccessfulSync": "...", "stale": false, "bookings": 12345, ... },
  "settings": { "thresholds": {...}, "revenueRules": [...], "budgets": [...], "usdIdrRate": 15500 },
  "notes": { "2026-11-06": { "text": "...", "updatedAt": "..." } },
  "bar": { "byDate": {...}, "updatedAt": "..." }
}
```

Each row in `rows` (one per day in range):

| Field | Type | Meaning |
|---|---|---|
| `date` | string | stay date |
| `lyDate` | string | comparison date, per `comparison` mode |
| `rooms` | number | room-nights on the books |
| `idrRooms` | number | subset of `rooms` with a priced/convertible rate |
| `revenue` | number | gross room revenue, IDR (USD converted at `usdIdrRate`) |
| `netRevenue` | number | `revenue` after breakfast/tax/service per `revenueRules` |
| `budgetRooms`, `budgetRevenue` | number \| null | null if any filter above is active — budget has no such dimension |
| `pickupRooms`, `pickupRevenue`, `pickupNetRevenue` | number \| null | `current - prior`; null if `pickupQuality` is `unavailable` |
| `newRooms`, `cancelledRooms`, `amendedRooms` | number \| null | pickup breakdown; null together with the pickup fields |
| `stlyRooms`, `stlyIdrRooms`, `stlyRevenue`, `stlyNetRevenue` | number \| null | same-time-last-year at equivalent lead time; null if `comparisonQuality` is `unavailable` |
| `lyFinalRooms`, `lyFinalRevenue` | number \| null | how last year's date actually finished; null if that date is in the future or unavailable |
| `currentQuality`, `comparisonQuality`, `pickupQuality` | `"observed"` \| `"estimated"` \| `"unavailable"` | see CLAUDE.md's data-quality model — always check before trusting the paired numbers |

**Errors:** all `400 { "status": "error", "message": "..." }` — bad
dates/numbers, invalid range (`"Pick an end date on or after the start, at
most 366 days"`), invalid `group`/`comparison`, missing `comparisonStart`
for `custom` mode. Note: a malformed `companyIds`/`nationalityIds` value
(e.g. non-numeric) surfaces as the generic
`"start/end/asOf must be YYYY-MM-DD and pickupDays a number"` message, which
is misleading — the actual cause may be those params instead.

## 3. `GET /api/rms/reports`

Grouped production/behaviour reports for a date range — this is the bigger
payload, what the "Pace & pickups" tab of Company Analytics renders via the
shared `RmsGroupedReports` component.

**Params:** same filter set as `/api/rms/pace` (`roomType`, `marketId`,
`companyIds`, `nationalityIds`, `channels`, `group`, `comparison`,
`comparisonStart`), plus:

| Param | Type | Default | Notes |
|---|---|---|---|
| `start`, `end` | date | today / `+29d` | same range rule as `/pace` |
| `dateBasis` | `stay` \| `booking` | `stay` | |
| `pickupDays` | int | `7` | **hard-errors 400 if outside `[1, 90]`** — unlike `/pace`, which clamps instead of erroring |

`compareWith` is sent by the frontend but **has no server-side effect** on
this endpoint — don't rely on it.

**Response:**

```json
{
  "status": "success",
  "start": "2026-11-01", "end": "2026-11-30",
  "quality": "observed",
  "production": {
    "market": [ ... ], "roomType": [ ... ], "ratePlan": [ ... ],
    "company": [ ... ], "nationality": [ ... ], "group": [ ... ]
  },
  "marketTrend": [ { "date": "...", "id": "2", "name": "Corporate", "rooms": 12, "idrRooms": 12, "revenue": 1234000, "netRevenue": 1100000 }, ... ],
  "behaviour": { ... },
  "unavailable": [
    { "report": "Promotion effectiveness and net channel contribution", "reason": "Requires verified promotion mapping and commission/cost data; rate-plan production is available." },
    { "report": "Audited actuals and forecast accuracy", "reason": "Requires verified final actuals and a history of forecast snapshots." }
  ]
}
```

Each `production.<dimension>` array (dimensions: `market`, `roomType`,
`ratePlan`, `company`, `nationality`, `group`) holds rows sorted by room
count descending:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | dimension key (e.g. company id, or `"unassigned"`) |
| `name` | string | resolved label |
| `rooms`, `idrRooms`, `revenue`, `netRevenue` | number \| null | null (all together) if top-level `quality` is `unavailable` |
| `pickup` | `{ "1": {rooms, quality}, "7": {...}, "30": {...}, "<pickupDays>": {...} }` | pickup at each horizon, each with its own quality flag |
| `newRooms`, `cancelledRooms`, `amendedRooms` | number \| null | pickup breakdown |
| `comparison` | `{rooms, idrRooms, revenue, netRevenue}` \| null | comparison-period totals; null if `comparisonQuality` is `unavailable` |
| `comparisonQuality` | quality string | |
| `budget` | number \| object \| null | **only populated for `dimension == "market"`**, and null if a `roomType` filter or `dateBasis=booking` is set |

`marketTrend` is a flat `(date, market)` array, always-populated numbers (no
quality flag — computed as-of today only).

`behaviour`:

```json
{
  "dateBasis": "stay",
  "bookings": 480, "allBookings": 512,
  "leadTime": [ { "label": "Same day", "bookings": 10 }, ... ],
  "lengthOfStay": [ { "label": "1 night", "bookings": 120 }, ... ],
  "invalidLeadTime": 0,
  "averageLeadTime": 14.2, "averageLengthOfStay": 2.3,
  "weekdays": [ { "label": "Monday", "booked": 60, "arrivals": 55 }, ... ],
  "losses": [ { "id": "2", "name": "Corporate", "bookings": 40, "cancelled": 3, "noShows": 1 }, ... ]
}
```

`leadTime` buckets: `Same day`, `1–7 days`, `8–14 days`, `15–30 days`,
`31–60 days`, `61–90 days`, `91–180 days`, `181+ days`.
`lengthOfStay` buckets: `1 night`, `2–3 nights`, `4–7 nights`,
`8–14 nights`, `15+ nights`.

`unavailable` is a fixed, non-data-dependent list — it always names the two
report types this API never provides (promotion/commission effectiveness,
audited actuals-vs-forecast accuracy), regardless of filters.

**Errors:** `400` for invalid range, invalid `dateBasis`, `pickupDays`
outside `1..90`, or any filter validation error from the shared
`_pace_options()` parsing (same messages as `/api/rms/pace`).

## Error shape (all endpoints)

```json
{ "status": "error", "message": "<human-readable reason>" }
```

HTTP status is `400` for validation errors, `401` for missing/expired
session, `503` if the backend has no PIN/secret configured.
