"""Allotment rules: compute_release for all three kinds, settings validation,
and the default seed that reproduces the old hardcoded per-room dispatch."""
import pytest

from app.revenue import allotment_rules as ar


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "get_data_path", lambda name: str(tmp_path / name))
    return tmp_path


# --- compute_release: tiered (replaces get_online_allotment) ----------------

TIERED = {"kind": "tiered", "rows": [
    {"min": 1, "max": 5, "release": 2}, {"min": 6, "max": 10, "release": 5},
    {"min": 11, "max": 50, "release": 10}, {"min": 51, "max": None, "release": 30},
]}


@pytest.mark.parametrize('remaining,release', [
    (-3, 0), (0, 0), (1, 1), (2, 2), (5, 2), (6, 5), (10, 5), (11, 10), (50, 10),
    (51, 30),  # one more room left jumps the release from 10 to 30
    (500, 30),
])
def test_tiered_matches_old_release_buckets(remaining, release):
    assert ar.compute_release(TIERED, remaining, 260) == release


def test_tiered_clamps_to_room_cap():
    assert ar.compute_release(TIERED, 100, 3) == 3


def test_tiered_no_matching_row_releases_zero():
    assert ar.compute_release({"kind": "tiered", "rows": [{"min": 5, "max": None, "release": 1}]}, 3, 10) == 0


# --- compute_release: keepBack (replaces allot_minus_one(_except_one)) ------

def test_keep_back_always_holds_last_room():
    rule = {"kind": "keepBack", "amount": 1, "exceptLast": False}
    assert [ar.compute_release(rule, r, 10) for r in (0, 1, 2, 3)] == [0, 0, 1, 2]


def test_keep_back_except_last_sells_the_final_room():
    rule = {"kind": "keepBack", "amount": 1, "exceptLast": True}
    assert [ar.compute_release(rule, r, 10) for r in (0, 1, 2, 3)] == [0, 1, 1, 2]


# --- compute_release: sellAsRemaining ---------------------------------------

def test_sell_as_remaining():
    rule = {"kind": "sellAsRemaining"}
    assert ar.compute_release(rule, -1, 10) == 0
    assert ar.compute_release(rule, 5, 10) == 5


# --- settings: defaults + persistence ---------------------------------------

def test_default_settings_cover_every_room_type():
    settings = ar.get_settings()
    assert set(settings["releaseRules"]) == ar.ROOM_TYPES
    assert settings["deluxeSuiteBorrow"] == {"fromRoomType": "Premiere Suite Room", "threshold": 3, "amount": 1}
    assert settings["suiteRouting"] == {}


def test_save_and_reload_round_trips():
    settings = ar.get_settings()
    settings["releaseRules"]["Beach Front Private Suite Room"] = {"kind": "keepBack", "amount": 2, "exceptLast": True}
    ar.save_settings(settings)
    reloaded = ar.get_settings()
    assert reloaded["releaseRules"]["Beach Front Private Suite Room"]["amount"] == 2


# --- validation --------------------------------------------------------------

def _valid():
    return {
        "releaseRules": {room: {"kind": "sellAsRemaining"} for room in ar.ROOM_TYPES},
        "deluxeSuiteBorrow": {"fromRoomType": "Premiere Suite Room", "threshold": 3, "amount": 1},
        "suiteRouting": {},
    }


def test_validate_rejects_missing_room_type():
    data = _valid()
    del data["releaseRules"]["Deluxe Room"]
    with pytest.raises(ar.ValidationError):
        ar.validate_settings(data)


def test_validate_rejects_unknown_room_type():
    data = _valid()
    data["releaseRules"]["Not A Room"] = {"kind": "sellAsRemaining"}
    with pytest.raises(ar.ValidationError):
        ar.validate_settings(data)


def test_validate_rejects_unknown_kind():
    data = _valid()
    data["releaseRules"]["Deluxe Room"] = {"kind": "mystery"}
    with pytest.raises(ar.ValidationError):
        ar.validate_settings(data)


def test_validate_rejects_overlapping_tiered_rows():
    data = _valid()
    data["releaseRules"]["Deluxe Room"] = {"kind": "tiered", "rows": [
        {"min": 1, "max": 10, "release": 1}, {"min": 5, "max": 20, "release": 2}]}
    with pytest.raises(ar.ValidationError, match="overlap"):
        ar.validate_settings(data)


def test_validate_rejects_non_last_row_with_unbounded_max():
    data = _valid()
    data["releaseRules"]["Deluxe Room"] = {"kind": "tiered", "rows": [
        {"min": 1, "max": None, "release": 1}, {"min": 5, "max": 10, "release": 2}]}
    with pytest.raises(ar.ValidationError, match="unbounded"):
        ar.validate_settings(data)


def test_validate_rejects_deluxe_suite_borrowing_from_itself():
    data = _valid()
    data["deluxeSuiteBorrow"]["fromRoomType"] = "Deluxe Suite Room"
    with pytest.raises(ar.ValidationError):
        ar.validate_settings(data)


def test_validate_delegates_suite_routing_to_load_policy():
    data = _valid()
    # Beach Front Private Suite Room has no upgrade destinations by hotel rule.
    data["suiteRouting"] = {"routes": {"Beach Front Private Suite Room": ["The Anvaya Villa"]}}
    with pytest.raises(ar.ValidationError, match="restrictions"):
        ar.validate_settings(data)


def test_validate_accepts_a_valid_suite_routing_override():
    data = _valid()
    data["suiteRouting"] = {"buffers": {"Deluxe Room": 2}}
    clean = ar.validate_settings(data)
    assert clean["suiteRouting"] == {"buffers": {"Deluxe Room": 2}}
