"""Stop sale persistence in stop_sale.db (runtime data dir):

- recipients      - who receives the email (name, email, company, segment)
- settings        - the rule (occupancy / per-room thresholds) and email text
- send_log        - every send, with each recipient's result
"""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from ..infrastructure.paths import get_data_path
from .rules import ROOM_TYPES

DB_FILE = "stop_sale.db"

DEFAULT_FROM_NAME = "The Anvaya Beach Resort Bali"
DEFAULT_SETTINGS = {
    "occupancyThreshold": 85,
    # Room type -> stop sale when remaining rooms <= this. None = not used.
    "roomThresholds": {room: None for room in ROOM_TYPES},
    # Room types never put in the stop sale email (unticked in Settings).
    "excludedRooms": [],
    # Sending speed: seconds between emails, and optionally a pause of
    # batchPauseMinutes after every batchSize emails (0 = no batches).
    "throttle": {"delaySeconds": 2, "batchSize": 0, "batchPauseMinutes": 0},
    "email": {
        "fromName": DEFAULT_FROM_NAME,
        "subject": f"Stop Sale - {DEFAULT_FROM_NAME}",
        "intro": ("Greetings from The Anvaya Beach Resort Bali.\n\n"
                  "Please apply a STOP SALE on all static rates for the room types and dates below, "
                  "effective immediately."),
        "closing": ("Kindly confirm once updated. Thank you for your continued support.\n\n"
                    "Warm regards,\nSales & Revenue Team\nThe Anvaya Beach Resort Bali"),
    },
}

MAX_TEXT = {"name": 120, "email": 254, "company": 160, "segment": 60}
# field -> (label, max); all whole numbers from 0.
THROTTLE_LIMITS = {
    "delaySeconds": ("Delay between emails", 300),
    "batchSize": ("Batch size", 1000),
    "batchPauseMinutes": ("Pause between batches", 180),
}
MAX_EMAIL_TEXT = {"fromName": 120, "subject": 200, "intro": 4000, "closing": 4000}
EMAIL_RE = re.compile(r"^[^@\s<>\",;]+@[^@\s<>\",;]+\.[^@\s<>\",;]+$")

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            company TEXT NOT NULL DEFAULT '',
            segment TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS send_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT NOT NULL,
            subject TEXT NOT NULL,
            ranges TEXT NOT NULL,
            results TEXT NOT NULL,
            sent_count INTEGER NOT NULL,
            failed_count INTEGER NOT NULL
        );
    """)
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        with conn:  # commits, or rolls back on error
            yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------- recipients

def _recipient(row):
    return {
        "id": row["id"], "name": row["name"], "email": row["email"],
        "company": row["company"], "segment": row["segment"],
        "active": bool(row["active"]), "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }


def _clean_recipient(data):
    clean = {}
    for field, limit in MAX_TEXT.items():
        value = data.get(field) or ""
        if not isinstance(value, str):
            raise ValidationError(f"{field.capitalize()} must be text")
        value = value.strip()
        if len(value) > limit:
            raise ValidationError(f"{field.capitalize()} can be at most {limit} characters")
        clean[field] = value
    if not clean["name"]:
        raise ValidationError("Name is required")
    if not EMAIL_RE.match(clean["email"]):
        raise ValidationError("Enter a valid email address")
    clean["active"] = 1 if data.get("active", True) else 0
    return clean


def list_recipients():
    with _lock, _db() as conn:
        rows = conn.execute("SELECT * FROM recipients ORDER BY company COLLATE NOCASE, name COLLATE NOCASE")
        return [_recipient(r) for r in rows]


def get_recipients(ids=None, active_only=True):
    recipients = list_recipients()
    if ids is not None:
        wanted = set(ids)
        recipients = [r for r in recipients if r["id"] in wanted]
    return [r for r in recipients if r["active"]] if active_only else recipients


def add_recipient(data):
    clean = _clean_recipient(data)
    now = _now()
    try:
        with _lock, _db() as conn:
            cur = conn.execute(
                "INSERT INTO recipients (name, email, company, segment, active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (clean["name"], clean["email"], clean["company"], clean["segment"], clean["active"], now, now))
            return _recipient(conn.execute("SELECT * FROM recipients WHERE id = ?", (cur.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        raise ValidationError(f"{clean['email']} is already a recipient")


def update_recipient(recipient_id, data):
    """Returns the updated recipient, or None if it doesn't exist."""
    clean = _clean_recipient(data)
    try:
        with _lock, _db() as conn:
            cur = conn.execute(
                "UPDATE recipients SET name = ?, email = ?, company = ?, segment = ?, active = ?, updated_at = ? "
                "WHERE id = ?",
                (clean["name"], clean["email"], clean["company"], clean["segment"], clean["active"], _now(),
                 recipient_id))
            if not cur.rowcount:
                return None
            return _recipient(conn.execute("SELECT * FROM recipients WHERE id = ?", (recipient_id,)).fetchone())
    except sqlite3.IntegrityError:
        raise ValidationError(f"{clean['email']} is already a recipient")


