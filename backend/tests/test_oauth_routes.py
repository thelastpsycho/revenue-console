"""OAuth Authorization Server routes: registration, authorize (login then
consent), token exchange, and the admin approval endpoints that gate consent -
the actual trust boundary, since registration itself is open by spec."""
import base64
import hashlib
import re
from urllib.parse import parse_qs, urlparse

import pytest

from app import create_app
from app.accounts import mcp_keys, oauth_server
from app.accounts import users as accounts_users
from app.routes import oauth_routes

REDIRECT_URI = "https://claude.ai/cb"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(oauth_server, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(mcp_keys, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(accounts_users, "get_data_path", lambda name: str(tmp_path / name))
    # The /oauth/register rate limiter is deliberately process-global state
    # (hygiene against junk rows in production); reset it per test so one
    # test's registrations don't trip the limit for the next.
    oauth_routes._register_hits.clear()
    return tmp_path


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("APP_SESSION_SECRET", "b" * 48)
    monkeypatch.delenv("ALLOW_INSECURE_LOCAL_DEV", raising=False)
    application = create_app()
    application.testing = True
    return application


def _create_user(username="alice", password="correct-password-1", permissions=None):
    return accounts_users.create_user({
        "username": username, "password": password, "permissions": permissions or [],
    })


def _pkce_pair(verifier="a" * 64):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _admin_client(app):
    _create_user("admin", "correct-password-1", permissions=["manage_users"])
    client = app.test_client()
    login = client.post("/api/auth/login", json={"username": "admin", "password": "correct-password-1"})
    return client, login.get_json()["csrf_token"]


def _register_client(client, redirect_uri=REDIRECT_URI, name="Claude"):
    resp = client.post("/oauth/register", json={"client_name": name, "redirect_uris": [redirect_uri]})
    assert resp.status_code == 201, resp.data
    return resp.get_json()["client_id"]


def _authorize_url(client_id, challenge, redirect_uri=REDIRECT_URI, state="xyz"):
    return (f"/oauth/authorize?response_type=code&client_id={client_id}"
            f"&redirect_uri={redirect_uri}&state={state}&code_challenge={challenge}"
            f"&code_challenge_method=S256")


def _flow_id(html_bytes):
    return re.search(rb'name="flow_id" value="([^"]+)"', html_bytes).group(1).decode()


def _complete_grant(app, client_id, verifier, challenge, *, username, password, redirect_uri=REDIRECT_URI):
    """Drives authorize (login + consent) -> token for an approved client,
    using a fresh browser-equivalent client. Returns (access_token, op_client)."""
    op_client = app.test_client()
    start = op_client.get(_authorize_url(client_id, challenge, redirect_uri))
    assert start.status_code == 200
    flow_id = _flow_id(start.data)

    login_resp = op_client.post("/oauth/authorize", data={
        "action": "login", "flow_id": flow_id, "username": username, "password": password})
    assert login_resp.status_code == 200
    assert b"Allow access" in login_resp.data

    consent_resp = op_client.post("/oauth/authorize", data={
        "action": "consent", "flow_id": flow_id, "decision": "allow"})
    assert consent_resp.status_code == 302
    qs = parse_qs(urlparse(consent_resp.headers["Location"]).query)
    assert qs["state"] == ["xyz"]
    code = qs["code"][0]

    token_resp = op_client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id,
        "redirect_uri": redirect_uri, "code": code, "code_verifier": verifier})
    assert token_resp.status_code == 200
    return token_resp.get_json()["access_token"], op_client


# --- metadata -------------------------------------------------------------------

def test_as_metadata_is_reachable_without_auth(app):
    client = app.test_client()
    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["response_types_supported"] == ["code"]
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["token_endpoint_auth_methods_supported"] == ["none"]
    assert body["authorization_endpoint"].endswith("/oauth/authorize")


# --- registration ---------------------------------------------------------------

def test_register_returns_public_client(app):
    client = app.test_client()
    client_id = _register_client(client)
    assert client_id.startswith(oauth_server.CLIENT_ID_PREFIX)


