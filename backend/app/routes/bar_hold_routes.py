"""BAR hold dates (integrations/dedge/bar_holds.py): dates every BAR update
leaves alone on D-EDGE until the hold is removed."""

import os

from flask import Blueprint, jsonify, request

from ..infrastructure.paths import get_data_path
from ..integrations.dedge import bar_holds

bp = Blueprint('bar_holds', __name__)


def _checkpoint_pending():
    # An unfinished BAR run resumes only with an identical plan, and changing
    # holds changes the plan - the UI warns about this.
    return os.path.exists(get_data_path("bar_apply_checkpoint.json"))


@bp.route('/api/bar/holds', methods=['GET'])
def list_bar_holds():
    return jsonify({"status": "success", "holds": bar_holds.list_holds(),
                    "checkpointPending": _checkpoint_pending()})


@bp.route('/api/bar/holds', methods=['POST'])
def add_bar_hold():
    data = request.get_json(silent=True) or {}
    try:
        hold = bar_holds.add_hold(data)
    except bar_holds.HoldValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except (OSError, ValueError) as exc:
        return jsonify({"status": "error", "message": f"Could not save the hold: {exc}"}), 500
    return jsonify({"status": "success", "hold": hold})


@bp.route('/api/bar/holds/<hold_id>', methods=['DELETE'])
def remove_bar_hold(hold_id):
    try:
        removed = bar_holds.remove_hold(hold_id)
    except (OSError, ValueError) as exc:
        return jsonify({"status": "error", "message": f"Could not remove the hold: {exc}"}), 500
    if not removed:
        return jsonify({"status": "error", "message": "Hold not found"}), 404
    return jsonify({"status": "success"})
