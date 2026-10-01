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
