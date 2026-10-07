# Running the Fast API Pipeline

Two separate paths, depending on where this is running:

- **Local Mac development** — the `allotment` zsh function + `scripts/trigger_fast_pipeline.sh`, unchanged, below.
- **Production (Docker)** — `docker compose up -d` + `scripts/trigger_fast_pipeline.py`, see further down. This is the path for the Windows/Docker deployment; the bash script above is superseded there but kept for local Mac dev where no containers are involved.

## Local Mac development

Shell function defined in `~/.zshrc`. Starts the backend + frontend and,
optionally, triggers the Fast API Pipeline (`backend/app/pipeline/fast_runner.py`)
via `scripts/trigger_fast_pipeline.sh`.

Flags after `run` can be given in any order.

### Commands

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

### Flags

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

### Notes

- `Ctrl-C` stops the backend, frontend, any pipeline trigger/schedule loop, and the tunnel (if started with `--tunnel`) together.
- Every run — manual or scheduled — shows up in the **Fast API Pipeline → History** page in the app.
- `--schedule`/`--schedule-<minutes>` only run while the terminal session stays open; they do not survive closing the terminal or logging out. They hold a `caffeinate` assertion to block macOS *idle* sleep (otherwise the countdown pauses while asleep and the next run fires late) - but closing the lid still sleeps the Mac, and the loop, regardless.
- A second `--schedule`/`--schedule-<minutes>` invocation refuses to start while one is already running (tracked via `scripts/.trigger_fast_pipeline.schedule.pid`); stop the existing one with the `kill <PID>` command it prints first.
- Default pipeline config (yield settings, room types, concurrency) lives in `backend/app/scraper/data/scheduled_fast_pipeline_config.json`.

## Production (Docker)

`docker compose up -d` (from the repo root) starts everything: `backend`
(Flask + Selenium/Chrome), `frontend` (nginx serving the built SPA and
reverse-proxying `/api/*`), `scheduler` (runs the recurring pipeline
trigger), and `cloudflared` (the same tunnel, `console.krisnatha.com`).

The `scheduler` service runs `scripts/trigger_fast_pipeline.py` — a pure
cross-platform Python port of the bash script above, with no
`caffeinate`/idle-sleep logic at all. That concern doesn't apply here: it
runs inside an always-up container rather than a terminal-attached loop, so
the only thing that matters is keeping the Windows host itself from
sleeping (a one-time host setting, not something this script manages).

### Schedule panel (default)

By default the scheduler runs with `--managed`: the schedule is controlled
from the **Schedule** panel on the Fast API Pipeline page, not from flags.

- **Run automatically** on/off, **Every** (5 min – 24 h), and **Mode**:
  - *Preview* — allotment dry run, BAR step forced off. Nothing is sent to
    the PMS or D-EDGE, whatever the saved run settings say.
  - *Live* — real allotment push and BAR update. Saving a live schedule asks
    for confirmation first.
- **Run settings** — by default `scheduled_fast_pipeline_config.json`.
  *Use this page's settings* snapshots the page's steps, room types,
  skip-unchanged options, concurrency, company ID and yield configuration
  for scheduled runs; *Revert to default* goes back to the JSON file.
  Credentials and the start date are never stored: scheduled runs use the
  backend's `backend/.env` credentials and today's date (hotel-local — both
  containers set `TZ=Asia/Makassar`).
- Turning it on runs immediately, then every interval. A run that comes due
  while another run is in progress waits for it and starts on the next 30s
  tick. Changing the interval re-times the next run from the last one.
- **Scheduler online/offline** shows whether the container is checking in
  (every 30s). Offline means no scheduled runs, regardless of the settings.

### D-EDGE device code

D-EDGE trusts this machine through a cookie in the persistent Chrome
profile (`backend/app/scraper/.dedge_profile/`). If it stops trusting it,
it emails a code to the hotel mailbox, and any run (scheduled or manual)
pauses at the D-EDGE login:

- A yellow **D-EDGE needs a device code** banner appears at the top of every
  page. Type the code from the email and press *Submit*; the paused run
  enters it in D-EDGE and continues. A rejected code shows an error and the
  run keeps waiting; *Resend email* asks D-EDGE for a new one.
- The run waits up to 15 minutes (`DEDGE_DEVICE_CODE_TIMEOUT`, in seconds),
  then fails. The next run asks again.
- The **D-EDGE session** card on the Fast API Pipeline page shows when the
  session was last verified, and *Check session now* runs the same login a
  run does (no export, no changes), so you can re-authorize between runs.
  It can't start while a pipeline run is in progress.

The settings are stored by the backend in
`backend/app/scraper/data/fast_pipeline_schedule.json` (gitignored) and take
effect on the next tick - no container restart. It ships **off**. Scheduled
runs are tagged `"trigger": "schedule"` in History. The scheduler doesn't
stream run logs to `docker compose logs` (the log stream has a single
consumer, so it would take them from a watching browser) - follow runs in
the page or the History view instead.

Only one machine should run a live schedule: both the Mac and this
deployment push to the same PMS and D-EDGE accounts.

### Fixed-flag loop (override)

Setting `SCHEDULER_ARGS` in a root `.env` (see `.env.docker.example`)
replaces `--managed` with the old fixed loop, e.g.
`SCHEDULER_ARGS=--live --schedule-60`, and the panel's settings are then
ignored. Apply with `docker compose up -d`; no rebuild needed.

Manual one-off triggers against an already-running stack:

```
docker compose exec scheduler python scripts/trigger_fast_pipeline.py \
  --live --base-url http://backend:5666 --skip-bar
```

The Python script also runs standalone outside Docker (any OS, given
`requests` + `python-dotenv` installed) exactly like the bash version, minus
the macOS-only pieces — it reads `backend/.env` for `APP_HOST`/`APP_PORT`
when `--base-url` isn't given.

Same valid `--skip-<step>` values and `scheduled_fast_pipeline_config.json`
as the local path above — nothing about the pipeline steps themselves
changes between the two.
