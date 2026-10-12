"""Yield engine rules that decide what goes online, pinned so a change is deliberate.

Covers the release buckets, per-suite holdback, demand/season/BAR boundaries,
the Deluxe override, capacity invariants over random snapshots, and the
manual Calculate yield action.
"""
import contextlib
import io
import random
import sqlite3

import pandas as pd
import pytest

from app import create_app
from app.pipeline import fast_runner
from app.revenue import yield_engine as engine
from app.routes import main as main_routes

D = 'Deluxe Room'
P = 'Premiere Room'
DS = 'Deluxe Suite Room'
PS = 'Premiere Suite Room'
WHIRL = 'The Anvaya Suite Whirpool'
SUITES_ABOVE_WHIRL = ['Beach Front Private Suite Room', 'The Anvaya Suite With Pool',
                      'The Anvaya Residence', 'The Anvaya Villa']


def online_column(room):
    prefix = {D: 'Deluxe', P: 'Premiere'}.get(room, room)
    return f'{prefix} Online Inventory'


def calculate(values, occupancy=80, season='Normal', demand='Medium', date='2026-10-01',
              policy=None, **kwargs):
    row = {**dict.fromkeys(engine.ROOM_CAPS, 0), **values, 'Date': pd.Timestamp(date),
           'Occupancy': occupancy, 'Season': season, 'DemandLevel': demand, 'DayOfWeek': 'x'}
    kwargs.setdefault('include_simple_rooms', True)
    with contextlib.redirect_stdout(io.StringIO()):
        return engine.apply_yield_matrix(
            pd.DataFrame([row]), allocation_policy=policy or {}, **kwargs).iloc[0]


def load(tmp_path, rows):
    path = tmp_path / 'combined.db'
    frame = pd.DataFrame([{**dict.fromkeys(engine.ROOM_CAPS, 1), **row} for row in rows])
    with sqlite3.connect(path) as conn:
        frame.to_sql('combined_inventory', conn, index=False)
    with contextlib.redirect_stdout(io.StringIO()):
        return engine.load_and_clean_data(str(path))


# --- Release rules -----------------------------------------------------------

@pytest.mark.parametrize('remaining,online', [
    (-3, 0), (0, 0), (1, 1), (2, 2), (5, 2), (6, 5), (10, 5), (11, 10), (50, 10),
    (51, 30),  # one more room left jumps the release from 10 to 30
    (500, 30),
])
def test_deluxe_premiere_release_buckets(remaining, online):
    assert engine.get_online_allotment(remaining, 260) == online


@pytest.mark.parametrize('room,by_remaining', [
    # The three mid suites always keep their last room back...
    ('Family Premiere Room', {1: 0, 2: 1, 3: 2}),
    (WHIRL, {1: 0, 2: 1, 3: 2}),
    ('The Anvaya Suite No Pool', {1: 0, 2: 1, 3: 2}),
    # ...Beach Front keeps one back except its very last room...
    ('Beach Front Private Suite Room', {1: 1, 2: 1, 3: 2}),
    # ...and the top categories, the final upgrade destinations, sell out.
    ('The Anvaya Suite With Pool', {1: 1, 2: 2}),
    ('The Anvaya Residence', {1: 1}),
    ('The Anvaya Villa', {1: 1}),
    (DS, {1: 1, 3: 2, 4: 3, 5: 4}),
    (PS, {1: 1, 5: 2, 6: 5}),
    ('Deluxe Pool Access', {1: 1, 5: 2, 11: 10}),
    ('Premiere Room Lagoon Access', {1: 1, 5: 2, 11: 10}),
])
def test_suite_release_rules(room, by_remaining):
    for remaining, online in by_remaining.items():
        # Deluxe Suite keeps one room so it doesn't borrow from Premiere Suite.
        row = calculate({DS: 1, room: remaining, D: 20, P: 20})
        assert row[online_column(room)] == online, (room, remaining)


def test_deluxe_suite_sells_one_borrowed_room_only_when_premiere_suite_has_more_than_three():
    assert calculate({DS: 0, PS: 3})[online_column(DS)] == 0
    row = calculate({DS: 0, PS: 6})
    assert row[online_column(DS)] == 1
    assert row[f'{PS} Override Reserve'] == 1
    # The borrowed room comes out of Premiere Suite's own release: 5 left -> 2, not 6 -> 5.
    assert row[online_column(PS)] == 2


# --- Demand, season, BAR -----------------------------------------------------

