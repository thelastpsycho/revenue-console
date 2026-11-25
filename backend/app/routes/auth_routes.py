"""Session login for the revenue console: per-operator username/password."""
from flask import Blueprint, current_app, g, jsonify, request, session

from ..accounts import users as accounts_users
from ..security import DEV_USER, new_csrf

bp = Blueprint("auth", __name__)


MAX_TOTP_ATTEMPTS = 8
TRUSTED_DEVICE_COOKIE = "rc_trusted_device"
TRUSTED_DEVICE_DAYS = 7


def _public_user(user):
    return {"id": user["id"], "username": user["username"], "displayName": user["displayName"],
            "permissions": user["permissions"], "twoFactorEnabled": user["twoFactorEnabled"],
            "twoFactorSetupRequired": user["twoFactorRequired"] and not user["twoFactorEnabled"]}


def _complete_login(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({"status": "success", "csrf_token": new_csrf(), "user": _public_user(user)})


@bp.route("/api/auth/status", methods=["GET"])
def status():
    conf = current_app.extensions["operator_auth"]
    user = None
    if conf["dev_mode"]:
        user = DEV_USER
    elif conf["configured"]:
        user_id = session.get("user_id")
        candidate = accounts_users.get_user(user_id) if user_id is not None else None
        if candidate and candidate["isActive"]:
            user = candidate
    authenticated = user is not None
    result = {
        "configured": conf["configured"],
        "dev_mode": conf["dev_mode"],
        "authenticated": authenticated,
        "user": _public_user(user) if user else None,
    }
    if authenticated:
        result["csrf_token"] = session.get("csrf_token") or new_csrf()
    if not conf["configured"] and not conf["dev_mode"]:
        result["message"] = "Set APP_SESSION_SECRET on the Flask backend, then run scripts/bootstrap_admin.py"
    return jsonify(result)


@bp.route("/api/auth/login", methods=["POST"])
def login():
    conf = current_app.extensions["operator_auth"]
    if not conf["configured"]:
        return jsonify({"status": "error", "message": "API authentication is not configured"}), 503
    session.pop("pending_2fa_user_id", None)
    session.pop("pending_2fa_attempts", None)
    data = request.get_json(silent=True) or {}
    user = accounts_users.verify_login(data.get("username", ""), data.get("password", ""))
    if not user:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401
    if user["twoFactorEnabled"]:
        trusted_token = request.cookies.get(TRUSTED_DEVICE_COOKIE, "")
        if trusted_token and accounts_users.verify_trusted_device(user["id"], trusted_token):
            return _complete_login(user)
        session["pending_2fa_user_id"] = user["id"]
        session["pending_2fa_attempts"] = 0
        return jsonify({"status": "totp_required"})
    return _complete_login(user)


@bp.route("/api/auth/login-totp", methods=["POST"])
def login_totp():
    pending_id = session.get("pending_2fa_user_id")
    if pending_id is None:
        return jsonify({"status": "error", "message": "No sign-in in progress"}), 401
    data = request.get_json(silent=True) or {}
    if accounts_users.verify_totp(pending_id, data.get("code", "")):
        session.pop("pending_2fa_user_id", None)
        session.pop("pending_2fa_attempts", None)
        user = accounts_users.get_user(pending_id)
        if not user or not user["isActive"]:
            return jsonify({"status": "error", "message": "Account no longer available"}), 401
        response = _complete_login(user)
        if data.get("rememberDevice"):
            token = accounts_users.create_trusted_device(user["id"], days=TRUSTED_DEVICE_DAYS)
            response.set_cookie(
                TRUSTED_DEVICE_COOKIE, token, max_age=TRUSTED_DEVICE_DAYS * 86400,
                httponly=True, samesite="Strict",
                secure=current_app.config.get("SESSION_COOKIE_SECURE", False))
        return response
    attempts = session.get("pending_2fa_attempts", 0) + 1
    if attempts >= MAX_TOTP_ATTEMPTS:
        session.pop("pending_2fa_user_id", None)
        session.pop("pending_2fa_attempts", None)
        return jsonify({"status": "error", "message": "Too many attempts. Sign in again.", "locked": True}), 401
    session["pending_2fa_attempts"] = attempts
    return jsonify({"status": "error", "message": "Invalid code"}), 401


@bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "success"})


@bp.route("/api/auth/change-password", methods=["POST"])
def change_password():
    user = g.current_user
    if user["id"] == 0:
        return jsonify({"status": "error", "message": "Not available in local dev mode"}), 400
    data = request.get_json(silent=True) or {}
    try:
        accounts_users.change_own_password(
            user["id"], data.get("currentPassword", ""), data.get("newPassword", ""))
    except accounts_users.ValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "success"})


@bp.route("/api/auth/2fa/setup", methods=["POST"])
def setup_totp():
    user = g.current_user
    if user["id"] == 0:
        return jsonify({"status": "error", "message": "Not available in local dev mode"}), 400
    secret, qr_data_uri = accounts_users.begin_totp_setup(user["id"])
    return jsonify({"status": "success", "secret": secret, "qrDataUri": qr_data_uri})


@bp.route("/api/auth/2fa/confirm", methods=["POST"])
def confirm_totp():
    user = g.current_user
    if user["id"] == 0:
        return jsonify({"status": "error", "message": "Not available in local dev mode"}), 400
    data = request.get_json(silent=True) or {}
    try:
        accounts_users.confirm_totp_setup(user["id"], data.get("code", ""))
    except accounts_users.ValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "success"})


@bp.route("/api/auth/2fa/disable", methods=["POST"])
def disable_totp():
    user = g.current_user
    if user["id"] == 0:
        return jsonify({"status": "error", "message": "Not available in local dev mode"}), 400
    data = request.get_json(silent=True) or {}
    try:
        accounts_users.disable_totp(user["id"], data.get("currentPassword", ""))
    except accounts_users.ValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "success"})
