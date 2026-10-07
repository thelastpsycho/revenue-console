"""Hand-off point for D-EDGE's emailed "new device" code between a running
Selenium session and the web UI.

When D-EDGE stops trusting the Chrome profile it bounces to /Device/Unknown
and emails a code to the hotel mailbox. In Docker the browser is headless, so
nobody can type the code into it. Instead the waiting session marks a code as
needed here, the UI (GET /api/dedge/auth/status) shows a prompt, and the code
submitted from the UI (POST /api/dedge/auth/code) is typed into the page by
the session that is waiting for it.

State lives in this process only, which is fine: the backend runs a single
gunicorn worker, and the waiting session is a thread in that same process.
"""

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_code_ready = threading.Event()

_state = {
    "pending": False,        # a session is waiting for a code right now
    "since": None,           # when it started waiting (ISO, UTC)
    "deadline": None,        # when it gives up (ISO, UTC)
    "email_hint": None,      # masked mailbox D-EDGE says it emailed
    "last_error": None,      # e.g. "D-EDGE rejected that code"
    "last_verified_at": None,
    "check_running": False,  # a manual session check is in progress
    "check_result": None,    # {"ok": bool, "message": str, "at": iso}
}
_submitted_code = None
_resend_requested = False


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def get_status():
    with _lock:
        return dict(_state)


def begin_wait(timeout_seconds, email_hint=None):
    global _submitted_code, _resend_requested
    now = _now()
    with _lock:
        _submitted_code = None
        _resend_requested = False
        _code_ready.clear()
        _state.update(
            pending=True,
            since=_iso(now),
            deadline=_iso(datetime.fromtimestamp(now.timestamp() + timeout_seconds, timezone.utc)),
            email_hint=email_hint,
            last_error=None,
        )


def end_wait(verified):
    global _submitted_code
    with _lock:
        _submitted_code = None
        _code_ready.clear()
        _state.update(pending=False, since=None, deadline=None)
        if verified:
            _state.update(last_verified_at=_iso(_now()), last_error=None)


def mark_verified():
    """A session reached the extranet without needing a code."""
    with _lock:
        _state["last_verified_at"] = _iso(_now())


def submit_code(code):
    """Returns (accepted, message). Accepted means handed to the waiting
    session - D-EDGE still has to accept it; watch last_error / pending."""
    global _submitted_code
    code = (code or "").strip()
    if not code or len(code) > 6 or not code.isalnum():
        return False, "The code is up to 6 letters/digits, exactly as in the D-EDGE email"
    with _lock:
        if not _state["pending"]:
            return False, "D-EDGE isn't waiting for a code right now"
        _submitted_code = code
        _state["last_error"] = None
        _code_ready.set()
    return True, "Code sent to D-EDGE - checking it..."


def request_resend():
    global _resend_requested
    with _lock:
        if not _state["pending"]:
            return False, "D-EDGE isn't waiting for a code right now"
        _resend_requested = True
        _code_ready.set()
    return True, "Asked D-EDGE to send the email again"


def take_action(wait_seconds):
    """Called by the waiting session. Blocks up to wait_seconds and returns
    ("code", value), ("resend", None) or (None, None)."""
    global _submitted_code, _resend_requested
    _code_ready.wait(wait_seconds)
    with _lock:
        _code_ready.clear()
        if _resend_requested:
            _resend_requested = False
            return "resend", None
        if _submitted_code:
            code, _submitted_code = _submitted_code, None
            return "code", code
    return None, None


def set_error(message):
    with _lock:
        _state["last_error"] = message


def try_start_check():
    with _lock:
        if _state["check_running"]:
            return False
        _state.update(check_running=True, check_result=None)
        return True


def finish_check(ok, message):
    with _lock:
        _state.update(check_running=False,
                      check_result={"ok": ok, "message": message, "at": _iso(_now())})
        if ok:
            _state["last_verified_at"] = _iso(_now())
