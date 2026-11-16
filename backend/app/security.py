"""Per-user session auth for every API endpoint.

APP_SESSION_SECRET must be configured, and at least one operator account
must exist (see scripts/bootstrap_admin.py), before the API becomes
available. Optional insecure development is restricted to an explicit
opt-in on a loopback-bound Flask server.
"""
import hmac
import os
import secrets
from datetime import timedelta

from flask import g, jsonify, request, session

from .accounts import users as accounts_users
from .accounts.permissions import PERMISSION_KEYS

DEV_USER = {
    "id": 0,
    "username": "dev",
    "displayName": "Local Dev",
    "permissions": sorted(PERMISSION_KEYS),
    "isActive": True,
}


def init_security(app):
    session_secret = os.environ.get("APP_SESSION_SECRET", "")
    dev_flag = os.environ.get("ALLOW_INSECURE_LOCAL_DEV") == "1"
    host = os.environ.get("APP_HOST", "127.0.0.1")
    dev_mode = dev_flag and host in ("127.0.0.1", "localhost", "::1") and not session_secret
    configured = len(session_secret) >= 32 and not session_secret.startswith("replace-")
    if session_secret and not configured:
        raise RuntimeError("Set APP_SESSION_SECRET to a random 32+ character secret; example values are invalid")

    # When unconfigured, the API is locked (not openly accessible). Health and
    # auth/status remain available to report the missing configuration.
    app.secret_key = session_secret if configured else secrets.token_urlsafe(48)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("APP_SECURE_COOKIES") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    )
    app.extensions["operator_auth"] = {
        "configured": configured,
        "dev_mode": dev_mode,
    }

    @app.before_request
    def secure_api():
        if not request.path.startswith("/api/"):
            return None
        if request.path in ("/api/health", "/api/auth/status", "/api/auth/login"):
            return None
        auth = app.extensions["operator_auth"]
        if auth["dev_mode"]:
            g.current_user = DEV_USER
            return None
        if not auth["configured"]:
            return jsonify({"status": "error", "message": "API access is not configured; set APP_SESSION_SECRET"}), 503
        user_id = session.get("user_id")
        user = accounts_users.get_user(user_id) if user_id is not None else None
        if not user or not user["isActive"]:
            session.clear()
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        g.current_user = user
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            actual = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(actual, expected):
                return jsonify({"status": "error", "message": "CSRF token required"}), 403
        return None


def new_csrf():
    value = secrets.token_urlsafe(32)
    session["csrf_token"] = value
    return value
