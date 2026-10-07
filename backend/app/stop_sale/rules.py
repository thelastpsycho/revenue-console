"""Stop sale rule, evaluated against combined_inventory.db.

A date stops sale for:
- every room type, when hotel occupancy is at or above the occupancy
  threshold (e.g. >= 85%), or
- a single room type, when its remaining rooms are at or below that room
  type's own threshold (room types without a threshold are never closed by
  this rule).

Only today and later are considered; the whole scraped range is checked.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..infrastructure.paths import get_data_path

COMBINED_DB = "combined_inventory.db"

# Hotel room types as they appear in combined_inventory, in display order
# (lowest category first) - the email lists room types in this order.
ROOM_TYPES = (
    "Deluxe Room",
    "Deluxe Pool Access",
    "Premiere Room",
    "Premiere Room Lagoon Access",
    "Family Premiere Room",
    "Deluxe Suite Room",
    "Premiere Suite Room",
    "Beach Front Private Suite Room",
    "The Anvaya Suite No Pool",
    "The Anvaya Suite Whirpool",
    "The Anvaya Suite With Pool",
    "The Anvaya Villa",
    "The Anvaya Residence",
)

ALL_ROOMS_LABEL = "All room types"


class InventoryUnavailable(RuntimeError):
    pass


def _today():
    return date.today()


def load_combined_rows():
    """[{"Date": "YYYY-MM-DD", "Occupancy": float, <room type>: int, ...}]"""
    path = get_data_path(COMBINED_DB)
    if not os.path.exists(path):
        raise InventoryUnavailable("Combined inventory has not been built yet - run the pipeline first")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM combined_inventory ORDER BY Date")]
    except sqlite3.Error as exc:
        raise InventoryUnavailable(f"Could not read combined inventory: {exc}")
    finally:
        conn.close()
    for row in rows:
        row["Date"] = str(row["Date"])[:10]
    return rows


def combined_updated_at():
    path = get_data_path(COMBINED_DB)
    if not os.path.exists(path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()


def _number(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate(rows, rule, today=None):
    """Dates that stop sale, in date order:
    [{"date", "occupancy", "hotelFull": bool, "allRooms": bool,
      "rooms": [{"room", "remaining", "threshold"}]}]

    Room types in rule["excludedRooms"] are left out entirely, even when the
    whole hotel closes. `hotelFull` = the occupancy rule fired; `allRooms` =
    it fired and no room type is excluded, so the email can say "All room
    types". `rooms` lists every included room type that closes on the date."""
    today = (today or _today()).isoformat()
    occupancy_threshold = _number(rule.get("occupancyThreshold"))
    thresholds = rule.get("roomThresholds") or {}
    excluded = set(rule.get("excludedRooms") or ())
    included = [room for room in ROOM_TYPES if room not in excluded]
    result = []
    for row in rows:
        day = row["Date"]
        if day < today:
            continue
        occupancy = _number(row.get("Occupancy"))
        hotel_full = (occupancy_threshold is not None and occupancy is not None
                      and occupancy >= occupancy_threshold)
        rooms = []
        for room in included:
            remaining = _number(row.get(room))
            threshold = _number(thresholds.get(room))
            if hotel_full or (threshold is not None and remaining is not None and remaining <= threshold):
                rooms.append({
                    "room": room,
                    "remaining": None if remaining is None else int(remaining),
                    "threshold": None if threshold is None else int(threshold),
                })
        if rooms:
            result.append({"date": day, "occupancy": occupancy, "hotelFull": hotel_full,
                           "allRooms": hotel_full and not excluded, "rooms": rooms})
    return result


def group_ranges(closures):
    """Merge consecutive dates closing the same room types into ranges, for
    the email: [{"start", "end", "allRooms", "rooms": [room names]}]."""
    ranges = []
    for item in closures:
        rooms = [r["room"] for r in item["rooms"]]
        all_rooms = item["allRooms"]
        last = ranges[-1] if ranges else None
        day = datetime.strptime(item["date"], "%Y-%m-%d").date()
        if (last and last["allRooms"] == all_rooms and last["rooms"] == rooms
                and datetime.strptime(last["end"], "%Y-%m-%d").date() + timedelta(days=1) == day):
            last["end"] = item["date"]
        else:
            ranges.append({"start": item["date"], "end": item["date"], "allRooms": all_rooms, "rooms": rooms})
    return ranges


def group_by_room(ranges):
    """Pivot date ranges to one entry per room type for the email:
    [{"room", "ranges": [{"start", "end"}]}]. Whole-hotel dates are listed
    once under "All room types" (first) and left out of each room type's
    own dates; room types follow ROOM_TYPES order and appear only if closed."""
    days = {ALL_ROOMS_LABEL: set(), **{room: set() for room in ROOM_TYPES}}
    for item in ranges:
        day = datetime.strptime(item["start"], "%Y-%m-%d").date()
        end = datetime.strptime(item["end"], "%Y-%m-%d").date()
        while day <= end:
            for room in ([ALL_ROOMS_LABEL] if item["allRooms"] else item["rooms"]):
                days[room].add(day)
            day += timedelta(days=1)
    result = []
    for room, closed in days.items():
        if room != ALL_ROOMS_LABEL:
            closed = closed - days[ALL_ROOMS_LABEL]
        merged = []
        for day in sorted(closed):
            if merged and merged[-1][1] + timedelta(days=1) == day:
                merged[-1][1] = day
            else:
                merged.append([day, day])
        if merged:
            result.append({"room": room, "ranges": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in merged]})
    return result


def format_range(start, end):
    """'Fri 9 Oct 2026' or 'Fri 9 Oct – Sun 11 Oct 2026'."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()

    def fmt(d, year):
        text = f"{d:%a} {d.day} {d:%b}"
        return f"{text} {d.year}" if year else text

    if s == e:
        return fmt(s, True)
    return f"{fmt(s, s.year != e.year)} – {fmt(e, True)}"
