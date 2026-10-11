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
- daily: RESERVATION_DATE, trailing 7 days.
- weekly: RESERVATION_DATE trailing 90 days + ARRIVAL_DATE next 365 days.
"""

import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from ..infrastructure.paths import get_data_path
from ..integrations.pms.api_client import PMSApiClient, PMSApiError

DB_FILE = "booking_events.db"
STATUSES = "D,T,Q,I,O,L,N"
CANCELLED = "L"
CHUNK_DAYS = 30
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
    return date.today()


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
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
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
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
    return {
        "reservation_id": int(row["ReservationId"]),
        "reservation_date": _day(row["ReservationDate"]),
        "arrival_date": _day(row["ArrivalDate"]),
        "departure_date": _day(row["DepartureDate"]),
        "nights": int(row.get("Nights") or 0),
        "status": row.get("ReservationStatus") or "",
        "type_id": row.get("TypeId"),
        "rate_type": row.get("RateType"),
        "market_id": row.get("MarketId"),
        "market": row.get("MarketDescription"),
        "room_rate": float(row.get("RoomRate") or 0),
        "currency": row.get("Currency") or "IDR",
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
                    nights, status, type_id, rate_type, market_id, market, room_rate, currency,
                    cancelled_on, updated_at, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec["reservation_id"], rec["reservation_date"], rec["arrival_date"], rec["departure_date"],
                 rec["nights"], rec["status"], rec["type_id"], rec["rate_type"], rec["market_id"], rec["market"],
                 rec["room_rate"], rec["currency"], cancelled_on, rec["updated_at"], synced))
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


def plan(kind, backfill_days=DEFAULT_BACKFILL_DAYS, today=None):
    """[(mode, start, end), ...] for a sync kind."""
    today = today or _today()
    if kind == "backfill":
        jobs = [("RESERVATION_DATE", *w) for w in _windows(today - timedelta(days=backfill_days), today)]
    elif kind == "daily":
        jobs = [("RESERVATION_DATE", *w) for w in _windows(today - timedelta(days=DAILY_DAYS - 1), today)]
    elif kind == "weekly":
        jobs = ([("RESERVATION_DATE", *w) for w in _windows(today - timedelta(days=WEEKLY_BACK_DAYS - 1), today)]
                + [("ARRIVAL_DATE", *w) for w in _windows(today, today + timedelta(days=WEEKLY_FORWARD_DAYS))])
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
        meta = {k: _get_meta(conn, k) for k in ("backfillFrom", "lastDaily", "lastWeekly", "lastBackfill")}
    return {
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
    now = now or datetime.now()
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

def _filters(room_type, market_id):
    clauses, params = [], []
    if room_type:
        clauses.append("b.type_id = ?")
        params.append(room_type)
    if market_id not in (None, ""):
        clauses.append("b.market_id = ?")
        params.append(int(market_id))
    return "".join(f" AND {c}" for c in clauses), params


def on_the_books(start, end, as_of, room_type=None, market_id=None):
    """{stay_date: {"rooms", "revenue", "revenueUsd"}} for stay dates in
    [start, end], counting bookings made on/before as_of and not cancelled
    by then. Revenue is room rate (IDR); USD-priced bookings are summed
    separately rather than converted."""
    extra, params = _filters(room_type, market_id)
    with _db_lock, _db() as conn:
        rows = conn.execute(f"""
            SELECT n.stay_date,
                   COUNT(*) AS rooms,
                   SUM(CASE WHEN b.currency = 'USD' THEN 0 ELSE b.room_rate END) AS revenue,
                   SUM(CASE WHEN b.currency = 'USD' THEN b.room_rate ELSE 0 END) AS revenue_usd
            FROM booking_nights n JOIN bookings b ON b.reservation_id = n.reservation_id
            WHERE n.stay_date BETWEEN ? AND ?
              AND b.reservation_date <= ?
              AND (b.status != '{CANCELLED}' OR COALESCE(b.cancelled_on, b.reservation_date) > ?)
              {extra}
            GROUP BY n.stay_date""", (start, end, as_of, as_of, *params)).fetchall()
    return {r["stay_date"]: {"rooms": r["rooms"], "revenue": r["revenue"] or 0, "revenueUsd": r["revenue_usd"] or 0}
            for r in rows}


LY_OFFSET = timedelta(days=364)  # same weekday last year


def pace_table(start, end, room_type=None, market_id=None, today=None, pickup_days=7):
    """Per stay date: on the books now, pickup over the last pickup_days,
    same time last year (STLY), and last year's final on-the-books."""
    today = today or _today()
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    ly_s, ly_e = (s - LY_OFFSET).isoformat(), (e - LY_OFFSET).isoformat()
    now = on_the_books(start, end, today.isoformat(), room_type, market_id)
    before = on_the_books(start, end, (today - timedelta(days=pickup_days)).isoformat(), room_type, market_id)
    stly = on_the_books(ly_s, ly_e, (today - LY_OFFSET).isoformat(), room_type, market_id)
    empty = {"rooms": 0, "revenue": 0, "revenueUsd": 0}
    out = []
    for i in range((e - s).days + 1):
        d = s + timedelta(days=i)
        ly = (d - LY_OFFSET).isoformat()
        cur, prev = now.get(d.isoformat(), empty), before.get(d.isoformat(), empty)
        # LY final = on the books as of that LY stay date itself.
        final = on_the_books(ly, ly, ly, room_type, market_id).get(ly, empty) if d - LY_OFFSET < today else None
        out.append({
            "date": d.isoformat(),
            "lyDate": ly,
            "rooms": cur["rooms"], "revenue": cur["revenue"], "revenueUsd": cur["revenueUsd"],
            "pickupRooms": cur["rooms"] - prev["rooms"], "pickupRevenue": cur["revenue"] - prev["revenue"],
            "stlyRooms": stly.get(ly, empty)["rooms"], "stlyRevenue": stly.get(ly, empty)["revenue"],
            "lyFinalRooms": final["rooms"] if final else None,
            "lyFinalRevenue": final["revenue"] if final else None,
        })
    return out


