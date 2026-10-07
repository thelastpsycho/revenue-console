"""D-EDGE device verification from the UI: see whether a running session is
waiting for the emailed "new device" code, hand it the code (or ask D-EDGE
to resend the email), and run an on-demand session check."""

import threading

from flask import Blueprint, jsonify, request

from ..integrations.dedge import device_auth
from ..integrations.dedge.inventory_scraper import verify_session
from ..pipeline import fast_runner

bp = Blueprint('dedge_auth', __name__)


@bp.route('/api/dedge/auth/status', methods=['GET'])
def dedge_auth_status():
    return jsonify({"status": "success", "auth": device_auth.get_status(),
                    "pipelineActive": fast_runner.pipeline_active})


@bp.route('/api/dedge/auth/code', methods=['POST'])
def dedge_auth_code():
    data = request.get_json(silent=True) or {}
    ok, message = device_auth.submit_code(data.get("code"))
    return jsonify({"status": "success" if ok else "error", "message": message}), (200 if ok else 400)


@bp.route('/api/dedge/auth/resend', methods=['POST'])
def dedge_auth_resend():
    ok, message = device_auth.request_resend()
    return jsonify({"status": "success" if ok else "error", "message": message}), (200 if ok else 400)


def _run_check():
    try:
        verify_session()
        device_auth.finish_check(True, "D-EDGE session is valid")
    except Exception as exc:
        device_auth.finish_check(False, f"D-EDGE session check failed: {exc}")
    finally:
        fast_runner.release()


@bp.route('/api/dedge/auth/check', methods=['POST'])
def dedge_auth_check():
    """Opens D-EDGE in the shared Chrome profile, so it takes the pipeline lock
    (a run and a check can't drive the same profile at once)."""
    if not device_auth.try_start_check():
        return jsonify({"status": "error", "message": "A session check is already running"}), 409
    acquired, reason = fast_runner.try_acquire()
    if not acquired:
        device_auth.finish_check(False, reason)
        return jsonify({"status": "error", "message": reason}), 409
    threading.Thread(target=_run_check, daemon=True).start()
    return jsonify({"status": "success", "message": "Checking the D-EDGE session..."})
