"""Selenium-free allotment push, for verifying the API-based approach against
the existing Selenium updaters (allotment_updater.py, other_room_allotment_updater.py)
without touching them.

Two modes:
- push_allotment(): a single (date range, room type) call, for manually
  testing the request/response shape.
- build_full_plan() + push_jobs_concurrent(): reads the real
  inventory_allocation.db (the same source the production updaters read) and
  fires the resulting (date range, room type) jobs at the PMS concurrently,
  with a dry_run mode that builds every payload without sending any of them.

FULL_ROOM_TYPE_CONFIG mirrors ROOM_TYPE_CONFIG (allotment_updater.py) +
REST_ROOM_TYPE_CONFIG (other_room_allotment_updater.py) - duplicated rather
than imported so this module stays fully standalone from the Selenium code
path it's meant to validate.

A job with zero rooms is pushed as an explicit close (IsClosed/Closed: "X"),
matching the PMS "Add Allotment Room" modal's own Close checkbox, rather than
NoOfRoom=0 with the category left open. The Selenium updaters this module is
validated against don't do this (no Close-checkbox interaction there) - only
this API path closes zero-inventory dates.

verify_pushed_jobs() re-queries api/AllotmentRoomInventory (the same call the
PMS's own "Allotment Room List" grid makes) after a live push, to catch cases
where save_allotment returned IsSuccess:true but the write didn't actually
stick. This is a best-effort, log-only sanity check - see its docstring for
why it doesn't raise on mismatch.
"""

import concurrent.futures
import time
from datetime import datetime, timedelta

from ...inventory.allocation_repository import load_allocation_rows
from ...inventory.cm_repository import load_cm_current_values
from .api_client import PMSApiClient, PMSApiError

FULL_ROOM_TYPE_CONFIG = {
    "deluxe": {"csv_column": "Deluxe Online Inventory", "checkbox_value": "DLT", "label": "Deluxe", "cm_column": "Deluxe Room"},
    "premiere": {"csv_column": "Premiere Online Inventory", "checkbox_value": "PRKG", "label": "Premiere", "cm_column": "Premiere Room"},
    "deluxe_suite": {"csv_column": "Deluxe Suite Room Online Inventory", "checkbox_value": "DLS", "label": "Deluxe Suite Room", "cm_column": "Deluxe Suite Room"},
    "family_premiere": {"csv_column": "Family Premiere Room Online Inventory", "checkbox_value": "FAM", "label": "Family Premiere Room", "cm_column": "Family Premiere Room"},
    "premiere_suite": {"csv_column": "Premiere Suite Room Online Inventory", "checkbox_value": "PSU", "label": "Premiere Suite Room", "cm_column": "Premiere Suite Room"},
    "beach_front_private_suite": {"csv_column": "Beach Front Private Suite Room Online Inventory", "checkbox_value": "BFS", "label": "Beach Front Private Suite Room", "cm_column": "Beach Front Private Suite Room"},
    "anvaya_suite_whirlpool": {"csv_column": "The Anvaya Suite Whirpool Online Inventory", "checkbox_value": "ASW", "label": "The Anvaya Suite Whirpool", "cm_column": "The Anvaya Suite with Whirpool"},
    "anvaya_suite_no_pool": {"csv_column": "The Anvaya Suite No Pool Online Inventory", "checkbox_value": "AVS", "label": "The Anvaya Suite No Pool", "cm_column": "The Anvaya Suite No Pool"},
    "anvaya_suite_with_pool": {"csv_column": "The Anvaya Suite With Pool Online Inventory", "checkbox_value": "ASP", "label": "The Anvaya Suite With Pool", "cm_column": "The Anvaya Suite With Pool"},
    "anvaya_residence": {"csv_column": "The Anvaya Residence Online Inventory", "checkbox_value": "AVR", "label": "The Anvaya Residence", "cm_column": "The Anvaya Residence"},
    "anvaya_villa": {"csv_column": "The Anvaya Villa Online Inventory", "checkbox_value": "AVP", "label": "The Anvaya Villa", "cm_column": "The Anvaya Villa"},
    "deluxe_pool_access": {"csv_column": "Deluxe Pool Access Online Inventory", "checkbox_value": "DLTP", "label": "Deluxe Pool Access", "cm_column": "Deluxe Pool Access"},
    "premiere_lagoon_access": {"csv_column": "Premiere Room Lagoon Access Online Inventory", "checkbox_value": "PRKL", "label": "Premiere Room Lagoon Access", "cm_column": "Premiere Room Lagoon Access"},
}

