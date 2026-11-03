"""Editable season calendar in season_calendar.db (runtime data dir).

Replaces the old hardcoded Jul-Aug/Christmas-New-Year season logic in
yield_engine.py with an operator-editable list of named date ranges, each
tagged with a tier (Peak / High / Normal). Entries are specific dated
ranges, not recurring annual rules - the operator adds next year's Nyepi,
Lebaran, Lunar New Year, Australian school holidays, events, etc. by hand,
the same way the migrated-in Jul-Aug/Christmas rows need yearly extension.

When two periods cover the same date, the higher tier wins (TIER_RANK).
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from ..infrastructure.paths import get_data_path

DB_FILE = "season_calendar.db"

VALID_TIERS = ('Peak', 'High', 'Shoulder', 'Normal')
TIER_RANK = {'Peak': 4, 'High': 3, 'Shoulder': 2, 'Normal': 1}
DEFAULT_TIER = 'Normal'

MAX_LABEL_LENGTH = 200
# One-time migration seed range: reproduces the old hardcoded behavior so
# existing pipeline output doesn't change until someone edits the calendar.
# Deliberately not seeded far into the future - beyond this, the operator
# adds next year's Jul-Aug/Christmas rows by hand, same as any other entry.
SEED_YEARS = range(2020, 2027)

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS season_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            tier TEXT NOT NULL
        )
    """)
    count = conn.execute("SELECT COUNT(*) FROM season_periods").fetchone()[0]
    if count == 0:
        _seed_defaults(conn)
    return conn


def _seed_defaults(conn):
    rows = []
    for year in SEED_YEARS:
        rows.append((f"Jul-Aug high season {year}", f"{year}-07-01", f"{year}-08-31", "High"))
        rows.append((f"Pre-Christmas high season {year}", f"{year}-12-23", f"{year}-12-26", "High"))
        rows.append((f"Year-end peak season {year}", f"{year}-12-27", f"{year + 1}-01-03", "Peak"))
    conn.executemany(
        "INSERT INTO season_periods (label, start_date, end_date, tier) VALUES (?, ?, ?, ?)", rows)


@contextmanager
def _db():
    conn = _connect()
    try:
        with conn:  # commits, or rolls back on error
            yield conn
    finally:
        conn.close()


def _period(row):
    return {"id": row["id"], "label": row["label"], "startDate": row["start_date"],
            "endDate": row["end_date"], "tier": row["tier"]}


def _parse_date(value, label):
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a date")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{label} must be a valid date (YYYY-MM-DD)")


def _clean_period(data):
    if not isinstance(data, dict):
        raise ValidationError("Period must be an object")
    label = data.get("label")
    if not isinstance(label, str):
        raise ValidationError("Label must be text")
    label = label.strip()
    if not label:
        raise ValidationError("Label is required")
    if len(label) > MAX_LABEL_LENGTH:
        raise ValidationError(f"Label can be at most {MAX_LABEL_LENGTH} characters")

    start = _parse_date(data.get("startDate"), "Start date")
    end = _parse_date(data.get("endDate"), "End date")
    if end < start:
        raise ValidationError("End date is before the start date")

    tier = data.get("tier")
    if tier not in VALID_TIERS:
        raise ValidationError(f"Tier must be one of {', '.join(VALID_TIERS)}")

    return {"label": label, "start_date": start.isoformat(), "end_date": end.isoformat(), "tier": tier}


def list_periods():
    with _lock, _db() as conn:
        rows = conn.execute("SELECT * FROM season_periods ORDER BY start_date").fetchall()
        return [_period(r) for r in rows]


def add_period(data):
    clean = _clean_period(data)
    with _lock, _db() as conn:
        cur = conn.execute(
            "INSERT INTO season_periods (label, start_date, end_date, tier) VALUES (?, ?, ?, ?)",
            (clean["label"], clean["start_date"], clean["end_date"], clean["tier"]))
        return _period(conn.execute("SELECT * FROM season_periods WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_period(period_id, data):
    """Returns the updated period, or None if it doesn't exist."""
    clean = _clean_period(data)
    with _lock, _db() as conn:
        cur = conn.execute(
            "UPDATE season_periods SET label = ?, start_date = ?, end_date = ?, tier = ? WHERE id = ?",
            (clean["label"], clean["start_date"], clean["end_date"], clean["tier"], period_id))
        if not cur.rowcount:
            return None
        return _period(conn.execute("SELECT * FROM season_periods WHERE id = ?", (period_id,)).fetchone())


def delete_period(period_id):
    with _lock, _db() as conn:
        return conn.execute("DELETE FROM season_periods WHERE id = ?", (period_id,)).rowcount > 0


def build_lookup():
    """Periods with start/end parsed to date objects, for repeated tier_for_date lookups."""
    periods = list_periods()
    for period in periods:
        period["_start"] = datetime.strptime(period["startDate"], "%Y-%m-%d").date()
        period["_end"] = datetime.strptime(period["endDate"], "%Y-%m-%d").date()
    return periods


def tier_for_date(date, periods):
    """Highest-tier period covering `date` (a date/Timestamp), else Normal."""
    day = date.date() if hasattr(date, "date") else date
    best_tier = DEFAULT_TIER
    best_rank = TIER_RANK[DEFAULT_TIER]
    for period in periods:
        if period["_start"] <= day <= period["_end"]:
            rank = TIER_RANK.get(period["tier"], 0)
            if rank > best_rank:
                best_tier = period["tier"]
                best_rank = rank
    return best_tier
