"""Physical capacity protection across unassigned bookings and PMS assignment."""
import sqlite3

import pandas as pd
import pytest

from app.revenue import yield_engine as engine
from app.revenue.upgrade_reserves import (
    _reserve_with_blocked, load_policy, prepare_capacity, reserve_shortages)

D = 'Deluxe Room'
P = 'Premiere Room'
S = 'Premiere Suite Room'
L = 'Premiere Room Lagoon Access'
DS = 'Deluxe Suite Room'
POLICY = {'routes': {D: [P, L, S], DS: [S], P: [L, S]}}


def snapshot(values, occupancy=90):
    return pd.DataFrame([{
        **dict.fromkeys(engine.ROOM_CAPS, 0), **values,
        'Date': pd.Timestamp('2026-10-01'), 'Occupancy': occupancy,
        'Season': 'Normal', 'DemandLevel': 'High', 'DayOfWeek': 'Thursday',
    }])


def calculate(values, occupancy=90, policy=POLICY, **kwargs):
    return engine.apply_yield_matrix(snapshot(values, occupancy), allocation_policy=policy, **kwargs).iloc[0]


@pytest.mark.parametrize('deluxe,premiere,needed', [(-10, 20, 0), (-10, 3, 7), (-10, -5, 15), (10, -5, 5)])
def test_shortages_cascade_without_downgrading(deluxe, premiere, needed):
    row = calculate({D: deluxe, P: premiere, L: 20}, deluxe_override_amount=0)
    assert row[f'{L} Upgrade Reserve'] == needed
    assert row['Unresolved Upgrade Rooms'] == 0


def test_room_assignment_does_not_double_deduct():
    policy = {'routes': {P: [S]}}
    before = calculate({P: -5, S: 8}, policy=policy)
    after = calculate({P: -4, S: 7}, policy=policy)
    assert before[f'{S} Upgrade Reserve'] == 5
    assert after[f'{S} Upgrade Reserve'] == 4
    assert before[f'{S} Safe Inventory'] == after[f'{S} Safe Inventory'] == 3
    assert before[f'{S} Online Inventory'] == after[f'{S} Online Inventory'] == 2


def test_repeated_calculation_does_not_accumulate_reserves():
    data = snapshot({P: -3, S: 8})
    first = engine.apply_yield_matrix(data, allocation_policy=POLICY).copy()
    second = engine.apply_yield_matrix(data, allocation_policy=POLICY)
    pd.testing.assert_frame_equal(first, second)


def test_last_premiere_cannot_back_both_deluxe_and_premiere_sale():
    row = calculate({D: -31, P: 32})
    assert row['Deluxe Online Inventory'] == 1
    assert row['Premiere Online Inventory'] == 0
    assert row[f'{P} Upgrade Reserve'] == 31
    assert row[f'{P} Override Reserve'] == 1


def test_suite_fallback_reserves_backing_before_direct_release():
    row = calculate({DS: 0, S: 6})
    assert row[f'{DS} Online Inventory'] == 1
    assert row[f'{S} Override Reserve'] == 1
    assert row[f'{S} Online Inventory'] == 2  # remaining five, not raw six


@pytest.mark.parametrize('occupancy', [96.9, 97, 99, 100])
def test_high_occupancy_does_not_close_available_higher_rooms(occupancy):
    row = calculate({S: 5, 'The Anvaya Villa': 1}, occupancy=occupancy,
                    policy={'routes': {DS: []}})
    assert row[f'{S} Online Inventory'] == 2
    assert row['The Anvaya Villa Online Inventory'] == 1


def test_shared_destinations_can_be_rebalanced_for_constrained_guest():
    # First demand prefers X, but the second can ONLY use X. Reroute the first.
    reserved, unresolved = reserve_shortages(
        {'A': 1, 'B': 1}, {'X': 1, 'Y': 1}, {'A': ['X', 'Y'], 'B': ['X']})
    assert reserved == {'X': 1, 'Y': 1}
    assert unresolved == 0


