"""Personal API keys: module-level CRUD/auth plus the self-service routes
(list own, create, revoke - admin sees/revokes everyone's)."""
import pytest

from app import create_app
from app.accounts import mcp_keys, users as accounts_users


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_keys, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(accounts_users, "get_data_path", lambda name: str(tmp_path / name))
    return tmp_path


# --- module: create / list / revoke / authenticate --------------------------

def test_create_returns_record_and_plaintext_token_once():
    record, token = mcp_keys.create_key(7, "laptop")
    assert record["userId"] == 7
    assert record["label"] == "laptop"
    assert record["revokedAt"] is None
    assert token.startswith(mcp_keys.KEY_PREFIX)
    # The stored record never carries the plaintext or its hash.
    assert "key_hash" not in record and "token" not in record


def test_blank_label_rejected():
    with pytest.raises(mcp_keys.ValidationError):
        mcp_keys.create_key(1, "   ")


def test_list_keys_for_user_excludes_other_users():
    mcp_keys.create_key(1, "mine")
    mcp_keys.create_key(2, "someone else's")
    assert [k["label"] for k in mcp_keys.list_keys_for_user(1)] == ["mine"]
    assert len(mcp_keys.list_all_keys()) == 2


def test_authenticate_round_trips_and_records_last_used():
    record, token = mcp_keys.create_key(3, "key")
    assert mcp_keys.list_keys_for_user(3)[0]["lastUsedAt"] is None
    assert mcp_keys.authenticate(token) == 3
    assert mcp_keys.list_keys_for_user(3)[0]["lastUsedAt"] is not None


def test_authenticate_rejects_wrong_or_missing_token():
    mcp_keys.create_key(1, "key")
    assert mcp_keys.authenticate("not-a-real-token") is None
    assert mcp_keys.authenticate("") is None


def test_revoked_key_no_longer_authenticates():
    record, token = mcp_keys.create_key(1, "key")
    assert mcp_keys.authenticate(token) == 1
    assert mcp_keys.revoke_key(record["id"]) is True
    assert mcp_keys.authenticate(token) is None


def test_revoke_is_scoped_to_the_owner_unless_admin():
    record, _ = mcp_keys.create_key(1, "key")
    assert mcp_keys.revoke_key(record["id"], user_id=2) is False
    assert mcp_keys.revoke_key(record["id"], user_id=1) is True


def test_revoke_missing_key_returns_false():
    assert mcp_keys.revoke_key(999) is False


# --- routes -------------------------------------------------------------------

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


def sign_in(client, username="alice", password="correct-password-1"):
    result = client.post("/api/auth/login", json={"username": username, "password": password})
    assert result.status_code == 200
    return result.get_json()["csrf_token"]


def test_create_list_and_revoke_own_key(app):
    _create_user()
    client = app.test_client()
    csrf = sign_in(client)

    created = client.post("/api/mcp-keys", json={"label": "my laptop"}, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 200
    body = created.get_json()
    assert body["apiKey"].startswith(mcp_keys.KEY_PREFIX)
    key_id = body["key"]["id"]

    listed = client.get("/api/mcp-keys")
    assert listed.status_code == 200
    listed_body = listed.get_json()
    assert listed_body["scope"] == "own"
    assert [k["id"] for k in listed_body["keys"]] == [key_id]

    revoked = client.post(f"/api/mcp-keys/{key_id}/revoke", headers={"X-CSRF-Token": csrf})
    assert revoked.status_code == 200
    assert mcp_keys.authenticate(body["apiKey"]) is None


def test_non_admin_cannot_see_or_revoke_someone_elses_key(app):
    alice = _create_user("alice", "correct-password-1", permissions=[])
    other_record, _ = mcp_keys.create_key(alice["id"] + 999, "someone else's")

    client = app.test_client()
    csrf = sign_in(client)

    listed = client.get("/api/mcp-keys?scope=all")
    # Not an admin: scope=all is silently ignored, falls back to "own" (empty).
    assert listed.get_json()["scope"] == "own"
    assert listed.get_json()["keys"] == []

    revoked = client.post(f"/api/mcp-keys/{other_record['id']}/revoke", headers={"X-CSRF-Token": csrf})
    assert revoked.status_code == 404


def test_admin_can_list_and_revoke_any_key(app):
    admin = _create_user("admin", "correct-password-1", permissions=["manage_users"])
    other = _create_user("bob", "correct-password-2", permissions=[])
    other_record, _ = mcp_keys.create_key(other["id"], "bob's key")

    client = app.test_client()
    csrf = sign_in(client, "admin", "correct-password-1")

    listed = client.get("/api/mcp-keys?scope=all")
    body = listed.get_json()
    assert body["scope"] == "all"
    assert [k["ownerUsername"] for k in body["keys"]] == ["bob"]

    revoked = client.post(f"/api/mcp-keys/{other_record['id']}/revoke", headers={"X-CSRF-Token": csrf})
    assert revoked.status_code == 200
