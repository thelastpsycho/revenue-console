"""Operator account management (app/accounts/users.py): admin-only CRUD for
per-user logins and their fine-grained feature permissions."""

from flask import Blueprint, g, jsonify, request

from ..accounts import users as accounts_users
from ..accounts.permissions import PERMISSIONS, require_permission

bp = Blueprint('users', __name__)


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


@bp.route('/api/users/permissions', methods=['GET'])
@require_permission('manage_users')
def list_permissions():
    return jsonify({"status": "success", "permissions": PERMISSIONS})


@bp.route('/api/users', methods=['GET'])
@require_permission('manage_users')
def list_users():
    return jsonify({"status": "success", "users": accounts_users.list_users()})


@bp.route('/api/users', methods=['POST'])
@require_permission('manage_users')
def create_user():
    try:
        user = accounts_users.create_user(request.get_json(silent=True) or {})
    except accounts_users.ValidationError as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "user": user})


@bp.route('/api/users/<int:user_id>', methods=['PUT'])
@require_permission('manage_users')
def update_user(user_id):
    try:
        user = accounts_users.update_user(
            user_id, request.get_json(silent=True) or {}, current_user_id=g.current_user['id'])
    except accounts_users.ValidationError as exc:
        return _error(str(exc), 400)
    if user is None:
        return _error("User not found", 404)
    return jsonify({"status": "success", "user": user})


@bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@require_permission('manage_users')
def delete_user(user_id):
    try:
        removed = accounts_users.delete_user(user_id, current_user_id=g.current_user['id'])
    except accounts_users.ValidationError as exc:
        return _error(str(exc), 400)
    if not removed:
        return _error("User not found", 404)
    return jsonify({"status": "success"})
