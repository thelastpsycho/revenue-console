"""Operator accounts: CRUD validation, password hashing, and the
self-lockout guards that stop an admin from locking everyone out."""
import pytest

from app.accounts import users


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "get_data_path", lambda name: str(tmp_path / name))
    return tmp_path


def _create(username="alice", password="correct-password-1", **extra):
    return users.create_user({"username": username, "password": password, **extra})


def test_create_and_list_round_trip():
    user = _create(displayName="Alice", permissions=["run_pms_scrape"])
    assert user["username"] == "alice"
    assert user["displayName"] == "Alice"
    assert user["permissions"] == ["run_pms_scrape"]
    assert user["isActive"] is True
    assert "_passwordHash" not in user
    assert [u["id"] for u in users.list_users()] == [user["id"]]


def test_display_name_defaults_to_username():
    user = _create()
    assert user["displayName"] == "alice"


def test_duplicate_username_rejected_case_insensitively():
    _create(username="Alice")
    with pytest.raises(users.ValidationError):
        _create(username="alice")


def test_short_password_rejected():
    with pytest.raises(users.ValidationError):
        _create(password="short")


def test_unknown_permission_rejected():
    with pytest.raises(users.ValidationError):
        _create(permissions=["not_a_real_permission"])


def test_invalid_username_rejected():
    with pytest.raises(users.ValidationError):
        _create(username="a b!")


def test_verify_login_round_trip_and_records_last_login():
    user = _create(password="correct-password-1")
    assert users.get_user(user["id"])["lastLoginAt"] is None

    assert users.verify_login("alice", "wrong-password") is None
    logged_in = users.verify_login("ALICE", "correct-password-1")
    assert logged_in is not None and logged_in["id"] == user["id"]
    assert users.get_user(user["id"])["lastLoginAt"] is not None


def test_verify_login_rejects_inactive_user():
    user = _create()
    users.update_user(user["id"], {"isActive": False})
    assert users.verify_login("alice", "correct-password-1") is None


def test_update_user_fields():
    user = _create(permissions=["run_pms_scrape"])
    updated = users.update_user(user["id"], {"displayName": "Alice A", "permissions": ["manage_users"]})
    assert updated["displayName"] == "Alice A"
    assert updated["permissions"] == ["manage_users"]


def test_update_user_can_reset_password():
    user = _create(password="correct-password-1")
    users.update_user(user["id"], {"password": "a-new-password-2"})
    assert users.verify_login("alice", "correct-password-1") is None
    assert users.verify_login("alice", "a-new-password-2") is not None


def test_update_missing_user_returns_none():
    assert users.update_user(999, {"displayName": "Ghost"}) is None


def test_cannot_remove_own_manage_users_permission():
    user = _create(permissions=["manage_users"])
    with pytest.raises(users.ValidationError):
        users.update_user(user["id"], {"permissions": []}, current_user_id=user["id"])
    # An admin editing someone else can still remove it.
    other = users.update_user(user["id"], {"permissions": []}, current_user_id=999)
    assert other["permissions"] == []


def test_cannot_deactivate_own_account():
    user = _create()
    with pytest.raises(users.ValidationError):
        users.update_user(user["id"], {"isActive": False}, current_user_id=user["id"])


def test_cannot_delete_own_account():
    user = _create()
    with pytest.raises(users.ValidationError):
        users.delete_user(user["id"], current_user_id=user["id"])
    assert users.get_user(user["id"]) is not None


def test_delete_user():
    user = _create()
    assert users.delete_user(user["id"], current_user_id=999) is True
    assert users.get_user(user["id"]) is None
    assert users.delete_user(999, current_user_id=1) is False


def test_change_own_password_requires_current_password():
    user = _create(password="correct-password-1")
    with pytest.raises(users.ValidationError):
        users.change_own_password(user["id"], "wrong-password", "a-new-password-2")
    users.change_own_password(user["id"], "correct-password-1", "a-new-password-2")
    assert users.verify_login("alice", "a-new-password-2") is not None


def test_any_users_exist():
    assert users.any_users_exist() is False
    _create()
    assert users.any_users_exist() is True
