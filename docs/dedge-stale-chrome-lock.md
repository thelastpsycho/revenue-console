# D-EDGE "session not created: Chrome instance exited"

**Status: fixed (2026-10-11).**

## Symptom

The D-EDGE session check ("Check session now" on the Fast API Pipeline
page's Automation tab) and the scheduled Fast API Pipeline's `scrape_cm`/
`bar` steps both failed with:

```
D-EDGE session check failed: Message: session not created: Chrome instance
exited. Examine ChromeDriver verbose log to determine the cause...
```

No D-EDGE device-code banner appeared, because the run never got far enough
to reach D-EDGE's device-check page - Chrome itself failed to start. This
looked like an OTP/banner bug but wasn't one; see the back half of this
investigation in the PR that added the immediate device-code webhook alert
for the (separate, real) gap that *does* affect the banner: an unattended
run's 15-minute device-code wait can expire with nobody watching the SPA.

## Root cause

Every D-EDGE call site (`pipeline/runner.py`'s Selenium pipeline,
`pipeline/fast_runner.py`'s Fast API Pipeline, and the manual session check
in `routes/dedge_auth_routes.py`) launches Chrome against the same on-disk
profile directory (`infrastructure/paths.py:get_dedge_profile_dir()`), so
the D-EDGE "trusted device" cookie survives across runs and the device-code
email is only needed once.

If a previous run's Chrome didn't exit cleanly - crashed, got OOM-killed, or
`driver.quit()` itself raised (swallowed by a bare `except: pass` in
`runner.py`/`fast_runner.py`'s `finally` blocks) - the profile directory is
left holding `SingletonLock`/`SingletonCookie`/`SingletonSocket`, Chrome's
own "another instance already has this profile open" markers. The next
`setup_driver()` call then launches a *new* Chrome against that same
profile; Chrome sees the lock, assumes another instance owns it, and exits
immediately. ChromeDriver reports that exit as `session not created: Chrome
instance exited`, which is indistinguishable at a glance from a real D-EDGE
problem.

Confirmed in production: both the 08:07 PM scheduled run and an 08:57 PM
manual session check failed with the identical error, on an hourly
schedule, until this fix shipped.

## Fix

`bar_updater.setup_driver()` now calls `_kill_stale_chrome(user_data_dir)`
before every launch. It's safe to run unconditionally: every caller already
holds the in-process `pipeline_active`/`check_running` lock
(`try_acquire()` / `try_start_check()`) before calling `setup_driver()`, so
nothing legitimate can be using the profile right now - anything still
pinned to it is leftover from a run that didn't clean up.

It does two things:

1. Scans `/proc/[0-9]*/cmdline` (pure Python, no `pgrep`/`pkill` - not
   installed in the slim Docker image) for any process whose command line
   references both the profile directory and `chrome`, and `SIGKILL`s it.
   A no-op on macOS/dev, where `/proc` doesn't exist.
2. Removes `SingletonLock`, `SingletonCookie`, `SingletonSocket` from the
   profile directory if present.

This only addresses the Chrome-launch failure. It does not change anything
about device-code handling - see the separate webhook-alert fix for that.

## Verification

- `backend/tests/test_stale_chrome_lock.py` - lock-file cleanup.
- Reproduced live on production (`console2.krisnatha.com`) before the fix:
  manual check and scheduled run both failed identically.
- Requires a redeploy of the backend container to take effect (the fix is
  in `setup_driver()`, called from the already-running gunicorn worker's
  code, not something a stale process picks up live).
