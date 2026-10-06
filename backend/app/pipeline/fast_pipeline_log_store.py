"""Persists every log line emitted by pipeline/fast_runner.py to
fast_pipeline_logs.db, so a run's history survives past the SSE stream (which
only exists while a browser tab is connected). Read by routes/fast_pipeline_routes.py's
history endpoints, in turn used by FastPipelineHistoryView.vue.

Each function opens and closes its own connection - matches the pattern
fast_runner.py already uses for the other data databases - rather than
holding one open across the life of a background pipeline thread.
"""

import json
import sqlite3
from datetime import datetime, timezone

from ..infrastructure.paths import get_data_path

DB_NAME = "fast_pipeline_logs.db"
_SECRET_CONFIG_KEYS = ("pmsPassword", "dedgePassword")


def _connect():
    conn = sqlite3.connect(get_data_path(DB_NAME))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                error TEXT,
                config_json TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES pipeline_runs(id),
                created_at TEXT NOT NULL,
                step TEXT,
                type TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_log_entries_run_id ON pipeline_log_entries(run_id)")
        conn.commit()
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def start_run(config):
    sanitized = {k: v for k, v in config.items() if k not in _SECRET_CONFIG_KEYS}
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO pipeline_runs (started_at, status, config_json) VALUES (?, 'running', ?)",
            (_now(), json.dumps(sanitized, default=str)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def log_entry(run_id, step, type_, message):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO pipeline_log_entries (run_id, created_at, step, type, message) VALUES (?, ?, ?, ?, ?)",
            (run_id, _now(), step, type_, message),
        )
        conn.commit()
    finally:
        conn.close()


def finish_run(run_id, status, error):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE pipeline_runs SET finished_at = ?, status = ?, error = ? WHERE id = ?",
            (_now(), status, error, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_runs(limit=50):
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, started_at, finished_at, status, error FROM pipeline_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def latest_run_by_trigger(trigger):
    """Most recent run whose config carries "trigger": <trigger> (set by
    fast_pipeline_schedule.build_run_config for scheduled runs)."""
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, started_at, finished_at, status, error FROM pipeline_runs "
            "WHERE json_extract(config_json, '$.trigger') = ? ORDER BY id DESC LIMIT 1",
            (trigger,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None  # table not created yet - no runs at all
    finally:
        conn.close()


def get_run(run_id):
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, started_at, finished_at, status, error, config_json FROM pipeline_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        run = dict(row)
        run["config"] = json.loads(run.pop("config_json"))
        return run
    finally:
        conn.close()


def get_run_logs(run_id):
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT step, type, message, created_at FROM pipeline_log_entries WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _escape_like(text):
    # Escapes SQLite LIKE wildcards so a literal "%" or "_" in the search box
    # doesn't get treated as a wildcard.
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_log_entries(query, limit=200):
    """Full-text-ish search across every run's log content (not just the
    currently expanded run), used by the history page's search box. Matches
    message text case-insensitively; newest matches first."""
    pattern = f"%{_escape_like(query)}%"
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT pipeline_log_entries.run_id AS run_id,
                   pipeline_log_entries.step AS step,
                   pipeline_log_entries.type AS type,
                   pipeline_log_entries.message AS message,
                   pipeline_log_entries.created_at AS created_at,
                   pipeline_runs.status AS run_status,
                   pipeline_runs.started_at AS run_started_at
            FROM pipeline_log_entries
            JOIN pipeline_runs ON pipeline_runs.id = pipeline_log_entries.run_id
            WHERE pipeline_log_entries.message LIKE ? ESCAPE '\\' COLLATE NOCASE
            ORDER BY pipeline_log_entries.id DESC
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


init_db()
