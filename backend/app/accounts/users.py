"""Operator accounts in users.db (runtime data dir).

Replaces the old single shared PIN with real per-operator accounts: each
row is a username/password login plus a set of fine-grained feature
permission keys (see permissions.py for the catalog). Admins manage
accounts from the Users page; the very first account is created by
scripts/bootstrap_admin.py since nobody exists yet to use that page.
"""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from ..infrastructure.paths import get_data_path
from .permissions import PERMISSION_KEYS

DB_FILE = "users.db"

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{3,60}$")
MIN_PASSWORD_LENGTH = 8
MAX_DISPLAY_NAME_LENGTH = 120

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            permissions TEXT NOT NULL DEFAULT '[]',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        )
    """)
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        with conn:  # commits, or rolls back on error
            yield conn
    finally:
        conn.close()


def _user(row, *, include_hash=False):
    user = {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "permissions": sorted(json.loads(row["permissions"])),
        "isActive": bool(row["is_active"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "lastLoginAt": row["last_login_at"],
    }
    if include_hash:
        user["_passwordHash"] = row["password_hash"]
    return user


def _clean_username(username):
    if not isinstance(username, str):
        raise ValidationError("Username must be text")
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Username must be 3-60 characters: letters, numbers, '.', '_' or '-'")
    return username


def _clean_display_name(display_name, fallback):
    if display_name is None or display_name == "":
        display_name = fallback
    if not isinstance(display_name, str):
        raise ValidationError("Display name must be text")
    display_name = display_name.strip() or fallback
    if len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise ValidationError(f"Display name can be at most {MAX_DISPLAY_NAME_LENGTH} characters")
    return display_name


def _clean_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return password


def _clean_permissions(permissions):
    if permissions is None:
        return []
    if not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions):
        raise ValidationError("Permissions must be a list of permission keys")
    unknown = sorted(set(permissions) - PERMISSION_KEYS)
    if unknown:
        raise ValidationError(f"Unknown permission key(s): {', '.join(unknown)}")
    return sorted(set(permissions))


def list_users():
    with _lock, _db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [_user(r) for r in rows]


def get_user(user_id, *, include_hash=False):
    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _user(row, include_hash=include_hash) if row else None


def get_user_by_username(username, *, include_hash=False):
    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        return _user(row, include_hash=include_hash) if row else None


def create_user(data):
    if not isinstance(data, dict):
        raise ValidationError("User must be an object")
    username = _clean_username(data.get("username"))
    display_name = _clean_display_name(data.get("displayName"), username)
    password = _clean_password(data.get("password"))
    permissions = _clean_permissions(data.get("permissions"))

    now = _now()
    with _lock, _db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if existing:
            raise ValidationError(f'Username "{username}" is already taken')
        cur = conn.execute(
            """INSERT INTO users (username, password_hash, display_name, permissions,
                                   is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (username, generate_password_hash(password), display_name,
             json.dumps(permissions), now, now))
        return _user(conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_user(user_id, data, *, current_user_id=None):
    """Returns the updated user, or None if it doesn't exist.

    Refuses to let a user remove their own manage_users permission or
    deactivate their own account - otherwise an admin could lock everyone
    (including themselves) out with no remaining way back in.
    """
    if not isinstance(data, dict):
        raise ValidationError("User must be an object")

    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        current = _user(row)

        display_name = current["displayName"]
        if "displayName" in data:
            display_name = _clean_display_name(data.get("displayName"), current["username"])

        permissions = current["permissions"]
        if "permissions" in data:
            permissions = _clean_permissions(data.get("permissions"))
            if user_id == current_user_id and "manage_users" not in permissions:
                raise ValidationError("You can't remove your own \"manage_users\" permission")

        is_active = current["isActive"]
        if "isActive" in data:
            is_active = bool(data.get("isActive"))
            if user_id == current_user_id and not is_active:
                raise ValidationError("You can't deactivate your own account")

        password_hash = None
        if data.get("password"):
            password_hash = generate_password_hash(_clean_password(data.get("password")))

        if password_hash is not None:
            conn.execute(
                """UPDATE users SET display_name = ?, permissions = ?, is_active = ?,
                                     password_hash = ?, updated_at = ? WHERE id = ?""",
                (display_name, json.dumps(permissions), int(is_active), password_hash,
                 _now(), user_id))
        else:
            conn.execute(
                """UPDATE users SET display_name = ?, permissions = ?, is_active = ?,
                                     updated_at = ? WHERE id = ?""",
                (display_name, json.dumps(permissions), int(is_active), _now(), user_id))
        return _user(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def delete_user(user_id, *, current_user_id=None):
    if user_id == current_user_id:
        raise ValidationError("You can't delete your own account")
    with _lock, _db() as conn:
        return conn.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount > 0


def verify_login(username, password):
    """Returns the user dict on success (and records last_login_at), else None."""
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if not row or not row["is_active"] or not check_password_hash(row["password_hash"], password):
            return None
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), row["id"]))
        return _user(conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())


def change_own_password(user_id, current_password, new_password):
    """Self-service password change. Raises ValidationError on bad input."""
    new_password = _clean_password(new_password)
    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], current_password or ""):
            raise ValidationError("Current password is incorrect")
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (generate_password_hash(new_password), _now(), user_id))


def any_users_exist():
    with _lock, _db() as conn:
        return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
