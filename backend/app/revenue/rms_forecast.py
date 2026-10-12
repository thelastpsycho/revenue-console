"""PMS forecast sections with a persistent stale-while-refresh cache.

Endpoint behaviour confirmed by live probes (2026-10-11):
- ReportForecastOccupancy always returns 7 days whatever `Days` says, but
  honours any TrxDate, so longer horizons are fetched in 7-day chunks.
- ReportForecastOccupancyMarketSegment honours `Days` exactly (one row per
  date per market segment).
- ReportExpectedRoomOccupied ignores `Days` entirely, but takes a separate
  `Mode` param - a string day-count ("7"/"20"/"30"...), not the enum/bool
  it looks like - that sets the window directly: floored at 7, clamped at
  30 (Mode "31"/"60"/"90" all return the same 30-day window). Found by
  watching the PMS UI's own "Allotment - Forecast" report call the sibling
  endpoint the same way. One row per room type, "MM-DD" columns plus
  NoOfRooms (that type's room count). It builds a server-side temp table
  named by hotel + timestamp, so concurrent calls collide ("Invalid object
  name 'xtempRoomAvail_...'") - chunks are fetched one after another, but
  30-day chunks means ~4x fewer of them than the old 7-day-only approach.

Room revenue only - no F&B/outlet fields are returned.
"""

from datetime import date, timedelta

from ..integrations.pms.api_client import PMSApiClient

CHUNK = 7
# ReportExpectedRoomOccupied's Mode window, clamped server-side at 30 days.
ROOM_CHUNK = 30
# The segment call is slow (~27 s for 30 days, ~44 s for 90), so it's split
# into chunks fetched in parallel too, keeping a 90-day load well under the
# ~100 s Cloudflare tunnel request timeout.
SEGMENT_CHUNK = 14
MAX_DAYS = 90


def _starts(start, days, chunk=CHUNK):
    return [start + timedelta(days=i) for i in range(0, days, chunk)]


def _post(client, name, trx_date, days=CHUNK):
    return client._api_post(name, {"TrxDate": trx_date.isoformat(), "Days": days,
                                   "HotelId": client.hotel_id, "UserId": client.user_id})


def _post_room_types(client, trx_date):
    # Always ask for the full 30-day window - the overhang beyond `days`
    # (from the last chunk, or Mode's own 7-day floor) is trimmed by
    # fetch_section's date filter, same as the other endpoints' chunks.
    return client._api_post("ReportExpectedRoomOccupied", {"TrxDate": trx_date.isoformat(), "Mode": str(ROOM_CHUNK),
                                                            "HotelId": client.hotel_id, "UserId": client.user_id})


def _hotel(rows):
    return [{
        "date": r["TrxDate"][:10],
        "roomsSold": r.get("RoomUsed"),
        "roomCount": r.get("RoomCount"),
        "occupancy": r.get("Occupancy"),
        "revenue": r.get("RoomRevenue"),
        "adr": r.get("AverageRoomRate"),
        "complimentary": r.get("Complimentary"),
        "houseUse": r.get("HouseUse"),
        "lastYear": r.get("LastYearTransient"),
    } for r in rows]


def _segments(rows):
    return [{
        "date": r["TrxDate"][:10],
        "marketId": r.get("MarketId"),
        "market": r.get("MarketDescription"),
        "rooms": r.get("OnhandReservation"),
        "complimentary": r.get("OnhandCompliment"),
        "houseUse": r.get("OnhandHouseUse"),
        "revenue": r.get("OnhandRevenue"),
    } for r in rows]


def _room_types(rows):
    """Unpivots the "MM-DD" columns back to full dates using each row's own
    StartDate/EndDate (so a chunk spanning New Year resolves correctly, and
    the row's actual span is used rather than an assumed chunk size)."""
    out = []
    for r in rows:
        start = date.fromisoformat(r["StartDate"][:10])
        end = date.fromisoformat(r["EndDate"][:10])
        for i in range((end - start).days + 1):
            d = start + timedelta(days=i)
            key = f"{d:%m-%d}"
            if key in r:
                out.append({"date": d.isoformat(), "typeId": r["TypeId"],
                            "rooms": r[key], "roomCount": r.get("NoOfRooms")})
    return out