def test_demand_level_boundaries_are_right_inclusive_and_overbooking_is_high(tmp_path):
    occupancies = [0, 70, 70.01, 85, 85.01, 100, 104]
    data = load(tmp_path, [{'Date': f'2026-10-{i + 1:02d}', 'Occupancy': occ}
                           for i, occ in enumerate(occupancies)])
    assert list(data['DemandLevel'].astype(str)) == [
        'Low', 'Low', 'Medium', 'Medium', 'High', 'High', 'High']
    assert data['Occupancy'].iloc[-1] == 104  # real value kept for display


@pytest.mark.parametrize('date,season', [
    ('2026-12-22', 'Normal'), ('2026-12-23', 'High'), ('2026-12-26', 'High'),
    ('2026-12-27', 'Peak'), ('2027-01-03', 'Peak'), ('2027-01-04', 'Normal'),
    ('2027-06-30', 'Normal'), ('2027-07-01', 'High'), ('2027-08-31', 'High'),
    ('2027-09-01', 'Normal'),
])
def test_season_boundaries(tmp_path, date, season):
    assert load(tmp_path, [{'Date': date, 'Occupancy': 50}])['Season'].iloc[0] == season


def test_leap_day_does_not_crash_the_yield_step(tmp_path):
    assert load(tmp_path, [{'Date': '2028-02-29', 'Occupancy': 50}])['Season'].iloc[0] == 'Normal'


@pytest.mark.parametrize('remaining,expected', [
    (100, 'BAR5'),  # Normal/Medium base
    (32, 'BAR4'),   # <= 20% of 160: one step up
    (8, 'BAR3'),    # <= 5% of 160: two steps up
    (-5, 'BAR3'),
])
def test_bar_escalates_with_scarcity(remaining, expected):
    assert calculate({D: remaining, P: 200})['Deluxe BAR Rate'] == expected


@pytest.mark.parametrize('season,ceiling', [('Normal', 'BAR3'), ('High', 'BAR2'), ('Peak', 'BAR2')])
def test_bar2_is_reserved_for_high_and_peak_seasons(season, ceiling):
    row = calculate({D: 0, P: 0}, season=season, demand='High', bar_level_shift=5)
    assert row['Deluxe BAR Rate'] == row['Premiere BAR Rate'] == ceiling


def test_bar_level_shift_is_clamped_at_bar7():
    row = calculate({D: 100, P: 200}, demand='Low', bar_level_shift=-5)
    assert row['Deluxe BAR Rate'] == 'BAR7'


def test_zero_scarcity_thresholds_disable_escalation():
    row = calculate({D: 8, P: 200}, very_low_threshold_pct=0.0, low_threshold_pct=0.0)
    assert row['Deluxe BAR Rate'] == 'BAR5'


# --- Deluxe override ---------------------------------------------------------

@pytest.mark.parametrize('occupancy,deluxe,premiere,opens', [
    (69.9, 0, 20, True),     # quiet day
    (70, 0, 20, False),      # threshold is strict
    (90, 0, 62, True),       # Premiere still plentiful
    (90, 0, 61, False),
    (60, 1, 20, False),      # Deluxe not sold out
    (60, -3, 3, False),      # nothing left across both
])
def test_deluxe_override_trigger_with_pipeline_settings(occupancy, deluxe, premiere, opens):
    assert engine.should_override_deluxe(occupancy, premiere, deluxe, 70, 61) is opens


def test_deluxe_override_borrows_from_premiere_before_premiere_release():
    row = calculate({D: 0, P: 12}, occupancy=60, deluxe_override_occupancy=70,
                    deluxe_override_premiere=61, deluxe_override_amount=2)
    assert row['Deluxe Online Inventory'] == 2
    assert row[f'{P} Override Reserve'] == 2
    assert row['Premiere Online Inventory'] == engine.get_online_allotment(10, 260)


def test_deluxe_override_cannot_borrow_from_blocked_premiere():
    # Premiere oversold with nothing above it: Premiere is blocked, so the
    # override has nothing to back it and Deluxe stays closed.
    row = calculate({D: 0, P: -1}, occupancy=60, deluxe_override_amount=2)
    assert row['Unresolved Upgrade Rooms'] == 1
    assert row['Deluxe Online Inventory'] == 0
    assert row[f'{P} Override Reserve'] == 0


# --- Blocking scope ----------------------------------------------------------

def test_blocked_suite_closes_itself_and_every_room_above_only():
    row = calculate({D: 30, P: 30, WHIRL: -1, 'The Anvaya Suite No Pool': 3, PS: 4})
    for room in [WHIRL] + SUITES_ABOVE_WHIRL:
        assert row[online_column(room)] == 0
    for room in (D, P, 'The Anvaya Suite No Pool', PS):
        assert row[online_column(room)] > 0


