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
from datetime import datetime, timezone

from ..infrastructure.paths import get_data_path

DB_FILE = "mcp_keys.db"
# Lets a leaked token be recognized at a glance (e.g. in a log line or a
# secret-scanning rule) as a Revenue Console key specifically.
KEY_PREFIX = "rck_"
MAX_LABEL_LENGTH = 120

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
    }


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


def create_key(user_id, label):
    label = _clean_label(label)
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    with _lock, _db() as conn:
        cur = conn.execute(
            "INSERT INTO mcp_keys (user_id, label, key_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, label, _hash(token), now))
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
        conn.execute("UPDATE mcp_keys SET last_used_at = ? WHERE id = ?", (_now(), row["id"]))
        return row["user_id"]
