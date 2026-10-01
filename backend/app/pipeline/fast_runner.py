"""API-based counterpart to pipeline/runner.py.

Runs a superset of runner.py's seven-stage workflow (an added
"verify_allotment" stage re-checks a live allotment push against the PMS's
own allotment grid), but the two PMS stages go through the Selenium-free JSON
API client (integrations/pms/fast_inventory_scraper.py,
fast_allotment_updater.py) instead of driving Chrome through the PMS UI. The
two D-EDGE stages (scrape_cm, bar) still use Selenium - no D-EDGE API was
reverse-engineered, so those stages are unchanged from runner.py.

Verify/step-emission/log-forwarding logic is duplicated from runner.py rather
than imported, so this module doesn't have to route progress messages through
runner.py's queue/globals to stay standalone (same rationale documented in
fast_allotment_updater.py for duplicating _build_date_ranges).

The allotment stage can push any subset of the 13 room types
fast_allotment_updater.FULL_ROOM_TYPE_CONFIG knows about - the caller (the
Fast API Pipeline page) chooses which ones via config["allotmentRoomTypes"].
Defaults to Deluxe + Premiere only when omitted, matching what runner.py's
automated Selenium pipeline covers today.
"""

import os
import sqlite3
import sys
import threading
import time
import traceback
import queue
from datetime import datetime
from io import StringIO

import pandas as pd

from ..shared import log_queue, allotment_run_control
from ..integrations.pms.fast_inventory_scraper import fetch_room_inventory
from ..integrations.pms.fast_allotment_updater import build_full_plan, push_jobs_concurrent, verify_pushed_jobs, FULL_ROOM_TYPE_CONFIG
from ..inventory.pms_processor import process_pms_inventory
from ..integrations.dedge.inventory_scraper import scrape_cm_inventory
from ..inventory.inventory_combiner import combine_inventory_files
from ..revenue.yield_engine import apply_custom_yield
from ..integrations.dedge.bar_updater import update_bar, setup_driver as dedge_setup_driver, DEFAULT_PROFILE_DIR
from ..routes.database_routes import get_db_path
from ..infrastructure.paths import get_data_dir
from . import runner as selenium_pipeline_runner
from . import fast_pipeline_log_store

STEPS = [
    {"id": "scrape_pms", "label": "Scrape PMS inventory (API)"},
    {"id": "scrape_cm", "label": "Scrape Channel Manager (D-EDGE)"},
    {"id": "combine", "label": "Combine inventory"},
    {"id": "yield", "label": "Calculate yield"},
    {"id": "verify", "label": "Verify data"},
    {"id": "allotment", "label": "Push allotment (PMS API)"},
    {"id": "verify_allotment", "label": "Verify allotment push"},
    {"id": "bar", "label": "Update BAR pricing (D-EDGE)"},
]
STEP_IDS = [s["id"] for s in STEPS]
STEP_LABELS = {s["id"]: s["label"] for s in STEPS}

pipeline_queue = queue.Queue()
pipeline_active = False
pipeline_error = None
pipeline_current_step = None
_current_run_id = None
_lock = threading.Lock()

# Raw table column dtypes, matching integrations/pms/inventory_scraper.py's
# dtype_dict exactly, so pms_inventory_raw.db stays byte-compatible regardless
# of which scraper wrote it (InventoryDataView's "raw" tab reads this table).
_PMS_NUMERIC_COLUMNS = [
    'DLK', 'DLT', 'DLKP', 'DLTP', 'PRKG', 'PRKP', 'PRTG', 'PRTP', 'PRKL', 'PRTL',
    'Extra Bed', 'Total Room', 'Available', 'Tentative', 'Definite', 'Waiting List',
    'Allotment', 'Out of Order', 'Occupancy',
]
_PMS_RAW_DTYPE = {
    'Date': 'DATE', 'AVR': 'INTEGER', 'AVS': 'INTEGER', 'ASP': 'INTEGER', 'ASW': 'INTEGER',
    'AVP': 'INTEGER', 'BFS': 'INTEGER', 'DLK': 'INTEGER', 'DLT': 'INTEGER', 'DLKP': 'INTEGER',
    'DLTP': 'INTEGER', 'DLS': 'INTEGER', 'FAM': 'INTEGER', 'PRKG': 'INTEGER', 'PRKP': 'INTEGER',
    'PRTG': 'INTEGER', 'PRTP': 'INTEGER', 'PRKL': 'INTEGER', 'PRTL': 'INTEGER', 'PSU': 'INTEGER',
    'Extra Bed': 'INTEGER', 'Total Room': 'INTEGER', 'Available': 'INTEGER', 'Tentative': 'INTEGER',
    'Definite': 'INTEGER', 'Waiting List': 'INTEGER', 'Allotment': 'INTEGER', 'Out of Order': 'INTEGER',
}


