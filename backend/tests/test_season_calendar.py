"""Season calendar: CRUD validation, tier-rank overlap resolution, and the
one-time migration seed that reproduces the old hardcoded season rule."""
from datetime import date

import pytest

from app.revenue import season_calendar as sc


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "get_data_path", lambda name: str(tmp_path / name))
    return tmp_path


def test_empty_table_is_seeded_with_migration_defaults():
    periods = sc.list_periods()
    assert periods  # seeded on first use
    assert any(p["tier"] == "Peak" and p["startDate"] == "2026-12-27" for p in periods)
    assert any(p["tier"] == "High" and p["startDate"] == "2026-07-01" for p in periods)


def test_seed_does_not_extend_past_the_configured_range():
    periods = sc.list_periods()
    assert max(int(p["startDate"][:4]) for p in periods) == sc.SEED_YEARS[-1]


def test_table_is_not_reseeded_once_populated():
    before = len(sc.list_periods())
    sc.delete_period(sc.list_periods()[0]["id"])
    after = len(sc.list_periods())
    assert after == before - 1  # re-querying does not top the table back up


def test_add_period_round_trips():
    period = sc.add_period({"label": "Nyepi 2027", "startDate": "2027-03-26", "endDate": "2027-03-26",
                            "tier": "Peak"})
    assert period["label"] == "Nyepi 2027"
    assert period["tier"] == "Peak"
    assert any(p["id"] == period["id"] for p in sc.list_periods())


def test_add_period_rejects_missing_label():
    with pytest.raises(sc.ValidationError):
        sc.add_period({"label": "", "startDate": "2027-03-26", "endDate": "2027-03-26", "tier": "Peak"})


def test_add_period_rejects_end_before_start():
    with pytest.raises(sc.ValidationError):
        sc.add_period({"label": "x", "startDate": "2027-03-26", "endDate": "2027-03-25", "tier": "Peak"})


def test_add_period_rejects_bad_date_format():
    with pytest.raises(sc.ValidationError):
        sc.add_period({"label": "x", "startDate": "26/03/2027", "endDate": "2027-03-26", "tier": "Peak"})


def test_add_period_rejects_unknown_tier():
    with pytest.raises(sc.ValidationError):
        sc.add_period({"label": "x", "startDate": "2027-03-26", "endDate": "2027-03-26", "tier": "Mid"})


def test_overlapping_periods_allowed_and_not_rejected():
    first = sc.add_period({"label": "A", "startDate": "2027-07-10", "endDate": "2027-07-20", "tier": "High"})
    second = sc.add_period({"label": "B", "startDate": "2027-07-15", "endDate": "2027-07-25", "tier": "Peak"})
    ids = {p["id"] for p in sc.list_periods()}
    assert {first["id"], second["id"]} <= ids


def test_update_period_returns_none_for_missing_id():
    assert sc.update_period(999999, {"label": "x", "startDate": "2027-01-01", "endDate": "2027-01-01",
                                     "tier": "Peak"}) is None


def test_delete_period_returns_false_for_missing_id():
    assert sc.delete_period(999999) is False


# --- tier_for_date / build_lookup --------------------------------------------

def _periods(*rows):
    """rows: (start, end, tier) with parsed date objects, matching build_lookup's shape."""
    return [{"startDate": s, "endDate": e, "tier": t,
             "_start": date.fromisoformat(s), "_end": date.fromisoformat(e)}
            for s, e, t in rows]


def test_tier_for_date_defaults_to_normal_outside_any_period():
    periods = _periods(("2027-07-01", "2027-08-31", "High"))
    assert sc.tier_for_date(date(2027, 6, 30), periods) == "Normal"


def test_tier_for_date_matches_covering_period():
    periods = _periods(("2027-07-01", "2027-08-31", "High"))
    assert sc.tier_for_date(date(2027, 7, 15), periods) == "High"


def test_tier_for_date_highest_tier_wins_on_overlap():
    periods = _periods(("2027-07-10", "2027-07-20", "High"), ("2027-07-15", "2027-07-25", "Peak"))
    assert sc.tier_for_date(date(2027, 7, 17), periods) == "Peak"
    # Outside the Peak range but still inside the High range.
    assert sc.tier_for_date(date(2027, 7, 12), periods) == "High"


def test_shoulder_beats_normal_but_loses_to_high():
    periods = _periods(("2027-05-01", "2027-05-31", "Shoulder"), ("2027-05-10", "2027-05-20", "High"))
    assert sc.tier_for_date(date(2027, 5, 5), periods) == "Shoulder"
    assert sc.tier_for_date(date(2027, 5, 15), periods) == "High"
    assert sc.tier_for_date(date(2027, 6, 1), periods) == "Normal"


def test_build_lookup_round_trips_through_tier_for_date():
    sc.add_period({"label": "Nyepi 2027", "startDate": "2027-03-26", "endDate": "2027-03-26", "tier": "Peak"})
    periods = sc.build_lookup()
    assert sc.tier_for_date(date(2027, 3, 26), periods) == "Peak"
    assert sc.tier_for_date(date(2027, 3, 27), periods) == "Normal"
