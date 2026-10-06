#!/bin/bash
# Triggers the Fast API Pipeline on an already-running (or just-started)
# backend, via the real HTTP API - not by importing fast_runner directly -
# so it shares pipeline_active guard state with anything else hitting the
# API (e.g. the UI) and shows up in the Fast API Pipeline History page like
# any other run.
#
# Usage: trigger_fast_pipeline.sh [--live] [--schedule|--schedule-<minutes>] [--skip-<step> ...]
#   (no args)     Safe/preview run: allotment push is a dry run and the BAR
#                 step is skipped entirely (fast_runner.py has no dry-run
#                 gate for BAR - only skipping it avoids a live price push).
#   --live        Real run: live allotment push and live BAR update, using
#                 scheduled_fast_pipeline_config.json as configured.
#   --schedule    Run immediately, then keep re-running every 60 minutes
#                 until stopped (Ctrl-C). Combine with --live for unattended
#                 live runs, or leave it off to repeat in safe/preview mode.
#   --schedule-N  Same as --schedule but every N minutes instead of 60, e.g.
#                 --schedule-15 for every 15 minutes.
#                 Either form refuses to start a second overlapping loop
#                 (see scripts/.trigger_fast_pipeline.schedule.pid) - if
#                 one's already running, kill its PID first. Holds a
#                 caffeinate assertion for the loop's lifetime so macOS idle
#                 sleep doesn't pause the countdown; closing the lid still
#                 sleeps the Mac (and the loop) regardless.
#   --skip-<step> Skip one pipeline step, e.g. --skip-bar. Repeatable.
#                 Valid steps: scrape_pms scrape_cm combine yield verify
#                 allotment verify_allotment bar (dashes in the flag are
#                 treated the same as underscores, e.g. --skip-verify-allotment).
set -euo pipefail

SELF="${BASH_SOURCE[0]}"
ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
CONFIG_FILE="$ROOT/backend/app/scraper/data/scheduled_fast_pipeline_config.json"
SCHEDULE_LOCK="$ROOT/scripts/.trigger_fast_pipeline.schedule.pid"

VALID_STEPS=(scrape_pms scrape_cm combine yield verify allotment verify_allotment bar)

SCHEDULE=0
SCHEDULE_MINUTES=60
LIVE=0
SKIP_STEPS=()
PASSTHROUGH_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --schedule)
      SCHEDULE=1
      ;;
    --schedule-[0-9]*)
      SCHEDULE=1
      SCHEDULE_MINUTES="${arg#--schedule-}"
      if ! [[ "$SCHEDULE_MINUTES" =~ ^[0-9]+$ ]] || [[ "$SCHEDULE_MINUTES" -lt 1 ]]; then
        echo "trigger_fast_pipeline.sh: invalid minutes in '$arg'" >&2
        exit 1
      fi
      ;;
    --live)
      LIVE=1
      PASSTHROUGH_ARGS+=("$arg")
      ;;
    --skip-*)
      step="${arg#--skip-}"
      step="${step//-/_}"
      if [[ ! " ${VALID_STEPS[*]} " == *" $step "* ]]; then
        echo "trigger_fast_pipeline.sh: unknown step '$step' in '$arg'" >&2
        echo "valid steps: ${VALID_STEPS[*]}" >&2
        exit 1
      fi
      SKIP_STEPS+=("$step")
      PASSTHROUGH_ARGS+=("$arg")
      ;;
    *)
      echo "trigger_fast_pipeline.sh: unknown argument '$arg'" >&2
      exit 1
      ;;
  esac
done

