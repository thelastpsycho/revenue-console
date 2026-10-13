"""Local booking-transaction cache for pace/pickup (RMS phase 1).

Pace needs "how did the books for a stay date build up", which no PMS
forecast endpoint carries. It is reconstructed from the booking transaction
log - POST api/ReportReservationStatus - cached in booking_events.db:

- bookings: one row per reservation (master folio only; the endpoint
  repeats a reservation once per extra folio with identical fields).
- booking_nights: one row per reservation per stay night, so on-the-books
  for a stay date is a plain indexed lookup.

Guest PII (name, email, phone, ID, notes...) is in the API response but is
dropped in _normalize() and never written to disk.

Confirmed by live probes (2026-10-11):
- Cancelled is status "L" (not "C"; "C" returns nothing). CancelReason is
  filled on L rows, and UpdatedDate (UTC) is the closest thing to a cancel
  time. N = no-show. The PMS UI's own default sends only D,T,Q,I,O.
- Mode "RESERVATION_DATE" filters on ReservationDate (booking creation),
  Mode "ARRIVAL_DATE" on ArrivalDate - the latter returns every booking for
  those arrivals however long ago it was made, so it is what catches
  cancellations/amendments of future stays.

Three sync jobs, differing only in mode/window:
- backfill: RESERVATION_DATE, 30-day chunks back from today (runs once).
- daily: trailing 7 creation days + ARRIVAL_DATE lookback/in-house through next 365 days.
- weekly: trailing 90 creation days + the same arrival refresh.
- booking_versions: append-only observed changes; older reconstructed history is estimated.
"""

from .report_cache import cached_report

import re
import json
from zoneinfo import ZoneInfo
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from ..infrastructure.paths import get_data_path
from ..integrations.pms.api_client import PMSApiClient, PMSApiError
from ..integrations.pms.fast_allotment_updater import TYPE_ID_ALIASES

DB_FILE = "booking_events.db"
STATUSES = "D,T,Q,I,O,L,N"
CANCELLED = "L"
CHUNK_DAYS = 30
# ADR here means the rate net of breakfast and tax/service, not the PMS's
# raw quoted rate: net_rate = (room_rate - BREAKFAST_IDR) / (1 + TAX_SERVICE_RATE).
BREAKFAST_IDR = 350_000
TAX_SERVICE_RATE = 0.21
DEFAULT_BACKFILL_DAYS = 3 * 365
MAX_BACKFILL_DAYS = 6 * 365
DAILY_DAYS = 7
WEEKLY_BACK_DAYS = 90
WEEKLY_FORWARD_DAYS = 365
# Scheduled syncs start at/after this local hour, so the PMS night audit has run.
SCHEDULED_HOUR = 4

