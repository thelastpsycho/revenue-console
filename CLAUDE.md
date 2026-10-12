# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## What this is

**Revenue Console** — a hotel inventory and revenue-automation tool. Selenium (and, for the PMS side, a reverse-engineered JSON API) collects inventory from the hospitality PMS and D-EDGE, the backend normalizes and combines those datasets, a yield engine calculates online allocation/BAR decisions, and automation flows can push allotment and pricing changes back to the PMS and D-EDGE.

- `backend/` — Flask API, data processing, Selenium integrations, and automation pipeline
- `frontend/` — Vue 3 + TypeScript + Vite SPA

## Commands

Backend (from `backend/`):

```bash
pip install -r requirements-dev.txt
python run.py
```

Frontend (from `frontend/`):

```bash
npm install
npm run dev
npm run build
npm run preview
```

Backend tests live in `backend/tests/` (`PYTHONPATH=backend pytest -q backend/tests` from the repository root). `.github/workflows/verify.yml` runs Python tests and `npm run build` on PRs.

## Backend architecture

`backend/app/__init__.py` is the Flask app factory and registers four blueprints:

- `routes/main.py` — individual scrape/process/yield/allotment/BAR actions and SSE progress streams
- `routes/database_routes.py` — read-only SQLite data endpoints
- `routes/pipeline_routes.py` — end-to-end pipeline control and SSE progress stream
- `routes/auth_routes.py` — operator session authentication and CSRF token issuance

Source code is organized by responsibility:

- `integrations/pms/` — hospitality PMS scraping and allotment automation
- `integrations/dedge/` — D-EDGE inventory scraping and BAR updates
- `inventory/` — PMS/CM processing, inventory combination, allocation persistence
- `revenue/` — yield engine and BAR-rate processing
- `pipeline/` — full workflow orchestration
- `infrastructure/` — shared runtime-path helpers

### Runtime data

For backward compatibility, runtime data remains in:

`backend/app/scraper/data/`

The source-code refactor does **not** move existing SQLite databases, uploads, screenshots, or HTML debug artifacts. This directory was briefly tracked in git (2026-09-26 to 2026-10-01) so pipeline output would have history, but that produced working-tree churn on every run instead - as of 2026-10-01 it's gitignored again, with one deliberate exception: `scheduled_fast_pipeline_config.json` (the Fast API Pipeline CLI's default config, not generated output) stays tracked. The persistent D-EDGE Chrome profile remains gitignored at:

`backend/app/scraper/.dedge_profile/`

Use `infrastructure/paths.py` instead of constructing these paths manually.

### Data pipeline

1. `integrations/pms/inventory_scraper.py` — scrapes PMS availability and writes `pms_inventory_raw.db`, then runs PMS processing.
2. `inventory/pms_processor.py` — writes `pms_inventory_processed.db`.
3. `integrations/dedge/inventory_scraper.py` — exports D-EDGE room planning data and runs CM processing.
4. `inventory/channel_manager_processor.py` — writes `cm_inventory_processed.db`.
5. `inventory/inventory_combiner.py` — writes `combined_inventory.db`.
6. `revenue/yield_engine.py` — writes `inventory_allocation.db` (table `daily_inventory_allocation`).
7. `integrations/pms/allotment_updater.py` and `other_room_allotment_updater.py` — push calculated allotments into the PMS.
8. `integrations/dedge/bar_updater.py` — pushes BAR levels into D-EDGE.

`pipeline/runner.py` orchestrates the automated seven-step workflow:

PMS scrape → D-EDGE scrape → combine → yield → verify → PMS allotment → D-EDGE BAR.

### Stop sale emails

`stop_sale/` + `routes/stop_sale_routes.py` + `StopSaleView.vue` (`/stop-sale`). Reads `combined_inventory.db`: a date stops sale for every room type when occupancy >= the occupancy threshold, or for a single room type when its remaining rooms <= that room type's threshold. The operator ticks dates and presses Send - nothing is automatic. One email per recipient (no CC) over SMTP configured by `SMTP_*` env vars in `backend/.env`; recipients, rule/email settings and send history live in `stop_sale.db`. Sends recompute closures server-side; the browser only supplies the ticked dates.

### RMS (forecast & pace)

`revenue/rms_forecast.py` + `revenue/booking_events.py` + `routes/rms_routes.py` + `RmsView.vue` (`/rms`). Forecast uses independently refreshed, persistent PMS report sections. Pace reads append-only observed versions in `booking_events.db` (PII-free master folios; cancelled = `L`); earlier reconstructed history is labeled estimated. After initial backfill, daily and weekly syncs revisit future and in-house arrivals. Local settings provide revenue rules, attention thresholds and monthly targets; notes and exports support meetings. Current behavior and limitations: `docs/rms-improvements.md`; original endpoint findings: `docs/rms-plan.md`.