# Section cache: persistent across worker restarts, with database-backed leases.
# All endpoints remain read-only towards the PMS.
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from ..infrastructure.paths import get_data_path

CACHE_TTL = 300
LEASE_SECONDS = 1800
SECTIONS = ("hotel", "segments", "roomTypes", "availability")


@contextmanager
def _cache_db():
    conn = sqlite3.connect(get_data_path("rms_forecast_cache.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS forecast_cache (
            key TEXT PRIMARY KEY, payload TEXT, fetched REAL, started REAL, error TEXT)""")
        with conn:
            yield conn
    finally:
        conn.close()


def fetch_section(start, days, section, client_factory=PMSApiClient):
    """Independent sections prevent a slow segment report blocking hotel totals."""
    client = client_factory().login()
    end = start + timedelta(days=days - 1)
    if section == "roomTypes":
        # The PMS temp table collides even across different requests/processes.
        import fcntl
        with open(get_data_path("rms_room_report.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows = _room_types([r for s in _starts(start, days, ROOM_CHUNK) for r in _post_room_types(client, s)])
    elif section == "availability":
        rows = [{"date": r["Date"][:10] if "Date" in r else r["TrxDate"][:10], "values": {
            k: v for k, v in r.items() if isinstance(v, (int, float)) and k not in ("HotelId", "ROW_ID")}}
            for r in client.get_available_room_inventory(start.isoformat(), days)]
    else:
        chunk = CHUNK if section == "hotel" else SEGMENT_CHUNK
        name = "ReportForecastOccupancy" if section == "hotel" else "ReportForecastOccupancyMarketSegment"
        # A single session stays on its owning thread; sections run concurrently.
        raw = [r for s in _starts(start, days, chunk)
               for r in _post(client, name, s, min(chunk, (end - s).days + 1))]
        rows = (_hotel if section == "hotel" else _segments)(raw)
    return sorted((r for r in rows if start.isoformat() <= r["date"] <= end.isoformat()), key=lambda r: r["date"])


def _refresh(key, start, days, section, lease):
    try:
        payload = json.dumps(fetch_section(start, days, section))
        with _cache_db() as conn:
            conn.execute("UPDATE forecast_cache SET payload=?, fetched=?, started=NULL, error=NULL WHERE key=? AND started=?",
                         (payload, time.time(), key, lease))
    except Exception:
        # Provider errors may contain internal response details. Keep the UI actionable and generic.
        import logging
        logging.getLogger(__name__).exception("RMS forecast section failed: %s", section)
        with _cache_db() as conn:
            conn.execute("UPDATE forecast_cache SET started=NULL, error=? WHERE key=? AND started=?",
                         ("PMS report unavailable. Retry refresh; the last successful result is retained.", key, lease))


def cached_forecast(start, days, force=False):
    from datetime import datetime, timezone
    now = time.time()
    result = {"start": start.isoformat(), "end": (start + timedelta(days=days - 1)).isoformat(), "sections": {}}
    jobs = []
    with _cache_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for section in SECTIONS:
            key = f"{start}:{days}:{section}"
            row = conn.execute("SELECT * FROM forecast_cache WHERE key=?", (key,)).fetchone()
            stale = not row or not row["fetched"] or now - row["fetched"] > CACHE_TTL
            running = bool(row and row["started"] and now - row["started"] < LEASE_SECONDS)
            # Failed sections retry only on explicit refresh, avoiding a polling retry storm.
            if not running and (force or (stale and not (row and row["error"]))):
                conn.execute("INSERT INTO forecast_cache(key, started) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET started=excluded.started, error=NULL", (key, now))
                jobs.append((key, start, days, section, now))
                running = True
            result[section] = json.loads(row["payload"]) if row and row["payload"] else []
            result["sections"][section] = {
                "loaded": bool(row and row["payload"] is not None), "refreshing": running, "stale": stale,
                "fetchedAt": datetime.fromtimestamp(row["fetched"], timezone.utc).isoformat() if row and row["fetched"] else None,
                "error": None if running else row["error"] if row else None,
            }
    for args in jobs:
        threading.Thread(target=_refresh, args=args, daemon=True, name="rms-forecast").start()
    return result