_db_lock = threading.Lock()
_sync_lock = threading.Lock()
_status = {"running": False, "kind": None, "startedAt": None, "finishedAt": None,
           "done": 0, "total": 0, "rows": 0, "error": None}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today():
    return datetime.now(ZoneInfo("Asia/Makassar")).date()


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bookings (
            reservation_id INTEGER PRIMARY KEY,
            reservation_date TEXT NOT NULL,
            arrival_date TEXT NOT NULL,
            departure_date TEXT NOT NULL,
            nights INTEGER NOT NULL,
            status TEXT NOT NULL,
            type_id TEXT,
            rate_type TEXT,
            market_id INTEGER,
            market TEXT,
            company_id INTEGER,
            company TEXT,
            room_rate REAL,
            currency TEXT,
            cancelled_on TEXT,
            updated_at TEXT,
            synced_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS booking_nights (
            reservation_id INTEGER NOT NULL,
            stay_date TEXT NOT NULL,
            PRIMARY KEY (reservation_id, stay_date)
        );
        CREATE INDEX IF NOT EXISTS idx_nights_stay ON booking_nights (stay_date);
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            rows INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS booking_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            observed_on TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_versions_reservation ON booking_versions(reservation_id, id);
        CREATE INDEX IF NOT EXISTS idx_versions_day ON booking_versions(observed_on);
        CREATE INDEX IF NOT EXISTS idx_versions_arrival ON booking_versions(json_extract(payload, '$.arrival_date'));
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(bookings)")}
    if "net_rate" not in columns:
        conn.execute("ALTER TABLE bookings ADD COLUMN net_rate REAL")
        conn.execute(
            "UPDATE bookings SET net_rate = MAX((room_rate - ?) / (1 + ?), 0) WHERE currency = 'IDR'",
            (BREAKFAST_IDR, TAX_SERVICE_RATE),
        )
    if "rate_id" not in columns:
        conn.execute("ALTER TABLE bookings ADD COLUMN rate_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE bookings ADD COLUMN company_id INTEGER")
    if "company" not in columns:
        conn.execute("ALTER TABLE bookings ADD COLUMN company TEXT")
    # company/company_id are static per reservation (the booking channel never
    # changes after creation), but pace/YoY reconstruction reads whichever
    # booking_versions snapshot was active "as of" a past date - for
    # reservations first observed before these columns existed, that snapshot
    # predates company tracking and has no company key, so channel filters
    # silently drop them (only the *current* row, not history, got backfilled
    # earlier). Patch every such snapshot with the reservation's now-known,
    # time-invariant company once.
    if not _get_meta(conn, "companyBackfilledIntoVersions"):
        conn.execute("""
            UPDATE booking_versions
            SET payload = json_set(payload,
                '$.company_id', (SELECT company_id FROM bookings b WHERE b.reservation_id = booking_versions.reservation_id),
                '$.company', (SELECT company FROM bookings b WHERE b.reservation_id = booking_versions.reservation_id))
            WHERE json_extract(payload, '$.company') IS NULL
              AND EXISTS (SELECT 1 FROM bookings b WHERE b.reservation_id = booking_versions.reservation_id AND b.company IS NOT NULL)
        """)
        _set_meta(conn, "companyBackfilledIntoVersions", "1")
    # Seed an existing installation once, preserving only the same PII-free fields.
    seeded = conn.execute("SELECT value FROM meta WHERE key='versionsSeeded'").fetchone()
    if not seeded:
        conn.execute("""INSERT INTO booking_versions(reservation_id, observed_on, observed_at, payload)
        SELECT b.reservation_id, ?, ?, json_object(
          'reservation_id', b.reservation_id, 'reservation_date', b.reservation_date,
          'arrival_date', b.arrival_date, 'departure_date', b.departure_date,
          'status', b.status, 'type_id', b.type_id, 'rate_type', b.rate_type, 'rate_id', b.rate_id,
          'market_id', b.market_id, 'market', b.market, 'company_id', b.company_id, 'company', b.company,
          'room_rate', b.room_rate, 'currency', b.currency, 'cancelled_on', b.cancelled_on)
        FROM bookings b WHERE NOT EXISTS (
          SELECT 1 FROM booking_versions v WHERE v.reservation_id = b.reservation_id)""",
            (_today().isoformat(), _now()))
        conn.execute("INSERT INTO meta(key,value) VALUES ('versionsSeeded','1')")
    conn.commit()
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


# ------------------------------------------------------------------- ingest

def _day(value):
    return value[:10] if value else None


def _cancel_day(row):
    """Local date of UpdatedDate (UTC, up to 7 fractional digits)."""
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", row.get("UpdatedDate") or "")
    if not match:
        return None
    utc = datetime.fromisoformat(match.group(1))
    return (utc + timedelta(hours=row.get("TimeZone") or 8)).date().isoformat()


def _normalize(row):
    """The whitelisted, PII-free subset of one API row."""
    room_rate = float(row.get("RoomRate") or 0)
    currency = (row.get("Currency") or "IDR").strip().upper()
    return {
        "reservation_id": int(row["ReservationId"]),
        "reservation_date": _day(row["ReservationDate"]),
        "arrival_date": _day(row["ArrivalDate"]),
        "departure_date": _day(row["DepartureDate"]),
        "nights": int(row.get("Nights") or 0),
        "status": row.get("ReservationStatus") or "",
        "type_id": TYPE_ID_ALIASES.get(row.get("TypeId"), row.get("TypeId")),
        "rate_type": row.get("RateType"),
        "rate_id": row.get("RateId"),
        "market_id": row.get("MarketId"),
        "market": row.get("MarketDescription"),
        "company_id": row.get("CompanyId"),
        "company": row.get("CompanyName"),
        "room_rate": room_rate,
        "currency": currency,
        # Net of breakfast and tax/service; USD rooms are left NULL since
        # breakfast is an IDR figure and this app doesn't track an FX rate.
        # Floored at 0: zero-rate (comp/house-use) rooms have no breakfast to take off.
        "net_rate": max(room_rate - BREAKFAST_IDR, 0) / (1 + TAX_SERVICE_RATE) if currency == "IDR" else None,
        "updated_at": row.get("UpdatedDate"),
        "cancel_day": _cancel_day(row) if row.get("ReservationStatus") == CANCELLED else None,
    }


def master_rows(rows):
    """One row per reservation: the master folio (or the first row if a
    reservation somehow has none)."""
    picked = {}
    for row in rows:
        rid = row["ReservationId"]
        if rid not in picked or (row.get("IsMasterFolio") and not picked[rid].get("IsMasterFolio")):
            picked[rid] = row
    return list(picked.values())


def _stay_dates(arrival, departure):
    start = date.fromisoformat(arrival)
    end = date.fromisoformat(departure)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days)]