def pace_curve(stay_date, max_lead=180, room_type=None, market_id=None):
    """On-the-books for one stay date at each lead time (days before arrival),
    for this year and the same weekday last year."""
    extra, params = _filters(room_type, market_id)
    d = date.fromisoformat(stay_date)
    ly = d - LY_OFFSET

    def bookings_for(day):
        with _db_lock, _db() as conn:
            return conn.execute(f"""
                SELECT b.reservation_date, b.status, b.cancelled_on, b.currency, b.room_rate
                FROM booking_nights n JOIN bookings b ON b.reservation_id = n.reservation_id
                WHERE n.stay_date = ? {extra}""", (day.isoformat(), *params)).fetchall()

    def curve(day, rows):
        points = []
        for lead in range(max_lead, -1, -1):
            as_of = (day - timedelta(days=lead)).isoformat()
            live = [r for r in rows if r["reservation_date"] <= as_of
                    and (r["status"] != CANCELLED or (r["cancelled_on"] or r["reservation_date"]) > as_of)]
            points.append({"lead": lead, "asOf": as_of, "rooms": len(live),
                           "revenue": sum(r["room_rate"] for r in live if r["currency"] != "USD")})
        return points

    return {"date": stay_date, "lyDate": ly.isoformat(),
            "current": curve(d, bookings_for(d)), "lastYear": curve(ly, bookings_for(ly))}


def dimensions():
    """Room types and markets seen in the cache, for filter dropdowns."""
    with _db_lock, _db() as conn:
        types = [r["type_id"] for r in conn.execute(
            "SELECT DISTINCT type_id FROM bookings WHERE type_id IS NOT NULL ORDER BY type_id")]
        markets = [{"id": r["market_id"], "name": r["market"]} for r in conn.execute(
            "SELECT market_id, MAX(market) market FROM bookings WHERE market_id IS NOT NULL "
            "GROUP BY market_id ORDER BY market")]
    return {"roomTypes": types, "markets": markets}


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