def test_covered_shortage_keeps_the_date_ready():
    row = calculate({D: 30, P: 30, WHIRL: -1, 'The Anvaya Villa': 1})
    assert row['Allocation Status'] == 'Ready'
    assert row['The Anvaya Villa Upgrade Reserve'] == 1
    assert row['The Anvaya Villa Online Inventory'] == 0  # its only room is spoken for


# --- Invariants over random snapshots ----------------------------------------

def random_snapshot(rng):
    values = {}
    for room, cap in engine.ROOM_CAPS.items():
        values[room] = rng.randint(-min(cap, 5), cap if cap < 20 else 60)
    return values


@pytest.mark.parametrize('seed', range(300))
def test_online_never_exceeds_physical_capacity(seed):
    rng = random.Random(seed)
    values = random_snapshot(rng)
    row = calculate(values, occupancy=rng.choice([40, 69, 75, 90, 99]),
                    deluxe_override_occupancy=70, deluxe_override_premiere=61,
                    deluxe_override_amount=2)
    blocked = row['Allocation Status'] != 'Ready'
    assert (row['Unresolved Upgrade Rooms'] > 0) == blocked
    for room, remaining in values.items():
        online = row[online_column(room)]
        assert online >= 0, room
        committed = (row[f'{room} Upgrade Reserve'] + row[f'{room} Override Reserve']
                     + (0 if room in (D, DS) and remaining <= 0 else online))
        # Nothing promised (upgrades, borrowed sales, direct sales) beyond what is physically free.
        assert committed <= max(0, remaining), (room, remaining, committed)
    # Borrowed sales are fully backed by reserves in their destinations.
    if values[D] <= 0:
        assert row['Deluxe Online Inventory'] == row[f'{P} Override Reserve']
    if values[DS] <= 0:
        backing = sum(row[f'{room} Override Reserve'] for room in engine.ROOM_CAPS if room not in (D, P))
        assert row[online_column(DS)] == backing


@pytest.mark.parametrize('seed', range(100))
def test_calculation_is_deterministic(seed):
    values = random_snapshot(random.Random(seed))
    assert calculate(values).equals(calculate(values))


# --- Manual "Calculate yield" ------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ACCESS_PIN", "123456")
    monkeypatch.setenv("APP_SESSION_SECRET", "b" * 48)
    monkeypatch.delenv("ALLOW_INSECURE_LOCAL_DEV", raising=False)
    monkeypatch.setattr(main_routes, 'get_data_path', lambda name: str(tmp_path / name))
    (tmp_path / 'combined_inventory.db').touch()
    application = create_app()
    application.testing = True
    c = application.test_client()
    csrf = c.post("/api/auth/login", json={"pin": "123456"}).get_json()["csrf_token"]
    c.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
    return c


def test_manual_yield_uses_the_pipeline_settings(client, monkeypatch, tmp_path):
    pipeline_yield = {'deluxe_override_premiere': 61, 'include_simple_rooms': True}
    monkeypatch.setattr(main_routes.fast_pipeline_schedule, 'get_state',
                        lambda: {'effectiveConfig': {'yieldConfig': pipeline_yield}})
    received = []

    def fake_apply(config):
        received.append(config)
        with sqlite3.connect(tmp_path / 'inventory_allocation.db') as conn:
            conn.execute('CREATE TABLE daily_inventory_allocation (Date TEXT)')
            conn.execute("INSERT INTO daily_inventory_allocation VALUES ('2026-10-14')")
        return pd.DataFrame([{'Date': '2026-10-14'}])
    monkeypatch.setattr(main_routes, 'apply_custom_yield', fake_apply)

    response = client.post('/api/yield')
    assert response.status_code == 200, response.get_json()
    assert received == [pipeline_yield]


def test_manual_yield_refuses_without_pipeline_settings(client, monkeypatch):
    monkeypatch.setattr(main_routes.fast_pipeline_schedule, 'get_state', lambda: {'effectiveConfig': None})
    monkeypatch.setattr(main_routes, 'apply_custom_yield', lambda config: pytest.fail('must not run'))
    assert client.post('/api/yield').status_code == 400


@pytest.mark.parametrize('path', ['/api/yield', '/api/custom-yield'])
def test_manual_yield_waits_for_a_running_scheduled_pipeline(client, monkeypatch, path):
    monkeypatch.setattr(fast_runner, 'pipeline_active', True)
    monkeypatch.setattr(main_routes, 'apply_custom_yield', lambda config: pytest.fail('must not run'))
    assert client.post(path, json={}).status_code == 409
