"""Whole-hotel 7/30-day briefing. No implied FX conversion or audited actuals."""
from datetime import timedelta
from . import booking_events as be, rms_forecast, rms_workspace


def _sum_known(rows, field):
    return sum(r[field] for r in rows) if rows and all(r.get(field) is not None for r in rows) else None


def summarise(rows, capacity, start, days):
    selected = rows[:days]
    known = len(selected) == days and all(r['currentQuality'] != 'unavailable' for r in selected)
    rooms = sum(r['rooms'] for r in selected) if known else None
    revenue = sum(r['revenue'] for r in selected) if known else None
    idr_rooms = sum(r['idrRooms'] for r in selected) if known else None
    total_capacity = sum(capacity[r['date']] for r in selected) if selected and all(capacity.get(r['date']) is not None for r in selected) else None
    budget = _sum_known(selected, 'budgetRevenue')
    end = (start + timedelta(days=days - 1)).isoformat()
    return {'days': days, 'start': start.isoformat(), 'end': end, 'rooms': rooms,
            'occupancy': rooms / total_capacity * 100 if rooms is not None and total_capacity else None,
            'capacity': total_capacity, 'revenue': revenue, 'adr': revenue / idr_rooms if revenue is not None and idr_rooms else None,
            'idrCoveragePct': idr_rooms / rooms * 100 if idr_rooms is not None and rooms else None,
            'pickupRooms': _sum_known(selected, 'pickupRooms') if known else None,
            'budgetRevenue': budget, 'budgetGap': revenue - budget if revenue is not None and budget is not None else None,
            'comparisonRooms': _sum_known(selected, 'stlyRooms'),
            'comparisonQuality': 'unavailable' if any(r['comparisonQuality'] == 'unavailable' for r in selected) else 'estimated' if any(r['comparisonQuality'] == 'estimated' for r in selected) else 'observed'}


def briefing():
    today = be._today()
    end = today + timedelta(days=29)
    rows = be.pace_table(today.isoformat(), end.isoformat(), pickup_days=7, comparison='calendar')
    # Persistent forecast cache responds immediately; report sections refresh in background.
    forecast = rms_forecast.cached_forecast(today, 30, sections=("hotel",))
    hotel_state = forecast['sections']['hotel']
    capacity = {r['date']: r['roomCount'] for r in forecast['hotel']}
    sync = be.status()
    thresholds = rms_workspace.get_settings()['thresholds']
    attention = []
    for r in rows:
        reasons = []
        known = r['currentQuality'] != 'unavailable'
        occ = r['rooms'] / capacity[r['date']] * 100 if known and capacity.get(r['date']) else None
        if known and occ is not None and occ >= thresholds['occupancy']:
            reasons.append('High occupancy')
        if known and r['stlyRooms'] is not None and r['rooms'] - r['stlyRooms'] <= -thresholds['behindRooms'] and r['pickupRooms'] is not None and r['pickupRooms'] < thresholds['weakPickup']:
            reasons.append('Behind comparison; weak pickup')
        if known and r['pickupRooms'] is not None and r['pickupRooms'] < 0:
            reasons.append('Negative pickup')
        if reasons:
            attention.append({'date': r['date'], 'rooms': r['rooms'], 'occupancy': occ,
                              'pickupRooms': r['pickupRooms'], 'reasons': reasons,
                              'comparisonQuality': r['comparisonQuality']})
    return {'today': today.isoformat(), 'basis': 'Gross quoted IDR room rates; ADR excludes foreign-currency rooms',
            'pickupDays': 7, 'periods': [summarise(rows, capacity, today, n) for n in (7,30)],
            'attention': attention, 'bookingSync': sync['lastSuccessfulSync'], 'bookingStale': sync['stale'],
            'bookingCoverage': sync['coverageFrom'], 'capacityState': hotel_state,
            'generatedAt': be._now(), 'warnings': [text for condition, text in (
                (sync['stale'], 'Booking history needs refresh.'),
                (not sync['coverageFrom'], 'Run an initial booking backfill before using this briefing.'),
                (hotel_state['stale'], 'Room capacity is loading or uses an older PMS forecast.'),
                (hotel_state['error'], 'PMS room-capacity refresh failed; retained values may be stale.')) if condition]}
