"""Bounded report cache: data-aware invalidation, single-flight and timing."""
import copy
import functools
import inspect
import json
import os
import threading
import time
from collections import OrderedDict, defaultdict, deque
from statistics import median

TTL_SECONDS = 60
MAX_ENTRIES = 64
_cache = OrderedDict()
_pending = set()
_condition = threading.Condition()
_metrics = defaultdict(lambda: deque(maxlen=200))


def fingerprint():
    from . import booking_events as be, rms_budget
    result = []
    for path in (be.get_data_path(be.DB_FILE), rms_budget.get_data_path(rms_budget.DB_FILE)):
        for filename in (path, path + '-wal'):
            try:
                st = os.stat(filename)
                result.append((filename, st.st_ino, st.st_mtime_ns, st.st_size))
            except FileNotFoundError:
                result.append((filename, None))
    return tuple(result)


def cached_report(function):
    signature = inspect.signature(function)
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        from . import booking_events as be
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        key = (function.__module__ + '.' + function.__name__, be._today().isoformat(),
               json.dumps(bound.arguments, sort_keys=True, default=str))
        while True:
            revision = fingerprint()
            with _condition:
                stored = _cache.get(key)
                if stored and stored[0] == revision and time.monotonic() - stored[1] < TTL_SECONDS:
                    _cache.move_to_end(key)
                    mark_cache('hit')
                    return copy.deepcopy(stored[2])
                if key in _pending:
                    _condition.wait(timeout=1)
                    continue
                _pending.add(key)
                break
        try:
            value = function(*args, **kwargs)
            if revision == fingerprint():
                with _condition:
                    _cache[key] = (revision, time.monotonic(), copy.deepcopy(value))
                    while len(_cache) > MAX_ENTRIES:
                        _cache.popitem(last=False)
            mark_cache('miss')
            return value
        finally:
            with _condition:
                _pending.discard(key)
                _condition.notify_all()
    return wrapped


def mark_cache(value):
    from flask import g, has_request_context
    if has_request_context():
        g.report_cache = value


def record_timing(endpoint, milliseconds):
    with _condition:
        _metrics[endpoint].append(milliseconds)


def timings():
    with _condition:
        rows = []
        for endpoint, values in _metrics.items():
            ordered = sorted(values)
            rows.append({'endpoint': endpoint, 'samples': len(values),
                         'p50Ms': round(median(values), 2),
                         'p95Ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 2)})
        return sorted(rows, key=lambda r: -r['p95Ms'])
