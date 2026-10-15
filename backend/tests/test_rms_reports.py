from datetime import date

import pytest

from app.revenue import booking_events as be
from app.revenue.rms_reports import build_reports, pickup_by_dimension, room_rate_breakdown
from test_rms import api_row, client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(be, 'get_data_path', lambda name: str(tmp_path / name))
    monkeypatch.setattr(be, '_today', lambda: date(2026, 10, 1))
    with be._db() as conn:
        be._set_meta(conn, 'backfillFrom', '2023-01-01')


def test_segment_and_room_type_production_reconcile_with_total():
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-04'),
               api_row(2, '2026-09-01', '2026-12-02', '2026-12-05', type_id='PRKG', market_id=9, currency='USD', rate=100)])
    report = build_reports('2026-12-02', '2026-12-03')
    assert sum(r['rooms'] for r in report['production']['market']) == 4
    assert sum(r['rooms'] for r in report['production']['roomType']) == 4
    assert sum(r['idrRooms'] for r in report['production']['market']) == 2
    assert sum(r['revenue'] for r in report['production']['market']) == 2000000
    assert report['behaviour']['bookings'] == 2
    assert report['behaviour']['averageLengthOfStay'] == 3


def test_segment_move_is_amendment_and_pickup_reconciles(monkeypatch):
    row = api_row(1, '2026-09-01', '2026-12-01', '2026-12-03')
    be.upsert([row])
    monkeypatch.setattr(be, '_today', lambda: date(2026, 10, 8))
    be.upsert([{**row, 'MarketId': 9, 'MarketDescription': 'Corporate'}])
    report = build_reports('2026-12-01', '2026-12-02')
    by_id = {r['id']: r for r in report['production']['market']}
    assert by_id['8']['amendedRooms'] == -2
    assert by_id['9']['amendedRooms'] == 2
    assert sum(r['pickup']['7']['rooms'] for r in by_id.values()) == 0
    for r in by_id.values():
        assert r['newRooms'] - r['cancelledRooms'] + r['amendedRooms'] == r['pickup']['7']['rooms']


def test_behaviour_counts_once_and_booking_date_cohort_differs():
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-05'),
               api_row(2, '2026-09-01', '2026-12-01', '2026-12-02', status='L'),
               api_row(3, '2026-09-01', '2026-12-01', '2026-12-02', status='N')])
    r = build_reports('2026-12-01', '2026-12-04')['behaviour']
    assert r['bookings'] == 1 and r['allBookings'] == 3
    assert sum(b['bookings'] for b in r['lengthOfStay']) == 1
    assert r['losses'][0]['cancelled'] == 1 and r['losses'][0]['noShows'] == 1
    assert build_reports('2026-09-01', '2026-09-01', date_basis='booking')['behaviour']['bookings'] == 1
    assert build_reports('2026-09-01', '2026-09-01')['behaviour']['bookings'] == 0


def test_missing_history_is_unavailable_and_unknown_market_retained():
    with be._db() as conn:
        be._set_meta(conn, 'backfillFrom', '2026-09-01')
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02', market_id=None)])
    r = build_reports('2026-12-01', '2026-12-01')['production']['market'][0]
    assert r['id'] == 'unassigned' and r['rooms'] == 1
    assert r['comparison'] is None and r['comparisonQuality'] == 'unavailable'


def test_reports_route_validates_and_honours_room_filter(client):
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02')])
    url = '/api/rms/reports?start=2026-12-01&end=2026-12-01'
    assert client.get(url + '&roomType=PRKG').get_json()['behaviour']['bookings'] == 0
    assert client.get(url + '&dateBasis=booking').status_code == 200
    for query in ['&dateBasis=bad', '&pickupDays=0', '&marketId=bad', '&comparison=custom']:
        assert client.get(url + query).status_code == 400


def test_custom_period_and_idr_rates_use_existing_rules():
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02', rate=1560000),
               api_row(2, '2025-01-01', '2025-11-01', '2025-11-02')])
    r = build_reports('2026-12-01', '2026-12-01', comparison='custom', comparison_start='2025-11-01')['production']['market'][0]
    assert r['netRevenue'] == pytest.approx(1000000)
    assert r['comparison']['rooms'] == 1 and r['comparisonQuality'] == 'estimated'


