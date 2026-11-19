"""OAuth 2.1 authorization-code + PKCE storage in oauth_server.db (runtime data dir).

Lets the mcp-server's remote connector use a real "Sign in" instead of pasting a
personal API key into a request header. This module only holds the two pieces of
state an Authorization Server needs: registered clients (RFC 7591 dynamic client
registration) and short-lived, single-use authorization codes (RFC 7636 PKCE,
S256 only). The human-facing login/consent flow lives in routes/oauth_routes.py;
the token this ultimately mints is a row in mcp_keys (see create_oauth_key there)
- there is no separate access-token table here, and no refresh tokens, since an
mcp_keys token already doesn't expire until revoked.

A client is untrusted until an admin approves it (status "pending" -> "approved").
Registration itself is intentionally open, per RFC 7591 - it grants nothing on its
own. What would otherwise be a phishing hole (anyone can register a client named
"Claude" pointing at an attacker's redirect_uri, then trick an already-logged-in
operator into approving consent) is closed by requiring that one-time admin
approval before /oauth/authorize will render consent for a client at all.
"""

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from ..infrastructure.paths import get_data_path

DB_FILE = "oauth_server.db"
CLIENT_ID_PREFIX = "oac_"
CODE_TTL = timedelta(minutes=2)

_lock = threading.Lock()


class ValidationError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _connect():
    conn = sqlite3.connect(get_data_path(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id TEXT PRIMARY KEY,
            client_name TEXT NOT NULL,
            redirect_uris TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_codes (
            code TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            redirect_uri TEXT NOT NULL,
            code_challenge TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
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


def _client(row):
    return {
        "clientId": row["client_id"],
        "clientName": row["client_name"],
        "redirectUris": json.loads(row["redirect_uris"]),
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def _clean_redirect_uris(redirect_uris):
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise ValidationError("redirect_uris must be a non-empty list")
    cleaned = []
    for uri in redirect_uris:
        if not isinstance(uri, str) or not uri:
            raise ValidationError("Each redirect_uri must be a non-empty string")
        parsed = urlparse(uri)
        loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if parsed.scheme == "https" or (loopback and parsed.scheme in ("http", "https")):
            cleaned.append(uri)
            continue
        raise ValidationError(f"redirect_uri must be https:// (or a loopback URL for local tools): {uri}")
    return cleaned


def _clean_client_name(client_name):
    if not isinstance(client_name, str) or not client_name.strip():
        raise ValidationError("client_name is required")
    return client_name.strip()[:120]


def register_client(client_name, redirect_uris):
    client_name = _clean_client_name(client_name)
    redirect_uris = _clean_redirect_uris(redirect_uris)
    client_id = CLIENT_ID_PREFIX + secrets.token_urlsafe(24)
    with _lock, _db() as conn:
        conn.execute(
            "INSERT INTO oauth_clients (client_id, client_name, redirect_uris, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (client_id, client_name, json.dumps(redirect_uris), _iso(_now())))
    return client_id


def get_client(client_id):
    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
        return _client(row) if row else None


def list_clients():
    with _lock, _db() as conn:
        rows = conn.execute("SELECT * FROM oauth_clients ORDER BY created_at DESC").fetchall()
        return [_client(r) for r in rows]


def approve_client(client_id):
    with _lock, _db() as conn:
        cur = conn.execute("UPDATE oauth_clients SET status = 'approved' WHERE client_id = ?", (client_id,))
        return cur.rowcount > 0


def reject_client(client_id):
    """A rejected client shell has no data worth retaining - delete it outright."""
    with _lock, _db() as conn:
        cur = conn.execute("DELETE FROM oauth_clients WHERE client_id = ?", (client_id,))
        return cur.rowcount > 0


def create_code(client_id, user_id, redirect_uri, code_challenge):
    code = secrets.token_urlsafe(32)
    now = _now()
    with _lock, _db() as conn:
        conn.execute(
            "INSERT INTO oauth_codes (code, client_id, user_id, redirect_uri, code_challenge, "
            "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, client_id, user_id, redirect_uri, code_challenge, _iso(now), _iso(now + CODE_TTL)))
    return code


def _challenge_from_verifier(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _pkce_ok(code_verifier, stored_code_challenge):
    if not isinstance(code_verifier, str) or not (43 <= len(code_verifier) <= 128):
        return False
    try:
        computed = _challenge_from_verifier(code_verifier)
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(computed, stored_code_challenge)


def consume_code(code, client_id, redirect_uri, code_verifier):
    """Returns the owning user_id on success, else None. Single-use: marks the
    code used in the same transaction it's validated in, so a replay (even a
    concurrent one) can't succeed twice."""
    with _lock, _db() as conn:
        row = conn.execute("SELECT * FROM oauth_codes WHERE code = ?", (code,)).fetchone()
        if not row or row["used_at"] is not None:
            return None
        if row["client_id"] != client_id or row["redirect_uri"] != redirect_uri:
            return None
        if datetime.fromisoformat(row["expires_at"]) < _now():
            return None
        if not _pkce_ok(code_verifier, row["code_challenge"]):
            return None
        conn.execute("UPDATE oauth_codes SET used_at = ? WHERE code = ?", (_iso(_now()), code))
        return row["user_id"]
