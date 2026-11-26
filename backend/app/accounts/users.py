"""Operator accounts in users.db (runtime data dir).

Replaces the old single shared PIN with real per-operator accounts: each
row is a username/password login plus a set of fine-grained feature
permission keys (see permissions.py for the catalog). Admins manage
accounts from the Users page; the very first account is created by
scripts/bootstrap_admin.py since nobody exists yet to use that page.
"""

import hashlib
import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from ..infrastructure.paths import get_data_path
from . import two_factor
from .permissions import PERMISSION_KEYS

DB_FILE = "users.db"

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{3,60}$")
MIN_PASSWORD_LENGTH = 8
MAX_DISPLAY_NAME_LENGTH = 120

# Mirrors the TOTP step's own attempt cap (MAX_TOTP_ATTEMPTS in auth_routes.py)
# so password guessing isn't the one unthrottled step in an otherwise-limited
# login flow. Locked accounts get the same generic "invalid" response as a
# wrong password - never a distinct message - so a lockout can't be used to
# fingerprint which usernames exist.
MAX_LOGIN_ATTEMPTS = 8
LOGIN_LOCKOUT_MINUTES = 15

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Permissions split off an existing key after that key already controlled
# everyone's access to the capability - holders of the "parent" key are
# backfilled with the new one once, so nobody's access shrinks on upgrade.
_SPLIT_PERMISSION_BACKFILL = {
    "manage_users": ["manage_oauth_clients", "manage_mcp_keys"],
    "run_pipeline": ["manage_pipeline_schedule"],
    "manage_rms_settings": ["manage_rms_notes"],
    "run_pms_scrape": ["view_pms_scrape_logs"],
    "run_dedge_scrape": ["view_dedge_scrape_logs"],
}
# Page-visibility permissions didn't exist before - every page was visible to
# any authenticated user, so every existing account is backfilled with all of
# them. Only users created after this migration can be scoped to fewer pages.
_NEW_PAGE_VIEW_PERMISSIONS = [
    "view_dashboard", "view_data", "view_rms", "view_mcp_access",
    "view_documentation", "view_administration",
]
_PERMISSION_MIGRATION = "view_and_split_2026_11"