def test_breakdown_nests_rate_plans_under_room_type_and_reconciles_totals():
    be.upsert([
        api_row(1, '2026-09-01', '2026-12-01', '2026-12-03', type_id='DLT', rate=1000000),
        {**api_row(2, '2026-09-01', '2026-12-01', '2026-12-03', type_id='DLT', rate=2000000), 'RateId': 'PROMO'},
        api_row(3, '2026-09-01', '2026-12-01', '2026-12-02', type_id='PRKG', rate=1500000),
    ])
    result = room_rate_breakdown('2026-12-01', '2026-12-01')
    dlt = next(rt for rt in result['roomTypes'] if rt['id'] == 'DLT')
    assert dlt['rooms'] == 2 and dlt['revenue'] == 3000000
    assert dlt['rooms'] == sum(p['rooms'] for p in dlt['ratePlans'])
    assert {p['id'] for p in dlt['ratePlans']} == {'BAR', 'PROMO'}
    assert result['total']['rooms'] == 3 and result['total']['revenue'] == 4500000


def test_breakdown_excludes_non_idr_revenue_but_counts_rooms():
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02', currency='EUR', rate=100)])
    rt = room_rate_breakdown('2026-12-01', '2026-12-01')['roomTypes'][0]
    assert (rt['rooms'], rt['idrRooms'], rt['revenue']) == (1, 0, 0)


def test_breakdown_honours_room_type_and_market_filters():
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02', type_id='DLT', market_id=8),
               api_row(2, '2026-09-01', '2026-12-01', '2026-12-02', type_id='PRKG', market_id=9)])
    assert [rt['id'] for rt in room_rate_breakdown('2026-12-01', '2026-12-01', room_type='DLT')['roomTypes']] == ['DLT']
    assert [rt['id'] for rt in room_rate_breakdown('2026-12-01', '2026-12-01', market_id=9)['roomTypes']] == ['PRKG']


def test_breakdown_excludes_cancelled_bookings(monkeypatch):
    row = api_row(1, '2026-09-01', '2026-12-01', '2026-12-02')
    be.upsert([row])
    monkeypatch.setattr(be, '_today', lambda: date(2026, 10, 2))
    be.upsert([{**row, 'ReservationStatus': 'L', 'UpdatedDate': '2026-10-02T01:00:00+00:00'}])
    assert room_rate_breakdown('2026-12-01', '2026-12-01')['total']['rooms'] == 0


def test_breakdown_route_validates_and_returns_totals(client):
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02')])
    r = client.get('/api/rms/pace/breakdown?start=2026-12-01&end=2026-12-01')
    assert r.status_code == 200 and r.get_json()['total']['rooms'] == 1
    assert client.get('/api/rms/pace/breakdown?start=2026-12-01&end=2026-12-01&marketId=bad').status_code == 400


def test_pickup_by_dimension_splits_new_booking_by_market_and_company():
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02', market_id=8),
               api_row(2, '2026-09-30', '2026-12-01', '2026-12-02', market_id=9,
                       company_id=5, company='Corporate X')])
    by_market = {r['id']: r for r in pickup_by_dimension(
        '2026-12-01', '2026-12-01', 'market', pickup_days=7, today=date(2026, 10, 1))}
    assert by_market['8']['rooms'] == 1 and by_market['8']['pickupRooms'] == 0
    assert by_market['9']['rooms'] == 1 and by_market['9']['pickupRooms'] == 1

    by_company = {r['id']: r for r in pickup_by_dimension(
        '2026-12-01', '2026-12-01', 'company', pickup_days=7, today=date(2026, 10, 1))}
    assert by_company['5']['name'] == 'Corporate X' and by_company['5']['pickupRooms'] == 1
    assert by_company['unassigned']['pickupRooms'] == 0


def test_pickup_groups_route_validates_and_limits(client):
    be.upsert([api_row(1, '2026-09-01', '2026-12-01', '2026-12-02', market_id=8),
               api_row(2, '2026-09-30', '2026-12-01', '2026-12-02', market_id=9,
                       company_id=5, company='Corporate X')])
    url = '/api/rms/pace/pickup-groups?start=2026-12-01&end=2026-12-01&pickupDays=7&asOf=2026-10-01'
    r = client.get(url + '&dimension=company&limit=1')
    assert r.status_code == 200
    rows = r.get_json()['rows']
    assert len(rows) == 1 and rows[0]['id'] == '5'
    assert client.get(url + '&dimension=bad').status_code == 400
