"""Editable allotment rules (app/revenue/allotment_rules): release rules per
room type, the Deluxe-Suite-borrows-from-Premiere-Suite trigger, and suite
upgrade routing/buffers/holds, consumed by yield_engine.py and
upgrade_reserves.py instead of hardcoded per-room dispatch."""

from flask import Blueprint, jsonify, request

from ..accounts.permissions import require_permission
from ..revenue import allotment_rules

bp = Blueprint('allotment_rules', __name__)


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


@bp.route('/api/allotment-rules/settings', methods=['GET'])
def get_settings():
    settings = allotment_rules.get_settings()
    return jsonify({
        "status": "success", "settings": settings,
        "roomTypes": sorted(allotment_rules.ROOM_TYPES),
        # Unspecified rooms keep the hotel tier order - resolve that here so
        # the UI can show what's actually in effect, not just the (possibly
        # empty) stored override.
        "effectiveRoutes": allotment_rules.effective_suite_routing(settings["suiteRouting"]),
    })


@bp.route('/api/allotment-rules/settings', methods=['PUT'])
@require_permission('manage_allotment_rules')
def save_settings():
    try:
        settings = allotment_rules.save_settings(request.get_json(silent=True) or {})
    except allotment_rules.ValidationError as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "settings": settings})
