"""Recurring-run schedule for the Fast API Pipeline, editable from the UI.

The schedule (on/off, interval, live vs. preview, and optionally a run config
saved from the Fast API Pipeline page) is persisted to
fast_pipeline_schedule.json in the runtime data dir. The scheduler container
(scripts/trigger_fast_pipeline.py --managed) is only a clock: it calls
POST /api/fast-pipeline/schedule/tick every ~30s and the backend decides
whether a run is due and starts it - so credentials stay in the backend's own
env and settings changes take effect without restarting any container.

Preview mode is enforced here, not trusted to the stored config: allotment is
forced to a dry run and the BAR step (which has no dry-run mode) is turned off.
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone

from ..infrastructure.paths import get_data_path

SCHEDULE_FILE = "fast_pipeline_schedule.json"
DEFAULT_CONFIG_FILE = "scheduled_fast_pipeline_config.json"

MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60
# The scheduler ticks every 30s; three missed ticks means it isn't running.
SCHEDULER_OFFLINE_AFTER = timedelta(seconds=90)

# Run-config keys the UI may save for scheduled runs. Credentials, startDate,
# headless and resetCheckpoint are deliberately excluded - they're decided per
# run here, never stored.
CONFIG_KEYS = (
    "steps", "barRooms", "allotmentRoomTypes", "yieldConfig",
    "skipUnchanged", "barSkipUnchanged", "allotmentConcurrency", "companyId",
)

_DEFAULT_STATE = {
    "enabled": False,
    "intervalMinutes": 60,
    "live": False,
    "config": None,          # None -> use scheduled_fast_pipeline_config.json
    "configSavedAt": None,
    "nextRunAt": None,
    "lastRunAt": None,
    "updatedAt": None,
}

_lock = threading.Lock()
_scheduler_last_seen = None  # in-memory: only meaningful while this process runs


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _parse(value):
    return datetime.fromisoformat(value) if value else None


def _load():
    path = get_data_path(SCHEDULE_FILE)
    state = dict(_DEFAULT_STATE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            state.update(json.load(f))
    return state


def _save(state):
    path = get_data_path(SCHEDULE_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def load_default_config():
    with open(get_data_path(DEFAULT_CONFIG_FILE), encoding="utf-8") as f:
        config = json.load(f)
    return {k: config[k] for k in CONFIG_KEYS if k in config}


def scheduler_online():
    return _scheduler_last_seen is not None and _now() - _scheduler_last_seen < SCHEDULER_OFFLINE_AFTER


def get_state():
    with _lock:
        state = _load()
    try:
        default = load_default_config()
    except (OSError, ValueError):
        default = None
    return {
        **state,
        "configSource": "custom" if state["config"] else "default",
        "effectiveConfig": state["config"] or default,
        "defaultConfig": default,
        "schedulerOnline": scheduler_online(),
        "schedulerLastSeen": _iso(_scheduler_last_seen),
        "minIntervalMinutes": MIN_INTERVAL_MINUTES,
        "maxIntervalMinutes": MAX_INTERVAL_MINUTES,
    }


class ScheduleValidationError(ValueError):
    pass


def _validate_config(config):
    if not isinstance(config, dict):
        raise ScheduleValidationError("config must be an object or null")
    unknown = set(config) - set(CONFIG_KEYS)
    if unknown:
        raise ScheduleValidationError(f"Unsupported config field(s): {', '.join(sorted(unknown))}")
    if not isinstance(config.get("yieldConfig"), dict):
        raise ScheduleValidationError("config.yieldConfig is required")
    for key in ("barRooms", "allotmentRoomTypes"):
        if key in config and not isinstance(config[key], list):
            raise ScheduleValidationError(f"config.{key} must be a list")
    if "steps" in config and not isinstance(config["steps"], dict):
        raise ScheduleValidationError("config.steps must be an object")
    return {k: config[k] for k in CONFIG_KEYS if k in config}


def update_settings(data):
    """Apply a partial update from the UI. Enabling (or re-enabling) schedules
    the first run immediately; changing the interval re-anchors the next run
    on the last run rather than on now."""
    with _lock:
        state = _load()
        was_enabled = state["enabled"]

        if "intervalMinutes" in data:
            try:
                minutes = int(data["intervalMinutes"])
            except (TypeError, ValueError):
                raise ScheduleValidationError("intervalMinutes must be a whole number")
            if not MIN_INTERVAL_MINUTES <= minutes <= MAX_INTERVAL_MINUTES:
                raise ScheduleValidationError(
                    f"intervalMinutes must be between {MIN_INTERVAL_MINUTES} and {MAX_INTERVAL_MINUTES}")
            state["intervalMinutes"] = minutes
        if "live" in data:
            if not isinstance(data["live"], bool):
                raise ScheduleValidationError("live must be true or false")
            state["live"] = data["live"]
        if "config" in data:
            if data["config"] is None:
                state["config"] = None
                state["configSavedAt"] = None
            else:
                state["config"] = _validate_config(data["config"])
                state["configSavedAt"] = _iso(_now())
        if "enabled" in data:
            if not isinstance(data["enabled"], bool):
                raise ScheduleValidationError("enabled must be true or false")
            state["enabled"] = data["enabled"]

        now = _now()
        if not state["enabled"]:
            state["nextRunAt"] = None
        elif not was_enabled:
            state["nextRunAt"] = _iso(now)
        elif "intervalMinutes" in data:
            last = _parse(state["lastRunAt"])
            nxt = last + timedelta(minutes=state["intervalMinutes"]) if last else now
            state["nextRunAt"] = _iso(max(nxt, now))

        state["updatedAt"] = _iso(now)
        _save(state)
    return get_state()


def build_run_config(state, env=None):
    env = os.environ if env is None else env
    config = dict(state["config"] or load_default_config())
    config["steps"] = dict(config.get("steps") or {})
    live = bool(state["live"])
    config.update({
        "pmsUsername": env.get("PMS_USERNAME"),
        "pmsPassword": env.get("PMS_PASSWORD"),
        "dedgeUsername": env.get("DEDGE_USERNAME"),
        "dedgePassword": env.get("DEDGE_PASSWORD"),
        # Hotel-local date: the containers set TZ so this is Bali's today.
        "startDate": datetime.now().strftime("%Y-%m-%d"),
        "headless": None,
        "resetCheckpoint": False,
        "allotmentDryRun": not live,
        "trigger": "schedule",
        "scheduleMode": "live" if live else "preview",
    })
    config.setdefault("skipUnchanged", True)
    config.setdefault("barSkipUnchanged", True)
    if not live:
        # BAR has no dry-run mode - preview must not reach it at all.
        config["barRooms"] = []
        config["steps"]["bar"] = False
    return config


def claim_due_run(try_acquire):
    """Called on every scheduler tick. Returns (config, None) when a run is
    due and the pipeline lock was acquired - the caller must then start it -
    or (None, reason) otherwise. A due run that can't acquire the lock (e.g. a
    manual run is in progress) stays due and is retried on the next tick."""
    global _scheduler_last_seen
    with _lock:
        now = _now()
        _scheduler_last_seen = now
        state = _load()
        if not state["enabled"]:
            return None, "schedule disabled"
        next_run = _parse(state["nextRunAt"])
        if next_run is None:
            # Enabled with no next run recorded (e.g. hand-edited file): run now.
            next_run = now
        if now < next_run:
            return None, f"next run at {state['nextRunAt']}"
        # Build before acquiring: try_acquire() sets pipeline_active, which only
        # run_pipeline() clears - an exception between the two would wedge it.
        config = build_run_config(state)
        acquired, reason = try_acquire()
        if not acquired:
            return None, reason
        state["lastRunAt"] = _iso(now)
        state["nextRunAt"] = _iso(now + timedelta(minutes=state["intervalMinutes"]))
        _save(state)
        return config, None
