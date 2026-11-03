"""Editable release-rule and suite-routing settings in allotment_rules.db
(runtime data dir).

Replaces the hardcoded per-room-type dispatch in yield_engine.py
(get_online_allotment/allot_minus_one/allot_minus_one_except_one/
allot_as_remaining/allot_deluxe_suite) with a settings document: one release
rule per room type (how many rooms go online for how many remain), the
Deluxe-Suite-borrows-from-Premiere-Suite trigger, and the suite upgrade
routing/buffers/holds override already supported by upgrade_reserves.py's
load_policy (previously only loadable from a JSON file via an env var, with
no UI or persistence).
"""

import copy
import json
import sqlite3
import threading
from contextlib import contextmanager

from ..infrastructure.paths import get_data_path
from . import upgrade_reserves

DB_FILE = "allotment_rules.db"

# upgrade_reserves.ROOM_TIERS enumerates the same 13 room types as
# yield_engine.ROOM_CAPS (just in tier order) - reusing it here avoids a
# circular import with yield_engine, which already imports this module.
ROOM_TYPES = set(upgrade_reserves.ROOM_TIERS)
DELUXE_SUITE_ROOM = 'Deluxe Suite Room'

_BUCKET_ROWS = [
    {"min": 1, "max": 5, "release": 2},
    {"min": 6, "max": 10, "release": 5},
    {"min": 11, "max": 50, "release": 10},
    {"min": 51, "max": None, "release": 30},
]
_DELUXE_SUITE_ROWS = [
    {"min": 1, "max": 1, "release": 1},
    {"min": 2, "max": 3, "release": 2},
    {"min": 4, "max": 4, "release": 3},
    {"min": 5, "max": None, "release": 4},
]

DEFAULT_SETTINGS = {
    "releaseRules": {
        'Deluxe Room': {"kind": "tiered", "rows": copy.deepcopy(_BUCKET_ROWS)},
        'Premiere Room': {"kind": "tiered", "rows": copy.deepcopy(_BUCKET_ROWS)},
        'Deluxe Pool Access': {"kind": "tiered", "rows": copy.deepcopy(_BUCKET_ROWS)},
        'Premiere Room Lagoon Access': {"kind": "tiered", "rows": copy.deepcopy(_BUCKET_ROWS)},
        'Premiere Suite Room': {"kind": "tiered", "rows": copy.deepcopy(_BUCKET_ROWS)},
        'Deluxe Suite Room': {"kind": "tiered", "rows": copy.deepcopy(_DELUXE_SUITE_ROWS)},
        'Family Premiere Room': {"kind": "keepBack", "amount": 1, "exceptLast": False},
        'The Anvaya Suite Whirpool': {"kind": "keepBack", "amount": 1, "exceptLast": False},
        'The Anvaya Suite No Pool': {"kind": "keepBack", "amount": 1, "exceptLast": False},
        'Beach Front Private Suite Room': {"kind": "keepBack", "amount": 1, "exceptLast": True},
        'The Anvaya Suite With Pool': {"kind": "sellAsRemaining"},
        'The Anvaya Residence': {"kind": "sellAsRemaining"},
        'The Anvaya Villa': {"kind": "sellAsRemaining"},
    },
    "deluxeSuiteBorrow": {"fromRoomType": "Premiere Suite Room", "threshold": 3, "amount": 1},
    "suiteRouting": {},
}
assert set(DEFAULT_SETTINGS["releaseRules"]) == ROOM_TYPES

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        with conn:  # commits, or rolls back on error
            yield conn
    finally:
        conn.close()


# ----------------------------------------------------------------- settings

def effective_suite_routing(suite_routing):
    """suite_routing resolved against DEFAULT_ROUTES (unspecified rooms keep
    the hotel tier order), for display - the stored value itself stays a
    sparse override so narrowing-only re-validates correctly on save."""
    return upgrade_reserves.load_policy(ROOM_TYPES, suite_routing)['routes']


def get_settings():
    with _lock, _db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'settings'").fetchone()
    stored = json.loads(row["value"]) if row else {}
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["releaseRules"].update(
        {room: rule for room, rule in (stored.get("releaseRules") or {}).items() if room in ROOM_TYPES})
    if "deluxeSuiteBorrow" in stored:
        settings["deluxeSuiteBorrow"] = stored["deluxeSuiteBorrow"]
    if "suiteRouting" in stored:
        settings["suiteRouting"] = stored["suiteRouting"]
    return settings


