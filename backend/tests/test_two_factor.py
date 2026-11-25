"""TOTP two-factor auth: self-service setup/disable, the two-step login
flow, the brute-force attempt cap, and the admin reset recovery path."""
import pyotp
import pytest

from app import create_app
from app.accounts import mcp_keys, two_factor
from app.accounts import users as accounts_users


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts_users, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(mcp_keys, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setenv("APP_SESSION_SECRET", "b" * 48)
    return tmp_path


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_LOCAL_DEV", raising=False)
    application = create_app()
    application.testing = True
    return application


def _create_user(username="alice", password="correct-password-1", permissions=None):
    return accounts_users.create_user({
        "username": username, "password": password, "permissions": permissions or [],
    })


def _enable_totp(user_id):
    """Drives the real begin/confirm setup functions end-to-end and returns
    the secret, so tests can compute live codes with pyotp."""
    secret, qr_data_uri = accounts_users.begin_totp_setup(user_id)
    assert qr_data_uri.startswith("data:image/png;base64,")
    accounts_users.confirm_totp_setup(user_id, pyotp.TOTP(secret).now())
    return secret


def sign_in(client, username="alice", password="correct-password-1"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# ---- accounts.users TOTP functions ------------------------------------------

def test_setup_is_pending_until_confirmed():
    user = _create_user()
    secret, _ = accounts_users.begin_totp_setup(user["id"])
    assert accounts_users.get_user(user["id"])["twoFactorEnabled"] is False
    accounts_users.confirm_totp_setup(user["id"], pyotp.TOTP(secret).now())
    assert accounts_users.get_user(user["id"])["twoFactorEnabled"] is True


def test_confirm_with_wrong_code_rejected_and_leaves_disabled():
    user = _create_user()
    accounts_users.begin_totp_setup(user["id"])
    with pytest.raises(accounts_users.ValidationError):
        accounts_users.confirm_totp_setup(user["id"], "000000")
    assert accounts_users.get_user(user["id"])["twoFactorEnabled"] is False


def test_confirm_without_pending_setup_rejected():
    user = _create_user()
    with pytest.raises(accounts_users.ValidationError):
        accounts_users.confirm_totp_setup(user["id"], "123456")


def test_disable_requires_correct_password():
    user = _create_user()
    secret = _enable_totp(user["id"])
    with pytest.raises(accounts_users.ValidationError):
        accounts_users.disable_totp(user["id"], "wrong-password")
    assert accounts_users.get_user(user["id"])["twoFactorEnabled"] is True
    accounts_users.disable_totp(user["id"], "correct-password-1")
    assert accounts_users.get_user(user["id"])["twoFactorEnabled"] is False
    assert accounts_users.verify_totp(user["id"], pyotp.TOTP(secret).now()) is False


def test_admin_reset_clears_totp_unconditionally():
    user = _create_user()
    _enable_totp(user["id"])
    assert accounts_users.admin_reset_totp(user["id"]) is True
    assert accounts_users.get_user(user["id"])["twoFactorEnabled"] is False


def test_admin_reset_on_missing_user_returns_false():
    assert accounts_users.admin_reset_totp(999) is False


# ---- login flow --------------------------------------------------------

def test_login_without_2fa_is_unchanged(app):
    _create_user()
    client = app.test_client()
    response = sign_in(client)
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"


def test_login_with_2fa_requires_a_second_step(app):
    user = _create_user()
    secret = _enable_totp(user["id"])
    client = app.test_client()

    first = sign_in(client)
    assert first.status_code == 200
    assert first.get_json()["status"] == "totp_required"
    # Not authenticated yet - no session user_id set.
    assert client.get("/api/pipeline/status").status_code == 401

    wrong = client.post("/api/auth/login-totp", json={"code": "000000"})
    assert wrong.status_code == 401

    correct = client.post("/api/auth/login-totp", json={"code": pyotp.TOTP(secret).now()})
    assert correct.status_code == 200
    assert correct.get_json()["status"] == "success"
    assert client.get("/api/pipeline/status").status_code == 200


def test_login_totp_without_pending_login_rejected(app):
    client = app.test_client()
    response = client.post("/api/auth/login-totp", json={"code": "123456"})
    assert response.status_code == 401


def test_login_totp_locks_out_after_too_many_attempts(app):
    user = _create_user()
    _enable_totp(user["id"])
    client = app.test_client()
    sign_in(client)

    # The Nth wrong attempt is the one that trips the cap and clears the
    # pending state, so only N-1 plain "invalid code" responses precede it.
    for _ in range(auth_routes_max_attempts() - 1):
        response = client.post("/api/auth/login-totp", json={"code": "000000"})
        assert response.status_code == 401
        assert response.get_json().get("locked") is not True

    locked = client.post("/api/auth/login-totp", json={"code": "000000"})
    assert locked.status_code == 401
    assert locked.get_json().get("locked") is True
    # The pending state is gone - even the right code no longer works.
    assert client.post("/api/auth/login-totp", json={"code": "000000"}).status_code == 401


def auth_routes_max_attempts():
    from app.routes.auth_routes import MAX_TOTP_ATTEMPTS
    return MAX_TOTP_ATTEMPTS


# ---- admin reset route ---------------------------------------------------

def test_reset_2fa_route_requires_manage_users(app):
    target = _create_user("alice", "correct-password-1")
    _enable_totp(target["id"])
    _create_user("bob", "correct-password-2", permissions=[])

    no_access = app.test_client()
    csrf = sign_in(no_access, "bob", "correct-password-2").get_json()["csrf_token"]
    response = no_access.post(f"/api/users/{target['id']}/reset-2fa", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 403
    assert accounts_users.get_user(target["id"])["twoFactorEnabled"] is True


def test_reset_2fa_route_clears_two_factor(app):
    target = _create_user("alice", "correct-password-1")
    _enable_totp(target["id"])
    _create_user("admin", "correct-password-2", permissions=["manage_users"])

    client = app.test_client()
    csrf = sign_in(client, "admin", "correct-password-2").get_json()["csrf_token"]
    response = client.post(f"/api/users/{target['id']}/reset-2fa", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert accounts_users.get_user(target["id"])["twoFactorEnabled"] is False


# ---- two_factor module ---------------------------------------------------

def test_encrypt_decrypt_round_trip():
    secret = two_factor.generate_secret()
    token = two_factor.encrypt(secret)
    assert token != secret
    assert two_factor.decrypt(token) == secret


def test_verify_code_accepts_current_code_and_rejects_garbage():
    secret = two_factor.generate_secret()
    assert two_factor.verify_code(secret, pyotp.TOTP(secret).now()) is True
    assert two_factor.verify_code(secret, "000000") is False
    assert two_factor.verify_code(secret, "") is False


# ---- trusted devices ------------------------------------------------------

def test_trusted_device_round_trip_and_wrong_token_rejected():
    user = _create_user()
    token = accounts_users.create_trusted_device(user["id"])
    assert accounts_users.verify_trusted_device(user["id"], token) is True
    assert accounts_users.verify_trusted_device(user["id"], "not-the-token") is False
    assert accounts_users.verify_trusted_device(999, token) is False


def test_disable_totp_revokes_trusted_devices():
    user = _create_user()
    _enable_totp(user["id"])
    token = accounts_users.create_trusted_device(user["id"])
    accounts_users.disable_totp(user["id"], "correct-password-1")
    assert accounts_users.verify_trusted_device(user["id"], token) is False


def test_admin_reset_totp_revokes_trusted_devices():
    user = _create_user()
    _enable_totp(user["id"])
    token = accounts_users.create_trusted_device(user["id"])
    accounts_users.admin_reset_totp(user["id"])
    assert accounts_users.verify_trusted_device(user["id"], token) is False


def test_remembered_device_skips_totp_step_on_next_login(app):
    user = _create_user()
    secret = _enable_totp(user["id"])
    client = app.test_client()

    sign_in(client)
    code = pyotp.TOTP(secret).now()
    remembered = client.post("/api/auth/login-totp", json={"code": code, "rememberDevice": True})
    assert remembered.status_code == 200
    logout_csrf = remembered.get_json()["csrf_token"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": logout_csrf})
    assert client.get("/api/pipeline/status").status_code == 401

    # Same client (same cookie jar) logs in again - wrong password still
    # fails, and a correct password skips straight past the TOTP step.
    assert sign_in(client, password="wrong-password").status_code == 401
    second = sign_in(client)
    assert second.status_code == 200
    assert second.get_json()["status"] == "success"
    assert client.get("/api/pipeline/status").status_code == 200


def test_login_totp_without_remember_does_not_set_cookie(app):
    user = _create_user()
    secret = _enable_totp(user["id"])
    client = app.test_client()
    sign_in(client)
    response = client.post("/api/auth/login-totp", json={"code": pyotp.TOTP(secret).now()})
    assert "rc_trusted_device" not in response.headers.get("Set-Cookie", "")


# ---- mandatory 2FA for flagged accounts -----------------------------------

def _create_user_requiring_2fa(username="alice", password="correct-password-1"):
    return accounts_users.create_user({
        "username": username, "password": password, "permissions": [],
        "twoFactorRequired": True,
    })


def test_account_can_opt_into_required_2fa_via_create_and_update():
    created = _create_user_requiring_2fa()
    assert created["twoFactorRequired"] is True
    updated = accounts_users.update_user(created["id"], {"twoFactorRequired": False})
    assert updated["twoFactorRequired"] is False


def test_required_2fa_blocks_other_routes_until_enrolled(app):
    _create_user_requiring_2fa()
    client = app.test_client()
    login = sign_in(client)
    assert login.status_code == 200
    assert login.get_json()["user"]["twoFactorSetupRequired"] is True

    blocked = client.get("/api/pipeline/status")
    assert blocked.status_code == 403
    assert blocked.get_json()["twoFactorSetupRequired"] is True

    # Still reachable while blocked: status, setup/confirm, change-password, logout.
    assert client.get("/api/auth/status").status_code == 200
    csrf = login.get_json()["csrf_token"]
    setup = client.post("/api/auth/2fa/setup", headers={"X-CSRF-Token": csrf})
    assert setup.status_code == 200
    code = pyotp.TOTP(setup.get_json()["secret"]).now()
    confirm = client.post("/api/auth/2fa/confirm", json={"code": code}, headers={"X-CSRF-Token": csrf})
    assert confirm.status_code == 200

    # Enrolled now - the rest of the API opens back up.
    assert client.get("/api/pipeline/status").status_code == 200


def test_account_without_required_flag_is_unaffected(app):
    _create_user()
    client = app.test_client()
    sign_in(client)
    assert client.get("/api/pipeline/status").status_code == 200
