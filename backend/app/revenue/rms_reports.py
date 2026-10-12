"""Grouped RMS analysis from observed, PII-free booking versions."""
from collections import defaultdict
from datetime import date, timedelta

from . import booking_events as be
from .rms_workspace import get_settings, net_rate

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
LEAD_BUCKETS = [(0, 0, 'Same day'), (1, 7, '1–7 days'), (8, 14, '8–14 days'),
                (15, 30, '15–30 days'), (31, 60, '31–60 days'), (61, 90, '61–90 days'),
                (91, 180, '91–180 days'), (181, 100000, '181+ days')]
LOS_BUCKETS = [(1, 1, '1 night'), (2, 3, '2–3 nights'), (4, 7, '4–7 nights'),
               (8, 14, '8–14 nights'), (15, 100000, '15+ nights')]


def _key(r, dimension):
    if dimension == 'market':
        return str(r['market_id']) if r.get('market_id') is not None else 'unassigned'
    if dimension == 'roomType':
        return r.get('type_id') or 'unassigned'
    return r.get('rate_id') or r.get('rate_type') or 'unassigned'


def _nights(r, start, end):
    first = max(start, r['arrival_date'])
    last = min(end, (date.fromisoformat(r['departure_date']) - timedelta(days=1)).isoformat())
    return be._stay_dates(first, (date.fromisoformat(last) + timedelta(days=1)).isoformat()) if first <= last else []


def _blank():
    return {'rooms': 0, 'idrRooms': 0, 'revenue': 0, 'netRevenue': 0}


def _group(states, start, end, as_of, dimension, room_type, market_id, rules):
    result = defaultdict(_blank)
    for r in states.values():
        if not be._active(r, as_of) or not be._matches(r, room_type, market_id):
            continue
        nights = _nights(r, start, end)
        if not nights:
            continue
        b = result[_key(r, dimension)]
        b['rooms'] += len(nights)
        if r['currency'] == 'IDR':
            b['idrRooms'] += len(nights)
            b['revenue'] += r['room_rate'] * len(nights)
            b['netRevenue'] += sum(net_rate(r['room_rate'], r.get('rate_type'), day, rules, r.get('rate_id')) for day in nights)
    return dict(result)


def room_rate_breakdown(start, end, room_type=None, market_id=None):
    """Current on-the-books nights/revenue by room type, nested by rate plan -
    the Booking.com-style 'breakdown by room and rate' table."""
    today = be._today().isoformat()
    states = be.state_as_of(be.version_history([(start, end)]), today)
    rules = get_settings()['revenueRules']
    totals = defaultdict(_blank)
    for r in states.values():
        if not be._active(r, today) or not be._matches(r, room_type, market_id):
            continue
        nights = _nights(r, start, end)
        if not nights:
            continue
        key = (r.get('type_id') or 'unassigned', r.get('rate_id') or r.get('rate_type') or 'unassigned')
        b = totals[key]
        b['rooms'] += len(nights)
        if r['currency'] == 'IDR':
            b['idrRooms'] += len(nights)
            b['revenue'] += r['room_rate'] * len(nights)
            b['netRevenue'] += sum(net_rate(r['room_rate'], r.get('rate_type'), day, rules, r.get('rate_id')) for day in nights)
    room_types = {}
    for (type_id, rate_id), metrics in totals.items():
        rt = room_types.setdefault(type_id, {'id': type_id, 'ratePlans': [], **_blank()})
        for k in metrics:
            rt[k] += metrics[k]
        rt['ratePlans'].append({'id': rate_id, **metrics})
    grand = _blank()
    for rt in room_types.values():
        for k in grand:
            grand[k] += rt[k]
        rt['ratePlans'].sort(key=lambda r: -r['rooms'])
    return {'roomTypes': sorted(room_types.values(), key=lambda r: -r['rooms']), 'total': grand}


