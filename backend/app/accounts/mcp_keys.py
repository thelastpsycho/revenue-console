"""Personal API keys in mcp_keys.db (runtime data dir).

Lets any logged-in operator mint their own bearer token - carrying their own
account's permissions, since it IS their account - to connect MCP clients
(or any other API caller) without a browser session cookie. Named for its
primary use case, but security.py accepts a valid key for any /api/ route.

The plaintext token is only ever returned once, at creation; only its sha256
hash is stored (a high-entropy random token needs no slow password hash,
unlike a human-chosen password).
"""

import hashlib
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from ..infrastructure.paths import get_data_path

DB_FILE = "mcp_keys.db"
# Lets a leaked token be recognized at a glance (e.g. in a log line or a
# secret-scanning rule) as a Revenue Console key specifically.
KEY_PREFIX = "rck_"
MAX_LABEL_LENGTH = 120

# Ordered so callers (the create-key form, the OAuth consent screen) can
# render options in a sensible sequence; "never" (None) matches this key
# type's original behavior and stays the default everywhere it's optional.
EXPIRY_PRESET_LABELS = [
    ("1d", "1 day"), ("1w", "1 week"), ("1m", "1 month"), ("1y", "1 year"), ("never", "Never"),
]
EXPIRY_PRESETS = {
    "1d": timedelta(days=1),
    "1w": timedelta(days=7),
    "1m": timedelta(days=30),
    "1y": timedelta(days=365),
    "never": None,
}

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mcp_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            last_used_at TEXT
        )
    """)
    try:
        # Tags a key minted via the OAuth token endpoint with the client that
        # caused it, so a reconnect can revoke its own previous key instead of
        # piling up a fresh non-expiring one every time (see create_oauth_key).
        conn.execute("ALTER TABLE mcp_keys ADD COLUMN oauth_client_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE mcp_keys ADD COLUMN expires_at TEXT")
    except sqlite3.OperationalError:
        pass
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        with conn:  # commits, or rolls back on error
            yield conn
    finally:
        conn.close()


def _record(row):
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "label": row["label"],
        "createdAt": row["created_at"],
        "revokedAt": row["revoked_at"],
        "lastUsedAt": row["last_used_at"],
        "oauthClientId": row["oauth_client_id"],
        "expiresAt": row["expires_at"],
    }


def _resolve_expiry(expiry_preset):
    """Converts a preset code to an absolute expires_at (or None for "never"),
    computed from this server's own clock rather than trusting any
    caller-supplied timestamp."""
    if expiry_preset not in EXPIRY_PRESETS:
        raise ValidationError(f"Unknown expiry preset: {expiry_preset}")
    delta = EXPIRY_PRESETS[expiry_preset]
    return (datetime.now(timezone.utc) + delta).isoformat(timespec="seconds") if delta else None


def _clean_label(label):
    if not isinstance(label, str):
        raise ValidationError("Label must be text")
    label = label.strip()
    if not label:
        raise ValidationError("Label is required")
    if len(label) > MAX_LABEL_LENGTH:
        raise ValidationError(f"Label can be at most {MAX_LABEL_LENGTH} characters")
    return label


def list_keys_for_user(user_id):
    with _lock, _db() as conn:
        rows = conn.execute(
            "SELECT * FROM mcp_keys WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [_record(r) for r in rows]


def list_all_keys():
    with _lock, _db() as conn:
        rows = conn.execute("SELECT * FROM mcp_keys ORDER BY created_at DESC").fetchall()
        return [_record(r) for r in rows]


def list_keys_by_oauth_client(client_id):
    """Every key ever minted for this OAuth client (one per user who's signed
    in through it) - lets the MCP Access page show who's actually connected
    through a given client, not just the client's own self-reported name."""
    with _lock, _db() as conn:
        rows = conn.execute(
            "SELECT * FROM mcp_keys WHERE oauth_client_id = ? ORDER BY created_at DESC", (client_id,)).fetchall()
        return [_record(r) for r in rows]


def create_key(user_id, label, expiry_preset="never"):
    label = _clean_label(label)
    expires_at = _resolve_expiry(expiry_preset)
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    with _lock, _db() as conn:
        cur = conn.execute(
            "INSERT INTO mcp_keys (user_id, label, key_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, label, _hash(token), now, expires_at))
        record = _record(conn.execute("SELECT * FROM mcp_keys WHERE id = ?", (cur.lastrowid,)).fetchone())
    return record, token


def create_oauth_key(user_id, client_id, client_name, expiry_preset="never"):
    """Mints a key on behalf of a completed OAuth grant (see routes/oauth_routes.py's
    /oauth/token). Revokes any still-live key already tagged with this exact
    (user_id, client_id) pair first, so reconnecting doesn't pile up a fresh
    non-expiring key on every sign-in - one live key per (user, client)."""
    label = f"OAuth: {client_name}"[:MAX_LABEL_LENGTH]
    expires_at = _resolve_expiry(expiry_preset)
    now = _now()
    with _lock, _db() as conn:
        conn.execute(
            "UPDATE mcp_keys SET revoked_at = ? WHERE user_id = ? AND oauth_client_id = ? AND revoked_at IS NULL",
            (now, user_id, client_id))
        token = KEY_PREFIX + secrets.token_urlsafe(32)
        cur = conn.execute(
            "INSERT INTO mcp_keys (user_id, label, key_hash, created_at, oauth_client_id, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, label, _hash(token), now, client_id, expires_at))
        record = _record(conn.execute("SELECT * FROM mcp_keys WHERE id = ?", (cur.lastrowid,)).fetchone())
    return record, token


def revoke_key(key_id, *, user_id=None):
    """Revokes a key, restricted to its own owner unless user_id is None
    (admin scope). Returns False if not found (or not owned by user_id)."""
    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM mcp_keys WHERE id = ?", (key_id,)).fetchone()
        if not row or (user_id is not None and row["user_id"] != user_id):
            return False
        if not row["revoked_at"]:
            conn.execute("UPDATE mcp_keys SET revoked_at = ? WHERE id = ?", (_now(), key_id))
        return True


def authenticate(token):
    """Returns the owning user_id on success (and records last_used_at), else None."""
    if not isinstance(token, str) or not token:
        return None
    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM mcp_keys WHERE key_hash = ?", (_hash(token),)).fetchone()
        if not row or row["revoked_at"]:
            return None
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            return None
        conn.execute("UPDATE mcp_keys SET last_used_at = ? WHERE id = ?", (_now(), row["id"]))
        return row["user_id"]
