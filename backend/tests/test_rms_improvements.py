"""Regression coverage for observed history, honest comparisons and cached reports."""
import copy
import json
from datetime import date

import pytest

from app.revenue import booking_events as be, rms_forecast as fc, rms_workspace as ws
from test_rms import api_row, client  # authenticated Flask fixture


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(be, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(fc, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 1))
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    return tmp_path


def test_amendments_preserve_old_dates_rates_and_dimensions(monkeypatch):
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-03", rate=1000000)])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 8))
    be.upsert([api_row(1, "2026-09-01", "2027-01-01", "2027-01-02", rate=2000000, type_id="PRKG", market_id=9)])
    before = be.on_the_books("2026-12-01", "2026-12-02", "2026-10-01", room_type="DLT", market_id=8)
    assert before["2026-12-01"]["revenue"] == 1000000
    assert be.on_the_books("2026-12-01", "2026-12-02", "2026-10-08") == {}
    assert be.on_the_books("2027-01-01", "2027-01-01", "2026-10-01") == {}
    assert be.on_the_books("2027-01-01", "2027-01-01", "2026-10-08", room_type="PRKG")["2027-01-01"]["revenue"] == 2000000
    row = be.pace_table("2026-12-01", "2026-12-01")[0]
    assert (row["newRooms"], row["cancelledRooms"], row["amendedRooms"], row["pickupRooms"]) == (0, 0, -1, -1)


def test_reinstatement_does_not_erase_cancellation_history(monkeypatch):
    base = api_row(1, "2026-09-01", "2026-12-01", "2026-12-02")
    be.upsert([base])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 2))
    be.upsert([{**base, "ReservationStatus": "L", "UpdatedDate": "2026-10-02T01:00:00+00:00"}])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 3))
    be.upsert([base])
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-02") == {}
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-03")["2026-12-01"]["rooms"] == 1


def test_versions_idempotent_and_no_pii(isolated):
    row = api_row(1, "2026-09-01", "2026-12-01", "2026-12-02")
    be.upsert([row]); be.upsert([row])
    with be._db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM booking_versions").fetchone()[0] == 1
        dump = '\n'.join(conn.iterdump())
    assert "Jane Guest" not in dump and "jane@example.com" not in dump


def test_cancellation_and_new_pickup_reconcile(monkeypatch):
    base = api_row(1, "2026-09-01", "2026-12-01", "2026-12-02")
    be.upsert([base])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 8))
    be.upsert([{**base, "ReservationStatus": "L", "UpdatedDate": "2026-10-05T01:00:00+00:00"},
               api_row(2, "2026-10-05", "2026-12-01", "2026-12-02")])
    r = be.pace_table("2026-12-01", "2026-12-01")[0]
    assert (r["newRooms"], r["cancelledRooms"], r["amendedRooms"]) == (1, 1, 0)
    assert r["pickupRooms"] == r["newRooms"] - r["cancelledRooms"] + r["amendedRooms"] == 0


def test_daily_refresh_revisits_old_bookings_and_long_inhouse_stays():
    be.upsert([api_row(1, "2026-01-01", "2026-07-01", "2026-10-20")])
    jobs = be.plan("daily", today=date(2026, 10, 1))
    arrivals = [(s, e) for mode, s, e in jobs if mode == "ARRIVAL_DATE"]
    assert min(s for s, e in arrivals) == date(2026, 7, 1)
    assert max(e for s, e in arrivals) == date(2027, 10, 1)
    assert all((e - s).days < 30 for s, e in arrivals)


def test_missing_coverage_is_null_not_zero():
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2026-09-01")
    r = be.pace_table("2026-12-01", "2026-12-01")[0]
    assert r["comparisonQuality"] == "unavailable"
    assert r["stlyRooms"] is None and r["lyFinalRooms"] is None
    assert r["rooms"] == 0


def test_old_history_marked_estimated():
    be.upsert([api_row(1, "2025-01-01", "2025-12-02", "2025-12-03")])
    r = be.pace_table("2026-12-01", "2026-12-01")[0]
    assert r["comparisonQuality"] == "estimated"


def test_curve_stops_today_and_all_future_curve_is_empty():
    curve = be.pace_curve("2026-10-20", max_lead=30)
    assert min(p["lead"] for p in curve["current"]) == 19
    assert all(p["asOf"] <= "2026-10-01" for p in curve["current"])
    assert be.pace_curve("2027-12-01", max_lead=30)["current"] == []