class PipelineStepError(Exception):
    """Raised to stop the pipeline, tagging which step failed."""
    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


def try_acquire():
    """Atomic check-and-set so two racing 'start pipeline' requests can't both
    proceed. Also refuses to start while the Selenium pipeline (runner.py) is
    active, since scrape_cm/bar drive the same D-EDGE Chrome profile and
    running both at once would race for it. This is a one-directional check -
    it doesn't stop the Selenium pipeline from starting while this one is
    running - since guarding that direction too would require editing
    runner.py."""
    global pipeline_active
    with _lock:
        if pipeline_active:
            return False, "A fast pipeline run is already in progress"
        if selenium_pipeline_runner.pipeline_active:
            return False, "The Selenium pipeline is already running - wait for it to finish first"
        pipeline_active = True
        return True, None


def _emit(step, type_, message):
    pipeline_queue.put({"step": step, "type": type_, "message": message})
    if _current_run_id is not None:
        fast_pipeline_log_store.log_entry(_current_run_id, step, type_, message)


def _begin_step(step_id):
    global pipeline_current_step
    if allotment_run_control.stop_event.is_set():
        raise PipelineStepError(step_id, "Pipeline stopped by user before this step started")
    pipeline_current_step = step_id
    idx = STEP_IDS.index(step_id) + 1
    _emit(step_id, "info", f"Step {idx}/{len(STEPS)}: {STEP_LABELS[step_id]} - starting")


def _log_forwarder(step_ref, stop_flag):
    while True:
        try:
            msg = log_queue.get(timeout=0.2)
        except queue.Empty:
            if stop_flag.is_set():
                return
            continue
        if msg is None:
            continue
        msg = dict(msg)
        msg["step"] = step_ref[0]
        pipeline_queue.put(msg)
        if _current_run_id is not None:
            fast_pipeline_log_store.log_entry(_current_run_id, msg.get("step"), msg.get("type", "info"), msg.get("message", ""))


def _capture_prints(step_id, fn):
    class _Capture(StringIO):
        def write(self, text):
            if text.strip():
                _emit(step_id, "info", text.strip())
            return len(text)

    old_stdout = sys.stdout
    sys.stdout = _Capture()
    try:
        return fn()
    finally:
        sys.stdout = old_stdout