def test_register_rejects_bad_redirect_uri(app):
    client = app.test_client()
    resp = client.post("/oauth/register", json={"client_name": "Evil", "redirect_uris": ["http://evil.test/cb"]})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_client_metadata"


# --- authorize: approval gate, then login -> consent ----------------------------

def test_authorize_refuses_unapproved_client(app):
    client = app.test_client()
    client_id = _register_client(client)
    _verifier, challenge = _pkce_pair()
    resp = client.get(_authorize_url(client_id, challenge))
    assert resp.status_code == 400
    assert b"approved" in resp.data


def test_authorize_rejects_unknown_client(app):
    client = app.test_client()
    _verifier, challenge = _pkce_pair()
    resp = client.get(_authorize_url("oac_does-not-exist", challenge))
    assert resp.status_code == 400
    assert b"Unknown client" in resp.data


def test_authorize_rejects_mismatched_redirect_uri(app):
    admin, csrf = _admin_client(app)
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    op_client = app.test_client()
    _verifier, challenge = _pkce_pair()
    resp = op_client.get(_authorize_url(client_id, challenge, redirect_uri="https://attacker.evil/cb"))
    assert resp.status_code == 400
    assert b"does not match" in resp.data


def test_authorize_requires_s256(app):
    admin, csrf = _admin_client(app)
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    op_client = app.test_client()
    resp = op_client.get(
        f"/oauth/authorize?response_type=code&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}&state=xyz&code_challenge=abc")
    assert resp.status_code == 400
    assert b"S256" in resp.data


def test_full_authorize_consent_token_round_trip(app):
    admin, csrf = _admin_client(app)
    _create_user("alice", "correct-password-2", permissions=[])
    client_id = _register_client(admin)
    approve = admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})
    assert approve.status_code == 200

    verifier, challenge = _pkce_pair()
    access_token, op_client = _complete_grant(
        app, client_id, verifier, challenge, username="alice", password="correct-password-2")
    assert access_token.startswith(mcp_keys.KEY_PREFIX)

    # The minted token works as an ordinary bearer token on an existing route.
    api_resp = op_client.get("/api/mcp-keys", headers={"Authorization": f"Bearer {access_token}"})
    assert api_resp.status_code == 200
    body = api_resp.get_json()
    assert body["scope"] == "own"
    assert body["keys"][0]["label"] == "OAuth: Claude"


def test_consent_deny_redirects_with_error(app):
    admin, csrf = _admin_client(app)
    _create_user("alice", "correct-password-2", permissions=[])
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    _verifier, challenge = _pkce_pair()
    op_client = app.test_client()
    start = op_client.get(_authorize_url(client_id, challenge))
    flow_id = _flow_id(start.data)
    op_client.post("/oauth/authorize", data={
        "action": "login", "flow_id": flow_id, "username": "alice", "password": "correct-password-2"})
    deny = op_client.post("/oauth/authorize", data={"action": "consent", "flow_id": flow_id, "decision": "deny"})
    assert deny.status_code == 302
    qs = parse_qs(urlparse(deny.headers["Location"]).query)
    assert qs["error"] == ["access_denied"]


def test_wrong_password_reprompts_login(app):
    admin, csrf = _admin_client(app)
    _create_user("alice", "correct-password-2", permissions=[])
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    _verifier, challenge = _pkce_pair()
    op_client = app.test_client()
    start = op_client.get(_authorize_url(client_id, challenge))
    flow_id = _flow_id(start.data)
    bad = op_client.post("/oauth/authorize", data={
        "action": "login", "flow_id": flow_id, "username": "alice", "password": "wrong"})
    assert bad.status_code == 200
    assert b"Invalid username or password" in bad.data


def test_expired_flow_id_shows_error(app):
    admin, csrf = _admin_client(app)
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    op_client = app.test_client()
    resp = op_client.post("/oauth/authorize", data={
        "action": "login", "flow_id": "not-a-real-flow", "username": "alice", "password": "x"})
    assert resp.status_code == 400
    assert b"expired" in resp.data


