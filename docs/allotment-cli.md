# `allotment` CLI

Shell function defined in `~/.zshrc`. Starts the backend + frontend and,
optionally, triggers the Fast API Pipeline (`backend/app/pipeline/fast_runner.py`)
via `scripts/trigger_fast_pipeline.sh`.

Flags after `run` can be given in any order.

## Commands

| Command | What it does |
|---|---|
| `allotment run` | Starts backend + frontend only. |
| `allotment run --pipeline` | + triggers a **safe/preview** pipeline run: allotment push is a dry run, BAR step is skipped entirely. |
| `allotment run --pipeline-live` | + triggers a **live** pipeline run: real allotment push to the PMS, real BAR update to D-EDGE. |
| `allotment run --pipeline --schedule` | Safe/preview run now, then repeats automatically every hour until stopped. |
| `allotment run --pipeline-live --schedule` | Live run now, then repeats automatically every hour until stopped. |
| `allotment run --pipeline-live --schedule-15` | Live run now, then repeats automatically every 15 minutes until stopped. |
| `allotment run --pipeline-live --skip-bar` | Live run, skipping the BAR update step. |
| `allotment run --pipeline-live --schedule --skip-bar` | Live, hourly, skipping BAR. |
| `allotment run --tunnel` | + starts the Cloudflare tunnel, exposing the frontend at `https://console.krisnatha.com`. |

## Flags

| Flag | Effect |
|---|---|
| `--pipeline` | Trigger pipeline in safe/preview mode. |
| `--pipeline-live` | Trigger pipeline in live mode. |
| `--schedule` | Re-run the pipeline every hour until Ctrl-C. Works with either mode. If one scheduled run fails, it warns and retries at the next hourly slot instead of stopping the loop. |
| `--schedule-<minutes>` | Same as `--schedule`, but every `<minutes>` minutes instead of 60, e.g. `--schedule-15`. |
| `--skip-<step>` | Skip one pipeline step. Repeatable. |
| `--tunnel` | Also start the named Cloudflare tunnel (`cloudflared tunnel run revenue-console`), exposing the frontend publicly at `https://console.krisnatha.com`. |

Valid `<step>` values for `--skip-<step>`:

```
scrape_pms
scrape_cm
combine
yield
verify
allotment
verify_allotment
bar
```

(dashes also work, e.g. `--skip-verify-allotment`)

## Notes

- `Ctrl-C` stops the backend, frontend, any pipeline trigger/schedule loop, and the tunnel (if started with `--tunnel`) together.
- Every run — manual or scheduled — shows up in the **Fast API Pipeline → History** page in the app.
- `--schedule`/`--schedule-<minutes>` only run while the terminal session stays open; they do not survive closing the terminal or logging out. They hold a `caffeinate` assertion to block macOS *idle* sleep (otherwise the countdown pauses while asleep and the next run fires late) - but closing the lid still sleeps the Mac, and the loop, regardless.
- A second `--schedule`/`--schedule-<minutes>` invocation refuses to start while one is already running (tracked via `scripts/.trigger_fast_pipeline.schedule.pid`); stop the existing one with the `kill <PID>` command it prints first.
- Default pipeline config (yield settings, room types, concurrency) lives in `backend/app/scraper/data/scheduled_fast_pipeline_config.json`.