def test_configured_destination_order_is_used_when_capacity_allows():
    row = calculate({P: -5, L: 4, S: 3})
    assert row[f'{L} Upgrade Reserve'] == 4
    assert row[f'{S} Upgrade Reserve'] == 1


@pytest.mark.parametrize('values,policy,closed', [
    ({P: -2, S: 8}, {'routes': {P: []}}, [P]),
    ({P: -1000000, S: 8}, POLICY, [P, L, S]),
])
def test_uncovered_demand_is_visible_and_prevents_new_sales(values, policy, closed):
    row = calculate({D: 20, **values}, policy=policy, include_simple_rooms=True)
    assert row['Unresolved Upgrade Rooms'] > 0
    assert row['Allocation Status'].startswith('Blocked:')
    for room in closed:
        prefix = {D: 'Deluxe', P: 'Premiere'}.get(room, room)
        assert row[f'{prefix} Online Inventory'] == 0
    assert row['Deluxe Online Inventory'] > 0  # cannot help the uncovered guests


def test_uncovered_suite_shortage_does_not_close_deluxe_or_premiere():
    # 2026-10-14: Whirlpool oversold by one with every higher category full.
    row = calculate({D: 36, P: 42, L: 1, S: 4, 'Family Premiere Room': 1,
                     'The Anvaya Suite No Pool': 3, 'The Anvaya Suite Whirpool': -1},
                    occupancy=82.48, policy={}, include_simple_rooms=True)
    assert row['Unresolved Upgrade Rooms'] == 1
    assert row['Allocation Status'].startswith('Blocked:')
    assert 'The Anvaya Suite Whirpool' in row['Allocation Status']
    assert row['Deluxe Online Inventory'] > 0
    assert row['Premiere Online Inventory'] > 0
    assert row[f'{S} Online Inventory'] > 0
    assert row['The Anvaya Suite No Pool Online Inventory'] > 0
    for room in ('The Anvaya Suite Whirpool', 'Beach Front Private Suite Room',
                 'The Anvaya Suite With Pool', 'The Anvaya Residence', 'The Anvaya Villa'):
        assert row[f'{room} Online Inventory'] == 0


@pytest.mark.parametrize('shortages,routes,expected', [
    # A is always covered via Y; only B (X only) can be the short guest.
    ({'A': 1, 'B': 2}, {'A': ['X', 'Y'], 'B': ['X']}, {'B', 'X'}),
    # Either A or B can be left short by rerouting, so both stay closed.
    ({'A': 2, 'B': 1}, {'A': ['X', 'Y'], 'B': ['Y']}, {'A', 'B', 'X', 'Y'}),
])
def test_blocked_rooms_are_every_category_that_could_be_uncovered(shortages, routes, expected):
    _, unresolved, blocked = _reserve_with_blocked(
        shortages, {'X': 1, 'Y': 1, 'Z': 5}, {**routes, 'C': ['Z']})
    assert unresolved == 1
    assert blocked == expected


def test_buffers_manual_holds_and_zero_online_lock():
    policy = {**POLICY, 'buffers': {S: 1}, 'holds': [
        {'room_type': S, 'start_date': '2026-10-01', 'end_date': '2026-10-01', 'rooms': 2},
        {'room_type': L, 'start_date': '2026-10-01', 'end_date': '2026-10-02', 'max_online': 0},
        {'room_type': S, 'start_date': '2026-10-02', 'end_date': '2026-10-03', 'rooms': 99},
    ]}
    row = calculate({S: 8, L: 5}, policy=policy)
    assert row[f'{S} Operational Hold'] == 3
    assert row[f'{L} Online Inventory'] == 0
    assert row[f'{S} Safe Inventory'] == 4  # five less one Deluxe Suite override


def test_manual_zero_override_cap_does_not_waste_destination_capacity():
    policy = {'holds': [{'room_type': D, 'start_date': '2026-10-01',
                         'end_date': '2026-10-01', 'max_online': 0}]}
    row = calculate({D: -31, P: 32}, policy=policy)
    assert row['Deluxe Online Inventory'] == 0
    assert row['Premiere Online Inventory'] == 1
    assert row[f'{P} Override Reserve'] == 0


