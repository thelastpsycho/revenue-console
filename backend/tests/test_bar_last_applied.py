"""Persisted last-applied BAR level record: round-trip and missing-file defaults."""
from app.integrations.dedge.bar_updater import _load_last_applied, _write_last_applied


def test_round_trips_through_an_atomic_write(tmp_path):
    path = str(tmp_path / "bar_last_applied.json")
    state = {"deluxe": {"2026-10-01": "BAR3"}, "premiere": {"2026-10-01": "BAR5"}}
    _write_last_applied(state, path=path)
    assert _load_last_applied(path=path) == state


def test_missing_file_loads_as_empty():
    assert _load_last_applied(path="/nonexistent/bar_last_applied.json") == {}


def test_corrupt_file_loads_as_empty(tmp_path):
    path = tmp_path / "bar_last_applied.json"
    path.write_text("not json")
    assert _load_last_applied(path=str(path)) == {}


def test_write_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "bar_last_applied.json"
    _write_last_applied({"deluxe": {"2026-10-01": "BAR3"}}, path=str(path))
    assert [p.name for p in tmp_path.iterdir()] == [path.name]