def upsert(rows):
    """Writes API rows (raw ReportReservationStatus dicts). Returns count."""
    records = [_normalize(r) for r in master_rows(rows)]
    synced = _now()
    with _db_lock, _db() as conn:
        for rec in records:
            existing = conn.execute("SELECT status, cancelled_on FROM bookings WHERE reservation_id = ?",
                                    (rec["reservation_id"],)).fetchone()
            cancelled_on = None
            if rec["status"] == CANCELLED:
                # Keep the first cancel date we saw: later edits move UpdatedDate.
                if existing and existing["status"] == CANCELLED and existing["cancelled_on"]:
                    cancelled_on = existing["cancelled_on"]
                else:
                    cancelled_on = rec["cancel_day"] or rec["reservation_date"]
            conn.execute("""
                INSERT OR REPLACE INTO bookings (reservation_id, reservation_date, arrival_date, departure_date,
                    nights, status, type_id, rate_type, market_id, market, company_id, company, room_rate,
                    currency, net_rate, rate_id, cancelled_on, updated_at, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec["reservation_id"], rec["reservation_date"], rec["arrival_date"], rec["departure_date"],
                 rec["nights"], rec["status"], rec["type_id"], rec["rate_type"], rec["market_id"], rec["market"],
                 rec["company_id"], rec["company"], rec["room_rate"], rec["currency"], rec["net_rate"], rec["rate_id"],
                 cancelled_on, rec["updated_at"], synced))
            version = {key: rec[key] for key in (
                "reservation_id", "reservation_date", "arrival_date", "departure_date", "status",
                "type_id", "rate_type", "rate_id", "market_id", "market", "company_id", "company",
                "room_rate", "currency")}
            version["cancelled_on"] = cancelled_on
            payload = json.dumps(version, sort_keys=True)
            last = conn.execute("SELECT payload FROM booking_versions WHERE reservation_id = ? ORDER BY id DESC LIMIT 1",
                                (rec["reservation_id"],)).fetchone()
            if not last or json.loads(last["payload"]) != version:
                conn.execute("INSERT INTO booking_versions(reservation_id, observed_on, observed_at, payload) VALUES (?, ?, ?, ?)",
                             (rec["reservation_id"], _today().isoformat(), synced, payload))
            conn.execute("DELETE FROM booking_nights WHERE reservation_id = ?", (rec["reservation_id"],))
            conn.executemany("INSERT INTO booking_nights (reservation_id, stay_date) VALUES (?, ?)",
                             [(rec["reservation_id"], d) for d in _stay_dates(rec["arrival_date"], rec["departure_date"])])
    return len(records)


# --------------------------------------------------------------------- sync

def _windows(start, end):
    """[start, end] split into inclusive CHUNK_DAYS windows, newest first."""
    windows = []
    cursor = end
    while cursor >= start:
        chunk_start = max(start, cursor - timedelta(days=CHUNK_DAYS - 1))
        windows.append((chunk_start, cursor))
        cursor = chunk_start - timedelta(days=1)
    return windows


def _arrival_refresh_start(today):
    # Include all known in-house stays, even long stays that began before the lookback.
    with _db_lock, _db() as conn:
        row = conn.execute("SELECT MIN(arrival_date) d FROM bookings WHERE arrival_date < ? AND departure_date > ? AND status != ?",
                           (today.isoformat(), today.isoformat(), CANCELLED)).fetchone()
    return min(today - timedelta(days=30), date.fromisoformat(row["d"])) if row["d"] else today - timedelta(days=30)


def plan(kind, backfill_days=DEFAULT_BACKFILL_DAYS, today=None):
    """[(mode, start, end), ...] for a sync kind."""
    today = today or _today()
    if kind == "backfill":
        jobs = [("RESERVATION_DATE", *w) for w in _windows(today - timedelta(days=backfill_days), today)]
    elif kind == "daily":
        jobs = [("RESERVATION_DATE", *w) for w in _windows(today - timedelta(days=DAILY_DAYS - 1), today)]
        jobs += [("ARRIVAL_DATE", *w) for w in _windows(_arrival_refresh_start(today), today + timedelta(days=WEEKLY_FORWARD_DAYS))]
    elif kind == "weekly":
        jobs = ([("RESERVATION_DATE", *w) for w in _windows(today - timedelta(days=WEEKLY_BACK_DAYS - 1), today)]
                + [("ARRIVAL_DATE", *w) for w in _windows(_arrival_refresh_start(today), today + timedelta(days=WEEKLY_FORWARD_DAYS))])
    else:
        raise ValueError(f"Unknown sync kind: {kind}")
    return jobs


def fetch_window(client, mode, start, end):
    return client._api_post("ReportReservationStatus", {
        "HotelId": str(client.hotel_id), "UserId": client.user_id,
        "TrxDate": start.isoformat(), "TrxDate2": end.isoformat(),
        "ReservationStatus": STATUSES, "ReservationSource": "", "Mode": mode,
    })


def status():
    with _sync_lock:
        snapshot = dict(_status)
    with _db_lock, _db() as conn:
        counts = conn.execute("SELECT COUNT(*) n, MIN(reservation_date) first, MAX(reservation_date) last "
                              "FROM bookings").fetchone()
        runs = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 10").fetchall()
        meta = {k: _get_meta(conn, k) for k in ("backfillFrom", "lastDaily", "lastWeekly", "lastBackfill", "lastSuccessfulSync")}
    return {
        "lastSuccessfulSync": meta["lastSuccessfulSync"],
        "historyBasis": "Observed booking versions; earlier history is reconstructed and estimated",
        "stale": not meta["lastSuccessfulSync"] or
            (datetime.now(timezone.utc) - datetime.fromisoformat(meta["lastSuccessfulSync"])).total_seconds() > 36 * 3600,
        "job": snapshot,
        "bookings": counts["n"],
        "firstReservationDate": counts["first"],
        "lastReservationDate": counts["last"],
        # Bookings made from this date are complete; earlier ones only where
        # an ARRIVAL_DATE resync happened to pull them in.
        "coverageFrom": meta["backfillFrom"],
        "lastDaily": meta["lastDaily"],
        "lastWeekly": meta["lastWeekly"],
        "lastBackfill": meta["lastBackfill"],
        "runs": [dict(r) for r in runs],
    }


def start_sync(kind, backfill_days=DEFAULT_BACKFILL_DAYS, client_factory=PMSApiClient):
    """Starts a sync in a background thread. Returns False if one is running."""
    jobs = plan(kind, backfill_days)
    with _sync_lock:
        if _status["running"]:
            return False
        _status.update(running=True, kind=kind, startedAt=_now(), finishedAt=None,
                       done=0, total=len(jobs), rows=0, error=None)
    threading.Thread(target=_run_sync, args=(kind, jobs, backfill_days, client_factory),
                     daemon=True, name=f"booking-sync-{kind}").start()
    return True


def _run_sync(kind, jobs, backfill_days, client_factory):
    with _db_lock, _db() as conn:
        run_id = conn.execute("INSERT INTO sync_runs (kind, started_at) VALUES (?, ?)",
                              (kind, _now())).lastrowid
    rows, error = 0, None
    try:
        client = client_factory().login()
        for mode, start, end in jobs:
            rows += upsert(fetch_window(client, mode, start, end))
            with _sync_lock:
                _status.update(done=_status["done"] + 1, rows=rows)
    except (PMSApiError, OSError, ValueError, KeyError) as exc:
        error = str(exc)
    except Exception as exc:  # keep the status honest on anything unexpected
        error = f"{type(exc).__name__}: {exc}"
    finished = _now()
    with _db_lock, _db() as conn:
        conn.execute("UPDATE sync_runs SET finished_at = ?, rows = ?, error = ? WHERE id = ?",
                     (finished, rows, error, run_id))
        if not error:
            today = _today().isoformat()
            _set_meta(conn, "lastSuccessfulSync", finished)
            if kind == "backfill":
                start = (_today() - timedelta(days=backfill_days)).isoformat()
                current = _get_meta(conn, "backfillFrom")
                _set_meta(conn, "backfillFrom", min(start, current) if current else start)
            _set_meta(conn, {"backfill": "lastBackfill", "daily": "lastDaily", "weekly": "lastWeekly"}[kind], today)
    with _sync_lock:
        _status.update(running=False, finishedAt=finished, rows=rows, error=error)


def due_scheduled_kind(now=None):
    """'weekly', 'daily' or None - what the scheduler tick should start.
    Nothing runs before a backfill exists (the operator starts that)."""
    now = now or datetime.now(ZoneInfo("Asia/Makassar"))
    if now.hour < SCHEDULED_HOUR:
        return None
    with _db_lock, _db() as conn:
        if not _get_meta(conn, "backfillFrom"):
            return None
        last_weekly = _get_meta(conn, "lastWeekly")
        last_daily = _get_meta(conn, "lastDaily")
    today = now.date()
    if not last_weekly or date.fromisoformat(last_weekly) <= today - timedelta(days=7):
        return "weekly"
    if last_daily != today.isoformat() and last_weekly != today.isoformat():
        return "daily"
    return None


def run_scheduled_if_due():
    kind = due_scheduled_kind()
    if kind and start_sync(kind):
        return kind
    return None


# --------------------------------------------------------------------- pace

class BookingHistory(dict):
    observed_from = None


# Keyed by (db path, MAX(booking_versions.id)) so a cache hit is just one
# cheap indexed query - reading and json-decoding the whole table made every
# report request's latency scale with total database size, even though new
# version rows only land a few times a day (sync jobs), not once per request.
# The db path is part of the key (not just max_id) so tests that point
# get_data_path at a fresh tmp_path per test can't collide with a stale
# cache entry from a different database that happens to share a row count.
_history_cache = {"key": None, "history": None}


def _cached_full_history():
    with _db_lock, _db() as conn:
        key = (get_data_path(DB_FILE), conn.execute("SELECT MAX(id) FROM booking_versions").fetchone()[0])
        if _history_cache["key"] == key and _history_cache["history"] is not None:
            return _history_cache["history"]
        rows = conn.execute("SELECT reservation_id, observed_on, payload FROM booking_versions ORDER BY id").fetchall()
        first = conn.execute("SELECT MIN(observed_on) FROM booking_versions").fetchone()[0]
        history = BookingHistory()
        history.observed_from = first
        for r in rows:
            history.setdefault(r["reservation_id"], []).append((r["observed_on"], json.loads(r["payload"])))
        _history_cache["key"], _history_cache["history"] = key, history
        return history


def version_history(ranges=None):
    """Booking_versions filtered to reservations touching `ranges` (or the
    whole table if None), served from the in-process cache above - the
    filter itself runs in Python against the cached table instead of SQL,
    since the expensive part was always reading/parsing the whole table."""
    history = _cached_full_history()
    if not ranges:
        return history
    filtered = BookingHistory()
    filtered.observed_from = history.observed_from
    for rid, versions in history.items():
        if any(payload["arrival_date"] <= end and payload["departure_date"] > start
               for start, end in ranges for _, payload in versions):
            filtered[rid] = versions
    return filtered


def state_as_of(history, as_of):
    result = {}
    for rid, versions in history.items():
        # Earlier than first observation: best-effort reconstruction, never called observed history.
        chosen = None
        for observed, payload in versions:
            if observed <= as_of:
                chosen = payload
            else:
                break
        if chosen is None:
            if history.observed_from and as_of >= history.observed_from:
                # Newly discovered old bookings must not rewrite already observed history.
                continue
            chosen = versions[0][1]
        if chosen["reservation_date"] <= as_of:
            result[rid] = chosen
    return result


def _active(r, as_of):
    return r["status"] != CANCELLED or (r.get("cancelled_on") or r["reservation_date"]) > as_of


# Booking-company channel classification, used by the Online segment report
# and as an optional filter here. (bucket id, display label, substrings
# matched case-insensitively against bookings.company.) Only "Santika Online
# Reservation", "Booking.com" and "Agoda.com" are confirmed exact strings
# from a live PMS probe (docs/pms-data-api.md); the rest are lenient markers,
# validated against real company names seen in bookings.company after the
# company_id/company columns were backfilled.
CHANNEL_BUCKETS = [
    ("direct", "Santika Online", ["santika online"]),
    ("booking_com", "Booking.com", ["booking.com"]),
    ("agoda", "Agoda", ["agoda"]),
    ("traveloka", "Traveloka", ["traveloka"]),
    ("expedia", "Expedia", ["expedia"]),
    ("tiket_com", "Tiket.com", ["tiket.com", "tiket"]),
    ("trip_com", "Trip.com", ["trip.com"]),
]
OTHER_BUCKET = ("other", "Other online channel")
UNASSIGNED_BUCKET = ("unassigned", "Unassigned")
BUCKET_ORDER = [b[:2] for b in CHANNEL_BUCKETS] + [OTHER_BUCKET, UNASSIGNED_BUCKET]


def channel_bucket(company):
    """(bucket id, display label) for a booking's CompanyName."""
    name = (company or "").strip().lower()
    if not name:
        return UNASSIGNED_BUCKET
    for bucket_id, label, markers in CHANNEL_BUCKETS:
        if any(marker in name for marker in markers):
            return bucket_id, label
    return OTHER_BUCKET


def _matches(r, room_type, market_id, channels=None):
    return (not room_type or r["type_id"] == room_type) and (
        market_id in (None, "") or r["market_id"] == int(market_id)) and (
        not channels or channel_bucket(r.get("company"))[0] in channels)


def _empty():
    return {"rooms": 0, "idrRooms": 0, "revenue": 0, "revenueUsd": 0, "netRevenue": 0}


def aggregate(states, start, end, as_of, room_type=None, market_id=None, rules=None, channels=None):
    from .rms_workspace import net_rate, get_settings
    rules = rules if rules is not None else get_settings()["revenueRules"]
    out = {}
    for r in states.values():
        if not _active(r, as_of) or not _matches(r, room_type, market_id, channels):
            continue
        first, last = max(start, r["arrival_date"]), min(end, (date.fromisoformat(r["departure_date"]) - timedelta(days=1)).isoformat())
        if first > last:
            continue
        for day in _stay_dates(first, (date.fromisoformat(last) + timedelta(days=1)).isoformat()):
            bucket = out.setdefault(day, _empty())
            bucket["rooms"] += 1
            if r["currency"] == "IDR":
                bucket["idrRooms"] += 1
                bucket["revenue"] += r["room_rate"]
                bucket["netRevenue"] += net_rate(r["room_rate"], r.get("rate_type"), day, rules, r.get("rate_id"))
            elif r["currency"] == "USD":
                bucket["revenueUsd"] += r["room_rate"]
    return out


def on_the_books(start, end, as_of, room_type=None, market_id=None, channels=None):
    return aggregate(state_as_of(version_history([(start, end)]), as_of), start, end, as_of, room_type, market_id,
                     channels=channels)


LY_OFFSET = timedelta(days=364)


def comparison_date(day, mode="weekday", custom_start=None, start=None):
    if mode == "weekday":
        return day - LY_OFFSET
    if mode == "calendar":
        try:
            return day.replace(year=day.year - 1)
        except ValueError:  # Feb 29 -> Feb 28
            return day.replace(year=day.year - 1, day=28)
    if mode == "custom" and custom_start and start:
        return date.fromisoformat(custom_start) + (day - date.fromisoformat(start))
    raise ValueError("comparison must be weekday, calendar, or custom with comparisonStart")


def _quality(as_of, coverage, history):
    if not coverage or as_of < coverage:
        return "unavailable"
    first = history.observed_from
    return "observed" if first and as_of >= first else "estimated"


def _occupied_days(r, start, end, as_of, room_type, market_id, channels):
    """ISO day strings in [start,end] where r is active and matches, as of as_of."""
    if not r or not _active(r, as_of) or not _matches(r, room_type, market_id, channels):
        return set()
    first, last = max(start, r["arrival_date"]), min(end, (date.fromisoformat(r["departure_date"]) - timedelta(days=1)).isoformat())
    if first > last:
        return set()
    return set(_stay_dates(first, (date.fromisoformat(last) + timedelta(days=1)).isoformat()))


def pickup_breakdown_series(previous, current, start, end, before, today, room_type, market_id, channels=None):
    """Per-day {newRooms, cancelledRooms, amendedRooms} for the whole
    [start,end] range in one pass over reservations - replaces calling the
    old per-day pickup_breakdown() once per day, which re-diffed every
    reservation for each day instead of just once."""
    buckets = {d: {"newRooms": 0, "cancelledRooms": 0, "amendedRooms": 0}
               for d in _stay_dates(start, (date.fromisoformat(end) + timedelta(days=1)).isoformat())}
    for rid in previous.keys() | current.keys():
        old, cur = previous.get(rid), current.get(rid)
        old_days = _occupied_days(old, start, end, before, room_type, market_id, channels)
        cur_days = _occupied_days(cur, start, end, today, room_type, market_id, channels)
        added, removed = cur_days - old_days, old_days - cur_days
        if added:
            key = "newRooms" if cur["reservation_date"] > before else "amendedRooms"
            for d in added:
                buckets[d][key] += 1
        if removed:
            # A true cancellation is a positive count of rooms lost; an
            # amendment that moves a reservation off this day is a negative
            # contribution to the net amendment figure (mirrors the old
            # per-day delta, which was negative here).
            if cur and not _active(cur, today):
                for d in removed:
                    buckets[d]["cancelledRooms"] += 1
            else:
                for d in removed:
                    buckets[d]["amendedRooms"] -= 1
    return buckets


def _version_segments(versions, observed_from, range_end):
    """[(as_of_start, as_of_end_exclusive, payload), ...]: the as-of window
    during which each version is the one state_as_of(history, as_of) would
    return for this reservation - including the pre-first-observation
    estimate and its observed_from cutoff (see state_as_of). Precomputed
    once per reservation instead of re-derived by walking the version list
    fresh for every as-of value a caller needs."""
    segments = []
    first_observed, first_payload = versions[0]
    pre_end = min(first_observed, observed_from) if observed_from else first_observed
    if pre_end > first_payload["reservation_date"]:
        segments.append((first_payload["reservation_date"], pre_end, first_payload))
    for i, (observed, payload) in enumerate(versions):
        seg_end = versions[i + 1][0] if i + 1 < len(versions) else range_end
        if seg_end > observed:
            segments.append((observed, seg_end, payload))
    return segments


def final_rooms_series(history, start, end, rules, room_type=None, market_id=None, channels=None):
    """Per-day actuals "as observed on that stay date itself" (no later
    cancellations/amendments counted) for every day in [start,end] - i.e.
    state_as_of(history, day) aggregated at exactly that diagonal day.

    Unlike stly/now/before (one as-of shared across many days, so a single
    state_as_of + aggregate() pair already covers the whole range), this
    as-of is different for every single day, so the old code paid a fresh
    state_as_of + aggregate pass per day. This instead walks each
    reservation's version timeline once and intersects it against the
    as-of-equals-day diagonal directly."""
    from .rms_workspace import net_rate
    range_end = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    out = {d: _empty() for d in _stay_dates(start, range_end)}
    for versions in history.values():
        for seg_start, seg_end, payload in _version_segments(versions, history.observed_from, range_end):
            if not _matches(payload, room_type, market_id, channels):
                continue
            lo = max(seg_start, start, payload["arrival_date"])
            hi = min(seg_end, range_end, payload["departure_date"])
            if payload["status"] == CANCELLED:
                hi = min(hi, payload.get("cancelled_on") or payload["reservation_date"])
            if lo >= hi:
                continue
            for day in _stay_dates(lo, hi):
                bucket = out[day]
                bucket["rooms"] += 1
                if payload["currency"] == "IDR":
                    bucket["idrRooms"] += 1
                    bucket["revenue"] += payload["room_rate"]
                    bucket["netRevenue"] += net_rate(payload["room_rate"], payload.get("rate_type"), day, rules, payload.get("rate_id"))
                elif payload["currency"] == "USD":
                    bucket["revenueUsd"] += payload["room_rate"]
    return out


@cached_report
def pace_table(start, end, room_type=None, market_id=None, today=None, pickup_days=7,
               comparison="weekday", comparison_start=None, channels=None):
    from .rms_workspace import get_settings
    from . import rms_budget
    today = today or _today()
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    ly_start = comparison_date(s, comparison, comparison_start, start).isoformat()
    ly_end = comparison_date(e, comparison, comparison_start, start).isoformat()
    history = version_history([(start, end), (ly_start, ly_end)])
    # Segment budget has no room-type or channel dimension, so those filters
    # leave no figure that actually matches what's being compared.
    budget = {} if room_type or channels else rms_budget.daily_totals(start, end, market_id=market_id, basis="gross")
    rules = get_settings()["revenueRules"]
    with _db_lock, _db() as conn:
        coverage = _get_meta(conn, "backfillFrom")
    current_day, prior_day = today.isoformat(), (today - timedelta(days=pickup_days)).isoformat()
    current, previous = state_as_of(history, current_day), state_as_of(history, prior_day)
    now = aggregate(current, start, end, current_day, room_type, market_id, rules, channels)
    before = aggregate(previous, start, end, prior_day, room_type, market_id, rules, channels)
    breakdown_series = pickup_breakdown_series(previous, current, start, end, prior_day, current_day,
                                               room_type, market_id, channels)

    days_meta = []
    for i in range((e - s).days + 1):
        d = s + timedelta(days=i)
        day = d.isoformat()
        ly_day = comparison_date(d, comparison, comparison_start, start)
        ly = ly_day.isoformat()
        ly_as_of = (today - (d - ly_day)).isoformat()
        quality = _quality(ly_as_of, coverage, history) if ly_as_of <= current_day else "unavailable"
        final_quality = _quality(ly, coverage, history)
        days_meta.append({"day": day, "ly": ly, "ly_day": ly_day, "ly_as_of": ly_as_of,
                          "quality": quality, "final_quality": final_quality})

    # stly shares one as-of across (near enough) the whole range - comparison_date
    # is a fixed shift for weekday/custom modes and only drifts by a leap day for
    # calendar mode - so group by the actual as-of value and reconstruct/aggregate
    # once per group instead of once per day.
    stly_by_day = {}
    as_of_groups = {}
    for m in days_meta:
        if m["quality"] != "unavailable":
            as_of_groups.setdefault(m["ly_as_of"], []).append(m["ly"])
    for as_of, lys in as_of_groups.items():
        bucket = aggregate(state_as_of(history, as_of), min(lys), max(lys), as_of, room_type, market_id, rules, channels)
        for ly in lys:
            stly_by_day[ly] = bucket.get(ly, _empty())

    # final's as-of is genuinely different per day (see final_rooms_series).
    final_by_day = final_rooms_series(history, ly_start, ly_end, rules, room_type, market_id, channels)

    out = []
    for m in days_meta:
        day, ly = m["day"], m["ly"]
        stly = stly_by_day.get(ly) if m["quality"] != "unavailable" else None
        final = final_by_day.get(ly) if m["ly_day"] < today and m["final_quality"] != "unavailable" else None
        cur, prev = now.get(day, _empty()), before.get(day, _empty())
        pickup_quality = _quality(prior_day, coverage, history)
        breakdown = breakdown_series[day]
        day_budget = budget.get(day)
        out.append({
            "date": day, "lyDate": ly, **cur,
            "budgetRooms": day_budget["rooms"] if day_budget else None,
            "budgetRevenue": day_budget["revenue"] if day_budget else None,
            "pickupRooms": cur["rooms"] - prev["rooms"] if pickup_quality != "unavailable" else None,
            "pickupRevenue": cur["revenue"] - prev["revenue"] if pickup_quality != "unavailable" else None,
            **{k: v if pickup_quality != "unavailable" else None for k, v in breakdown.items()},
            "comparisonQuality": m["quality"], "pickupQuality": pickup_quality,
            "currentQuality": _quality(current_day, coverage, history),
            "stlyRooms": stly["rooms"] if stly else None,
            "stlyRevenue": stly["revenue"] if stly else None,
            "stlyIdrRooms": stly["idrRooms"] if stly else None,
            "stlyNetRevenue": stly["netRevenue"] if stly else None,
            "lyFinalRooms": final["rooms"] if final else None,
            "lyFinalRevenue": final["revenue"] if final else None,
        })
    return out


@cached_report
def pace_curve(stay_date, max_lead=180, room_type=None, market_id=None,
               comparison="weekday", comparison_start=None, range_start=None, channels=None):
    from .rms_workspace import get_settings
    d = date.fromisoformat(stay_date)
    ly = comparison_date(d, comparison, comparison_start, range_start or stay_date)
    history, today = version_history([(stay_date, stay_date), (ly.isoformat(), ly.isoformat())]), _today()
    rules = get_settings()["revenueRules"]
    with _db_lock, _db() as conn:
        coverage = _get_meta(conn, "backfillFrom")
    def curve(day):
        points = []
        for lead in range(max_lead, -1, -1):
            as_of = day - timedelta(days=lead)
            if as_of > today:
                continue
            quality = _quality(as_of.isoformat(), coverage, history)
            value = aggregate(state_as_of(history, as_of.isoformat()), day.isoformat(), day.isoformat(),
                              as_of.isoformat(), room_type, market_id, rules, channels).get(day.isoformat(), _empty())
            points.append({"lead": lead, "asOf": as_of.isoformat(), "quality": quality,
                           "rooms": value["rooms"] if quality != "unavailable" else None,
                           "revenue": value["revenue"] if quality != "unavailable" else None})
        return points
    return {"date": stay_date, "lyDate": ly.isoformat(), "todayLead": (d - today).days,
            "maxLead": max_lead, "current": curve(d), "lastYear": curve(ly)}


def dimensions():
    """Room types and markets seen in the cache, for filter dropdowns."""
    with _db_lock, _db() as conn:
        types = [r["type_id"] for r in conn.execute(
            "SELECT DISTINCT type_id FROM bookings WHERE type_id IS NOT NULL ORDER BY type_id")]
        markets = [{"id": r["market_id"], "name": r["market"]} for r in conn.execute(
            "SELECT market_id, MAX(market) market FROM bookings WHERE market_id IS NOT NULL "
            "GROUP BY market_id ORDER BY market")]
    channels = [{"id": bucket_id, "name": label} for bucket_id, label in BUCKET_ORDER]
    return {"roomTypes": types, "markets": markets, "channels": channels}


if __name__ == "__main__":  # python -m app.revenue.booking_events [backfill|daily|weekly] [days]
    import sys
    import time

    from dotenv import load_dotenv

    load_dotenv()
    kind = sys.argv[1] if len(sys.argv) > 1 else "daily"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BACKFILL_DAYS
    start_sync(kind, days)
    while status()["job"]["running"]:
        job = status()["job"]
        print(f"{kind}: {job['done']}/{job['total']} windows, {job['rows']} rows", flush=True)
        time.sleep(5)
    print(status()["job"])
