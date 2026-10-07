"""Stop sale emails (app/stop_sale): preview which dates stop sale from
combined inventory, manage recipients and the rule, and send the email.

Sends always recompute the closures on the server from the current combined
inventory; the browser only says which dates are ticked."""

import smtplib
import threading
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from ..stop_sale import mailer, rules, store

bp = Blueprint('stop_sale', __name__)

_send_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


def _closures():
    return rules.evaluate(rules.load_combined_rows(), store.get_settings())


def _selected_ranges(dates):
    """Ranges for the ticked dates that still stop sale right now."""
    if not isinstance(dates, list) or not dates or not all(isinstance(d, str) for d in dates):
        raise store.ValidationError("Tick at least one date")
    wanted = set(dates)
    return rules.group_ranges([c for c in _closures() if c["date"] in wanted])


@bp.route('/api/stop-sale/preview', methods=['GET'])
def preview():
    try:
        closures = _closures()
    except rules.InventoryUnavailable as exc:
        return _error(str(exc), 404)
    return jsonify({"status": "success", "closures": closures, "updatedAt": rules.combined_updated_at()})


@bp.route('/api/stop-sale/settings', methods=['GET'])
def get_settings():
    return jsonify({"status": "success", "settings": store.get_settings(),
                    "roomTypes": list(rules.ROOM_TYPES), "smtp": mailer.public_smtp_status()})


@bp.route('/api/stop-sale/settings', methods=['PUT'])
def save_settings():
    try:
        settings = store.save_settings(request.get_json(silent=True))
    except store.ValidationError as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "settings": settings})


@bp.route('/api/stop-sale/recipients', methods=['GET'])
def list_recipients():
    return jsonify({"status": "success", "recipients": store.list_recipients()})


@bp.route('/api/stop-sale/recipients', methods=['POST'])
def add_recipient():
    try:
        recipient = store.add_recipient(request.get_json(silent=True) or {})
    except store.ValidationError as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "recipient": recipient})


@bp.route('/api/stop-sale/recipients/<int:recipient_id>', methods=['PUT'])
def update_recipient(recipient_id):
    try:
        recipient = store.update_recipient(recipient_id, request.get_json(silent=True) or {})
    except store.ValidationError as exc:
        return _error(str(exc), 400)
    if recipient is None:
        return _error("Recipient not found", 404)
    return jsonify({"status": "success", "recipient": recipient})


@bp.route('/api/stop-sale/recipients/<int:recipient_id>', methods=['DELETE'])
def delete_recipient(recipient_id):
    if not store.delete_recipient(recipient_id):
        return _error("Recipient not found", 404)
    return jsonify({"status": "success"})


@bp.route('/api/stop-sale/email-preview', methods=['POST'])
def email_preview():
    """The email exactly as the first active recipient would get it."""
    data = request.get_json(silent=True) or {}
    try:
        ranges = _selected_ranges(data.get("dates"))
    except store.ValidationError as exc:
        return _error(str(exc), 400)
    except rules.InventoryUnavailable as exc:
        return _error(str(exc), 404)
    if not ranges:
        return _error("None of the ticked dates stop sale any more - refresh the preview", 409)
    active = store.get_recipients()
    sample = active[0] if active else {"name": "Partner name", "email": "partner@example.com", "company": "Company"}
    from_email = mailer.smtp_config()["fromEmail"] or "reservations@example.com"
    msg = mailer.build_message(store.get_settings()["email"], ranges, sample, from_email)
    return jsonify({
        "status": "success", "ranges": ranges, "recipientCount": len(active),
        "subject": msg["Subject"], "from": msg["From"], "to": msg["To"],
        "html": msg.get_body(("html",)).get_content(),
    })


def _prepare(dates, recipients):
    """(ranges, None) when ready to send, else (None, error response)."""
    try:
        ranges = _selected_ranges(dates)
    except store.ValidationError as exc:
        return None, _error(str(exc), 400)
    except rules.InventoryUnavailable as exc:
        return None, _error(str(exc), 404)
    if not ranges:
        return None, _error("None of the ticked dates stop sale any more - refresh the preview", 409)
    if not recipients:
        return None, _error("There are no active recipients", 400)
    smtp = mailer.smtp_config()
    if not smtp["configured"]:
        return None, _error(f"Email is not set up yet: {'; '.join(smtp['problems'])}", 503)
    return ranges, None