def test_comparison_modes_handle_leap_day_and_custom_event():
    assert be.comparison_date(date(2024, 2, 29), "calendar") == date(2023, 2, 28)
    assert be.comparison_date(date(2026, 10, 20), "weekday") == date(2025, 10, 21)
    assert be.comparison_date(date(2026, 10, 20), "custom", "2025-11-01", "2026-10-18") == date(2025, 11, 3)
    with pytest.raises(ValueError): be.comparison_date(date(2026, 10, 20), "custom")


def test_non_idr_currency_never_added_to_idr():
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02", currency="EUR", rate=100)])
    r = be.on_the_books("2026-12-01", "2026-12-01", "2026-10-01")["2026-12-01"]
    assert (r["rooms"], r["idrRooms"], r["revenue"], r["netRevenue"]) == (1, 0, 0, 0)


def test_rate_rules_override_default_by_stay_date_and_type():
    settings = ws.get_settings()
    settings["revenueRules"].append({"rateType": "BAR", "from": "2026-12-01", "to": "2026-12-31", "breakfast": 0, "taxService": 0})
    ws.save_settings(settings)
    be.upsert([api_row(1, "2026-09-01", "2026-11-30", "2026-12-02", rate=1210000)])
    r = be.on_the_books("2026-11-30", "2026-12-01", "2026-10-01")
    assert r["2026-12-01"]["netRevenue"] == 1210000
    assert r["2026-11-30"]["netRevenue"] == pytest.approx((1210000-350000)/1.21)


@pytest.mark.parametrize("value", [float('nan'), float('inf'), -1, True])
def test_settings_reject_nonfinite_or_invalid_threshold(value):
    settings = ws.get_settings(); settings["thresholds"]["occupancy"] = value
    with pytest.raises(ValueError): ws.save_settings(settings)


def test_notes_settings_validation_and_auth(client):
    assert client.put('/api/rms/notes/2026-12-01', json={"text": "Review pickup"}).status_code == 200
    assert ws.notes("2026-12-01", "2026-12-01")["2026-12-01"]["text"] == "Review pickup"
    assert client.put('/api/rms/notes/invalid', json={"text": "x"}).status_code == 400
    assert client.put('/api/rms/settings', json=[]).status_code == 400
    assert client.get('/api/rms/pace?marketId=invalid').status_code == 400
    assert client.get('/api/rms/pace?comparison=custom').status_code == 400
    assert client.get('/api/rms/forecast?days=0').status_code == 400
    client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert client.put('/api/rms/notes/2026-12-01', json={"text": "x"}).status_code == 403


class DeferredThread:
    jobs = []
    def __init__(self, target, args, **kwargs): self.target, self.args = target, args
    def start(self): self.jobs.append((self.target, self.args))


def test_forecast_cache_returns_sections_and_deduplicates_refresh(monkeypatch):
    DeferredThread.jobs = []
    monkeypatch.setattr(fc.threading, "Thread", DeferredThread)
    monkeypatch.setattr(fc, "fetch_section", lambda *a: [{"date": "2026-10-01"}])
    first = fc.cached_forecast(date(2026, 10, 1), 7)
    assert all(s["refreshing"] for s in first["sections"].values())
    assert len(DeferredThread.jobs) == 4
    fc.cached_forecast(date(2026, 10, 1), 7)
    assert len(DeferredThread.jobs) == 4
    for target, args in DeferredThread.jobs: target(*args)
    ready = fc.cached_forecast(date(2026, 10, 1), 7)
    assert ready["hotel"] == [{"date": "2026-10-01"}]
    assert all(s["loaded"] and not s["stale"] and not s["refreshing"] for s in ready["sections"].values())


def test_failed_refresh_preserves_stale_payload_without_poll_retry(monkeypatch):
    DeferredThread.jobs = []
    monkeypatch.setattr(fc.threading, "Thread", DeferredThread)
    def fail(*args): raise RuntimeError("provider detail")
    monkeypatch.setattr(fc, "fetch_section", fail)
    with fc._cache_db() as conn:
        conn.execute("INSERT INTO forecast_cache(key,payload,fetched) VALUES (?,?,?)", ("2026-10-01:7:hotel", '[{"roomsSold":5}]', 1))
    first = fc.cached_forecast(date(2026, 10, 1), 7)
    assert first["hotel"] == [{"roomsSold": 5}]
    for target, args in DeferredThread.jobs: target(*args)
    count = len(DeferredThread.jobs)
    failed = fc.cached_forecast(date(2026, 10, 1), 7)
    assert len(DeferredThread.jobs) == count
    assert failed["hotel"] == first["hotel"]
    assert "provider detail" not in failed["sections"]["hotel"]["error"]
    fc.cached_forecast(date(2026, 10, 1), 7, force=True)
    assert len(DeferredThread.jobs) == count + 4


