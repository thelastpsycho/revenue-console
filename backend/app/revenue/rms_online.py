"""Online-segment (market_id 8) reporting: per-company source mix and the
Santika Online (direct) vs named-OTA channel split, grouped from the same
observed booking cache as rms_reports.py.

Channel classification (booking_events.channel_bucket) is a best-effort
substring match on the booking's CompanyName (captured from
ReportReservationStatus since the company_id/company columns were added to
bookings). Only "Santika Online Reservation", "Booking.com" and "Agoda.com"
are confirmed exact strings from a live PMS probe (docs/pms-data-api.md);
the other named OTAs are matched by a lenient marker, validated against
real company names seen in bookings.company after backfilling.
"""
from collections import defaultdict
from datetime import date, timedelta

from . import booking_events as be
from . import rms_reports as rr
from .booking_events import BUCKET_ORDER, channel_bucket
from .rms_workspace import get_settings, net_rate

ONLINE_MARKET_ID = 8


def _blank():
    return {"rooms": 0, "idrRooms": 0, "revenue": 0, "netRevenue": 0}


def _add_night(bucket, r, day, rules):
    bucket["rooms"] += 1
    if r["currency"] == "IDR":
        bucket["idrRooms"] += 1
        bucket["revenue"] += r["room_rate"]
        bucket["netRevenue"] += net_rate(r["room_rate"], r.get("rate_type"), day, rules, r.get("rate_id"))


def source_breakdown(start, end, market_id=ONLINE_MARKET_ID, room_type=None, channels=None):
    """Current on-the-books nights/revenue by booking company within a
    market segment (default Online) - "where is this demand coming from"."""
    today = be._today().isoformat()
    states = be.state_as_of(be.version_history([(start, end)]), today)
    rules = get_settings()["revenueRules"]
    totals = defaultdict(_blank)
    names = {}
    for r in states.values():
        if not be._active(r, today) or not be._matches(r, room_type, market_id, channels):
            continue
        nights = rr._nights(r, start, end)
        if not nights:
            continue
        key = str(r["company_id"]) if r.get("company_id") is not None else (r.get("company") or "unassigned")
        names[key] = r.get("company") or "Unassigned"
        bucket = totals[key]
        for day in nights:
            _add_night(bucket, r, day, rules)
    rows = [{"id": key, "name": names[key], **metrics} for key, metrics in totals.items()]
    rows.sort(key=lambda row: -row["rooms"])
    grand = _blank()
    for row in rows:
        for k in grand:
            grand[k] += row[k]
    return {"start": start, "end": end, "companies": rows, "total": grand}


def direct_share(start, end, market_id=ONLINE_MARKET_ID, room_type=None, channels=None):
    """Daily Santika Online (direct) vs named-OTA vs other channel split,
    plus period totals and the direct-channel share of known-channel rooms."""
    today = be._today().isoformat()
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    history = be.version_history([(start, end)])
    rules = get_settings()["revenueRules"]
    states = be.state_as_of(history, today)
    with be._db_lock, be._db() as conn:
        coverage = be._get_meta(conn, "backfillFrom")
    quality = be._quality(today, coverage, history)

    daily = defaultdict(lambda: defaultdict(_blank))
    totals = defaultdict(_blank)
    for r in states.values():
        if not be._active(r, today) or not be._matches(r, room_type, market_id, channels):
            continue
        nights = rr._nights(r, start, end)
        if not nights:
            continue
        bucket_id, _ = channel_bucket(r.get("company"))
        for day in nights:
            _add_night(daily[day][bucket_id], r, day, rules)
            _add_night(totals[bucket_id], r, day, rules)

    series = [{"date": (s + timedelta(days=i)).isoformat(),
               **{bid: dict(daily[(s + timedelta(days=i)).isoformat()].get(bid, _blank())) for bid, _ in BUCKET_ORDER}}
              for i in range((e - s).days + 1)]
    buckets = [{"id": bid, "name": label, **totals.get(bid, _blank())} for bid, label in BUCKET_ORDER]
    known_rooms = sum(b["rooms"] for b in buckets if b["id"] != "unassigned")
    direct_rooms = totals.get("direct", _blank())["rooms"]
    return {
        "start": start, "end": end, "quality": quality,
        "buckets": buckets, "series": series,
        "directSharePct": (direct_rooms / known_rooms * 100) if known_rooms else None,
    }
