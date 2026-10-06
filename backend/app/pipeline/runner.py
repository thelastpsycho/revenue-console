"""Orchestrates the full data pipeline end-to-end in one background run:

  scrape PMS -> scrape CM -> combine inventory -> calculate yield ->
  verify data -> update Deluxe+Premiere allotment -> update BAR pricing

Each stage already exists as its own function (called individually today from
separate pages/buttons); this module calls them directly - not via their HTTP
routes - so it can own the whole run's progress stream and stop cleanly on
the first failure instead of continuing with stale/partial data.

Two of those stage functions (`scrape_cm_inventory`, `update_allotmet`,
`update_bar`) push their own progress messages onto the process-wide
`shared.log_queue` as a side effect of being called, regardless of caller.
`_log_forwarder` drains that queue for the duration of the run and republishes
each message onto `pipeline_queue`, tagged with whichever step is currently
running, so the pipeline can present one continuous, step-labeled stream
without those functions needing to change.
"""

import os
import sqlite3
import sys
import threading
import time
import queue
from datetime import datetime
from io import StringIO

from ..shared import log_queue, allotment_run_control
from ..integrations.pms.inventory_scraper import scrape_pms_inventory
from ..integrations.dedge.inventory_scraper import scrape_cm_inventory
from ..inventory.inventory_combiner import combine_inventory_files
from ..revenue.yield_engine import apply_custom_yield
from ..integrations.pms.allotment_updater import update_allotment_multi, setup_driver as pms_allot_setup_driver
from ..integrations.dedge.bar_updater import update_bar, setup_driver as dedge_setup_driver, DEFAULT_PROFILE_DIR
from ..routes.database_routes import get_db_path

STEPS = [
    {"id": "scrape_pms", "label": "Scrape PMS inventory"},
    {"id": "scrape_cm", "label": "Scrape Channel Manager (D-EDGE)"},
    {"id": "combine", "label": "Combine inventory"},
    {"id": "yield", "label": "Calculate yield (Deluxe/Premiere)"},
    {"id": "verify", "label": "Verify data"},
    {"id": "allotment", "label": "Update Deluxe + Premiere allotment (PMS)"},
    {"id": "bar", "label": "Update BAR pricing (D-EDGE)"},
]
STEP_IDS = [s["id"] for s in STEPS]
STEP_LABELS = {s["id"]: s["label"] for s in STEPS}

pipeline_queue = queue.Queue()
pipeline_active = False
pipeline_error = None
pipeline_current_step = None
_lock = threading.Lock()


class PipelineStepError(Exception):
    """Raised to stop the pipeline, tagging which step failed."""
    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


def try_acquire():
    """Atomic check-and-set so two racing 'start pipeline' requests can't
    both proceed."""
    global pipeline_active
    with _lock:
        if pipeline_active:
            return False
        pipeline_active = True
        return True


def _emit(step, type_, message):
    pipeline_queue.put({"step": step, "type": type_, "message": message})


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
            # Only the pipeline pushes its own terminal sentinel; a None from
            # some other caller of log_queue is not relevant here.
            continue
        msg = dict(msg)
        msg["step"] = step_ref[0]
        pipeline_queue.put(msg)


def _capture_prints(step_id, fn):
    """Redirects stdout during a print-only, non-log_queue call
    (scrape_pms_inventory, combine_inventory_files, apply_custom_yield) and
    forwards each printed line as a step-tagged progress message."""
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


# Which step produces each file the verify step inspects - used to skip the
# freshness assertion for a file whose producing step was skipped this run
# (the row-count/date-overlap checks below still run unconditionally, since
# those validate whatever data is actually on disk regardless of who wrote it).
_FILE_OWNER_STEP = {
    "pms_inventory_processed.db": "scrape_pms",
    "cm_inventory_processed.db": "scrape_cm",
    "combined_inventory.db": "combine",
    "inventory_allocation.db": "yield",
}


def _run_verify_step(pipeline_start_time, enabled_steps):
    # Freshness: a file whose producing step ran this run must be newer than
    # the moment the run started (catches a step that silently no-op'd and
    # left a stale file behind). Skipped steps intentionally reuse whatever is
    # already on disk, so their file's freshness isn't checked.
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

    # Row-count invariants: an outer merge can never shrink below its largest
    # input; apply_custom_yield never drops rows, so allocation must equal combined.
    if comb_n < max(pms_n, cm_n):
        raise PipelineStepError("verify", f"Combined ({comb_n}) is smaller than a source (PMS {pms_n}, CM {cm_n})")
    if alloc_n != comb_n:
        raise PipelineStepError("verify", f"Allocation row count ({alloc_n}) != combined row count ({comb_n})")

    # Date-range overlap: catches "the two scrapers used different start
    # dates" silently producing an NaN-riddled merge.
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