# For the single-row manual test endpoint's dropdown - sourced from the same
# config above so it can't drift from the room types the bulk planner knows about.
ROOM_TYPES = [
    {"label": config["label"], "value": config["checkbox_value"]}
    for config in FULL_ROOM_TYPE_CONFIG.values()
]

# checkbox value (e.g. "DLT") -> label (e.g. "Deluxe"), for building remarks
# that read the same way the production Selenium updaters' remarks do.
LABEL_BY_CHECKBOX_VALUE = {
    config["checkbox_value"]: config["label"] for config in FULL_ROOM_TYPE_CONFIG.values()
}


def _to_pms_date(iso_date):
    """'YYYY-MM-DD' -> 'YYYY/MM/DD', matching convertDateInputToDateDB() in
    the PMS's own front-end JS."""
    return iso_date.replace("-", "/")


def push_allotment(company_id, room_type, start_date, end_date, number_of_rooms, remark,
                    dry_run=True, username=None, password=None):
    """Build (and optionally send) one allotment save call, exactly matching
    the payload shape the PMS "Add Allotment Room" modal sends for a single
    date range + room type.

    start_date/end_date: 'YYYY-MM-DD'. dry_run=True (default) builds the
    payload and logs in, but never calls POST api/allotment.

    Returns a dict describing what happened, safe to return directly as a
    JSON API response.
    """
    started = time.monotonic()
    client = PMSApiClient(username=username, password=password)
    client.login()

    # Zero rooms is sent as an explicit close (IsClosed/Closed), not just
    # NoOfRoom=0 - matches the PMS "Add Allotment Room" modal's own Close
    # checkbox rather than leaving the category open with a zero count.
    is_closed = number_of_rooms <= 0
    payload = {
        "CompanyId": company_id,
        "StartDate": _to_pms_date(start_date),
        "EndDate": _to_pms_date(end_date),
        "TypeId": room_type,
        "NoOfRoom": number_of_rooms,
        "Remark": remark,
        "IsClosed": is_closed,
        "Closed": "X" if is_closed else "0",
        "HotelId": client.hotel_id,
        "UserId": client.user_id,
    }

    result = {
        "dry_run": dry_run,
        "request_payload": payload,
        "response": None,
    }

    if not dry_run:
        result["response"] = client.save_allotment(
            company_id=company_id,
            start_date=payload["StartDate"],
            end_date=payload["EndDate"],
            type_id=room_type,
            no_of_rooms=number_of_rooms,
            remark=remark,
            is_closed=is_closed,
        )

    result["elapsed_seconds"] = time.monotonic() - started
    return result


def _build_date_ranges(date_inventory):
    """Collapse a date-ordered list of {'date', 'inventory', 'skip'} dicts into
    contiguous (start, end, inventory) runs, dropping runs flagged 'skip'.

    Same algorithm as _build_date_ranges() in allotment_updater.py, duplicated
    here to keep this module standalone. A new run starts whenever either the
    inventory value or the skip status changes between consecutive days.

    Returns (kept_runs, skipped_run_count).
    """
    runs = []
    current_run = None
    for item in date_inventory:
        if current_run is None:
            current_run = {'start': item['date'], 'end': item['date'], 'inventory': item['inventory'], 'skip': item['skip']}
        elif item['inventory'] == current_run['inventory'] and item['skip'] == current_run['skip']:
            current_run['end'] = item['date']
        else:
            runs.append(current_run)
            current_run = {'start': item['date'], 'end': item['date'], 'inventory': item['inventory'], 'skip': item['skip']}
    if current_run is not None:
        runs.append(current_run)

    skipped_run_count = sum(1 for r in runs if r['skip'])
    kept_runs = [r for r in runs if not r['skip']]
    return kept_runs, skipped_run_count


