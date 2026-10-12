"""Simple RMS (phase 1): live PMS forecast and pace from booking_events.db.
Read-only towards the PMS - the only writes are to the local booking cache."""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from ..integrations.pms.fast_allotment_updater import LABEL_BY_CHECKBOX_VALUE
from ..revenue import booking_events, rms_forecast, rms_workspace

bp = Blueprint('rms', __name__)

MAX_PACE_DAYS = 366


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


def _date_arg(name, default):
    value = request.args.get(name)
    if not value:
        return default
    return date.fromisoformat(value)


@bp.route('/api/rms/room-types', methods=['GET'])
def room_types():
    return jsonify({"status": "success", "labels": LABEL_BY_CHECKBOX_VALUE,
                    **booking_events.dimensions()})


@bp.route('/api/rms/forecast', methods=['GET'])
def forecast():
    try:
        start = _date_arg("start", booking_events._today())
        days = int(request.args.get("days", 14))
    except ValueError:
        return _error("start must be YYYY-MM-DD and days a number", 400)
    if not 1 <= days <= rms_forecast.MAX_DAYS:
        return _error("days must be between 1 and 90", 400)
    result = rms_forecast.cached_forecast(start, days, force=request.args.get("refresh") == "1")
    return jsonify({"status": "success", **result})


@bp.route('/api/rms/pace', methods=['GET'])
def pace():
    try:
        start = _date_arg("start", booking_events._today())
        end = _date_arg("end", start + timedelta(days=29))
        pickup_days = int(request.args.get("pickupDays", 7))
    except ValueError:
        return _error("start/end must be YYYY-MM-DD and pickupDays a number", 400)
    if end < start or (end - start).days >= MAX_PACE_DAYS:
        return _error(f"Pick an end date on or after the start, at most {MAX_PACE_DAYS} days", 400)
    try:
        options = _pace_options()
        rows = booking_events.pace_table(start.isoformat(), end.isoformat(),
                                         pickup_days=max(1, min(pickup_days, 90)), **options)
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "rows": rows, "sync": booking_events.status(),
                    "settings": rms_workspace.get_settings(),
                    "notes": rms_workspace.notes(start.isoformat(), end.isoformat()),
                    "bar": rms_workspace.bar_context(start.isoformat(), end.isoformat())})


@bp.route('/api/rms/pace/curve', methods=['GET'])
def pace_curve():
    try:
        stay_date = _date_arg("date", None)
        max_lead = int(request.args.get("maxLead", 120))
    except ValueError:
        return _error("date must be YYYY-MM-DD and maxLead a number", 400)
    if stay_date is None:
        return _error("date is required", 400)
    try:
        options = _pace_options()
        range_start = _date_arg("start", stay_date).isoformat()
        curve = booking_events.pace_curve(stay_date.isoformat(), max_lead=max(7, min(max_lead, 365)),
                                           range_start=range_start, **options)
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", **curve})


@bp.route('/api/rms/sync', methods=['GET'])
def sync_status():
    return jsonify({"status": "success", **booking_events.status()})


@bp.route('/api/rms/sync', methods=['POST'])
def start_sync():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _error("Request body must be an object", 400)
    kind = data.get("kind")
    if kind not in ("backfill", "daily", "weekly"):
        return _error("kind must be backfill, daily or weekly", 400)
    try:
        days = int(data.get("backfillDays", booking_events.DEFAULT_BACKFILL_DAYS))
    except (TypeError, ValueError):
        return _error("backfillDays must be a number", 400)
    if not 30 <= days <= booking_events.MAX_BACKFILL_DAYS:
        return _error(f"backfillDays must be between 30 and {booking_events.MAX_BACKFILL_DAYS}", 400)
    if not booking_events.start_sync(kind, days):
        return _error("A booking sync is already running", 409)
    return jsonify({"status": "success", **booking_events.status()}), 202


def _pace_options():
    market = request.args.get("marketId")
    if market:
        market = int(market)
    mode = request.args.get("comparison", "weekday")
    custom = request.args.get("comparisonStart") or None
    if mode not in ("weekday", "calendar", "custom"):
        raise ValueError("Unknown comparison mode")
    if mode == "custom":
        if not custom:
            raise ValueError("comparisonStart is required for custom comparisons")
        date.fromisoformat(custom)
    return {"room_type": request.args.get("roomType") or None, "market_id": market,
            "comparison": mode, "comparison_start": custom}


@bp.route('/api/rms/settings', methods=['GET', 'PUT'])
def settings():
    try:
        value = rms_workspace.save_settings(request.get_json(silent=True)) if request.method == 'PUT' else rms_workspace.get_settings()
    except (ValueError, TypeError, KeyError) as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "settings": value})


@bp.route('/api/rms/notes/<day>', methods=['PUT'])
def note(day):
    try:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("Request body must be an object")
        value = rms_workspace.save_note(day, body.get("text"))
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "note": value})
