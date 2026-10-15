"""Simple RMS (phase 1): live PMS forecast and pace from booking_events.db.
Read-only towards the PMS - the only writes are to the local booking cache."""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request, g
import time

from ..integrations.pms.fast_allotment_updater import LABEL_BY_CHECKBOX_VALUE
from ..revenue import booking_events, rms_forecast, rms_online, rms_workspace

bp = Blueprint('rms', __name__)

@bp.before_request
def start_report_timer():
    g.report_started = time.perf_counter()


@bp.after_request
def report_timing(response):
    if hasattr(g, 'report_started'):
        from ..revenue.report_cache import record_timing
        elapsed = (time.perf_counter() - g.report_started) * 1000
        response.headers['Server-Timing'] = f'report;dur={elapsed:.2f}'
        response.headers['X-Report-Cache'] = getattr(g, 'report_cache', 'none')
        record_timing(request.url_rule.rule if request.url_rule else request.path, elapsed)
    return response


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
        return _error(f"days must be between 1 and {rms_forecast.MAX_DAYS}", 400)
    sections_arg = request.args.get("sections")
    if sections_arg:
        sections = tuple(s for s in sections_arg.split(",") if s)
        if not sections or any(s not in rms_forecast.SECTIONS for s in sections):
            return _error(f"sections must be a subset of {', '.join(rms_forecast.SECTIONS)}", 400)
    else:
        sections = rms_forecast.SECTIONS
    result = rms_forecast.cached_forecast(start, days, force=request.args.get("refresh") == "1", sections=sections)
    return jsonify({"status": "success", **result})


@bp.route('/api/rms/pace', methods=['GET'])
def pace():
    try:
        start = _date_arg("start", booking_events._today())
        end = _date_arg("end", start + timedelta(days=29))
        pickup_days = int(request.args.get("pickupDays", 7))
        # Pickup normally compares "today" against pickupDays earlier, but a
        # caller can pin the comparison's later end to any past date instead
        # (e.g. "last week"/"last month", not anchored to today).
        as_of = _date_arg("asOf", booking_events._today())
    except ValueError:
        return _error("start/end/asOf must be YYYY-MM-DD and pickupDays a number", 400)
    if end < start or (end - start).days >= MAX_PACE_DAYS:
        return _error(f"Pick an end date on or after the start, at most {MAX_PACE_DAYS} days", 400)
    try:
        options = _pace_options()
        rows = booking_events.pace_table(start.isoformat(), end.isoformat(), today=as_of,
                                         pickup_days=max(1, min(pickup_days, 90)), **options)
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "rows": rows, "sync": booking_events.status(),
                    "settings": rms_workspace.get_settings(),
                    "notes": rms_workspace.notes(start.isoformat(), end.isoformat()),
                    "bar": rms_workspace.bar_context(start.isoformat(), end.isoformat())})


@bp.route('/api/rms/pace/pickup-groups', methods=['GET'])
def pace_pickup_groups():
    from ..revenue.rms_reports import pickup_by_dimension
    try:
        start = _date_arg("start", booking_events._today())
        end = _date_arg("end", start + timedelta(days=29))
        pickup_days = int(request.args.get("pickupDays", 7))
        as_of = _date_arg("asOf", booking_events._today())
        limit = request.args.get("limit")
        limit = int(limit) if limit else None
    except ValueError:
        return _error("start/end/asOf must be YYYY-MM-DD, pickupDays/limit numbers", 400)
    dimension = request.args.get("dimension", "market")
    if dimension not in ("market", "company"):
        return _error("dimension must be market or company", 400)
    if end < start or (end - start).days >= MAX_PACE_DAYS:
        return _error(f"Pick an end date on or after the start, at most {MAX_PACE_DAYS} days", 400)
    try:
        options = _pace_options()
        rows = pickup_by_dimension(start.isoformat(), end.isoformat(), dimension, today=as_of,
                                   pickup_days=max(1, min(pickup_days, 90)), room_type=options["room_type"],
                                   market_id=options["market_id"], channels=options["channels"])
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    if limit:
        rows = rows[:limit]
    return jsonify({"status": "success", "rows": rows})


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


def _channels_arg():
    raw = request.args.get("channels")
    if not raw:
        return None
    values = [v for v in raw.split(",") if v]
    return values or None


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
            "comparison": mode, "comparison_start": custom, "channels": _channels_arg()}


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


@bp.route('/api/rms/reports', methods=['GET'])
def reports():
    from ..revenue.rms_reports import build_reports
    try:
        start = _date_arg('start', booking_events._today())
        end = _date_arg('end', start + timedelta(days=29))
        if end < start or (end - start).days >= MAX_PACE_DAYS:
            raise ValueError('Choose a valid range of at most 366 days')
        basis = request.args.get('dateBasis', 'stay')
        if basis not in ('stay', 'booking'):
            raise ValueError('dateBasis must be stay or booking')
        pickup = int(request.args.get('pickupDays', 7))
        if not 1 <= pickup <= 90:
            raise ValueError('pickupDays must be between 1 and 90')
        result = build_reports(start.isoformat(), end.isoformat(), pickup_days=pickup,
                               date_basis=basis, **_pace_options())
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({'status': 'success', **result})


@bp.route('/api/rms/pace/breakdown', methods=['GET'])
def pace_breakdown():
    from ..revenue.rms_reports import room_rate_breakdown
    try:
        start = _date_arg('start', booking_events._today())
        end = _date_arg('end', start + timedelta(days=29))
        if end < start or (end - start).days >= MAX_PACE_DAYS:
            raise ValueError('Choose a valid range of at most 366 days')
        market = request.args.get('marketId')
        if market:
            market = int(market)
        result = room_rate_breakdown(start.isoformat(), end.isoformat(),
                                     room_type=request.args.get('roomType') or None, market_id=market,
                                     channels=_channels_arg())
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({'status': 'success', **result})


def _online_range():
    start = _date_arg('start', booking_events._today())
    end = _date_arg('end', start + timedelta(days=29))
    if end < start or (end - start).days >= MAX_PACE_DAYS:
        raise ValueError('Choose a valid range of at most 366 days')
    market = request.args.get('marketId')
    market = int(market) if market else rms_online.ONLINE_MARKET_ID
    return start, end, market


@bp.route('/api/rms/online/source', methods=['GET'])
def online_source():
    try:
        start, end, market = _online_range()
        result = rms_online.source_breakdown(start.isoformat(), end.isoformat(), market_id=market,
                                             room_type=request.args.get('roomType') or None,
                                             channels=_channels_arg())
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({'status': 'success', **result})


@bp.route('/api/rms/online/direct-share', methods=['GET'])
def online_direct_share():
    try:
        start, end, market = _online_range()
        result = rms_online.direct_share(start.isoformat(), end.isoformat(), market_id=market,
                                         room_type=request.args.get('roomType') or None,
                                         channels=_channels_arg())
    except (ValueError, TypeError) as exc:
        return _error(str(exc), 400)
    return jsonify({'status': 'success', **result})


@bp.route('/api/rms/briefing', methods=['GET'])
def daily_briefing():
    from ..revenue.revenue_briefing import briefing
    return jsonify({'status': 'success', **briefing()})
