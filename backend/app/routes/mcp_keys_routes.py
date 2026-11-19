"""Personal API keys (app/accounts/mcp_keys.py): self-service bearer tokens
any logged-in operator can mint for their own account, to connect MCP
clients or other API callers without a session cookie. No permission is
required beyond being logged in - a key only ever carries its own owner's
existing permissions, never more."""

from flask import Blueprint, g, jsonify, request

from ..accounts import mcp_keys
from ..accounts import users as accounts_users

bp = Blueprint('mcp_keys', __name__)


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


def _is_admin(user):
    return 'manage_users' in user.get('permissions', ())


def _with_owner(record):
    owner = accounts_users.get_user(record["userId"])
    return {**record, "ownerUsername": owner["username"] if owner else None,
            "ownerDisplayName": owner["displayName"] if owner else None}


@bp.route('/api/mcp-keys', methods=['GET'])
def list_keys():
    user = g.current_user
    if request.args.get('scope') == 'all' and _is_admin(user):
        return jsonify({"status": "success", "scope": "all",
                         "keys": [_with_owner(k) for k in mcp_keys.list_all_keys()]})
    return jsonify({"status": "success", "scope": "own", "keys": mcp_keys.list_keys_for_user(user['id'])})


@bp.route('/api/mcp-keys', methods=['POST'])
def create_key():
    data = request.get_json(silent=True) or {}
    try:
        record, token = mcp_keys.create_key(
            g.current_user['id'], data.get('label', ''), data.get('expiryPreset', 'never'))
    except mcp_keys.ValidationError as exc:
        return _error(str(exc), 400)
    return jsonify({"status": "success", "key": record, "apiKey": token})


@bp.route('/api/mcp-keys/expiry-presets', methods=['GET'])
def expiry_presets():
    return jsonify({"status": "success",
                    "presets": [{"value": value, "label": label} for value, label in mcp_keys.EXPIRY_PRESET_LABELS]})


@bp.route('/api/mcp-keys/<int:key_id>/revoke', methods=['POST'])
def revoke_key(key_id):
    user = g.current_user
    scope_user_id = None if _is_admin(user) else user['id']
    if not mcp_keys.revoke_key(key_id, user_id=scope_user_id):
        return _error("Key not found", 404)
    return jsonify({"status": "success"})
