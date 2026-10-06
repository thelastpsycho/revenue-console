#!/usr/bin/env python3
"""Triggers the Fast API Pipeline on an already-running (or just-started)
backend, via the real HTTP API - not by importing fast_runner directly - so
it shares pipeline_active guard state with anything else hitting the API
(e.g. the UI) and shows up in the Fast API Pipeline History page like any
other run.

Cross-platform port of trigger_fast_pipeline.sh (stdlib + requests +
python-dotenv only) for use in the production/Docker scheduler container,
Windows, or any environment without bash. The .sh script remains the local
Mac dev path; this one has no OS-specific idle-sleep handling at all - that
concern now belongs to whatever host/container keeps this process running.

Usage: trigger_fast_pipeline.py [--live] [--schedule|--schedule-<minutes>]
                                 [--skip-<step> ...] [--base-url URL]
  (no args)     Safe/preview run: allotment push is a dry run and the BAR
                step is skipped entirely (fast_runner.py has no dry-run
                gate for BAR - only skipping it avoids a live price push).
  --live        Real run: live allotment push and live BAR update, using
                scheduled_fast_pipeline_config.json as configured.
  --schedule    Run immediately, then keep re-running every 60 minutes
                until stopped (Ctrl-C). Combine with --live for unattended
                live runs, or leave it off to repeat in safe/preview mode.
  --schedule-N  Same as --schedule but every N minutes instead of 60, e.g.
                --schedule-15 for every 15 minutes.
                Either form refuses to start a second overlapping loop (see
                scripts/.trigger_fast_pipeline.schedule.pid) unless the lock
                is stale (last refreshed more than 3x the interval ago).
  --skip-<step> Skip one pipeline step, e.g. --skip-bar. Repeatable.
                Valid steps: scrape_pms scrape_cm combine yield verify
                allotment verify_allotment bar (dashes in the flag are
                treated the same as underscores, e.g. --skip-verify-allotment).
  --base-url    Base URL of the running backend, e.g. http://backend:5666.
                Not present in the bash version - needed because inside a
                container "127.0.0.1" means "this container," not the
                backend. Defaults to http://<APP_HOST>:<APP_PORT> read from
                backend/.env (or the environment) when omitted, matching the
                bash script's behavior for local/manual runs.
"""
import atexit
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "backend" / "app" / "scraper" / "data" / "scheduled_fast_pipeline_config.json"
SCHEDULE_LOCK = ROOT / "scripts" / ".trigger_fast_pipeline.schedule.pid"
ENV_FILE = ROOT / "backend" / ".env"

VALID_STEPS = [
    "scrape_pms", "scrape_cm", "combine", "yield",
    "verify", "allotment", "verify_allotment", "bar",
]

RESET, DIM, BOLD, GREEN, RED, CYAN = (
    "\033[0m", "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[36m",
)
MARKERS = {"success": f"{GREEN}✓{RESET}", "error": f"{RED}✗{RESET}", "skipped": f"{DIM}–{RESET}"}
COLORS = {"success": GREEN, "error": RED, "skipped": DIM}

SCHEDULE_MINUTES_RE = re.compile(r"^--schedule-(\d+)$")

# Env var names this script actually needs - checked in os.environ first (how
# the scheduler container gets them, via compose's `env_file:`) and only
# falls back to reading backend/.env directly when a var isn't already set,
# matching bash's dotenv_values() behavior for local/manual runs where
# nothing has pre-populated the process environment.
ENV_KEYS = (
    "APP_ACCESS_PIN", "APP_HOST", "APP_PORT",
    "PMS_USERNAME", "PMS_PASSWORD", "DEDGE_USERNAME", "DEDGE_PASSWORD",
)


class PipelineRunError(Exception):
    """A single run attempt failed - caller decides whether to retry."""


class Args:
    def __init__(self):
        self.live = False
        self.schedule = False
        self.schedule_minutes = 60
        self.skip_steps = []
        self.base_url = None

    def describe(self):
        parts = []
        if self.live:
            parts.append("--live")
        parts.extend(f"--skip-{s.replace('_', '-')}" for s in self.skip_steps)
        return " ".join(parts) or "none"


def parse_args(argv):
    args = Args()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--schedule":
            args.schedule = True
        elif SCHEDULE_MINUTES_RE.match(arg):
            minutes = int(SCHEDULE_MINUTES_RE.match(arg).group(1))
            if minutes < 1:
                sys.exit(f"trigger_fast_pipeline.py: invalid minutes in '{arg}'")
            args.schedule = True
            args.schedule_minutes = minutes
        elif arg == "--live":
            args.live = True
        elif arg.startswith("--skip-"):
            step = arg[len("--skip-"):].replace("-", "_")
            if step not in VALID_STEPS:
                sys.exit(
                    f"trigger_fast_pipeline.py: unknown step '{step}' in '{arg}'\n"
                    f"valid steps: {' '.join(VALID_STEPS)}"
                )
            args.skip_steps.append(step)
        elif arg == "--base-url":
            i += 1
            if i >= len(argv):
                sys.exit("trigger_fast_pipeline.py: --base-url requires a value")
            args.base_url = argv[i]
        elif arg.startswith("--base-url="):
            args.base_url = arg[len("--base-url="):]
        else:
            sys.exit(f"trigger_fast_pipeline.py: unknown argument '{arg}'")
        i += 1
    return args


