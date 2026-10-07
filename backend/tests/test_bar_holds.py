"""BAR hold dates: validation, auto-expiry, and update_bar leaving held dates
untouched (neither pushed nor recorded as applied)."""
import json
from datetime import date

import pytest

from app.integrations.dedge import bar_checkpoint, bar_holds, bar_updater

TODAY = date(2026, 10, 7)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    path = lambda name: str(tmp_path / name)
    monkeypatch.setattr(bar_holds, "get_data_path", path)
    monkeypatch.setattr(bar_checkpoint, "get_data_path", path)
    monkeypatch.setattr(bar_holds, "_today", lambda: TODAY)
    monkeypatch.setattr(bar_updater, "LAST_APPLIED_PATH", path("bar_last_applied.json"))
    return tmp_path


def test_rooms_match_bar_updater():
    assert set(bar_holds.ROOMS) == set(bar_updater.ROOM_CONFIG)


def test_add_list_remove():
    hold = bar_holds.add_hold({"start": "2026-10-20", "end": "2026-10-22", "note": " Wedding "})
    assert hold["rooms"] == ["deluxe", "premiere"] and hold["note"] == "Wedding"
    assert [h["id"] for h in bar_holds.list_holds()] == [hold["id"]]
    assert bar_holds.remove_hold(hold["id"]) is True
    assert bar_holds.remove_hold(hold["id"]) is False
    assert bar_holds.list_holds() == []


def test_single_day_hold_defaults_end_to_start():
    hold = bar_holds.add_hold({"start": "2026-10-20", "rooms": ["premiere"]})
    assert hold["end"] == "2026-10-20"
    assert bar_holds.held_dates_by_room(("deluxe", "premiere")) == {"deluxe": set(), "premiere": {"2026-10-20"}}


def test_past_holds_drop_off():
    bar_holds.add_hold({"start": "2026-10-07", "end": "2026-10-08"})
    assert bar_holds.list_holds(today=date(2026, 10, 8))
    assert bar_holds.list_holds(today=date(2026, 10, 9)) == []


@pytest.mark.parametrize("payload", [
    {},
    {"start": "20-10-2026"},
    {"start": "2026-10-22", "end": "2026-10-20"},
    {"start": "2026-10-01", "end": "2026-10-05"},
    {"start": "2026-10-20", "end": "2027-12-31"},
    {"start": "2026-10-20", "rooms": []},
    {"start": "2026-10-20", "rooms": ["suite"]},
    {"start": "2026-10-20", "rooms": "deluxe"},
    {"start": "2026-10-20", "note": "x" * 201},
])
def test_invalid_holds_are_rejected(payload):
    with pytest.raises(bar_holds.HoldValidationError):
        bar_holds.add_hold(payload)
    assert bar_holds.list_holds() == []


def test_update_bar_skips_held_dates_and_does_not_record_them(monkeypatch, data_dir):
    rows = [{"Date": f"2026-10-{d:02d}", "Deluxe BAR Rate": "BAR3", "Premiere BAR Rate": "BAR4"}
            for d in range(10, 16)]
    periods = []
    monkeypatch.setattr(bar_updater, "log", lambda *a, **k: None)
    monkeypatch.setattr(bar_updater, "ensure_logged_in", lambda *a, **k: True)
    monkeypatch.setattr(bar_updater, "load_allocation_rows", lambda: rows)
    monkeypatch.setattr(bar_updater, "_open_apply_form", lambda d: None)
    monkeypatch.setattr(bar_updater, "_select_only", lambda *a: None)
    monkeypatch.setattr(bar_updater, "_apply_price_level", lambda d: None)

    def define_period(driver, chunk, level):
        periods.append([(s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")) for s, e in chunk])
    monkeypatch.setattr(bar_updater, "define_period", define_period)

    bar_holds.add_hold({"start": "2026-10-12", "end": "2026-10-13", "rooms": ["deluxe"]})
    assert bar_updater.update_bar(driver=object(), rooms=("deluxe", "premiere")) is True

    # Deluxe is split around the hold; Premiere is pushed in full.
    assert periods == [
        [("2026-10-10", "2026-10-11"), ("2026-10-14", "2026-10-15")],
        [("2026-10-10", "2026-10-15")],
    ]
    applied = json.loads((data_dir / "bar_last_applied.json").read_text())
    assert sorted(applied["deluxe"]) == ["2026-10-10", "2026-10-11", "2026-10-14", "2026-10-15"]
    assert len(applied["premiere"]) == 6

    # After the hold is removed, only the held dates are still to push.
    bar_holds.remove_hold(bar_holds.list_holds()[0]["id"])
    periods.clear()
    assert bar_updater.update_bar(driver=object(), rooms=("deluxe", "premiere")) is True
    assert periods == [[("2026-10-12", "2026-10-13")]]
