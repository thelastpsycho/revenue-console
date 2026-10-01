"""BAR date grouping and D-EDGE row-limit regression tests."""
from datetime import datetime

import pytest

from app.integrations.dedge.bar_updater import (
    _build_skip_map, _chunk_ranges, _planned_chunks, _select_price_level, bar_number,
    build_level_groups, MAX_RANGES_PER_APPLY,
)


class _FakeOption:
    def __init__(self, text):
        self.text = text


class _FakeSelect:
    def __init__(self, *labels):
        self.options = [_FakeOption(label) for label in labels]
        self.selected = None

    def select_by_visible_text(self, text):
        self.selected = text


def rows(*items):
    return [{"Date": date, "Deluxe BAR Rate": rate, "Premiere BAR Rate": None}
            for date, rate in items]


def test_year_boundary_does_not_split_a_same_level_run():
    # The BAR number is the real price level identity - D-EDGE's option labels
    # happen to carry a year suffix, but that's cosmetic (see
    # _select_price_level), so a run of consecutive same-BAR days stays one
    # range even across a year boundary, and even if the later year's price
    # levels haven't been created on the extranet yet.
    source = rows(
        ("2026-12-30", "BAR3"), ("2026-12-31", "BAR3"),
        ("2027-01-01", "BAR3"), ("2027-01-02", "BAR3"),
    )
    result = build_level_groups(source, "Deluxe BAR Rate")
    assert result == {
        "BAR3": [(datetime(2026, 12, 30), datetime(2027, 1, 2))],
    }
    plan = _planned_chunks(source, ("deluxe",), None)
    assert {part[1] for part in plan} == {"BAR 3"}


def test_chunking_never_exceeds_dedge_limit():
    values = list(range(25))
    chunks = _chunk_ranges(values)
    assert [len(chunk) for chunk in chunks] == [10, 10, 5]
    assert [item for chunk in chunks for item in chunk] == values
    assert all(len(chunk) <= MAX_RANGES_PER_APPLY for chunk in chunks)


def test_chunking_preserves_small_and_empty_inputs():
    assert _chunk_ranges([]) == []
    assert _chunk_ranges([1, 2]) == [[1, 2]]
    with pytest.raises(ValueError):
        _chunk_ranges([1], size=0)


def test_nonconsecutive_dates_do_not_merge():
    source = rows(("2026-11-01", "BAR3"), ("2026-11-03", "BAR3"),
                  ("2026-11-04", "BAR4"))
    groups = build_level_groups(source, "Deluxe BAR Rate")
    assert len(groups["BAR3"]) == 2
    assert len(groups["BAR4"]) == 1


def test_bar_number_strips_the_prefix():
    assert bar_number("BAR3") == 3
    assert bar_number("bar10") == 10


def test_select_price_level_ignores_year_suffix():
    select = _FakeSelect("BAR 3 2026", "BAR 4 2026", "BAR 10 2026")
    chosen = _select_price_level(None, select, 4)
    assert chosen == "BAR 4 2026"
    assert select.selected == "BAR 4 2026"


def test_select_price_level_does_not_confuse_1_and_10():
    select = _FakeSelect("BAR 1 2026", "BAR 10 2026")
    assert _select_price_level(None, select, 1) == "BAR 1 2026"
    assert _select_price_level(None, select, 10) == "BAR 10 2026"


def test_select_price_level_raises_when_missing():
    select = _FakeSelect("BAR 3 2026", "BAR 4 2026")
    with pytest.raises(RuntimeError, match="No price level 'BAR 7'"):
        _select_price_level(None, select, 7)


def test_build_level_groups_drops_unchanged_dates():
    source = rows(("2026-11-01", "BAR3"), ("2026-11-02", "BAR3"), ("2026-11-03", "BAR4"))
    groups = build_level_groups(source, "Deluxe BAR Rate", unchanged_dates={"2026-11-01"})
    assert groups == {
        "BAR3": [(datetime(2026, 11, 2), datetime(2026, 11, 2))],
        "BAR4": [(datetime(2026, 11, 3), datetime(2026, 11, 3))],
    }


def test_build_skip_map_only_flags_dates_matching_last_applied():
    source = [
        {"Date": "2026-10-01", "Deluxe BAR Rate": "BAR3", "Premiere BAR Rate": "BAR5"},
        {"Date": "2026-10-02", "Deluxe BAR Rate": "BAR3", "Premiere BAR Rate": "BAR5"},
        {"Date": "2026-10-03", "Deluxe BAR Rate": "BAR4", "Premiere BAR Rate": "BAR5"},
    ]
    # No prior record at all -> nothing is considered unchanged (safe default).
    assert _build_skip_map(source, ("deluxe", "premiere"), {}) == {
        "deluxe": set(), "premiere": set(),
    }
    last_applied = {
        "deluxe": {"2026-10-01": "BAR3", "2026-10-02": "BAR3"},
        "premiere": {"2026-10-01": "BAR5", "2026-10-02": "BAR5", "2026-10-03": "BAR5"},
    }
    skip_map = _build_skip_map(source, ("deluxe", "premiere"), last_applied)
    assert skip_map["deluxe"] == {"2026-10-01", "2026-10-02"}
    assert skip_map["premiere"] == {"2026-10-01", "2026-10-02", "2026-10-03"}
