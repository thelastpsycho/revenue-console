"""OAuth AS storage: client registration/approval and PKCE authorization codes."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.accounts import oauth_server


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(oauth_server, "get_data_path", lambda name: str(tmp_path / name))
    return tmp_path


def _pkce_pair(verifier="a" * 64):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# --- client registration / approval -------------------------------------------

def test_register_client_defaults_to_pending():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/callback"])
    client = oauth_server.get_client(client_id)
    assert client["status"] == "pending"
    assert client["clientName"] == "Claude"
    assert client["redirectUris"] == ["https://claude.ai/callback"]


def test_register_rejects_non_https_non_loopback_redirect_uri():
    with pytest.raises(oauth_server.ValidationError):
        oauth_server.register_client("Evil", ["http://attacker.evil/cb"])


def test_register_allows_loopback_http_for_local_tools():
    client_id = oauth_server.register_client("Local tool", ["http://127.0.0.1:33418/cb"])
    assert oauth_server.get_client(client_id)["status"] == "pending"


def test_register_rejects_blank_name_or_empty_redirect_uris():
    with pytest.raises(oauth_server.ValidationError):
        oauth_server.register_client("", ["https://claude.ai/cb"])
    with pytest.raises(oauth_server.ValidationError):
        oauth_server.register_client("Claude", [])


def test_approve_and_reject_client():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    assert oauth_server.approve_client(client_id) is True
    assert oauth_server.get_client(client_id)["status"] == "approved"
    assert oauth_server.reject_client(client_id) is True
    assert oauth_server.get_client(client_id) is None


def test_approve_missing_client_returns_false():
    assert oauth_server.approve_client("nope") is False


def test_list_clients_returns_all():
    oauth_server.register_client("A", ["https://a.test/cb"])
    oauth_server.register_client("B", ["https://b.test/cb"])
    assert {c["clientName"] for c in oauth_server.list_clients()} == {"A", "B"}


# --- authorization codes / PKCE -----------------------------------------------

def test_consume_code_happy_path():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    oauth_server.approve_client(client_id)
    verifier, challenge = _pkce_pair()
    code = oauth_server.create_code(client_id, 7, "https://claude.ai/cb", challenge)
    assert oauth_server.consume_code(code, client_id, "https://claude.ai/cb", verifier) == (7, "never")


def test_consume_code_carries_the_chosen_expiry_preset():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    verifier, challenge = _pkce_pair()
    code = oauth_server.create_code(client_id, 7, "https://claude.ai/cb", challenge, "1w")
    assert oauth_server.consume_code(code, client_id, "https://claude.ai/cb", verifier) == (7, "1w")


def test_consume_code_is_single_use():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    verifier, challenge = _pkce_pair()
    code = oauth_server.create_code(client_id, 7, "https://claude.ai/cb", challenge)
    assert oauth_server.consume_code(code, client_id, "https://claude.ai/cb", verifier) == (7, "never")
    assert oauth_server.consume_code(code, client_id, "https://claude.ai/cb", verifier) is None


def test_consume_code_rejects_wrong_client_or_redirect_uri():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    verifier, challenge = _pkce_pair()
    code = oauth_server.create_code(client_id, 7, "https://claude.ai/cb", challenge)
    assert oauth_server.consume_code(code, "someone-else", "https://claude.ai/cb", verifier) is None
    assert oauth_server.consume_code(code, client_id, "https://other.test/cb", verifier) is None


def test_consume_code_rejects_wrong_verifier():
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    _verifier, challenge = _pkce_pair()
    code = oauth_server.create_code(client_id, 7, "https://claude.ai/cb", challenge)
    wrong = "b" * 64
    assert oauth_server.consume_code(code, client_id, "https://claude.ai/cb", wrong) is None


def test_consume_code_rejects_expired_code(monkeypatch):
    client_id = oauth_server.register_client("Claude", ["https://claude.ai/cb"])
    verifier, challenge = _pkce_pair()
    code = oauth_server.create_code(client_id, 7, "https://claude.ai/cb", challenge)
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    monkeypatch.setattr(oauth_server, "_now", lambda: future)
    assert oauth_server.consume_code(code, client_id, "https://claude.ai/cb", verifier) is None


def test_consume_code_missing_code_returns_none():
    assert oauth_server.consume_code("nope", "client", "https://x.test/cb", "verifier") is None


# --- PKCE edge cases -----------------------------------------------------------

def test_pkce_rejects_short_or_long_verifier():
    assert oauth_server._pkce_ok("short", "irrelevant") is False
    assert oauth_server._pkce_ok("a" * 200, "irrelevant") is False


def test_pkce_rejects_non_ascii_verifier():
    verifier = "a" * 42 + "é"  # length 43, but not ASCII
    assert len(verifier) == 43
    assert oauth_server._pkce_ok(verifier, "irrelevant") is False


def test_pkce_rejects_padded_stored_challenge():
    verifier, challenge = _pkce_pair()
    assert oauth_server._pkce_ok(verifier, challenge + "==") is False


def test_pkce_accepts_matching_pair():
    verifier, challenge = _pkce_pair()
    assert oauth_server._pkce_ok(verifier, challenge) is True