def _backfill_split_permissions(conn):
    applied = conn.execute(
        "SELECT 1 FROM permission_migrations WHERE name = ?", (_PERMISSION_MIGRATION,)).fetchone()
    if applied:
        return
    for row in conn.execute("SELECT id, permissions FROM users").fetchall():
        current = set(json.loads(row["permissions"]))
        updated = set(current) | set(_NEW_PAGE_VIEW_PERMISSIONS)
        for parent, children in _SPLIT_PERMISSION_BACKFILL.items():
            if parent in current:
                updated.update(children)
        if updated != current:
            conn.execute("UPDATE users SET permissions = ? WHERE id = ?",
                         (json.dumps(sorted(updated)), row["id"]))
    conn.execute("INSERT INTO permission_migrations (name, applied_at) VALUES (?, ?)",
                 (_PERMISSION_MIGRATION, _now()))


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS permission_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trusted_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_used_at TEXT
        )
    """)
    for ddl in (
        "ALTER TABLE users ADD COLUMN totp_secret TEXT",
        "ALTER TABLE users ADD COLUMN totp_pending_secret TEXT",
        "ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN totp_required INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN locked_until TEXT",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    with conn:
        _backfill_split_permissions(conn)
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
        "twoFactorEnabled": bool(row["totp_enabled"]),
        "twoFactorRequired": bool(row["totp_required"]),
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
    two_factor_required = bool(data.get("twoFactorRequired"))

    now = _now()
    with _lock, _db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if existing:
            raise ValidationError(f'Username "{username}" is already taken')
        cur = conn.execute(
            """INSERT INTO users (username, password_hash, display_name, permissions,
                                   is_active, totp_required, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
            (username, generate_password_hash(password), display_name,
             json.dumps(permissions), int(two_factor_required), now, now))
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

        two_factor_required = current["twoFactorRequired"]
        if "twoFactorRequired" in data:
            two_factor_required = bool(data.get("twoFactorRequired"))

        password_hash = None
        if data.get("password"):
            password_hash = generate_password_hash(_clean_password(data.get("password")))

        if password_hash is not None:
            # An admin-issued password reset is itself a form of re-auth, so
            # it also clears any lockout left over from the old password.
            conn.execute(
                """UPDATE users SET display_name = ?, permissions = ?, is_active = ?,
                                     totp_required = ?, password_hash = ?, failed_login_attempts = 0,
                                     locked_until = NULL, updated_at = ? WHERE id = ?""",
                (display_name, json.dumps(permissions), int(is_active), int(two_factor_required),
                 password_hash, _now(), user_id))
        else:
            conn.execute(
                """UPDATE users SET display_name = ?, permissions = ?, is_active = ?,
                                     totp_required = ?, updated_at = ? WHERE id = ?""",
                (display_name, json.dumps(permissions), int(is_active), int(two_factor_required),
                 _now(), user_id))
        return _user(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def delete_user(user_id, *, current_user_id=None):
    if user_id == current_user_id:
        raise ValidationError("You can't delete your own account")
    with _lock, _db() as conn:
        return conn.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount > 0


def verify_login(username, password):
    """Returns the user dict on success (and records last_login_at), else None.

    A run of MAX_LOGIN_ATTEMPTS wrong passwords locks the account for
    LOGIN_LOCKOUT_MINUTES; a locked account fails the same way as a wrong
    password (no distinct error), so the lockout itself can't be probed to
    enumerate valid usernames.
    """
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if not row or not row["is_active"]:
            return None
        if row["locked_until"] and row["locked_until"] > _now():
            return None
        if not check_password_hash(row["password_hash"], password):
            attempts = row["failed_login_attempts"] + 1
            locked_until = None
            if attempts >= MAX_LOGIN_ATTEMPTS:
                locked_until = (datetime.now(timezone.utc)
                                 + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)).isoformat(timespec="seconds")
                attempts = 0
            conn.execute(
                "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                (attempts, locked_until, row["id"]))
            return None
        conn.execute(
            "UPDATE users SET last_login_at = ?, failed_login_attempts = 0, locked_until = NULL WHERE id = ?",
            (_now(), row["id"]))
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


def begin_totp_setup(user_id):
    """Generates a fresh TOTP secret and stashes it (encrypted) as pending -
    doesn't touch an existing enabled secret until confirm_totp_setup()
    verifies a real code, so an abandoned setup can't disturb working 2FA
    or silently enable it. Returns (secret, qr_data_uri)."""
    secret = two_factor.generate_secret()
    with _lock, _db() as conn:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValidationError("User not found")
        conn.execute("UPDATE users SET totp_pending_secret = ?, updated_at = ? WHERE id = ?",
                     (two_factor.encrypt(secret), _now(), user_id))
        qr_data_uri = two_factor.provisioning_qr_data_uri(secret, row["username"])
    return secret, qr_data_uri


def confirm_totp_setup(user_id, code):
    """Verifies `code` against the pending secret from begin_totp_setup() and,
    on success, makes it the account's active TOTP secret."""
    with _lock, _db() as conn:
        row = conn.execute("SELECT totp_pending_secret FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not row["totp_pending_secret"]:
            raise ValidationError("No two-factor setup in progress")
        secret = two_factor.decrypt(row["totp_pending_secret"])
        if not secret or not two_factor.verify_code(secret, code):
            raise ValidationError("Invalid code")
        conn.execute(
            """UPDATE users SET totp_secret = ?, totp_pending_secret = NULL,
                                 totp_enabled = 1, updated_at = ? WHERE id = ?""",
            (two_factor.encrypt(secret), _now(), user_id))


def disable_totp(user_id, current_password):
    """Self-service disable: requires the current password, same spirit as
    change_own_password - a security feature shouldn't turn off with no
    re-auth at all."""
    with _lock, _db() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], current_password or ""):
            raise ValidationError("Current password is incorrect")
        conn.execute(
            """UPDATE users SET totp_secret = NULL, totp_pending_secret = NULL,
                                 totp_enabled = 0, updated_at = ? WHERE id = ?""",
            (_now(), user_id))
        conn.execute("DELETE FROM trusted_devices WHERE user_id = ?", (user_id,))


def admin_reset_totp(user_id):
    """Unconditional recovery path for a lost authenticator - gated by the
    manage_users permission at the route layer, not by the account's own
    password or a code."""
    with _lock, _db() as conn:
        updated = conn.execute(
            """UPDATE users SET totp_secret = NULL, totp_pending_secret = NULL,
                                 totp_enabled = 0, updated_at = ? WHERE id = ?""",
            (_now(), user_id)).rowcount
        conn.execute("DELETE FROM trusted_devices WHERE user_id = ?", (user_id,))
        return updated > 0


def verify_totp(user_id, code):
    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT totp_secret, totp_enabled FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not row["totp_enabled"] or not row["totp_secret"]:
            return False
        secret = two_factor.decrypt(row["totp_secret"])
        return bool(secret) and two_factor.verify_code(secret, code)


def create_trusted_device(user_id, days=7):
    """Issues a 'remember this device' token so a future login can skip the
    TOTP step - the password is still always required, this only ever
    substitutes for the second factor. Returns the raw token (only time
    it's available in plaintext; the DB only ever stores its hash)."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=days)).isoformat(timespec="seconds")
    with _lock, _db() as conn:
        conn.execute(
            """INSERT INTO trusted_devices (user_id, token_hash, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, token_hash, now.isoformat(timespec="seconds"), expires_at))
    return token


def verify_trusted_device(user_id, token):
    if not isinstance(token, str) or not token:
        return False
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _lock, _db() as conn:
        row = conn.execute(
            """SELECT id, expires_at FROM trusted_devices WHERE user_id = ? AND token_hash = ?""",
            (user_id, token_hash)).fetchone()
        if not row or row["expires_at"] <= _now():
            return False
        conn.execute("UPDATE trusted_devices SET last_used_at = ? WHERE id = ?", (_now(), row["id"]))
    return True


def revoke_trusted_devices(user_id):
    with _lock, _db() as conn:
        conn.execute("DELETE FROM trusted_devices WHERE user_id = ?", (user_id,))