def build_jobs_for_room_type(room_type_key, rows, cm_values, max_dates=None, skip_unchanged=True):
    """Build the flat list of (date range, room type) jobs for one room type
    from already-loaded allocation rows. Returns (jobs, skipped_run_count)."""
    config = FULL_ROOM_TYPE_CONFIG[room_type_key]
    cm_column = config.get('cm_column')

    date_inventory = []
    for row in rows:
        if config['csv_column'] not in row or row[config['csv_column']] is None:
            continue
        inventory = int(row[config['csv_column']])
        cm_current = cm_values.get(row['Date'], {}).get(cm_column) if cm_column else None
        is_unchanged = skip_unchanged and cm_current is not None and int(cm_current) == inventory
        date_obj = datetime.strptime(row['Date'], '%Y-%m-%d')
        date_inventory.append({
            'date': date_obj.strftime('%Y/%m/%d'),
            'inventory': inventory,
            'skip': is_unchanged,
        })
    if max_dates:
        date_inventory = date_inventory[:max_dates]

    runs, skipped_run_count = _build_date_ranges(date_inventory)
    jobs = [{
        'room_type': room_type_key,
        'label': config['label'],
        'checkbox_value': config['checkbox_value'],
        'start_date': r['start'],
        'end_date': r['end'],
        'number_of_rooms': r['inventory'],
    } for r in runs]
    return jobs, skipped_run_count


def build_full_plan(room_types=None, max_dates=None, skip_unchanged=True):
    """Read inventory_allocation.db (same source the production updaters use)
    and build the full flat list of (date range, room type) jobs that would
    need to be pushed. Purely local - no PMS login or network call.

    room_types: optional list of FULL_ROOM_TYPE_CONFIG keys to restrict to
    (defaults to all 13).
    """
    rows = load_allocation_rows()
    cm_values = load_cm_current_values() if skip_unchanged else {}

    keys = [k for k in (room_types or FULL_ROOM_TYPE_CONFIG.keys()) if k in FULL_ROOM_TYPE_CONFIG]

    plan = {'jobs': [], 'skipped_ranges': 0, 'by_room_type': {}}
    for key in keys:
        jobs, skipped = build_jobs_for_room_type(key, rows, cm_values, max_dates=max_dates, skip_unchanged=skip_unchanged)
        plan['jobs'].extend(jobs)
        plan['skipped_ranges'] += skipped
        plan['by_room_type'][key] = {'label': FULL_ROOM_TYPE_CONFIG[key]['label'], 'job_count': len(jobs)}
    return plan


def push_jobs_concurrent(jobs, company_id=1001, dry_run=True, max_workers=4, username=None, password=None,
                          on_result=None, on_retry=None, max_retries=2, retry_delay=3.0):
    """Fire one PMS login, then push every job concurrently (bounded by
    max_workers). dry_run=True builds every payload without sending it.

    A handful of jobs failing with a PMS-side "error occurred while sending
    the request" or an HttpClient timeout - while the same room type/date
    shape succeeds in every other job in the same run - has been observed in
    production to be the PMS's own backend buckling under max_workers
    concurrent requests, not a bad payload. Those failures are retried up to
    max_retries times, retry_delay seconds apart; retrying only the small
    failed subset (not all jobs) removes the contention that caused it.

    on_result: optional callback invoked once per job with its FINAL outcome
    (after any retries), as soon as that outcome is known - lets a caller
    stream live progress instead of only seeing a single summary once every
    job has finished. on_retry(attempt, retrying_count, max_attempts):
    optional callback fired once per retry round, before it starts.
    result['attempts'] tells a caller a job needed more than one try.

    Both callbacks are called from the same thread that's iterating results,
    so it's safe to mutate caller-owned state without extra locking.

    Returns a summary dict with per-job results, safe to return directly as a
    JSON API response.
    """
    started = time.monotonic()
    client = PMSApiClient(username=username, password=password)
    client.login()
    max_attempts = max_retries + 1

    def run_one(job):
        # Zero rooms closes the category (IsClosed/Closed) instead of leaving
        # it open with a zero count - see push_allotment()'s docstring note.
        is_closed = job['number_of_rooms'] <= 0
        remark = f"Updated from yield matrix - {job['label']} Online Inventory {job['number_of_rooms']}"
        if is_closed:
            remark += " (closed)"
        payload_preview = {
            'CompanyId': company_id,
            'StartDate': job['start_date'],
            'EndDate': job['end_date'],
            'TypeId': job['checkbox_value'],
            'NoOfRoom': job['number_of_rooms'],
            'Remark': remark,
            'IsClosed': is_closed,
            'Closed': 'X' if is_closed else '0',
        }
        result = {'job': job, 'payload': payload_preview, 'success': None, 'response': None, 'error': None}
        if dry_run:
            result['success'] = True
            return result
        try:
            resp = client.save_allotment(
                company_id=company_id,
                start_date=job['start_date'],
                end_date=job['end_date'],
                type_id=job['checkbox_value'],
                no_of_rooms=job['number_of_rooms'],
                remark=remark,
                is_closed=is_closed,
            )
            result['response'] = resp
            result['success'] = bool(resp.get('IsSuccess'))
            if not result['success']:
                result['error'] = resp.get('Message') or resp.get('ReturnMessage')
        except PMSApiError as e:
            result['success'] = False
            result['error'] = str(e)
        return result

    def run_batch(batch):
        out = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(run_one, job) for job in batch]
            for future in concurrent.futures.as_completed(futures):
                out.append(future.result())
        return out

    results = []
    pending = list(jobs)
    attempt = 1
    while pending:
        batch_results = run_batch(pending)
        next_pending = []
        for r in batch_results:
            r['attempts'] = attempt
            is_final = r['success'] or dry_run or attempt >= max_attempts
            if is_final:
                results.append(r)
                if on_result:
                    on_result(r)
            else:
                next_pending.append(r['job'])
        if not next_pending:
            break
        if on_retry:
            on_retry(attempt + 1, len(next_pending), max_attempts)
        time.sleep(retry_delay)
        pending = next_pending
        attempt += 1

    success_count = sum(1 for r in results if r['success'])
    return {
        'dry_run': dry_run,
        'total': len(results),
        'success_count': success_count,
        'failed_count': len(results) - success_count,
        'elapsed_seconds': time.monotonic() - started,
        'results': results,
    }