def load_env():
    file_values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    merged = dict(file_values)
    for key in ENV_KEYS:
        if os.environ.get(key):
            merged[key] = os.environ[key]
    return merged


def resolve_base_url(explicit_base_url, env):
    if explicit_base_url:
        return explicit_base_url.rstrip("/")
    host = env.get("APP_HOST") or "127.0.0.1"
    port = env.get("APP_PORT") or "5666"
    return f"http://{host}:{port}"


def build_payload(env, start_date, live, skip_steps):
    with open(CONFIG_FILE) as f:
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
    return config


def wait_for_backend(session, base_url, attempts=30):
    print(f"Waiting for backend at {base_url} ...")
    for _ in range(attempts):
        try:
            resp = session.get(f"{base_url}/api/health", timeout=5)
            if resp.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise PipelineRunError(f"backend never came up at {base_url}")


def login(session, base_url, pin):
    try:
        resp = session.post(f"{base_url}/api/auth/login", json={"pin": pin}, timeout=10)
        resp.raise_for_status()
        return resp.json()["csrf_token"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise PipelineRunError(f"login failed: {exc}") from exc


def start_pipeline(session, base_url, csrf_token, payload):
    try:
        resp = session.post(
            f"{base_url}/api/fast-pipeline/start",
            json=payload,
            headers={"X-CSRF-Token": csrf_token},
            timeout=10,
        )
        resp.raise_for_status()
        print(resp.text)
    except requests.RequestException as exc:
        raise PipelineRunError(f"failed to start pipeline: {exc}") from exc


def stream_logs(session, base_url):
    try:
        with session.get(f"{base_url}/api/fast-pipeline/stream", stream=True, timeout=(10, None)) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                try:
                    event = json.loads(raw_line[len("data: "):])
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
    except requests.RequestException as exc:
        raise PipelineRunError(f"log stream failed: {exc}") from exc


def run_once(args):
    env = load_env()
    base_url = resolve_base_url(args.base_url, env)
    start_date = datetime.now().strftime("%Y-%m-%d")
    payload = build_payload(env, start_date, args.live, args.skip_steps)

    session = requests.Session()
    wait_for_backend(session, base_url)

    csrf_token = login(session, base_url, env.get("APP_ACCESS_PIN"))

    skip_msg = f", skipping: {' '.join(args.skip_steps)}" if args.skip_steps else ""
    mode = "LIVE" if args.live else "safe/preview"
    print(f"Starting Fast API Pipeline ({mode}{skip_msg})...")
    start_pipeline(session, base_url, csrf_token, payload)

    print("Streaming pipeline logs...")
    stream_logs(session, base_url)


def try_run_once(args):
    try:
        run_once(args)
        return True
    except PipelineRunError as exc:
        print(f"trigger_fast_pipeline.py: {exc}", file=sys.stderr)
        return False


def _write_lock(pid, describe):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    SCHEDULE_LOCK.write_text(f"{pid}\nstarted {now_str}, args: {describe}\n")


def _remove_lock(expected_pid):
    try:
        if SCHEDULE_LOCK.exists():
            first_line = SCHEDULE_LOCK.read_text().splitlines()[0]
            if first_line == str(expected_pid):
                SCHEDULE_LOCK.unlink()
    except OSError:
        pass


def schedule_loop(args):
    # A lockfile guards against a second overlapping --schedule loop. Unlike
    # the bash version's `kill -0 <pid>` liveness probe, this isn't reliable
    # cross-platform (os.kill(pid, 0) doesn't mean the same thing on
    # Windows), so staleness is judged by how recently the lock was refreshed
    # instead of whether some PID is still alive: a lock untouched for more
    # than 3x the configured interval is assumed to be left over from a loop
    # that died without cleanup (kill -9, crash, power loss) rather than one
    # still genuinely running.
    if SCHEDULE_LOCK.exists():
        age = time.time() - SCHEDULE_LOCK.stat().st_mtime
        stale_after = args.schedule_minutes * 60 * 3
        if age < stale_after:
            existing = SCHEDULE_LOCK.read_text().splitlines()
            existing_pid = existing[0] if existing else "?"
            sys.exit(
                f"trigger_fast_pipeline.py: a --schedule loop already appears to be running "
                f"(lock last refreshed {int(age)}s ago by PID {existing_pid}).\n"
                f"  Remove {SCHEDULE_LOCK} if you're sure it isn't."
            )
        print(f"trigger_fast_pipeline.py: clearing a stale schedule lock ({int(age)}s old)", file=sys.stderr)

    pid = os.getpid()
    describe = args.describe()
    _write_lock(pid, describe)
    atexit.register(_remove_lock, pid)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    print(f"Schedule mode: running now, then every {args.schedule_minutes} minute(s) until stopped (Ctrl-C).")
    while True:
        _write_lock(pid, describe)  # refresh the heartbeat before each run
        if not try_run_once(args):
            print("trigger_fast_pipeline.py: this run failed - will retry at the next scheduled time", file=sys.stderr)
        next_run = datetime.now() + timedelta(minutes=args.schedule_minutes)
        print(f"Next scheduled run at {next_run.strftime('%H:%M')} (Ctrl-C to stop)...")
        time.sleep(args.schedule_minutes * 60)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.schedule:
        schedule_loop(args)
        return 0
    return 0 if try_run_once(args) else 1


if __name__ == "__main__":
    sys.exit(main())
