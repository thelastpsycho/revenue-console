from datetime import date

import pytest

from app.revenue import booking_events as be
from app.revenue import rms_online
from test_rms import api_row


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(be, 'get_data_path', lambda name: str(tmp_path / name))
    monkeypatch.setattr(be, '_today', lambda: date(2026, 10, 1))
    with be._db() as conn:
        be._set_meta(conn, 'backfillFrom', '2023-01-01')


def test_channel_bucket_matches_known_companies():
    assert rms_online.channel_bucket('Santika Online Reservation') == ('direct', 'Santika Online')
    assert rms_online.channel_bucket('Booking.com') == ('booking_com', 'Booking.com')
    assert rms_online.channel_bucket('Agoda.com') == ('agoda', 'Agoda')
    assert rms_online.channel_bucket('Some Random DMC') == ('other', 'Other online channel')
    assert rms_online.channel_bucket(None) == ('unassigned', 'Unassigned')
    assert rms_online.channel_bucket('') == ('unassigned', 'Unassigned')


def test_source_breakdown_groups_by_company_within_market():
    be.upsert([
        api_row(1, '2026-09-01', '2026-10-10', '2026-10-12', company_id=11647, company='Booking.com'),
        api_row(2, '2026-09-01', '2026-10-10', '2026-10-11', company_id=11647, company='Booking.com'),
        api_row(3, '2026-09-01', '2026-10-10', '2026-10-11', company_id=4400, company='Agoda.com'),
        # Different market segment - must not leak into the Online breakdown.
        api_row(4, '2026-09-01', '2026-10-10', '2026-10-11', market_id=2, company='Some Corp'),
    ])
    result = rms_online.source_breakdown('2026-10-10', '2026-10-11')
    by_id = {row['id']: row for row in result['companies']}
    assert by_id['11647']['rooms'] == 3
    assert by_id['11647']['name'] == 'Booking.com'
    assert by_id['4400']['rooms'] == 1
    assert result['total']['rooms'] == 4


def test_source_breakdown_buckets_missing_company_as_unassigned():
    be.upsert([api_row(1, '2026-09-01', '2026-10-10', '2026-10-11')])
    result = rms_online.source_breakdown('2026-10-10', '2026-10-11')
    assert result['companies'] == [{'id': 'unassigned', 'name': 'Unassigned', 'rooms': 1, 'idrRooms': 1,
                                    'revenue': 1_000_000, 'netRevenue': pytest.approx(
                                        (1_000_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE))}]


def test_direct_share_splits_channels_by_day_and_computes_percentage():
    be.upsert([
        api_row(1, '2026-09-01', '2026-10-10', '2026-10-12', company='Santika Online Reservation'),
        api_row(2, '2026-09-01', '2026-10-10', '2026-10-11', company='Booking.com'),
        api_row(3, '2026-09-01', '2026-10-10', '2026-10-11', company='Agoda.com'),
    ])
    result = rms_online.direct_share('2026-10-10', '2026-10-11')
    buckets = {b['id']: b for b in result['buckets']}
    assert buckets['direct']['rooms'] == 2
    assert buckets['booking_com']['rooms'] == 1
    assert buckets['agoda']['rooms'] == 1
    assert result['directSharePct'] == pytest.approx(50.0)
    day = next(d for d in result['series'] if d['date'] == '2026-10-10')
    assert day['direct']['rooms'] == 1
    assert day['booking_com']['rooms'] == 1
    assert day['agoda']['rooms'] == 1


def test_direct_share_handles_no_bookings():
    result = rms_online.direct_share('2026-10-10', '2026-10-11')
    assert result['directSharePct'] is None
    assert all(b['rooms'] == 0 for b in result['buckets'])


def test_source_breakdown_channel_filter_narrows_to_selected_buckets():
    be.upsert([
        api_row(1, '2026-09-01', '2026-10-10', '2026-10-11', company='Santika Online Reservation'),
        api_row(2, '2026-09-01', '2026-10-10', '2026-10-11', company='Booking.com'),
        api_row(3, '2026-09-01', '2026-10-10', '2026-10-11', company='Agoda.com'),
    ])
    result = rms_online.source_breakdown('2026-10-10', '2026-10-11', channels=['direct', 'booking_com'])
    names = {row['name'] for row in result['companies']}
    assert names == {'Santika Online Reservation', 'Booking.com'}
    assert result['total']['rooms'] == 2


def test_direct_share_channel_filter_recomputes_share_over_subset():
    be.upsert([
        api_row(1, '2026-09-01', '2026-10-10', '2026-10-11', company='Santika Online Reservation'),
        api_row(2, '2026-09-01', '2026-10-10', '2026-10-11', company='Booking.com'),
        api_row(3, '2026-09-01', '2026-10-10', '2026-10-11', company='Agoda.com'),
    ])
    result = rms_online.direct_share('2026-10-10', '2026-10-11', channels=['direct', 'booking_com'])
    buckets = {b['id']: b for b in result['buckets']}
    assert buckets['agoda']['rooms'] == 0
    assert buckets['direct']['rooms'] == 1
    assert buckets['booking_com']['rooms'] == 1
    assert result['directSharePct'] == pytest.approx(50.0)


def test_pace_table_channel_filter_matches_booking_events():
    be.upsert([
        api_row(1, '2026-09-01', '2026-10-10', '2026-10-11', company='Santika Online Reservation'),
        api_row(2, '2026-09-01', '2026-10-10', '2026-10-11', company='Booking.com'),
    ])
    rows = be.pace_table('2026-10-10', '2026-10-10', channels=['direct'])
    assert rows[0]['rooms'] == 1
