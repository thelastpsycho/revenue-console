"""The PMS API's AvailableRoomInventoryType endpoint has been observed to
intermittently return every specialty room type pinned to one value for
almost the whole scraped window, with real values only at the edges -
closing rooms that are actually open once that bad snapshot drives a live
allotment push. _scrape_and_process_pms must detect that shape and retry
rather than trust it."""
import pandas as pd
import pytest

from app.pipeline import fast_runner as fr

_DAYS = 40


def _rows(avp):
    """avp: per-day values for The Anvaya Villa's raw code (AVP); every
    other specialty code gets a plainly-varying pattern (0/1 alternating)
    so only AVP is a candidate for flagging."""
    rows = []
    for i in range(_DAYS):
        rows.append({
            "Date": f"2026-11-{i + 1:02d}", "AVR": i % 2, "AVS": i % 2, "ASP": i % 2,
            "ASW": i % 2, "AVP": avp[i], "BFS": i % 2, "DLK": 10, "DLT": 10,
            "DLKP": i % 2, "DLTP": 0, "PRKG": 10, "PRKP": 0, "PRTG": 0, "PRTP": 0,
            "PRKL": i % 2, "PRTL": 0, "DLS": i % 2, "FAM": i % 2, "PSU": i % 2,
            "Extra Bed": 0, "Total Room": 400, "Available": 100, "Tentative": 0,
            "Definite": 300, "Waiting List": 0, "Allotment": 0, "Out of Order": 0,
            "Occupancy": 75,
        })
    return rows


_GOOD_AVP = [1 if i % 3 else 0 for i in range(_DAYS)]
_FLATLINED_AVP = [1, 0] + [0] * (_DAYS - 4) + [0, 1]  # edges differ from a stuck middle


def test_flatlined_specialty_room_types_flags_a_stuck_middle_with_different_edges():
    df = pd.DataFrame(_rows(_FLATLINED_AVP))
    assert _flagged(df) == ['The Anvaya Villa']


def test_flatlined_specialty_room_types_ignores_normal_variation():
    df = pd.DataFrame(_rows(_GOOD_AVP))
    assert _flagged(df) == []


def test_flatlined_specialty_room_types_ignores_a_short_window():
    df = pd.DataFrame(_rows(_FLATLINED_AVP)).iloc[:10]
    assert _flagged(df) == []


def _flagged(df):
    return fr._flatlined_specialty_room_types(df)


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "get_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fr.time, "sleep", lambda seconds: None)
    emitted = []
    monkeypatch.setattr(fr, "_emit", lambda step, type_, message: emitted.append((step, type_, message)))
    monkeypatch.setattr(fr, "process_pms_inventory", lambda df: df)
    return tmp_path, emitted


def test_retries_until_a_good_snapshot_arrives(pipeline_env, monkeypatch):
    tmp_path, emitted = pipeline_env
    attempts = [_rows(_FLATLINED_AVP), _rows(_FLATLINED_AVP), _rows(_GOOD_AVP)]
    calls = []

    def fake_fetch(start_date, days, username, password):
        calls.append(start_date)
        return attempts[len(calls) - 1], 0.1

    monkeypatch.setattr(fr, "fetch_room_inventory", fake_fetch)
    processed, elapsed = fr._scrape_and_process_pms("2026-11-01", "u", "p")

    assert len(calls) == 3
    assert (tmp_path / "pms_inventory_raw.db").exists()
    assert any(t == "warning" for _, t, _ in emitted)


def test_raises_without_writing_anything_when_every_attempt_is_corrupted(pipeline_env, monkeypatch):
    tmp_path, emitted = pipeline_env
    monkeypatch.setattr(fr, "fetch_room_inventory",
                         lambda start_date, days, username, password: (_rows(_FLATLINED_AVP), 0.1))

    with pytest.raises(fr.PipelineStepError) as exc_info:
        fr._scrape_and_process_pms("2026-11-01", "u", "p", max_attempts=2, retry_delay=0)

    assert exc_info.value.step == "scrape_pms"
    assert "The Anvaya Villa" in str(exc_info.value)
    assert not (tmp_path / "pms_inventory_raw.db").exists()
