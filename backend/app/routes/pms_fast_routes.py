"""Test-only endpoints for the Selenium-free PMS API client
(integrations/pms/api_client.py and friends). Kept separate from
routes/main.py so the existing scrape/allotment endpoints and their
Selenium-based implementations are never touched by this work.
"""

from flask import Blueprint, jsonify, request

from ..accounts.permissions import require_permission
from ..integrations.pms.fast_allotment_updater import (
    ROOM_TYPES,
    FULL_ROOM_TYPE_CONFIG,
    LABEL_BY_CHECKBOX_VALUE,
    push_allotment,
    build_full_plan,
    push_jobs_concurrent,
)
from ..integrations.pms.fast_inventory_scraper import fetch_room_inventory
from ..integrations.pms.api_client import PMSApiError

bp = Blueprint('pms_fast', __name__)


@bp.route('/api/pms-fast/room-types', methods=['GET'])
def room_types():
    return jsonify({"status": "success", "roomTypes": ROOM_TYPES})


@bp.route('/api/pms-fast/room-type-config', methods=['GET'])
def room_type_config():
    return jsonify({
        "status": "success",
        "roomTypes": [
            {"key": key, "label": config["label"], "checkboxValue": config["checkbox_value"]}
            for key, config in FULL_ROOM_TYPE_CONFIG.items()
        ],
    })


@bp.route('/api/pms-fast/inventory', methods=['POST'])
def inventory():
    data = request.get_json(silent=True) or {}
    start_date = data.get('startDate')
    days = data.get('days', 14)
    if not start_date:
        return jsonify({"status": "error", "message": "startDate is required"}), 400
    try:
        days = int(days)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "days must be a number"}), 400

    try:
        rows, elapsed = fetch_room_inventory(
            start_date, days,
            username=data.get('username') or None,
            password=data.get('password') or None,
        )
    except PMSApiError as e:
        return jsonify({"status": "error", "message": str(e)}), 502

    return jsonify({
        "status": "success",
        "elapsedSeconds": round(elapsed, 3),
        "count": len(rows),
        "rows": rows,
    })


@bp.route('/api/pms-fast/allotment', methods=['POST'])
@require_permission('push_pms_allotment')
def allotment():
    data = request.get_json(silent=True) or {}
    required = ['roomType', 'startDate', 'endDate', 'numberOfRooms']
    missing = [f for f in required if not data.get(f) and data.get(f) != 0]
    if missing:
        return jsonify({"status": "error", "message": f"Missing required field(s): {', '.join(missing)}"}), 400

    try:
        number_of_rooms = int(data.get('numberOfRooms'))
        company_id = int(data.get('companyId', 1001))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "numberOfRooms/companyId must be numbers"}), 400

    dry_run = data.get('dryRun', True) is not False
    room_label = LABEL_BY_CHECKBOX_VALUE.get(data['roomType'], data['roomType'])
    default_remark = f"Updated from yield matrix - {room_label} Online Inventory {number_of_rooms}"

    try:
        result = push_allotment(
            company_id=company_id,
            room_type=data['roomType'],
            start_date=data['startDate'],
            end_date=data['endDate'],
            number_of_rooms=number_of_rooms,
            remark=data.get('remark') or default_remark,
            dry_run=dry_run,
            username=data.get('username') or None,
            password=data.get('password') or None,
        )
    except PMSApiError as e:
        return jsonify({"status": "error", "message": str(e)}), 502

    return jsonify({"status": "success", **result})


def _parse_bulk_params(data):
    room_types = data.get('roomTypes') or None
    if room_types is not None and not isinstance(room_types, list):
        raise ValueError("roomTypes must be a list of room-type keys")
    max_dates = data.get('maxDates')
    if max_dates is not None:
        max_dates = int(max_dates)
    skip_unchanged = data.get('skipUnchanged', True) is not False
    return room_types, max_dates, skip_unchanged


@bp.route('/api/pms-fast/allotment-bulk/plan', methods=['POST'])
def allotment_bulk_plan():
    data = request.get_json(silent=True) or {}
    try:
        room_types_filter, max_dates, skip_unchanged = _parse_bulk_params(data)
    except (TypeError, ValueError) as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    try:
        plan = build_full_plan(room_types=room_types_filter, max_dates=max_dates, skip_unchanged=skip_unchanged)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({
        "status": "success",
        "totalJobs": len(plan['jobs']),
        "skippedRanges": plan['skipped_ranges'],
        "byRoomType": plan['by_room_type'],
        "jobs": plan['jobs'][:300],
        "jobsTruncated": len(plan['jobs']) > 300,
    })


@bp.route('/api/pms-fast/allotment-bulk/push', methods=['POST'])
@require_permission('push_pms_allotment')
def allotment_bulk_push():
    data = request.get_json(silent=True) or {}
    try:
        room_types_filter, max_dates, skip_unchanged = _parse_bulk_params(data)
    except (TypeError, ValueError) as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    dry_run = data.get('dryRun', True) is not False
    try:
        company_id = int(data.get('companyId', 1001))
        max_concurrency = int(data.get('maxConcurrency', 4))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "companyId/maxConcurrency must be numbers"}), 400

    try:
        plan = build_full_plan(room_types=room_types_filter, max_dates=max_dates, skip_unchanged=skip_unchanged)
        result = push_jobs_concurrent(
            plan['jobs'],
            company_id=company_id,
            dry_run=dry_run,
            max_workers=max_concurrency,
            username=data.get('username') or None,
            password=data.get('password') or None,
        )
    except PMSApiError as e:
        return jsonify({"status": "error", "message": str(e)}), 502
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    result['results'] = result['results'][:300]
    return jsonify({
        "status": "success",
        "skippedRanges": plan['skipped_ranges'],
        "byRoomType": plan['by_room_type'],
        **result,
    })