def delete_recipient(recipient_id):
    with _lock, _db() as conn:
        return conn.execute("DELETE FROM recipients WHERE id = ?", (recipient_id,)).rowcount > 0


# ------------------------------------------------------------------ settings

def get_settings():
    with _lock, _db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'settings'").fetchone()
    stored = json.loads(row["value"]) if row else {}
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if "occupancyThreshold" in stored:
        settings["occupancyThreshold"] = stored["occupancyThreshold"]
    for room in ROOM_TYPES:
        if room in (stored.get("roomThresholds") or {}):
            settings["roomThresholds"][room] = stored["roomThresholds"][room]
    settings["excludedRooms"] = [room for room in ROOM_TYPES if room in (stored.get("excludedRooms") or ())]
    settings["email"].update({k: v for k, v in (stored.get("email") or {}).items() if k in MAX_EMAIL_TEXT})
    settings["throttle"].update({k: v for k, v in (stored.get("throttle") or {}).items() if k in THROTTLE_LIMITS})
    return settings


def _clean_threshold(value, label, low, high):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a number")
    if number != int(number) or not low <= number <= high:
        raise ValidationError(f"{label} must be a whole number from {low} to {high}")
    return int(number)


def save_settings(data):
    if not isinstance(data, dict):
        raise ValidationError("Settings must be an object")
    occupancy = _clean_threshold(data.get("occupancyThreshold"), "Occupancy threshold", 1, 200)
    raw_rooms = data.get("roomThresholds") or {}
    if not isinstance(raw_rooms, dict) or any(room not in ROOM_TYPES for room in raw_rooms):
        raise ValidationError("Unknown room type in room thresholds")
    rooms = {room: _clean_threshold(raw_rooms.get(room), f"{room} threshold", 0, 500) for room in ROOM_TYPES}

    raw_email = data.get("email") or {}
    email = {}
    for field, limit in MAX_EMAIL_TEXT.items():
        value = raw_email.get(field, DEFAULT_SETTINGS["email"][field])
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise ValidationError(f"Email {field} must be text of at most {limit} characters")
        email[field] = value.strip()
    if not email["fromName"] or not email["subject"]:
        raise ValidationError("Sender name and subject are required")
    if any(c in email["fromName"] + email["subject"] for c in "\r\n"):
        raise ValidationError("Sender name and subject must be a single line")

    raw_throttle = data.get("throttle") or {}
    throttle = {}
    for field, (label, high) in THROTTLE_LIMITS.items():
        value = _clean_threshold(raw_throttle.get(field, DEFAULT_SETTINGS["throttle"][field]), label, 0, high)
        throttle[field] = value or 0
    if throttle["batchSize"] and not throttle["batchPauseMinutes"]:
        raise ValidationError("Set how many minutes to pause between batches, or set batch size to 0")

    excluded = data.get("excludedRooms") or []
    if not isinstance(excluded, list) or any(room not in ROOM_TYPES for room in excluded):
        raise ValidationError("Unknown room type in excluded rooms")
    if len(set(excluded)) == len(ROOM_TYPES):
        raise ValidationError("Tick at least one room type")
    excluded = [room for room in ROOM_TYPES if room in excluded]

    settings = {"occupancyThreshold": occupancy, "roomThresholds": rooms, "excludedRooms": excluded,
                "throttle": throttle, "email": email}
    with _lock, _db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('settings', ?)", (json.dumps(settings),))
    return settings


# ------------------------------------------------------------------- history

def log_send(subject, ranges, results):
    sent = sum(1 for r in results if r["ok"])
    with _lock, _db() as conn:
        cur = conn.execute(
            "INSERT INTO send_log (sent_at, subject, ranges, results, sent_count, failed_count) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), subject, json.dumps(ranges), json.dumps(results), sent, len(results) - sent))
        return cur.lastrowid


def list_history(limit=50):
    with _lock, _db() as conn:
        rows = conn.execute("SELECT * FROM send_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{
        "id": r["id"], "sentAt": r["sent_at"], "subject": r["subject"],
        "ranges": json.loads(r["ranges"]), "results": json.loads(r["results"]),
        "sentCount": r["sent_count"], "failedCount": r["failed_count"],
    } for r in rows]