### Progress streaming

Long-running operations run in background threads and use SSE for live logs.

- PMS scraping uses `scraping_progress` in `routes/main.py`.
- Allotment and BAR operations share `log_queue` from `app/shared.py`.
- The full pipeline republishes progress through its own `pipeline_queue`.

## Frontend architecture

Vue Router lives in `src/router.ts`. Routed components use the `*View.vue` naming convention:

- `DashboardView.vue`
- `InventoryCollectionView.vue`
- `InventoryDataView.vue`
- `YieldManagementView.vue`
- `AllotmentManagementView.vue`
- `BarPricingView.vue`
- `AutomationPipelineView.vue`

The existing public route URLs remain unchanged.

The shared axios instance uses a relative base URL and Vite proxies `/api` to the Flask backend during development.

## Security

`APP_ACCESS_PIN` (a 6-digit PIN) and `APP_SESSION_SECRET` must be configured on the backend before authenticated API endpoints become available. The UI is gated by `AuthGate.vue` and the axios client attaches CSRF tokens on writes. Never introduce provider credentials via `VITE_*` frontend variables. BAR partial-run recovery is implemented in `integrations/dedge/bar_checkpoint.py`.

The DeepSeek-backed chat/assistant page (`InventoryAssistantView.vue`) and its `routes/assistant_routes.py` server-side proxy were removed - the feature called DeepSeek with a hardcoded API key. Both the DeepSeek key and the D-EDGE password were previously embedded in public frontend history: rotate/revoke them immediately; see `SECURITY.md`. Removing the source file does not do that.

## Production server access

The production deployment runs on a Windows laptop reachable via SSH over a Cloudflare tunnel (not the public hotel Wi-Fi, which is firewalled off). From a machine with `cloudflared` installed, add to `~/.ssh/config`:

```
Host console2-ssh
  HostName ssh-console2.krisnatha.com
  User "The Anvaya Bali"
  ProxyCommand cloudflared access ssh --hostname %h
```

Then `ssh console2-ssh`. Key-based auth is set up; password login may still be enabled server-side.

- Log in as the **`The Anvaya Bali`** Windows account, not `User` - the repo checkout, git install, and Docker Desktop all belong to that account. Logging in as `User` hits a git "dubious ownership" error and can't find `git` on PATH.
- Remote shell is `cmd.exe` (Windows OpenSSH default) - use Windows path syntax (`C:\...`, `&&`/`&` separators, double-quoted paths with spaces), not bash.
- Project path: `C:\Users\The Anvaya Bali\Documents\revenue-console`
- `git.exe` isn't on PATH over SSH; use the full path: `C:\Users\The Anvaya Bali\AppData\Local\Programs\Git\cmd\git.exe`
- The server checkout tracks `origin/main` (not `docker-production`) and deploys via `docker compose`. `docker ps` shows four containers: `revenue-console-frontend`, `revenue-console-backend`, `revenue-console-scheduler`, and `revenue-console-cloudflared` (the tunnel exposing the app itself, separate from the SSH tunnel above).
- This is a live system serving real traffic - treat rebuilds/restarts as having real downtime, and confirm with the user before running them.

### Docker builds over SSH

`docker compose build` fails over this SSH session with `error getting credentials` / `A specified logon session does not exist`. Cause: SSH key-based (pubkey) logins get a Windows logon type that never sees the account password, so Docker Desktop's credential helper can't unlock DPAPI-protected secrets - this happens even for pulling fully public images (node, python, nginx base images), and isn't fixable by editing `~/.docker/config.json` (tried: removing `credsStore`, disabling BuildKit, switching Docker context - none bypass it, since Desktop forwards credentials at the engine level, not the CLI config level).

Working fix: a Windows Scheduled Task with **"Run whether user is logged on or not"** (`taskschd.msc`, not `schtasks /create` with an `/rp` password argument - that would put the password in shell history/process logs). This logon type does have DPAPI access. One-time setup, done locally at the machine (not over SSH):

1. Task Scheduler → Create Task → name it e.g. `revenue-console-deploy`.
2. General tab → Security options → **"Run whether user is logged on or not"** → enter the account password in the dialog when prompted.
3. Actions tab → New → Program: `cmd.exe`, Arguments:
   ```
   /c cd /d "C:\Users\The Anvaya Bali\Documents\revenue-console" && docker compose build && docker compose up -d > deploy_log.txt 2>&1
   ```
4. Triggers tab: none needed - start it manually.

Once created, trigger it over SSH with `schtasks /run /tn revenue-console-deploy` and check `deploy_log.txt` for the result, instead of running `docker compose build` directly over SSH.
