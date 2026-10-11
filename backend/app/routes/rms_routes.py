"""Simple RMS (phase 1): live PMS forecast and pace from booking_events.db.
Read-only towards the PMS - the only writes are to the local booking cache."""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from ..integrations.pms.api_client import PMSApiError
from ..integrations.pms.fast_allotment_updater import LABEL_BY_CHECKBOX_VALUE
from ..revenue import booking_events, rms_forecast

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
        start = _date_arg("start", date.today())
        days = int(request.args.get("days", 14))
    except ValueError:
        return _error("start must be YYYY-MM-DD and days a number", 400)
    try:
        result = rms_forecast.fetch_forecast(start, days)
    except PMSApiError as exc:
        return _error(str(exc), 502)
    return jsonify({"status": "success", **result})


@bp.route('/api/rms/pace', methods=['GET'])
def pace():
    try:
        start = _date_arg("start", date.today())
        end = _date_arg("end", start + timedelta(days=29))
        pickup_days = int(request.args.get("pickupDays", 7))
    except ValueError:
        return _error("start/end must be YYYY-MM-DD and pickupDays a number", 400)
    if end < start or (end - start).days >= MAX_PACE_DAYS:
        return _error(f"Pick an end date on or after the start, at most {MAX_PACE_DAYS} days", 400)
    rows = booking_events.pace_table(start.isoformat(), end.isoformat(),
                                     room_type=request.args.get("roomType") or None,
                                     market_id=request.args.get("marketId") or None,
                                     pickup_days=max(1, min(pickup_days, 90)))
    return jsonify({"status": "success", "rows": rows, "sync": booking_events.status()})


@bp.route('/api/rms/pace/curve', methods=['GET'])
def pace_curve():
    try:
        stay_date = _date_arg("date", None)
        max_lead = int(request.args.get("maxLead", 120))
    except ValueError:
        return _error("date must be YYYY-MM-DD and maxLead a number", 400)
    if stay_date is None:
        return _error("date is required", 400)
    curve = booking_events.pace_curve(stay_date.isoformat(), max_lead=max(7, min(max_lead, 365)),
                                      room_type=request.args.get("roomType") or None,
                                      market_id=request.args.get("marketId") or None)
    return jsonify({"status": "success", **curve})


@bp.route('/api/rms/sync', methods=['GET'])
def sync_status():
    return jsonify({"status": "success", **booking_events.status()})


@bp.route('/api/rms/sync', methods=['POST'])
def start_sync():
    data = request.get_json(silent=True) or {}
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