# --schedule/--schedule-N re-invokes this same script (minus the schedule
# flag itself) as a fresh process every interval, rather than looping inline -
# a single-run failure (curl error, PMS timeout, etc.) then just fails that
# one invocation's own `set -e` and exits with non-zero, which this loop
# treats as "try again next interval" instead of a set -e footgun that could
# silently skip cleanup or run partway through iteration N+1 with stale state.
# A lockfile recording this loop's own PID - so a second `--schedule`
# invocation (e.g. started again without noticing an earlier one never got
# killed) refuses to start instead of silently stacking a second hourly
# loop on top of the first. Each recursive single-run invocation below does
# NOT re-enter this block (SCHEDULE is only set on the top-level process -
# --schedule is deliberately excluded from PASSTHROUGH_ARGS), so the lock is
# acquired/released exactly once per schedule loop's lifetime.
if [[ "$SCHEDULE" == 1 ]]; then
  if [[ -f "$SCHEDULE_LOCK" ]]; then
    existing_pid="$(sed -n '1p' "$SCHEDULE_LOCK" 2>/dev/null)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "trigger_fast_pipeline.sh: a --schedule loop is already running (PID $existing_pid)." >&2
      echo "  $(sed -n '2p' "$SCHEDULE_LOCK" 2>/dev/null)" >&2
      echo "Stop it first with: kill $existing_pid" >&2
      exit 1
    fi
    echo "trigger_fast_pipeline.sh: clearing a stale schedule lock (PID $existing_pid is no longer running)" >&2
  fi
  printf '%s\n%s\n' "$$" "started $(date '+%Y-%m-%d %H:%M:%S'), args: ${PASSTHROUGH_ARGS[*]:-none}" > "$SCHEDULE_LOCK"
  trap '[[ "$(sed -n "1p" "$SCHEDULE_LOCK" 2>/dev/null)" == "$$" ]] && rm -f "$SCHEDULE_LOCK"' EXIT

  # Without this, macOS idle sleep suspends the `sleep` below along with
  # everything else - the countdown doesn't advance while asleep, so a run
  # due at HH:50 can fire arbitrarily late instead (confirmed: a loop idle
  # overnight drifted its "hourly" run by over an hour). `-w $$` ties
  # caffeinate's lifetime to this process, so it exits on its own whenever
  # the loop does (Ctrl-C included) - no separate cleanup needed. This only
  # blocks *idle* sleep; closing the lid still sleeps the Mac regardless.
  caffeinate -i -w $$ &

  echo "Schedule mode: running now, then every $SCHEDULE_MINUTES minute(s) until stopped (Ctrl-C)."
  while true; do
    if ! "$SELF" "${PASSTHROUGH_ARGS[@]}"; then
      echo "trigger_fast_pipeline.sh: this run failed - will retry at the next scheduled time" >&2
    fi
    echo "Next scheduled run at $(date -v+${SCHEDULE_MINUTES}M '+%H:%M') (Ctrl-C to stop)..."
    sleep "$((SCHEDULE_MINUTES * 60))"
  done
fi

COOKIES="$(mktemp)"
LOGIN_BODY="$(mktemp)"
PAYLOAD_BODY="$(mktemp)"
CSRF_FILE="$(mktemp)"
HOST_PORT_FILE="$(mktemp)"
LOG_FORMATTER="$(mktemp)"
trap 'rm -f "$COOKIES" "$LOGIN_BODY" "$PAYLOAD_BODY" "$CSRF_FILE" "$HOST_PORT_FILE" "$LOG_FORMATTER"' EXIT

# Pretty-prints the SSE log stream: one colored, symbol-prefixed line per
# event instead of raw `data: {"step": ..., "type": ..., "message": ...}`
# JSON. Runs as a separate process (not inline python -c) so curl's stdout
# can pipe straight into its stdin.
cat > "$LOG_FORMATTER" <<'PYEOF'
import json
import sys

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"

MARKERS = {
    "success": f"{GREEN}✓{RESET}",
    "error": f"{RED}✗{RESET}",
    "skipped": f"{DIM}–{RESET}",
}
COLORS = {"success": GREEN, "error": RED, "skipped": DIM}