def build_reports(start, end, room_type=None, market_id=None, comparison='weekday',
                  comparison_start=None, pickup_days=7, date_basis='stay'):
    from . import rms_budget
    today = be._today().isoformat()
    # Segment budget has no room-type dimension and is tied to stay dates,
    # not booking-creation dates, so neither filter leaves a matching figure.
    budget_by_market = {} if room_type or date_basis != 'stay' else rms_budget.segment_totals(start, end, basis='gross')
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    comparison_days = [(first + timedelta(days=i), be.comparison_date(first + timedelta(days=i), comparison, comparison_start, start))
                       for i in range((last - first).days + 1)]
    ranges = [(start, end), (min(d.isoformat() for _, d in comparison_days), max(d.isoformat() for _, d in comparison_days))]
    # Booking-date analysis needs bookings outside the selected stay-date range.
    history = be.version_history(None if date_basis == 'booking' else ranges)
    states = be.state_as_of(history, today)
    rules = get_settings()['revenueRules']
    with be._db_lock, be._db() as conn:
        coverage = be._get_meta(conn, 'backfillFrom')
    quality = be._quality(today, coverage, history)
    prior = {n: be.state_as_of(history, (be._today() - timedelta(days=n)).isoformat())
             for n in sorted(set([1, 7, 30, pickup_days]))}
    names = {str(r['market_id']): r.get('market') or str(r['market_id']) for versions in history.values()
             for _, r in versions if r.get('market_id') is not None}
    production = {}
    trend = []
    state_cache = {}
    for dimension in ['market', 'roomType', 'ratePlan']:
        cur = _group(states, start, end, today, dimension, room_type, market_id, rules)
        before = {n: _group(s, start, end, (be._today() - timedelta(days=n)).isoformat(), dimension, room_type, market_id, rules)
                  for n, s in prior.items()}
        comp = defaultdict(_blank)
        comp_quality = []
        for current_day, matched_day in comparison_days:
            day, matched = current_day.isoformat(), matched_day.isoformat()
            as_of = (be._today() - (current_day - matched_day)).isoformat()
            q = be._quality(as_of, coverage, history) if as_of <= today else 'unavailable'
            comp_quality.append(q)
            if q != 'unavailable':
                if as_of not in state_cache:
                    state_cache[as_of] = be.state_as_of(history, as_of)
                grouped = _group(state_cache[as_of], matched, matched, as_of, dimension, room_type, market_id, rules)
                for key, metrics in grouped.items():
                    for metric, value in metrics.items(): comp[key][metric] += value
            if dimension == 'market':
                for key, metrics in _group(states, day, day, today, dimension, room_type, market_id, rules).items():
                    trend.append({'date': day, 'id': key, 'name': names.get(key, 'Unassigned' if key == 'unassigned' else key), **metrics})
        comparison_quality = 'unavailable' if 'unavailable' in comp_quality else 'estimated' if 'estimated' in comp_quality else 'observed'
        keys = set(cur) | set(comp)
        for values in before.values(): keys.update(values)
        group_rows = []
        for key in keys:
            metrics = cur.get(key, _blank())
            pickup = {}
            for n, values in before.items():
                q = be._quality((be._today() - timedelta(days=n)).isoformat(), coverage, history)
                pickup[str(n)] = {'rooms': metrics['rooms'] - values.get(key, _blank())['rooms'] if q != 'unavailable' else None, 'quality': q}
            cutoff = (be._today() - timedelta(days=pickup_days)).isoformat()
            new = sum(len(_nights(r, start, end)) for r in states.values() if r['reservation_date'] > cutoff
                      and be._active(r, today) and be._matches(r, room_type, market_id) and _key(r, dimension) == key)
            cancelled = sum(len(_nights(r, start, end)) for rid, r in prior[pickup_days].items()
                            if be._active(r, cutoff) and be._matches(r, room_type, market_id) and _key(r, dimension) == key
                            and rid in states and not be._active(states[rid], today))
            net = pickup[str(pickup_days)]['rooms']
            group_rows.append({'id': key, 'name': names.get(key, 'Unassigned' if key == 'unassigned' else key) if dimension == 'market' else key,
                               **{k: v if quality != 'unavailable' else None for k, v in metrics.items()},
                               'pickup': pickup, 'newRooms': new if net is not None else None,
                               'cancelledRooms': cancelled if net is not None else None,
                               'amendedRooms': net - new + cancelled if net is not None else None,
                               'comparison': dict(comp.get(key, _blank())) if comparison_quality != 'unavailable' else None,
                               'comparisonQuality': comparison_quality,
                               'budget': budget_by_market.get(key) if dimension == 'market' else None})
        production[dimension] = sorted(group_rows, key=lambda r: (-(r['rooms'] or 0), r['name']))
    eligible = [r for r in states.values() if be._matches(r, room_type, market_id) and
                (start <= r['reservation_date'] <= end if date_basis == 'booking' else bool(_nights(r, start, end)))]
    # Do not count cancelled/no-show bookings as realized occupancy.
    active = [r for r in eligible if be._active(r, today) and r['status'] != 'N']
    def distribution(buckets, measure):
        return [{'label': label, 'bookings': sum(low <= measure(r) <= high for r in active)} for low, high, label in buckets]
    lead = lambda r: (date.fromisoformat(r['arrival_date']) - date.fromisoformat(r['reservation_date'])).days
    los = lambda r: (date.fromisoformat(r['departure_date']) - date.fromisoformat(r['arrival_date'])).days
    weekdays = [{'label': day, 'booked': sum(date.fromisoformat(r['reservation_date']).weekday() == i for r in active),
                 'arrivals': sum(date.fromisoformat(r['arrival_date']).weekday() == i for r in active)} for i, day in enumerate(WEEKDAYS)]
    losses = []
    for key in sorted({_key(r, 'market') for r in eligible}):
        bookings = [r for r in eligible if _key(r, 'market') == key]
        losses.append({'id': key, 'name': names.get(key, 'Unassigned' if key == 'unassigned' else key), 'bookings': len(bookings),
                       'cancelled': sum(not be._active(r, today) for r in bookings),
                       'noShows': sum(r['status'] == 'N' for r in bookings)})
    return {'start': start, 'end': end, 'quality': quality, 'production': production, 'marketTrend': trend,
            'behaviour': {'dateBasis': date_basis, 'bookings': len(active), 'allBookings': len(eligible),
                          'leadTime': distribution(LEAD_BUCKETS, lead), 'lengthOfStay': distribution(LOS_BUCKETS, los),
                          'invalidLeadTime': sum(lead(r) < 0 for r in active),
                          'averageLeadTime': sum(lead(r) for r in active if lead(r) >= 0) / sum(lead(r) >= 0 for r in active) if any(lead(r) >= 0 for r in active) else None,
                          'averageLengthOfStay': sum(los(r) for r in active) / len(active) if active else None,
                          'weekdays': weekdays, 'losses': losses},
            'unavailable': [
                {'report': 'Channel, company and nationality production', 'reason': 'These dimensions are not yet stored in the verified booking cache.'},
                {'report': 'Promotion effectiveness and net channel contribution', 'reason': 'Requires verified promotion mapping and commission/cost data; rate-plan production is available.'},
                {'report': 'Audited actuals and forecast accuracy', 'reason': 'Requires verified final actuals and a history of forecast snapshots.'}]}