def save_settings(data):
    clean = validate_settings(data)
    with _lock, _db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('settings', ?)", (json.dumps(clean),))
    return clean


# ---------------------------------------------------------------- validation

def _int(value, name, low=0):
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a whole number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a whole number") from None
    if not number.is_integer() or number < low:
        raise ValidationError(f"{name} must be a whole number of at least {low}")
    return int(number)


def _validate_tiered_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValidationError("A tiered rule needs at least one row")
    clean = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"min", "max", "release"}:
            raise ValidationError("Invalid tiered row")
        rmin = _int(row.get("min"), "Row min", low=1)
        raw_max = row.get("max")
        rmax = _int(raw_max, "Row max", low=rmin) if raw_max is not None else None
        release = _int(row.get("release"), "Row release", low=0)
        clean.append({"min": rmin, "max": rmax, "release": release})
    clean.sort(key=lambda r: r["min"])
    for row in clean[:-1]:
        if row["max"] is None:
            raise ValidationError("Only the highest tier may leave max unbounded")
    for a, b in zip(clean, clean[1:]):
        if a["max"] >= b["min"]:
            raise ValidationError("Tiered rows must not overlap")
    return clean


def _validate_release_rule(rule, room_type):
    if not isinstance(rule, dict):
        raise ValidationError(f"Release rule for {room_type} must be an object")
    kind = rule.get("kind")
    if kind == "tiered":
        return {"kind": "tiered", "rows": _validate_tiered_rows(rule.get("rows"))}
    if kind == "keepBack":
        amount = _int(rule.get("amount"), f"{room_type} keep-back amount")
        except_last = rule.get("exceptLast", False)
        if not isinstance(except_last, bool):
            raise ValidationError(f"{room_type} exceptLast must be true or false")
        return {"kind": "keepBack", "amount": amount, "exceptLast": except_last}
    if kind == "sellAsRemaining":
        return {"kind": "sellAsRemaining"}
    raise ValidationError(f"Unknown release rule kind for {room_type}: {kind!r}")


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValidationError("Settings must be an object")

    raw_rules = data.get("releaseRules")
    if not isinstance(raw_rules, dict) or set(raw_rules) != ROOM_TYPES:
        raise ValidationError("releaseRules must have exactly one entry per room type")
    release_rules = {room: _validate_release_rule(raw_rules[room], room) for room in ROOM_TYPES}

    raw_borrow = data.get("deluxeSuiteBorrow")
    if not isinstance(raw_borrow, dict):
        raise ValidationError("deluxeSuiteBorrow must be an object")
    from_room = raw_borrow.get("fromRoomType")
    if from_room not in ROOM_TYPES or from_room == DELUXE_SUITE_ROOM:
        raise ValidationError("deluxeSuiteBorrow.fromRoomType must be a room type other than Deluxe Suite Room")
    deluxe_suite_borrow = {
        "fromRoomType": from_room,
        "threshold": _int(raw_borrow.get("threshold"), "deluxeSuiteBorrow.threshold"),
        "amount": _int(raw_borrow.get("amount"), "deluxeSuiteBorrow.amount"),
    }

    suite_routing = data.get("suiteRouting")
    if not isinstance(suite_routing, dict):
        raise ValidationError("suiteRouting must be an object")
    try:
        upgrade_reserves.load_policy(ROOM_TYPES, suite_routing)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    return {"releaseRules": release_rules, "deluxeSuiteBorrow": deluxe_suite_borrow, "suiteRouting": suite_routing}


# ------------------------------------------------------------------ release

def compute_release(rule, remaining, room_cap):
    """How many rooms to open online, given how many physically remain."""
    kind = rule["kind"]
    if kind == "sellAsRemaining":
        return max(0, remaining)
    if kind == "keepBack":
        if remaining <= 0:
            return 0
        if rule.get("exceptLast") and remaining <= rule["amount"]:
            return remaining
        return max(0, remaining - rule["amount"])
    if kind == "tiered":
        if remaining <= 0:
            return 0
        for row in rule["rows"]:
            if row["min"] <= remaining and (row["max"] is None or remaining <= row["max"]):
                return max(0, min(row["release"], remaining, room_cap))
        return 0
    raise ValueError(f"Unknown release rule kind: {kind!r}")
