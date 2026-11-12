"""Session login for the revenue console: per-operator username/password."""
from flask import Blueprint, current_app, g, jsonify, request, session

from ..accounts import users as accounts_users
from ..security import DEV_USER, new_csrf

bp = Blueprint("auth", __name__)


def _public_user(user):
    return {"id": user["id"], "username": user["username"], "displayName": user["displayName"],
            "permissions": user["permissions"]}


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
    data = request.get_json(silent=True) or {}
    user = accounts_users.verify_login(data.get("username", ""), data.get("password", ""))
    if not user:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({"status": "success", "csrf_token": new_csrf(), "user": _public_user(user)})


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