@pytest.mark.parametrize('policy', [
    {'routes': {P: [D]}}, {'routes': {P: ['typo']}}, {'buffers': {S: -1}},
    {'buffers': {S: 0.5}}, {'routes': {P: [S, S]}}, {'unexpected': True},
    {'holds': [{'room_type': S, 'start_date': '2026-10-02', 'end_date': '2026-10-01'}]},
])
def test_invalid_policy_fails_explicitly(policy):
    with pytest.raises(ValueError):
        load_policy(engine.ROOM_CAPS, policy)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), 1.5])
def test_unknown_or_fractional_inventory_cannot_be_sold(value):
    with pytest.raises(ValueError):
        calculate({S: value})


def test_bar_pricing_is_independent_of_reserve_policy():
    values = {D: -2, P: 20, S: 8}
    a = calculate(values)
    b = calculate(values, policy={'buffers': {P: 20, S: 8}})
    for col in ('Deluxe BAR Rate', 'Premiere BAR Rate'):
        assert a[col] == b[col] == 'BAR3'


def config(all_rooms):
    return {'demand_bins': [0, 70, 85, 100], 'demand_labels': ['Low', 'Medium', 'High'],
            'very_low_threshold_pct': 5, 'low_threshold_pct': 20,
            'room_caps': {D: 160, P: 260}, 'deluxe_override_occupancy': 70,
            'deluxe_override_premiere': 31, 'deluxe_override_amount': 2,
            'include_simple_rooms': all_rooms}


@pytest.mark.parametrize('all_rooms', [False, True])
def test_custom_yield_persists_explanations_and_respects_room_scope(tmp_path, monkeypatch, all_rooms):
    monkeypatch.setattr(engine, 'DATA_DIR', str(tmp_path))
    policy_file = tmp_path / 'policy.json'
    policy_file.write_text('{"routes": {"Premiere Room": ["Premiere Suite Room"]}}')
    monkeypatch.setenv('ALLOCATION_POLICY_PATH', str(policy_file))
    source = snapshot({P: -5, S: 8}, occupancy=99).drop(columns=['Season', 'DemandLevel', 'DayOfWeek'])
    with sqlite3.connect(tmp_path / 'combined_inventory.db') as conn:
        source.to_sql('combined_inventory', conn, index=False)
    result = engine.apply_custom_yield(config(all_rooms))
    with sqlite3.connect(tmp_path / 'inventory_allocation.db') as conn:
        saved = pd.read_sql_query('SELECT * FROM daily_inventory_allocation', conn)
    if all_rooms:
        assert saved.loc[0, f'{S} Upgrade Reserve'] == 5
        assert saved.loc[0, f'{S} Safe Inventory'] == 3
    else:
        assert saved.loc[0, f'{S} Upgrade Reserve'] == 0
    assert saved.loc[0, 'Allocation Status'] == (
        'Ready' if all_rooms else 'Blocked: upgrade capacity or routes insufficient (Premiere Room)')
    assert (f'{S} Online Inventory' in result.columns) == all_rooms
    if all_rooms:
        assert saved.loc[0, f'{S} Online Inventory'] == 2


def test_missing_source_date_values_are_rejected(tmp_path):
    source = snapshot({S: float('nan')}).drop(columns=['Season', 'DemandLevel', 'DayOfWeek'])
    path = tmp_path / 'combined.db'
    with sqlite3.connect(path) as conn:
        source.to_sql('combined_inventory', conn, index=False)
    with pytest.raises(ValueError, match='Incomplete inventory snapshot'):
        engine.load_and_clean_data(str(path))


def test_unrelated_negative_category_does_not_block_deluxe_premiere_only_run():
    row = calculate({D: 20, P: 20, 'The Anvaya Suite With Pool': -1}, policy={}, include_simple_rooms=False)
    assert row['Allocation Status'] == 'Ready'
    assert row['Deluxe Online Inventory'] > 0
    assert row['Premiere Online Inventory'] > 0