def run_pipeline(config):
    """Runs the enabled steps sequentially in a background thread, in the
    fixed order defined by STEPS. Expects pipeline_active already True (set
    by try_acquire() before this thread was started). Always restarts clean
    from step 1 - no resume state is kept.

    config["steps"]: optional dict of step id -> bool. A step missing from
    this dict, or an entirely absent "steps" key, defaults to enabled - so
    older callers that don't know about step-skipping still run everything.
    config["allotmentRoomTypes"] / config["barRooms"]: optional lists of
    "deluxe"/"premiere" narrowing which rooms those two steps touch; an empty
    list is equivalent to skipping the step (nothing to do).
    """
    global pipeline_error, pipeline_current_step, pipeline_active
    pipeline_error = None
    pipeline_start_time = time.time()
    allotment_run_control.reset()

    enabled = {s["id"]: (config.get("steps") or {}).get(s["id"], True) for s in STEPS}
    allotment_room_types = tuple(config.get("allotmentRoomTypes") or ("deluxe", "premiere"))
    # None (omitted) means both rooms; an explicit empty list means skip BAR.
    # Must not use `or` here - [] is falsy and would fall back to both rooms,
    # turning the trigger script's safe mode into a live price push.
    bar_rooms = config.get("barRooms")
    bar_rooms = ("deluxe", "premiere") if bar_rooms is None else tuple(bar_rooms)

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
    pms_driver = None
    try:
        headless = config.get("headless")

        if enabled["scrape_pms"]:
            begin("scrape_pms")
            result = _capture_prints("scrape_pms", lambda: scrape_pms_inventory(
                start_date=config["startDate"], username=config["pmsUsername"],
                password=config["pmsPassword"], headless=headless))
            if result is None:
                raise PipelineStepError("scrape_pms", "PMS scrape failed (see log above)")
            _emit("scrape_pms", "success", "PMS inventory scraped and processed")
        else:
            skip("scrape_pms")

        # The D-EDGE driver is shared by scrape_cm and bar (so the second
        # reuses the first's trusted-device session) - build it lazily the
        # first time either step actually needs it.
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

        if enabled["allotment"] and allotment_room_types:
            begin("allotment")
            pms_driver = pms_allot_setup_driver(headless=headless)
            # One login, one page load - both room types are pushed in the same
            # session so the second doesn't need to re-navigate from the login
            # page (which was failing when re-run mid-session; see
            # update_allotment_multi's docstring).
            if not update_allotment_multi(driver=pms_driver, username=config["pmsUsername"],
                                           password=config["pmsPassword"], room_types=allotment_room_types,
                                           headless=headless, skip_unchanged=config.get("skipUnchanged", True)):
                raise PipelineStepError("allotment", "Allotment update failed (see log above)")
            pms_driver.quit()
            pms_driver = None
            _emit("allotment", "success", f"Allotment updated successfully ({', '.join(allotment_room_types)})")
        else:
            skip("allotment", "No room types selected" if enabled["allotment"] else "Skipped by user")

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

    except Exception as e:
        pipeline_error = str(e)
        step = getattr(e, "step", pipeline_current_step)
        _emit(step, "error", str(e))
        _emit(None, "error", f"Pipeline stopped: {e}")

    finally:
        if pms_driver is not None:
            try:
                pms_driver.quit()
            except Exception:
                pass
        # Quit the D-EDGE driver: device trust lives in the persistent profile
        # on disk (a clean quit is what flushes cookies there), not in the
        # running browser. Leaving Chrome open keeps the profile locked, so the
        # next run's Chrome on the same --user-data-dir dies with "session not
        # created: Chrome instance exited".
        if dedge_driver is not None:
            try:
                dedge_driver.quit()
            except Exception:
                pass
        stop_flag.set()
        forwarder.join(timeout=5)
        pipeline_current_step = None
        pipeline_active = False
        pipeline_queue.put(None)  # single terminal sentinel for the whole run
