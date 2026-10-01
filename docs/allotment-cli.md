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
| `allotment run --pipeline-live --skip-bar` | Live run, skipping the BAR update step. |
| `allotment run --pipeline-live --schedule --skip-bar` | Live, hourly, skipping BAR. |

## Flags

| Flag | Effect |
|---|---|
| `--pipeline` | Trigger pipeline in safe/preview mode. |
| `--pipeline-live` | Trigger pipeline in live mode. |
| `--schedule` | Re-run the pipeline every hour until Ctrl-C. Works with either mode. If one scheduled run fails, it warns and retries at the next hourly slot instead of stopping the loop. |
| `--skip-<step>` | Skip one pipeline step. Repeatable. |

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

- `Ctrl-C` stops the backend, frontend, and any pipeline trigger/schedule loop together.
- Every run — manual or scheduled — shows up in the **Fast API Pipeline → History** page in the app.
- `--schedule` only runs while the terminal session stays open; it does not survive closing the terminal, logging out, or the Mac sleeping.
- Default pipeline config (yield settings, room types, concurrency) lives in `backend/app/scraper/data/scheduled_fast_pipeline_config.json`.
