"""BAR hold dates: date ranges that BAR updates must leave alone on D-EDGE,
e.g. while a rate is being managed by hand for an event.

Holds are persisted to bar_hold_dates.json in the runtime data dir and
applied inside update_bar(), so every way of pushing BAR (scheduled and
manual Fast API Pipeline runs, the Selenium pipeline, the standalone BAR
action) respects them. Held dates are simply left out of the plan - they are
not recorded as applied - so once a hold is removed the next run compares
them against the last pushed level as usual.

Holds whose end date has passed (hotel-local date) are dropped automatically.
"""

import json
import os
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from ...infrastructure.paths import get_data_path

HOLDS_FILE = "bar_hold_dates.json"
# Must match bar_updater.ROOM_CONFIG's keys (asserted in the tests).
ROOMS = ("deluxe", "premiere")
MAX_HOLD_DAYS = 400
MAX_NOTE_LENGTH = 200

_lock = threading.Lock()


class HoldValidationError(ValueError):
    pass


def _today():
    return date.today()


def _parse_day(value, field):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HoldValidationError(f"{field} must be a date (YYYY-MM-DD)")


def _load():
    path = get_data_path(HOLDS_FILE)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        holds = json.load(f)
    return holds if isinstance(holds, list) else []


def _save(holds):
    path = get_data_path(HOLDS_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(holds, f, indent=2)
    os.replace(tmp, path)


def _active(holds, today):
    return [h for h in holds if _parse_day(h["end"], "end") >= today]


def list_holds(today=None):
    today = today or _today()
    with _lock:
        return sorted(_active(_load(), today), key=lambda h: (h["start"], h["end"]))


def add_hold(data, today=None):
    today = today or _today()
    start = _parse_day(data.get("start"), "Start date")
    end = _parse_day(data.get("end") or data.get("start"), "End date")
    if end < start:
        raise HoldValidationError("End date is before the start date")
    if end < today:
        raise HoldValidationError("Those dates are already in the past")
    if (end - start).days + 1 > MAX_HOLD_DAYS:
        raise HoldValidationError(f"A hold can cover at most {MAX_HOLD_DAYS} days")

    rooms = data.get("rooms", list(ROOMS))
    if (not isinstance(rooms, list) or not rooms
            or any(r not in ROOMS for r in rooms)):
        raise HoldValidationError(f"Rooms must be a non-empty list of {', '.join(ROOMS)}")
    note = data.get("note") or ""
    if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH:
        raise HoldValidationError(f"Note must be text of at most {MAX_NOTE_LENGTH} characters")

    hold = {
        "id": uuid.uuid4().hex[:12],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rooms": [r for r in ROOMS if r in rooms],
        "note": note.strip(),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _lock:
        holds = _active(_load(), today)
        holds.append(hold)
        _save(holds)
    return hold


def remove_hold(hold_id, today=None):
    """Returns True if a hold was removed."""
    today = today or _today()
    with _lock:
        holds = _load()
        kept = [h for h in holds if h.get("id") != hold_id]
        if len(kept) == len(holds):
            return False
        _save(_active(kept, today))
        return True


def held_dates_by_room(rooms, today=None):
    """{room: {"YYYY-MM-DD", ...}} of dates update_bar must not touch."""
    held = {room: set() for room in rooms}
    for hold in list_holds(today):
        day = _parse_day(hold["start"], "start")
        end = _parse_day(hold["end"], "end")
        while day <= end:
            for room in hold["rooms"]:
                if room in held:
                    held[room].add(day.isoformat())
            day += timedelta(days=1)
    return held
