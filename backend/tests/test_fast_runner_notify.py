"""n8n webhook notification: opt-in via env var, forwards the full run record
plus log lines (same data the History page reads), never raises on failure."""
from app.pipeline import fast_runner


_RUN = {"id": 7, "started_at": "t0", "finished_at": "t1", "status": "error",
        "error": "BAR update failed", "config": {"startDate": "2026-10-01"}}
_LOGS = [{"step": "bar", "type": "error", "message": "boom", "created_at": "t1"}]


def test_no_webhook_configured_does_not_call_requests(monkeypatch):
    monkeypatch.delenv("N8N_FAST_PIPELINE_WEBHOOK_URL", raising=False)
    calls = []
    monkeypatch.setattr(fast_runner.requests, "post", lambda *a, **k: calls.append((a, k)))
    fast_runner._notify_pipeline_result(1)
    assert calls == []


def test_posts_full_run_record_and_logs_when_configured(monkeypatch):
    monkeypatch.setenv("N8N_FAST_PIPELINE_WEBHOOK_URL", "https://example.com/webhook/fast-pipeline")
    monkeypatch.setattr(fast_runner.fast_pipeline_log_store, "get_run", lambda run_id: dict(_RUN))
    monkeypatch.setattr(fast_runner.fast_pipeline_log_store, "get_run_logs", lambda run_id: list(_LOGS))
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))

    monkeypatch.setattr(fast_runner.requests, "post", fake_post)
    fast_runner._notify_pipeline_result(7)

    assert len(calls) == 1
    url, payload, timeout = calls[0]
    assert url == "https://example.com/webhook/fast-pipeline"
    assert payload == {**_RUN, "logs": _LOGS}
    assert timeout == 10


def test_no_op_when_run_not_found(monkeypatch):
    monkeypatch.setenv("N8N_FAST_PIPELINE_WEBHOOK_URL", "https://example.com/webhook/fast-pipeline")
    monkeypatch.setattr(fast_runner.fast_pipeline_log_store, "get_run", lambda run_id: None)
    calls = []
    monkeypatch.setattr(fast_runner.requests, "post", lambda *a, **k: calls.append((a, k)))
    fast_runner._notify_pipeline_result(999)
    assert calls == []


def test_notification_failure_is_swallowed_not_raised(monkeypatch):
    monkeypatch.setenv("N8N_FAST_PIPELINE_WEBHOOK_URL", "https://example.com/webhook/fast-pipeline")
    monkeypatch.setattr(fast_runner.fast_pipeline_log_store, "get_run", lambda run_id: dict(_RUN))
    monkeypatch.setattr(fast_runner.fast_pipeline_log_store, "get_run_logs", lambda run_id: list(_LOGS))

    def raising_post(*a, **k):
        raise ConnectionError("n8n unreachable")

    monkeypatch.setattr(fast_runner.requests, "post", raising_post)
    # Must not raise - a notification outage should never break the pipeline run.
    fast_runner._notify_pipeline_result(7)
