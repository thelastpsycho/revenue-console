"""Segment-level budget import, daily pro-ration, and pace/production wiring."""
import sqlite3
from datetime import date

import openpyxl
import pytest

from app.revenue import rms_budget as rb
from app.revenue import booking_events as be
from app.revenue.rms_reports import build_reports
from test_rms import api_row


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(be, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(be, "_today", lambda: date(2026, 10, 1))
    return tmp_path


def make_workbook(path, rows):
    """rows: [(month_name, segment, share, rn, arr, rev), ...]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = rb.SHEET_NAME
    ws.append(["Month", "Segment", "Share", "RN", "ARR", "REV"])
    for row in rows:
        ws.append(list(row))
    wb.save(path)


def test_import_maps_segments_and_prorates_daily(data_dir):
    path = data_dir / "budget.xlsx"
    make_workbook(path, [
        ("January", "FIT - Direct", 0.1, 310, 2_000_000, 620_000_000),   # 31 days -> 10/day, 20,000,000/day
        ("February", "CORPORATE", 0.2, 280, 1_000_000, 280_000_000),    # 28 days (2026 not leap) -> 10/day
        ("Total", None, 1.0, 590, None, 900_000_000),                   # trailing total row, no segment
    ])
    imported = rb.import_budget(str(path), 2026)
    assert imported == 2

    conn = sqlite3.connect(str(data_dir / rb.DB_FILE))
    conn.row_factory = sqlite3.Row

    monthly = {r["month"]: dict(r) for r in conn.execute("SELECT * FROM market_segment_budgets")}
    assert monthly["2026-01"]["market_id"] == 3  # FIT - Direct -> PMS "FIT"
    assert monthly["2026-02"]["market_id"] == 2  # CORPORATE -> PMS "Corporate"

    jan1 = conn.execute("SELECT rooms, revenue FROM daily_budget WHERE date = '2026-01-01' AND market_id = 3").fetchone()
    assert tuple(jan1) == (10.0, 20_000_000.0)
    feb1 = conn.execute("SELECT rooms, revenue FROM daily_budget WHERE date = '2026-02-01' AND market_id = 2").fetchone()
    assert tuple(feb1) == (10.0, 10_000_000.0)
    # Every day of January got a row, nothing leaked into February for market 3.
    assert conn.execute("SELECT COUNT(*) FROM daily_budget WHERE market_id = 3").fetchone()[0] == 31
    assert conn.execute("SELECT COUNT(*) FROM daily_budget WHERE date = '2026-03-01'").fetchone()[0] == 0


def test_reimport_replaces_rather_than_duplicates(data_dir):
    path = data_dir / "budget.xlsx"
    make_workbook(path, [("January", "UNIQUE", 1.0, 100, 1_000_000, 100_000_000)])
    rb.import_budget(str(path), 2026)
    make_workbook(path, [("January", "UNIQUE", 1.0, 310, 2_000_000, 620_000_000)])
    rb.import_budget(str(path), 2026)

    conn = sqlite3.connect(str(data_dir / rb.DB_FILE))
    assert conn.execute("SELECT COUNT(*) FROM market_segment_budgets").fetchone()[0] == 1
    rooms, revenue = conn.execute(
        "SELECT rooms, revenue FROM daily_budget WHERE date = '2026-01-01'").fetchone()
    assert (rooms, revenue) == (10.0, 20_000_000.0)


def test_unmapped_segment_raises(data_dir):
    path = data_dir / "budget.xlsx"
    make_workbook(path, [("January", "Some New Segment", 1.0, 100, 1_000_000, 100_000_000)])
    with pytest.raises(ValueError, match="Unmapped budget segment"):
        rb.import_budget(str(path), 2026)


def test_invalid_basis_rejected(data_dir):
    path = data_dir / "budget.xlsx"
    make_workbook(path, [("January", "UNIQUE", 1.0, 100, 1_000_000, 100_000_000)])
    with pytest.raises(ValueError, match="basis"):
        rb.import_budget(str(path), 2026, basis="net100")


def seed_december_adhoc_budget(data_dir):
    """310 RN / 620,000,000 REV over December (31 days) -> 10 rooms, 20,000,000/day."""
    path = data_dir / "budget.xlsx"
    make_workbook(path, [("December", "ADHOC", 1.0, 310, 2_000_000, 620_000_000)])
    rb.import_budget(str(path), 2026)


def test_pace_table_attaches_segment_budget_per_day(data_dir):
    seed_december_adhoc_budget(data_dir)
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02", market_id=11)])
    rows = be.pace_table("2026-12-01", "2026-12-01", market_id=11)
    assert rows[0]["budgetRooms"] == 10.0
    assert rows[0]["budgetRevenue"] == 20_000_000.0


def test_pace_table_tolerates_empty_string_market_id(data_dir):
    """_pace_options() leaves marketId as '' rather than None when the
    frontend sends an empty query param (matching _matches()'s own
    `market_id in (None, "")` check) - daily_totals must treat that as
    unfiltered too instead of calling int('')."""
    seed_december_adhoc_budget(data_dir)
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02", market_id=11)])
    rows = be.pace_table("2026-12-01", "2026-12-01", market_id="")
    assert rows[0]["budgetRooms"] == 10.0
    assert rows[0]["budgetRevenue"] == 20_000_000.0


def test_pace_table_omits_budget_when_room_type_filtered(data_dir):
    seed_december_adhoc_budget(data_dir)
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02", market_id=11)])
    rows = be.pace_table("2026-12-01", "2026-12-01", room_type="DLT")
    assert rows[0]["budgetRooms"] is None
    assert rows[0]["budgetRevenue"] is None


def test_build_reports_market_dimension_includes_budget(data_dir):
    seed_december_adhoc_budget(data_dir)
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    be.upsert([api_row(1, "2026-09-01", "2026-12-01", "2026-12-02", market_id=11)])
    report = build_reports("2026-12-01", "2026-12-01")
    by_id = {r["id"]: r for r in report["production"]["market"]}
    assert by_id["11"]["budget"] == {"rooms": 10.0, "revenue": 20_000_000.0}
    # Non-market dimensions have no segment-level figure to show.
    assert all(r["budget"] is None for r in report["production"]["roomType"])
    # A booking-date cohort isn't tied to calendar budget periods.
    booking_report = build_reports("2026-12-01", "2026-12-01", date_basis="booking")
    assert {r["id"]: r for r in booking_report["production"]["market"]}["11"]["budget"] is None
