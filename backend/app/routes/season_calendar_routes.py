"""Editable season calendar (app/revenue/season_calendar): named date ranges
tagged with a tier (Peak/High/Normal), consumed by yield_engine.py instead
of the old hardcoded Jul-Aug/Christmas-New-Year rule."""

from flask import Blueprint, jsonify, request

from ..accounts.permissions import require_permission
from ..revenue import season_calendar

bp = Blueprint('season_calendar', __name__)


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


@bp.route('/api/season-calendar/periods', methods=['GET'])
def list_periods():
    return jsonify({"status": "success", "periods": season_calendar.list_periods(),
                    "tiers": list(season_calendar.VALID_TIERS)})


@bp.route('/api/season-calendar/periods', methods=['POST'])
@require_permission('manage_season_calendar')
def add_period():
    try:
        period = season_calendar.add_period(request.get_json(silent=True) or {})
    except season_calendar.ValidationError as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "period": period})


@bp.route('/api/season-calendar/periods/<int:period_id>', methods=['PUT'])
@require_permission('manage_season_calendar')
def update_period(period_id):
    try:
        period = season_calendar.update_period(period_id, request.get_json(silent=True) or {})
    except season_calendar.ValidationError as exc:
        return _error(str(exc), 400)
    if period is None:
        return _error("Period not found", 404)
    return jsonify({"status": "success", "period": period})


@bp.route('/api/season-calendar/periods/<int:period_id>', methods=['DELETE'])
@require_permission('manage_season_calendar')
def delete_period(period_id):
    if not season_calendar.delete_period(period_id):
        return _error("Period not found", 404)
    return jsonify({"status": "success"})
