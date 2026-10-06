"""UI-managed schedule: preview mode can never push BAR or live allotments,
due-run claiming, interval re-anchoring, and input validation."""
import json
from datetime import timedelta

import pytest

from app.pipeline import fast_pipeline_schedule as sched

_DEFAULT = {
    "steps": {"scrape_pms": True, "bar": True},
    "barRooms": ["deluxe", "premiere"],
    "allotmentRoomTypes": ["deluxe", "premiere"],
    "yieldConfig": {"room_caps": {"Deluxe Room": 160, "Premiere Room": 260}},
    "headless": False,
}
_ENV = {"PMS_USERNAME": "p", "PMS_PASSWORD": "pp", "DEDGE_USERNAME": "d", "DEDGE_PASSWORD": "dd"}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    (tmp_path / sched.DEFAULT_CONFIG_FILE).write_text(json.dumps(_DEFAULT))
    monkeypatch.setattr(sched, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(sched, "_scheduler_last_seen", None)
    return tmp_path


def _acquire_ok():
    return True, None


def test_defaults_are_disabled_preview():
    state = sched.get_state()
    assert state["enabled"] is False
    assert state["live"] is False
    assert state["configSource"] == "default"
    assert state["effectiveConfig"]["barRooms"] == ["deluxe", "premiere"]
    assert "headless" not in state["effectiveConfig"]


def test_preview_forces_bar_off_and_allotment_dry_run():
    state = dict(sched._DEFAULT_STATE, live=False)
    config = sched.build_run_config(state, env=_ENV)
    assert config["allotmentDryRun"] is True
    assert config["barRooms"] == []
    assert config["steps"]["bar"] is False
    assert config["trigger"] == "schedule"
    assert config["scheduleMode"] == "preview"


def test_preview_overrides_a_saved_config_that_enables_bar():
    state = dict(sched._DEFAULT_STATE, live=False,
                 config={"steps": {"bar": True}, "barRooms": ["deluxe"], "yieldConfig": {}})
    config = sched.build_run_config(state, env=_ENV)
    assert config["barRooms"] == []
    assert config["steps"]["bar"] is False


def test_live_keeps_configured_bar_rooms_and_pushes_allotment():
    state = dict(sched._DEFAULT_STATE, live=True)
    config = sched.build_run_config(state, env=_ENV)
    assert config["allotmentDryRun"] is False
    assert config["barRooms"] == ["deluxe", "premiere"]
    assert config["steps"]["bar"] is True
    assert config["pmsPassword"] == "pp"
    assert config["resetCheckpoint"] is False
    assert config["headless"] is None


def test_build_does_not_mutate_stored_config():
    stored = {"steps": {"bar": True}, "yieldConfig": {}}
    sched.build_run_config(dict(sched._DEFAULT_STATE, live=False, config=stored), env=_ENV)
    assert stored == {"steps": {"bar": True}, "yieldConfig": {}}


def test_enabling_makes_a_run_due_immediately_and_claim_advances_next_run():
    sched.update_settings({"enabled": True, "intervalMinutes": 30})
    config, reason = sched.claim_due_run(_acquire_ok)
    assert config is not None and reason is None
    state = sched.get_state()
    last, nxt = sched._parse(state["lastRunAt"]), sched._parse(state["nextRunAt"])
    assert nxt - last == timedelta(minutes=30)
    # Not due again until the interval passes.
    config, reason = sched.claim_due_run(_acquire_ok)
    assert config is None and reason.startswith("next run at")


def test_disabled_schedule_never_claims():
    config, reason = sched.claim_due_run(_acquire_ok)
    assert config is None and reason == "schedule disabled"


def test_busy_pipeline_leaves_run_due_for_next_tick():
    sched.update_settings({"enabled": True})
    before = sched.get_state()["nextRunAt"]
    config, reason = sched.claim_due_run(lambda: (False, "A run is already in progress"))
    assert config is None and reason == "A run is already in progress"
    assert sched.get_state()["nextRunAt"] == before
    assert sched.get_state()["lastRunAt"] is None


def test_config_error_does_not_acquire_pipeline_lock(data_dir):
    sched.update_settings({"enabled": True})
    (data_dir / sched.DEFAULT_CONFIG_FILE).unlink()
    acquired = []
    with pytest.raises(OSError):
        sched.claim_due_run(lambda: acquired.append(1) or (True, None))
    assert acquired == []


def test_claim_records_scheduler_heartbeat():
    assert sched.get_state()["schedulerOnline"] is False
    sched.claim_due_run(_acquire_ok)
    assert sched.get_state()["schedulerOnline"] is True


def test_interval_change_reanchors_on_last_run():
    sched.update_settings({"enabled": True, "intervalMinutes": 60})
    sched.claim_due_run(_acquire_ok)
    last = sched._parse(sched.get_state()["lastRunAt"])
    sched.update_settings({"intervalMinutes": 120})
    assert sched._parse(sched.get_state()["nextRunAt"]) - last == timedelta(minutes=120)


def test_disabling_clears_next_run():
    sched.update_settings({"enabled": True})
    sched.update_settings({"enabled": False})
    assert sched.get_state()["nextRunAt"] is None


def test_saved_config_is_used_and_can_be_reverted():
    saved = {"steps": {"bar": False}, "barRooms": ["deluxe"], "yieldConfig": {"x": 1}}
    state = sched.update_settings({"config": saved})
    assert state["configSource"] == "custom"
    assert state["effectiveConfig"] == saved
    assert state["configSavedAt"]
    state = sched.update_settings({"config": None})
    assert state["configSource"] == "default"
    assert state["configSavedAt"] is None


@pytest.mark.parametrize("payload", [
    {"intervalMinutes": 1},
    {"intervalMinutes": 24 * 60 + 1},
    {"intervalMinutes": "soon"},
    {"live": "yes"},
    {"enabled": 1},
    {"config": {"yieldConfig": {}, "pmsPassword": "x"}},
    {"config": {"steps": {}}},
    {"config": {"yieldConfig": {}, "barRooms": "deluxe"}},
])
def test_invalid_updates_are_rejected_and_not_saved(payload):
    with pytest.raises(sched.ScheduleValidationError):
        sched.update_settings(payload)
    assert sched.get_state()["intervalMinutes"] == 60
    assert sched.get_state()["live"] is False