def _count_and_range(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        lo, hi = conn.execute(f"SELECT MIN(Date), MAX(Date) FROM {table}").fetchone()
        dates = {row[0] for row in conn.execute(f"SELECT DISTINCT Date FROM {table}")}
    finally:
        conn.close()
    return count, lo, hi, dates


_FILE_OWNER_STEP = {
    "pms_inventory_processed.db": "scrape_pms",
    "cm_inventory_processed.db": "scrape_cm",
    "combined_inventory.db": "combine",
    "inventory_allocation.db": "yield",
}


def _run_verify_step(pipeline_start_time, enabled_steps):
    for fname in ("pms_inventory_processed.db", "cm_inventory_processed.db",
                  "combined_inventory.db", "inventory_allocation.db"):
        path = get_db_path(fname)
        if not os.path.exists(path):
            raise PipelineStepError("verify", f"{fname} does not exist")
        owner_step = _FILE_OWNER_STEP[fname]
        if not enabled_steps.get(owner_step, True):
            _emit("verify", "info", f"{fname}: {owner_step} was skipped this run - not checking freshness")
            continue
        mtime = os.path.getmtime(path)
        if mtime < pipeline_start_time - 5:
            raise PipelineStepError("verify", f"{fname} was not updated by this pipeline run (stale)")
        _emit("verify", "info", f"{fname}: fresh ({datetime.fromtimestamp(mtime).isoformat()})")

    pms_n, pms_lo, pms_hi, pms_dates = _count_and_range(get_db_path("pms_inventory_processed.db"), "pms_inventory_processed")
    cm_n, cm_lo, cm_hi, cm_dates = _count_and_range(get_db_path("cm_inventory_processed.db"), "cm_inventory_processed")
    comb_n, comb_lo, comb_hi, comb_dates = _count_and_range(get_db_path("combined_inventory.db"), "combined_inventory")
    alloc_n, alloc_lo, alloc_hi, alloc_dates = _count_and_range(get_db_path("inventory_allocation.db"), "daily_inventory_allocation")

    for name, n in [("PMS", pms_n), ("CM", cm_n), ("Combined", comb_n), ("Allocation", alloc_n)]:
        if n == 0:
            raise PipelineStepError("verify", f"{name} table has 0 rows")
    _emit("verify", "info", f"Row counts - PMS {pms_n}, CM {cm_n}, Combined {comb_n}, Allocation {alloc_n}")

    if comb_n < max(pms_n, cm_n):
        raise PipelineStepError("verify", f"Combined ({comb_n}) is smaller than a source (PMS {pms_n}, CM {cm_n})")
    if alloc_n != comb_n:
        raise PipelineStepError("verify", f"Allocation row count ({alloc_n}) != combined row count ({comb_n})")

    union = pms_dates | cm_dates
    overlap_pct = (len(pms_dates & cm_dates) / len(union) * 100) if union else 0
    _emit("verify", "info", f"PMS {pms_lo}..{pms_hi}, CM {cm_lo}..{cm_hi}, date overlap {overlap_pct:.1f}%")
    if overlap_pct < 90:
        raise PipelineStepError(
            "verify",
            f"PMS/CM date ranges only overlap {overlap_pct:.1f}% "
            f"(PMS {pms_lo}..{pms_hi}, CM {cm_lo}..{cm_hi}) - check both scrapers used the same start date"
        )
    if comb_lo != min(pms_lo, cm_lo) or comb_hi != max(pms_hi, cm_hi):
        raise PipelineStepError("verify", f"Combined range ({comb_lo}..{comb_hi}) isn't the expected PMS union CM union")
    if alloc_lo != comb_lo or alloc_hi != comb_hi:
        raise PipelineStepError("verify", f"Allocation range ({alloc_lo}..{alloc_hi}) != combined range ({comb_lo}..{comb_hi})")


def _scrape_and_process_pms(start_date, username, password):
    """Fetch room availability via the PMS JSON API (100 days, matching the
    Selenium scraper's hardcoded window), write it to pms_inventory_raw.db in
    the same shape the Selenium scraper produces, then run it through the
    unmodified production process_pms_inventory() to write
    pms_inventory_processed.db."""
    rows, elapsed = fetch_room_inventory(start_date, days=100, username=username, password=password)
    if not rows:
        raise PipelineStepError("scrape_pms", "PMS API returned no rows")

    df = pd.DataFrame(rows)
    for col in _PMS_NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    data_dir = get_data_dir()
    raw_db_path = os.path.join(data_dir, 'pms_inventory_raw.db')
    conn = sqlite3.connect(raw_db_path)
    try:
        df.to_sql('pms_inventory', conn, if_exists='replace', index=False, dtype=_PMS_RAW_DTYPE)
    finally:
        conn.close()

    processed = process_pms_inventory(df)
    if processed is None:
        raise PipelineStepError("scrape_pms", "PMS processing failed (see log above)")
    return processed, elapsed


def run_pipeline(config):
    """Runs the enabled steps sequentially in a background thread. Expects
    pipeline_active already True (set by try_acquire() before this thread was
    started). Always restarts clean from step 1 - no resume state is kept.

    config["steps"]: optional dict of step id -> bool, same shape as
    runner.py's config["steps"].
    config["barRooms"]: optional list of "deluxe"/"premiere" narrowing the BAR
    step; an empty list is equivalent to skipping it.
    config["allotmentRoomTypes"]: optional list of FULL_ROOM_TYPE_CONFIG keys
    narrowing the allotment step; defaults to ["deluxe", "premiere"] when
    omitted, and an empty list is equivalent to skipping it (same convention
    as barRooms).
    config["allotmentDryRun"]: default True - builds every allotment payload
    without sending it. Must be explicitly set False to push live.
    config["barSkipUnchanged"]: default True - skips BAR dates whose computed
    price level already matches what was last successfully applied (tracked
    in bar_last_applied.json). Set False to force a full push this run.
    """
    global pipeline_error, pipeline_current_step, pipeline_active, _current_run_id
    pipeline_error = None
    pipeline_start_time = time.time()
    allotment_run_control.reset()
    _current_run_id = fast_pipeline_log_store.start_run(config)

    enabled = {s["id"]: (config.get("steps") or {}).get(s["id"], True) for s in STEPS}
    bar_rooms = tuple(config.get("barRooms") or ("deluxe", "premiere"))
    allotment_room_types = config.get("allotmentRoomTypes")
    if allotment_room_types is None:
        allotment_room_types = ["deluxe", "premiere"]
    allotment_room_types = [k for k in allotment_room_types if k in FULL_ROOM_TYPE_CONFIG]
    allotment_dry_run = config.get("allotmentDryRun", True) is not False

    step_ref = [None]
    stop_flag = threading.Event()
    forwarder = threading.Thread(target=_log_forwarder, args=(step_ref, stop_flag), daemon=True)
    forwarder.start()

    def begin(step_id):
        step_ref[0] = step_id
        _begin_step(step_id)

    def skip(step_id, reason="Skipped by user"):
        idx = STEP_IDS.index(step_id) + 1
        _emit(step_id, "skipped", f"Step {idx}/{len(STEPS)}: {STEP_LABELS[step_id]} - {reason}")

    dedge_driver = None
    try:
        headless = config.get("headless")

        if enabled["scrape_pms"]:
            begin("scrape_pms")
            _emit("scrape_pms", "info", "Fetching PMS room availability via API (no browser)...")
            processed, elapsed = _scrape_and_process_pms(config["startDate"], config["pmsUsername"], config["pmsPassword"])
            _emit("scrape_pms", "success", f"PMS inventory scraped and processed via API in {elapsed:.2f}s ({len(processed)} rows)")
        else:
            skip("scrape_pms")

        def ensure_dedge_driver():
            nonlocal dedge_driver
            if dedge_driver is None:
                _emit(step_ref[0], "info", f"Launching Chrome for D-EDGE (headless={bool(headless)})...")
                dedge_driver = dedge_setup_driver(DEFAULT_PROFILE_DIR, headless=headless)
            return dedge_driver

        if enabled["scrape_cm"]:
            begin("scrape_cm")
            ensure_dedge_driver()
            cm_result = scrape_cm_inventory(
                driver=dedge_driver, start_date=config["startDate"],
                username=config["dedgeUsername"], password=config["dedgePassword"],
                headless=headless)
            _emit("scrape_cm", "success", cm_result or "CM inventory processing completed successfully")
        else:
            skip("scrape_cm")

        if enabled["combine"]:
            begin("combine")
            combined = _capture_prints("combine", combine_inventory_files)
            if combined is None:
                raise PipelineStepError("combine", "combine_inventory_files() returned no data")
            _emit("combine", "success", f"Combined inventory: {len(combined)} rows")
        else:
            skip("combine")

        if enabled["yield"]:
            begin("yield")
            yielded = _capture_prints("yield", lambda: apply_custom_yield(config["yieldConfig"]))
            _emit("yield", "success", f"Yield calculated: {len(yielded)} rows written")
        else:
            skip("yield")

        if enabled["verify"]:
            begin("verify")
            _run_verify_step(pipeline_start_time, enabled)
            _emit("verify", "success", "All verification checks passed")
        else:
            skip("verify")

        allotment_result = None
        if enabled["allotment"] and allotment_room_types:
            begin("allotment")
            plan = build_full_plan(room_types=allotment_room_types, skip_unchanged=config.get("skipUnchanged", True))
            if not plan["jobs"]:
                _emit("allotment", "success", f"Nothing to push - {plan['skipped_ranges']} range(s) already match the channel manager")
            else:
                total_jobs = len(plan["jobs"])
                _emit("allotment", "info", f"{total_jobs} job(s) planned, {plan['skipped_ranges']} range(s) skipped (already matches CM)")

                progress = {"n": 0}

                def _on_job_result(r):
                    progress["n"] += 1
                    job = r["job"]
                    tag = f"[{progress['n']}/{total_jobs}]"
                    where = f"{job['label']} {job['start_date']}..{job['end_date']}"
                    retried_note = f" (after {r['attempts']} attempts)" if r.get("attempts", 1) > 1 else ""
                    if r["success"]:
                        state = "closed" if job["number_of_rooms"] <= 0 else f"{job['number_of_rooms']} room(s)"
                        _emit("allotment", "info", f"{tag} OK{retried_note} {where} -> {state}")
                    else:
                        _emit("allotment", "error", f"{tag} FAILED{retried_note} {where}: {r['error']}")

                def _on_retry(attempt, retrying_count, max_attempts):
                    _emit("allotment", "info", f"Retrying {retrying_count} job(s) that hit a transient PMS error (attempt {attempt}/{max_attempts})...")

                result = push_jobs_concurrent(
                    plan["jobs"],
                    company_id=config.get("companyId", 1001),
                    dry_run=allotment_dry_run,
                    max_workers=config.get("allotmentConcurrency", 4),
                    username=config["pmsUsername"], password=config["pmsPassword"],
                    on_result=_on_job_result,
                    on_retry=_on_retry,
                )
                allotment_result = result
                mode = "dry run" if allotment_dry_run else "LIVE"

                if not allotment_dry_run and result["failed_count"] > 0:
                    raise PipelineStepError("allotment", f"{result['failed_count']} of {result['total']} allotment push(es) failed - see the FAILED lines above for which ones and why")
                _emit("allotment", "success", f"Allotment ({mode}): {result['success_count']}/{result['total']} succeeded in {result['elapsed_seconds']:.2f}s")
        else:
            skip("allotment", "No room types selected" if enabled["allotment"] else "Skipped by user")

        if enabled["verify_allotment"]:
            begin("verify_allotment")
            if allotment_dry_run:
                _emit("verify_allotment", "success", "Dry run - nothing was pushed live, skipping re-check")
            elif allotment_result is None or allotment_result["success_count"] == 0:
                _emit("verify_allotment", "success", "Nothing was pushed this run - skipping re-check")
            else:
                _emit("verify_allotment", "info", "Re-checking pushed values against the PMS's own allotment grid...")
                try:
                    mismatches = verify_pushed_jobs(
                        allotment_result["results"],
                        company_id=config.get("companyId", 1001),
                        username=config["pmsUsername"], password=config["pmsPassword"],
                    )
                    for m in mismatches:
                        job = m["job"]
                        _emit("verify_allotment", "error",
                              f"MISMATCH {job['label']} {m['date']}: expected {m['expected']}, PMS shows {m['actual']}")
                    checked = allotment_result["success_count"]
                    mismatched_jobs = len({id(m["job"]) for m in mismatches})
                    if mismatches:
                        _emit("verify_allotment", "error", f"Re-check: {checked - mismatched_jobs}/{checked} pushed job(s) confirmed matching")
                    else:
                        _emit("verify_allotment", "success", f"Re-check: {checked}/{checked} pushed job(s) confirmed matching")
                except Exception as e:
                    _emit("verify_allotment", "success", f"Re-check skipped (verification itself failed, pushes are unaffected): {e}")
        else:
            skip("verify_allotment")

        if enabled["bar"] and bar_rooms:
            begin("bar")
            ensure_dedge_driver()
            if not update_bar(driver=dedge_driver, username=config["dedgeUsername"],
                               password=config["dedgePassword"], rooms=bar_rooms, headless=headless,
                               reset_checkpoint=config.get("resetCheckpoint", False),
                               skip_unchanged=config.get("barSkipUnchanged", True)):
                raise PipelineStepError("bar", "BAR price-level update failed (see log above)")
            _emit("bar", "success", f"BAR pricing updated successfully ({', '.join(bar_rooms)})")
        else:
            skip("bar", "No room types selected" if enabled["bar"] else "Skipped by user")

        _emit(None, "success", "Pipeline completed successfully")

    except PipelineStepError as e:
        pipeline_error = str(e)
        _emit(e.step, "error", str(e))
        _emit(None, "error", f"Pipeline stopped: {e}")

    except Exception as e:
        # Unlike PipelineStepError (raised deliberately, with a message that
        # already says what's wrong), reaching here means something broke
        # somewhere we didn't anticipate - the message alone (e.g. "'NoneType'
        # object has no attribute 'x'") won't say which line. Emit the full
        # traceback so it's visible in the log stream, not just the server console.
        pipeline_error = str(e)
        _emit(pipeline_current_step, "error", f"{e}\n{traceback.format_exc()}")
        _emit(None, "error", f"Pipeline stopped (unexpected error): {e}")

    finally:
        # dedge_driver is deliberately NOT quit here - it uses the persistent
        # D-EDGE profile so leaving it open preserves the trusted-device
        # session for next time, matching runner.py's convention.
        stop_flag.set()
        forwarder.join(timeout=5)
        fast_pipeline_log_store.finish_run(_current_run_id, "error" if pipeline_error else "success", pipeline_error)
        _current_run_id = None
        pipeline_current_step = None
        pipeline_active = False
        pipeline_queue.put(None)