def test_null_outside_scope_is_ignored_for_deluxe_premiere_run(tmp_path):
    source = snapshot({D: 20, P: 20, 'The Anvaya Suite With Pool': float('nan')}).drop(
        columns=['Season', 'DemandLevel', 'DayOfWeek'])
    path = tmp_path / 'combined.db'
    with sqlite3.connect(path) as conn:
        source.to_sql('combined_inventory', conn, index=False)
    loaded = engine.load_and_clean_data(
        str(path), required_room_types=[D, P])
    assert loaded['The Anvaya Suite With Pool'].iloc[0] == 0


@pytest.mark.parametrize('source', engine.ROOM_CAPS)
def test_default_routes_follow_hotel_order_and_exceptions(source):
    from app.revenue.upgrade_reserves import ROOM_TIERS
    expected = ROOM_TIERS[ROOM_TIERS.index(source) + 1:]
    if source == L:
        expected = ['The Anvaya Suite Whirpool', 'Beach Front Private Suite Room']
    elif source == 'Beach Front Private Suite Room':
        expected = []
    assert load_policy(engine.ROOM_CAPS, {})['routes'][source] == expected


@pytest.mark.parametrize('source', [L, 'Beach Front Private Suite Room'])
def test_restricted_categories_cannot_indirectly_upgrade_to_villa(source):
    row = calculate({source: -1, 'The Anvaya Villa': 1}, policy={})
    assert row['Unresolved Upgrade Rooms'] == 1
    assert row['The Anvaya Villa Upgrade Reserve'] == 0


@pytest.mark.parametrize('source,destination', [
    (L, 'The Anvaya Villa'), ('Beach Front Private Suite Room', 'The Anvaya Residence'),
    (P, 'Deluxe Pool Access'),
])
def test_custom_policy_cannot_bypass_hotel_restrictions(source, destination):
    with pytest.raises(ValueError, match='restrictions'):
        load_policy(engine.ROOM_CAPS, {'routes': {source: [destination]}})


def test_deluxe_prefers_pool_access_before_premiere():
    row = calculate({D: -2, 'Deluxe Pool Access': 1, P: 2}, policy={}, deluxe_override_amount=0)
    assert row['Deluxe Pool Access Upgrade Reserve'] == 1
    assert row[f'{P} Upgrade Reserve'] == 1


def test_lagoon_uses_only_whirlpool_then_beach_front():
    row = calculate({L: -3, 'The Anvaya Suite Whirpool': 2,
                     'Beach Front Private Suite Room': 2, S: 8}, policy={})
    assert row['The Anvaya Suite Whirpool Upgrade Reserve'] == 2
    assert row['Beach Front Private Suite Room Upgrade Reserve'] == 1
    assert row[f'{S} Upgrade Reserve'] == 0


def test_default_yield_persists_only_deluxe_premiere_with_no_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ALLOCATION_POLICY_PATH', str(tmp_path / 'absent.json'))
    source = snapshot({D: 20, P: 20, 'The Anvaya Suite With Pool': -1,
                       S: float('nan')}).drop(columns=['Season', 'DemandLevel', 'DayOfWeek'])
    with sqlite3.connect(tmp_path / 'combined_inventory.db') as conn:
        source.to_sql('combined_inventory', conn, index=False)
    result = engine.main()
    assert result is not None
    with sqlite3.connect(tmp_path / 'inventory_allocation.db') as conn:
        saved = pd.read_sql_query('SELECT * FROM daily_inventory_allocation', conn)
    assert saved.loc[0, 'Allocation Status'] == 'Ready'
    assert saved.loc[0, 'Deluxe Online Inventory'] > 0
    assert saved.loc[0, 'Premiere Online Inventory'] > 0
    assert not any(f'{room} Online Inventory' in saved.columns for room in engine.SIMPLE_ROOM_TYPES)
