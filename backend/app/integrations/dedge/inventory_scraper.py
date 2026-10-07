"""Download the Channel Manager "Rooms" planning export from D-EDGE / Availpro
and process it into cm_inventory_processed.db - automating what the "Process
CM" modal previously required by hand (download the Excel export from
https://extranet.availpro.com/Planning/Monthly?hotelId=22255&language=en,
upload it, click Process CM).

The extranet's own "Export" button POSTs exportType=excel&start=...&end=... to
Planning/Monthly/Export, which redirects to a token URL that streams back the
.xlsx. We replicate that POST with an in-page `fetch()` (run via
`execute_async_script`) so it runs inside the already-authenticated browser
tab rather than a separate Python HTTP client.

bar_updater.py's ensure_logged_in() only checks session validity against the
pricing-grid page (Plannings/.../pricinggrid/apply), which - inconsistently
with the rest of the site - does NOT enforce the "new device" check the way
Planning/Monthly does. So a session that looks valid there can still bounce
to the device-verification page the moment we load Planning/Monthly. We check
again after navigating there and, same as ensure_logged_in, block for a human
to enter the emailed code in the visible browser window if needed.

Login reuses bar_updater.py's D-EDGE session handling (persistent Chrome
profile so the "new device" email code is only needed once).
"""

import base64
import os
from datetime import datetime, timedelta

from ...inventory.channel_manager_processor import process_cm_inventory
from .bar_updater import (
    DEFAULT_PROFILE_DIR,
    HOTEL_ID,
    _wait_for_device_authorization,
    ensure_logged_in,
    log,
    resolve_headless,
    setup_driver,
    wait_for_page_load,
)

PLANNING_URL = f"https://extranet.availpro.com/Planning/Monthly?hotelId={HOTEL_ID}&language=en"
EXPORT_URL = "https://extranet.availpro.com/Planning/Monthly/Export"

_FETCH_EXPORT_SCRIPT = """
var start = arguments[0];
var end = arguments[1];
var callback = arguments[arguments.length - 1];
fetch(arguments[2], {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    credentials: 'include',
    body: 'exportType=excel&start=' + start + '&end=' + end
}).then(function(res) {
    return res.blob().then(function(blob) {
        var reader = new FileReader();
        reader.onloadend = function() {
            callback({
                status: res.status,
                contentType: res.headers.get('Content-Type') || '',
                dataUrl: reader.result
            });
        };
        reader.onerror = function() { callback({error: 'FileReader failed'}); };
        reader.readAsDataURL(blob);
    });
}).catch(function(err) { callback({error: String(err)}); });
"""


def _fetch_export(driver, start_str, end_str, timeout=60):
    driver.set_script_timeout(timeout)
    result = driver.execute_async_script(_FETCH_EXPORT_SCRIPT, start_str, end_str, EXPORT_URL)
    if result.get("error"):
        raise RuntimeError(f"CM export fetch failed: {result['error']}")
    if result.get("status") != 200:
        raise RuntimeError(f"CM export fetch returned HTTP {result.get('status')}")
    content_type = result.get("contentType", "")
    if "spreadsheetml" not in content_type:
        raise RuntimeError(
            f"Unexpected export response (expected an Excel file, got {content_type!r})"
        )
    # dataUrl looks like "data:<mime>;base64,<payload>".
    _, _, b64_payload = result["dataUrl"].partition(",")
    return base64.b64decode(b64_payload)


def _open_planning(driver):
    """Load Planning/Monthly. It enforces the device-trust check more strictly
    than ensure_logged_in's probe page, so re-check for it here."""
    driver.get(PLANNING_URL)
    wait_for_page_load(driver)
    if "/Device" in driver.current_url:
        _wait_for_device_authorization(driver)
        driver.get(PLANNING_URL)
        wait_for_page_load(driver)
        if "/Device" in driver.current_url:
            raise RuntimeError(f"Still on the device-verification page after waiting (at {driver.current_url})")


def verify_session(username=None, password=None, user_data_dir=DEFAULT_PROFILE_DIR):
    """Log in (if needed) and open the planning page, the same checks a
    pipeline run makes, without exporting or changing anything. If D-EDGE asks
    for a device code, this waits for it like a run would. Raises on failure."""
    username = username or os.environ.get("DEDGE_USERNAME", "")
    password = password or os.environ.get("DEDGE_PASSWORD", "")
    driver = setup_driver(user_data_dir)
    try:
        ensure_logged_in(driver, username, password)
        _open_planning(driver)
    finally:
        driver.quit()


def scrape_cm_inventory(driver=None, start_date=None, days=100, username=None, password=None,
                         user_data_dir=DEFAULT_PROFILE_DIR, headless=None):
    """Log into D-EDGE, export the Rooms planning grid as Excel, and process it.

    start_date: 'YYYY-MM-DD', defaults to today. days defaults to 100 to match
    the PMS scraper's range, so combine_inventory has full date overlap between
    the two sources.
    Credentials fall back to the DEDGE_USERNAME / DEDGE_PASSWORD env vars.
    """
    username = username or os.environ.get("DEDGE_USERNAME", "")
    password = password or os.environ.get("DEDGE_PASSWORD", "")

    from ...infrastructure.paths import get_data_dir
    data_dir = get_data_dir()
    os.makedirs(data_dir, exist_ok=True)

    owns_driver = driver is None
    try:
        if driver is None:
            driver = setup_driver(user_data_dir, headless=headless)

        ensure_logged_in(driver, username, password)

        # The export endpoint relies on server-side session state (current hotel /
        # planning context) that only gets set by actually loading the Planning
        # page, not just by having a valid extranet cookie.
        _open_planning(driver)

        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now()
        end = start + timedelta(days=days)

        log(driver, f"Exporting CM planning from {start:%Y-%m-%d} to {end:%Y-%m-%d}...")
        content = _fetch_export(driver, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

        upload_path = os.path.join(data_dir, "cm_upload.xlsx")
        with open(upload_path, "wb") as f:
            f.write(content)
        log(driver, f"CM export saved to {upload_path}")

        result = process_cm_inventory()
        log(driver, result)
        return result

    finally:
        if owns_driver and driver and resolve_headless(headless):
            # Nobody can inspect a headless browser, and leaving it running keeps
            # the persistent profile locked for the next run.
            driver.quit()
        elif owns_driver and driver:
            # Leave the browser open for inspection, matching update_bar's habit.
            pass


if __name__ == "__main__":
    scrape_cm_inventory()