for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data: "):
        continue
    try:
        event = json.loads(line[len("data: "):])
    except json.JSONDecodeError:
        continue
    step = event.get("step") or "pipeline"
    etype = event.get("type", "info")
    marker = MARKERS.get(etype, " ")
    color = COLORS.get(etype, "")
    label = f"{BOLD}{CYAN}[{step}]{RESET}"
    for msg_line in (event.get("message") or "").split("\n"):
        if not msg_line.strip():
            continue
        print(f"{marker} {label} {color}{msg_line}{RESET}")
    sys.stdout.flush()
PYEOF

START_DATE="$(date +%Y-%m-%d)"
SKIP_STEPS_CSV="$(IFS=,; echo "${SKIP_STEPS[*]:-}")"

# .env values (PINs, passwords) may contain shell metacharacters (backticks,
# $, quotes) - parsed with python-dotenv and written straight to request-body
# files, never threaded through bash variable interpolation into a command
# line, which would mangle or break on those.
python3 - "$ROOT/backend/.env" "$CONFIG_FILE" "$START_DATE" "$LIVE" "$SKIP_STEPS_CSV" \
  "$LOGIN_BODY" "$PAYLOAD_BODY" "$HOST_PORT_FILE" <<'PYEOF'
import json
import sys
from dotenv import dotenv_values

env_path, config_path, start_date, live, skip_steps_csv, login_body, payload_body, host_port_file = sys.argv[1:]
env = dotenv_values(env_path)
live = live == "1"
skip_steps = [s for s in skip_steps_csv.split(",") if s]

with open(config_path) as f:
    config = json.load(f)

config["startDate"] = start_date
config["pmsUsername"] = env.get("PMS_USERNAME")
config["pmsPassword"] = env.get("PMS_PASSWORD")
config["dedgeUsername"] = env.get("DEDGE_USERNAME")
config["dedgePassword"] = env.get("DEDGE_PASSWORD")
config["allotmentDryRun"] = not live
if not live:
    # No dry-run gate exists for the BAR step in fast_runner.py - skip it
    # entirely in safe mode rather than risk a live price push.
    config["barRooms"] = []

steps = config.setdefault("steps", {})
if not live:
    steps["bar"] = False
for step in skip_steps:
    steps[step] = False

with open(login_body, "w") as f:
    json.dump({"pin": env.get("APP_ACCESS_PIN")}, f)
with open(payload_body, "w") as f:
    json.dump(config, f)
with open(host_port_file, "w") as f:
    f.write(f"{env.get('APP_HOST') or '127.0.0.1'} {env.get('APP_PORT') or '5666'}\n")
PYEOF

read -r HOST PORT < "$HOST_PORT_FILE"
BASE="http://$HOST:$PORT"

echo "Waiting for backend at $BASE ..."
for _ in $(seq 1 30); do
  if curl -sf "$BASE/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -sf "$BASE/api/health" >/dev/null 2>&1; then
  echo "Backend never came up at $BASE" >&2
  exit 1
fi

curl -sf -c "$COOKIES" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  --data-binary "@$LOGIN_BODY" \
  | python3 -c 'import json,sys; json.dump({"csrf_token": json.load(sys.stdin)["csrf_token"]}, open(sys.argv[1], "w"))' "$CSRF_FILE"
CSRF="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["csrf_token"])' "$CSRF_FILE")"

SKIP_MSG=""
if [[ ${#SKIP_STEPS[@]} -gt 0 ]]; then
  SKIP_MSG=", skipping: ${SKIP_STEPS[*]}"
fi
echo "Starting Fast API Pipeline ($([[ "$LIVE" == 1 ]] && echo LIVE || echo safe/preview)$SKIP_MSG)..."
START_RESPONSE="$(curl -sf -b "$COOKIES" -X POST "$BASE/api/fast-pipeline/start" \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $CSRF" \
  --data-binary "@$PAYLOAD_BODY")"
echo "$START_RESPONSE"

echo "Streaming pipeline logs..."
curl -sN -b "$COOKIES" "$BASE/api/fast-pipeline/stream" | python3 -u "$LOG_FORMATTER"