# --- token exchange ---------------------------------------------------------------

def test_token_rejects_reused_code(app):
    admin, csrf = _admin_client(app)
    _create_user("alice", "correct-password-2", permissions=[])
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    verifier, challenge = _pkce_pair()
    _token, op_client = _complete_grant(
        app, client_id, verifier, challenge, username="alice", password="correct-password-2")

    # Replaying the same (already-consumed) code must fail.
    start = op_client.get(_authorize_url(client_id, challenge))
    flow_id = _flow_id(start.data)
    op_client.post("/oauth/authorize", data={
        "action": "login", "flow_id": flow_id, "username": "alice", "password": "correct-password-2"})
    consent = op_client.post("/oauth/authorize", data={"action": "consent", "flow_id": flow_id, "decision": "allow"})
    code = parse_qs(urlparse(consent.headers["Location"]).query)["code"][0]

    first = op_client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id,
        "redirect_uri": REDIRECT_URI, "code": code, "code_verifier": verifier})
    assert first.status_code == 200
    second = op_client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id,
        "redirect_uri": REDIRECT_URI, "code": code, "code_verifier": verifier})
    assert second.status_code == 400
    assert second.get_json()["error"] == "invalid_grant"


def test_token_rejects_client_rejected_after_code_issued(app):
    admin, csrf = _admin_client(app)
    _create_user("alice", "correct-password-2", permissions=[])
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    verifier, challenge = _pkce_pair()
    op_client = app.test_client()
    start = op_client.get(_authorize_url(client_id, challenge))
    flow_id = _flow_id(start.data)
    op_client.post("/oauth/authorize", data={
        "action": "login", "flow_id": flow_id, "username": "alice", "password": "correct-password-2"})
    consent = op_client.post("/oauth/authorize", data={"action": "consent", "flow_id": flow_id, "decision": "allow"})
    code = parse_qs(urlparse(consent.headers["Location"]).query)["code"][0]

    admin.post(f"/api/oauth-clients/{client_id}/reject", headers={"X-CSRF-Token": csrf})

    resp = op_client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id,
        "redirect_uri": REDIRECT_URI, "code": code, "code_verifier": verifier})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_client"


def test_reconnecting_revokes_the_previous_oauth_key(app):
    admin, csrf = _admin_client(app)
    _create_user("alice", "correct-password-2", permissions=[])
    client_id = _register_client(admin)
    admin.post(f"/api/oauth-clients/{client_id}/approve", headers={"X-CSRF-Token": csrf})

    v1, c1 = _pkce_pair("a" * 64)
    first_token, _ = _complete_grant(app, client_id, v1, c1, username="alice", password="correct-password-2")
    v2, c2 = _pkce_pair("b" * 64)
    second_token, op_client = _complete_grant(app, client_id, v2, c2, username="alice", password="correct-password-2")

    assert first_token != second_token
    stale = op_client.get("/api/mcp-keys", headers={"Authorization": f"Bearer {first_token}"})
    assert stale.status_code == 401
    fresh = op_client.get("/api/mcp-keys", headers={"Authorization": f"Bearer {second_token}"})
    assert fresh.status_code == 200


# --- admin approval endpoints: the actual trust boundary --------------------------

def test_non_admin_cannot_list_or_approve_oauth_clients(app):
    _create_user("alice", "correct-password-2", permissions=[])
    client = app.test_client()
    client.post("/api/auth/login", json={"username": "alice", "password": "correct-password-2"})
    client_id = oauth_server.register_client("Claude", [REDIRECT_URI])

    assert client.get("/api/oauth-clients").status_code == 403
    assert client.post(f"/api/oauth-clients/{client_id}/approve").status_code == 403


def test_admin_can_list_pending_clients(app):
    admin, _csrf = _admin_client(app)
    oauth_server.register_client("Claude", [REDIRECT_URI])
    resp = admin.get("/api/oauth-clients")
    assert resp.status_code == 200
    clients = resp.get_json()["clients"]
    assert [c["clientName"] for c in clients] == ["Claude"]
    assert clients[0]["status"] == "pending"