# A full send (hundreds of individual emails) outlasts the ~100 s Cloudflare
# tunnel request timeout, so it runs in a background thread and the page
# polls /api/stop-sale/send-status for progress.
_job = {"running": False, "total": 0, "sent": 0, "failed": 0, "results": [],
        "error": None, "logId": None, "startedAt": None, "finishedAt": None,
        "pausedUntil": None, "stopped": False, "throttle": None}
_stop = threading.Event()


def _job_snapshot():
    with _send_lock:
        return {**_job, "results": list(_job["results"])}


def _run_send(email_settings, ranges, recipients, throttle):
    def on_result(result):
        with _send_lock:
            _job["results"].append(result)
            _job["sent" if result["ok"] else "failed"] += 1

    def wait(seconds):
        """Throttle wait; returns True when Stop was pressed."""
        with _send_lock:
            _job["pausedUntil"] = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")
        stopped = _stop.wait(seconds)
        with _send_lock:
            _job["pausedUntil"] = None
        return stopped

    error = None
    try:
        mailer.send_individually(email_settings, ranges, recipients, on_result=on_result,
                                 throttle=throttle, wait=wait)
    except (mailer.SmtpNotConfigured, smtplib.SMTPException, OSError) as exc:
        error = f"Could not send through the mail server: {exc}"
    results = _job_snapshot()["results"]
    log_id = store.log_send(email_settings["subject"], ranges, results) if results else None
    with _send_lock:
        _job.update(running=False, error=error, logId=log_id, finishedAt=_now(),
                    pausedUntil=None, stopped=_stop.is_set())


@bp.route('/api/stop-sale/send', methods=['POST'])
def send():
    data = request.get_json(silent=True) or {}
    recipients = store.get_recipients()
    ranges, failure = _prepare(data.get("dates"), recipients)
    if failure:
        return failure
    with _send_lock:
        if _job["running"]:
            return _error("A stop sale email is already being sent", 409)
        settings = store.get_settings()
        _stop.clear()
        _job.update(running=True, total=len(recipients), sent=0, failed=0, results=[],
                    error=None, logId=None, startedAt=_now(), finishedAt=None,
                    pausedUntil=None, stopped=False, throttle=settings["throttle"])
    threading.Thread(target=_run_send, args=(settings["email"], ranges, recipients, settings["throttle"]),
                     daemon=True, name="stop-sale-send").start()
    return jsonify({"status": "success", "job": _job_snapshot()}), 202


@bp.route('/api/stop-sale/send-status', methods=['GET'])
def send_status():
    return jsonify({"status": "success", "job": _job_snapshot()})


@bp.route('/api/stop-sale/send-stop', methods=['POST'])
def send_stop():
    """Stops a running send before its next email; emails already sent stay sent."""
    if not _job_snapshot()["running"]:
        return _error("No stop sale email is being sent", 409)
    _stop.set()
    return jsonify({"status": "success"})


@bp.route('/api/stop-sale/send-test', methods=['POST'])
def send_test():
    """Sends the email for the ticked dates to one address only (subject
    prefixed [TEST], not logged) - for checking SMTP and the layout."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not store.EMAIL_RE.match(email):
        return _error("Enter a valid email address for the test", 400)
    recipients = [{"id": None, "name": "Test", "email": email, "company": ""}]
    ranges, failure = _prepare(data.get("dates"), recipients)
    if failure:
        return failure
    if _job_snapshot()["running"]:
        return _error("A stop sale email is already being sent", 409)
    email_settings = store.get_settings()["email"]
    email_settings = {**email_settings, "subject": f"[TEST] {email_settings['subject']}"}
    try:
        results = mailer.send_individually(email_settings, ranges, recipients)
    except (mailer.SmtpNotConfigured, smtplib.SMTPException, OSError) as exc:
        return _error(f"Could not send through the mail server: {exc}", 502)
    if not results[0]["ok"]:
        return _error(f"The mail server refused the test: {results[0]['error']}", 502)
    return jsonify({"status": "success", "results": results})


@bp.route('/api/stop-sale/history', methods=['GET'])
def history():
    return jsonify({"status": "success", "history": store.list_history()})