def _expand_dates(start_str, end_str):
    """'YYYY/MM/DD'..'YYYY/MM/DD' (job date-range format) -> every 'YYYY-MM-DD' in between, inclusive."""
    start = datetime.strptime(start_str, '%Y/%m/%d')
    end = datetime.strptime(end_str, '%Y/%m/%d')
    return [(start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((end - start).days + 1)]


def verify_pushed_jobs(results, company_id=1001, username=None, password=None, chunk_days=60, settle_seconds=3):
    """Re-query api/AllotmentRoomInventory and compare it against what was
    just pushed, for jobs where the push succeeded (results with
    success=True; dry-run results should be filtered out by the caller since
    nothing was sent for them). Returns a list of mismatches, each
    {job, date, expected, actual} - an empty list means everything matched.

    This is a best-effort sanity check on top of the PMS's own
    IsSuccess:true response, not a replacement for it: save_allotment already
    told us the write succeeded, so a mismatch here is logged by the caller,
    not raised - re-querying a live system for a value that could
    legitimately keep moving (further sales, other allotment edits) is not a
    trustworthy basis for failing an otherwise-successful pipeline run.

    settle_seconds: paused before the first re-query, since the PMS's own
    backend has shown it can lag under load (see push_jobs_concurrent's
    retry logic) - avoids flagging false mismatches from checking too soon.
    """
    pushed_jobs = [r['job'] for r in results if r.get('success')]
    if not pushed_jobs:
        return []

    time.sleep(settle_seconds)

    client = PMSApiClient(username=username, password=password)
    client.login()

    all_dates = sorted({d for job in pushed_jobs for d in _expand_dates(job['start_date'], job['end_date'])})
    min_dt = datetime.strptime(all_dates[0], '%Y-%m-%d')
    max_dt = datetime.strptime(all_dates[-1], '%Y-%m-%d')
    total_days = (max_dt - min_dt).days + 1

    lookup = {}
    cursor = min_dt
    remaining = total_days
    while remaining > 0:
        span = min(chunk_days, remaining)
        rows = client.get_allotment_room_inventory(company_id, cursor.strftime('%Y-%m-%d'), span)
        for row in rows:
            lookup[row['TrxDate'].split('T')[0]] = row
        cursor += timedelta(days=span)
        remaining -= span

    mismatches = []
    for job in pushed_jobs:
        for date_str in _expand_dates(job['start_date'], job['end_date']):
            row = lookup.get(date_str)
            if row is None:
                # Confirmed via a live probe (2026-10-05): the grid omits a date
                # entirely rather than returning a zeroed row when every room
                # type is closed/sold out for it. A missing row is therefore
                # consistent with "closed" (number_of_rooms<=0) - only flag it
                # as a mismatch if we'd expected an open allotment to exist.
                if job['number_of_rooms'] <= 0:
                    continue
                mismatches.append({
                    'job': job, 'date': date_str,
                    'expected': job['number_of_rooms'], 'actual': None,
                })
                continue
            actual = row.get(job['checkbox_value'])
            if actual != job['number_of_rooms']:
                mismatches.append({
                    'job': job, 'date': date_str,
                    'expected': job['number_of_rooms'], 'actual': actual,
                })
    return mismatches