def test_version_history_cache_does_not_leak_across_databases(tmp_path, monkeypatch):
    """version_history() caches the whole table keyed by (db path, max row
    id) so repeat requests skip re-reading it - but two different databases
    that happen to reach the same row count must not be treated as the same
    cache entry, or one tenant's/test's data would leak into another's."""
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    dir_a.mkdir(); dir_b.mkdir()

    monkeypatch.setattr(be, "get_data_path", lambda name: str(dir_a / name))
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02")])
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-01")["2026-12-01"]["rooms"] == 1

    monkeypatch.setattr(be, "get_data_path", lambda name: str(dir_b / name))
    be.upsert([api_row(1, "2026-09-01", "2027-01-01", "2027-01-02")])  # same row count, different dates
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-01") == {}
    assert be.on_the_books("2027-01-01", "2027-01-01", "2026-10-01")["2027-01-01"]["rooms"] == 1


def test_final_reflects_same_day_state_not_a_later_cancellation(monkeypatch):
    """lyFinalRooms is "as observed on the stay date itself" - a cancellation
    recorded after that date must not erase that day's actuals, even though
    the reservation is cancelled in every state queried after that point."""
    monkeypatch.setattr(be, "_today", lambda: date(2025, 9, 1))
    be.upsert([api_row(1, "2025-09-01", "2025-10-21", "2025-10-22")])
    monkeypatch.setattr(be, "_today", lambda: date(2025, 10, 25))
    be.upsert([{**api_row(1, "2025-09-01", "2025-10-21", "2025-10-22"), "ReservationStatus": "L",
               "UpdatedDate": "2025-10-25T01:00:00+00:00"}])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 11))
    row = be.pace_table("2026-10-20", "2026-10-20")[0]
    assert row["lyDate"] == "2025-10-21"
    assert row["rooms"] == 0           # cancelled as of today
    assert row["lyFinalRooms"] == 1    # but still on the books as of the stay date itself


def test_final_reflects_an_amendment_observed_before_the_stay_date(monkeypatch):
    """An amendment recorded before the stay date had already happened by
    then, so lyFinalRooms/Revenue should use the amended version, not the
    original one - multi-version history, not just the single-version case."""
    monkeypatch.setattr(be, "_today", lambda: date(2025, 9, 1))
    be.upsert([api_row(1, "2025-09-01", "2025-10-21", "2025-10-22", rate=1000000)])
    monkeypatch.setattr(be, "_today", lambda: date(2025, 10, 10))
    be.upsert([api_row(1, "2025-09-01", "2025-10-21", "2025-10-22", rate=1500000)])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 11))
    row = be.pace_table("2026-10-20", "2026-10-20")[0]
    assert row["lyDate"] == "2025-10-21"
    assert row["lyFinalRevenue"] == 1500000


def test_late_discovery_does_not_rewrite_observed_history(monkeypatch):
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02")])
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 8))
    be.upsert([api_row(2, "2026-09-01", "2026-12-01", "2026-12-02")])
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-01")["2026-12-01"]["rooms"] == 1
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-08")["2026-12-01"]["rooms"] == 2


def test_package_rule_is_applied_only_to_matching_rate_id():
    settings = ws.get_settings()
    settings["revenueRules"].append({"rateType": "BAR", "rateId": "ROOM-ONLY", "from": "2026-01-01", "to": "2026-12-31", "breakfast": 0, "taxService": 0})
    ws.save_settings(settings)
    row = api_row(1, "2026-09-01", "2026-12-01", "2026-12-02", rate=1210000)
    be.upsert([{**row, "RateId": "ROOM-ONLY"}])
    assert be.on_the_books("2026-12-01", "2026-12-01", "2026-10-01")["2026-12-01"]["netRevenue"] == 1210000


def test_settings_require_baseline_and_reject_overlapping_rules():
    settings = ws.get_settings()
    settings["revenueRules"][0]["from"] = "2026-01-01"
    with pytest.raises(ValueError, match="baseline"): ws.save_settings(settings)
    settings = ws.get_settings()
    settings["revenueRules"].append(copy.deepcopy(settings["revenueRules"][0]))
    with pytest.raises(ValueError, match="overlap"): ws.save_settings(settings)
