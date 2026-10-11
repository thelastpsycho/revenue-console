"""Checkpoint persistence, dry-run isolation, and safe plan mismatch."""
import pytest

from app.integrations.dedge.bar_checkpoint import BarCheckpoint


PLAN = [["deluxe", "BAR 3 2026", [["2026-11-01T00:00:00", "2026-11-03T00:00:00"]]]]
DIFFERENT = [["premiere", "BAR 4 2026", [["2026-11-01T00:00:00", "2026-11-03T00:00:00"]]]]


def test_resume_skips_only_confirmed_chunks(tmp_path):
    path = tmp_path / "checkpoint.json"
    first = BarCheckpoint(PLAN, path=str(path))
    assert not first.resumed
    assert not first.contains(PLAN[0])
    first.mark(PLAN[0])
    second = BarCheckpoint(PLAN, path=str(path))
    assert second.resumed
    assert second.contains(PLAN[0])
    assert not second.contains(DIFFERENT[0])
    second.finish()
    assert not path.exists()
    assert not BarCheckpoint(PLAN, path=str(path)).resumed


def test_different_plan_needs_explicit_reset(tmp_path):
    path = str(tmp_path / "checkpoint.json")
    BarCheckpoint(PLAN, path=path).mark(PLAN[0])
    with pytest.raises(RuntimeError, match="different date/room/price plan"):
        BarCheckpoint(DIFFERENT, path=path)
    fresh = BarCheckpoint(DIFFERENT, path=path, reset=True)
    assert not fresh.resumed
    assert not fresh.contains(PLAN[0])
    fresh.mark(DIFFERENT[0])
    assert BarCheckpoint(DIFFERENT, path=path).contains(DIFFERENT[0])


def test_dry_run_does_not_mutate_partial_checkpoint(tmp_path):
    path = str(tmp_path / "checkpoint.json")
    first = BarCheckpoint(PLAN, path=path)
    first.mark(PLAN[0])
    rehearsal = BarCheckpoint(DIFFERENT, path=path, dry_run=True, reset=True)
    rehearsal.mark(DIFFERENT[0])
    rehearsal.finish()
    assert BarCheckpoint(PLAN, path=path).contains(PLAN[0])


def test_discard_stale_drops_mismatched_checkpoint_but_keeps_matching(tmp_path):
    path = tmp_path / "checkpoint.json"
    BarCheckpoint(PLAN, path=str(path)).mark(PLAN[0])
    same = BarCheckpoint(PLAN, path=str(path), discard_stale=True)
    assert same.resumed and not same.discarded_stale
    assert same.contains(PLAN[0])
    fresh = BarCheckpoint(DIFFERENT, path=str(path), discard_stale=True)
    assert fresh.discarded_stale and not fresh.resumed
    assert not path.exists()
    assert not fresh.contains(PLAN[0])
