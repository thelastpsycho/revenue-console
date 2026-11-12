"""Verify the API fails closed, protects writes, and enforces per-user permissions."""
import pytest

from app import create_app
from app.accounts import users as accounts_users


@pytest.fixture(autouse=True)
def user_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts_users, "get_data_path", lambda name: str(tmp_path / name))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("APP_SESSION_SECRET", "b" * 48)
    monkeypatch.delenv("ALLOW_INSECURE_LOCAL_DEV", raising=False)
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
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


def test_api_locked_when_unconfigured(monkeypatch):
    for name in ("APP_SESSION_SECRET", "ALLOW_INSECURE_LOCAL_DEV"):
        monkeypatch.delenv(name, raising=False)
    application = create_app()
    application.testing = True
    client = application.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/pipeline/status").status_code == 503
    assert client.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 503


def test_login_csrf_logout_and_protected_get(app):
    _create_user()
    client = app.test_client()
    assert client.get("/api/pipeline/status").status_code == 401
    assert client.post("/api/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    csrf = sign_in(client)
    assert client.get("/api/pipeline/status").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert client.get("/api/pipeline/status").status_code == 401


def test_invalid_session_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_SESSION_SECRET", "too-short")
    monkeypatch.delenv("ALLOW_INSECURE_LOCAL_DEV", raising=False)
    with pytest.raises(RuntimeError):
        create_app()


def test_unsafe_dev_requires_explicit_local_flag(monkeypatch):
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)
    monkeypatch.setenv("ALLOW_INSECURE_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    remote = create_app().test_client()
    assert remote.get("/api/pipeline/status").status_code == 503
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    local = create_app().test_client()
    assert local.get("/api/pipeline/status").status_code == 200


def test_dev_mode_has_every_permission(monkeypatch):
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)
    monkeypatch.setenv("ALLOW_INSECURE_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    client = create_app().test_client()
    # manage_users-gated route works without logging in at all.
    assert client.get("/api/users").status_code == 200


def test_permission_gated_route_requires_the_right_permission(app):
    _create_user("alice", "correct-password-1", permissions=[])
    _create_user("bob", "correct-password-2", permissions=["manage_users"])

    no_access = app.test_client()
    sign_in(no_access, "alice", "correct-password-1")
    assert no_access.get("/api/users").status_code == 403

    has_access = app.test_client()
    sign_in(has_access, "bob", "correct-password-2")
    assert has_access.get("/api/users").status_code == 200


def test_inactive_user_is_logged_out(app):
    user = _create_user()
    client = app.test_client()
    sign_in(client)
    accounts_users.update_user(user["id"], {"isActive": False})
    assert client.get("/api/pipeline/status").status_code == 401
