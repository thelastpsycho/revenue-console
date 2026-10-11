"""RMS phase 1: booking cache ingest (PII-free, master folio only), pace
on-the-books/cancellation logic, sync planning, and forecast unpivoting."""
import sqlite3
import time
from datetime import date, datetime

import pytest

from app import create_app
from app.revenue import booking_events as be
from app.revenue import rms_forecast

TODAY = date(2026, 10, 11)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(be, "get_data_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(be, "_today", lambda: TODAY)
    return tmp_path


def api_row(rid, booked, arrival, departure, status="D", folio=None, master=True, rate=1_000_000.0,
            currency="IDR", type_id="DLT", market_id=8, updated=None):
    return {
        "ReservationId": rid, "FolioId": folio or rid * 10, "IsMasterFolio": master,
        "ReservationDate": f"{booked}T00:00:00", "ArrivalDate": f"{arrival}T00:00:00",
        "DepartureDate": f"{departure}T00:00:00",
        "Nights": (date.fromisoformat(departure) - date.fromisoformat(arrival)).days,
        "ReservationStatus": status, "TypeId": type_id, "RateType": "BAR", "MarketId": market_id,
        "MarketDescription": "Online", "RoomRate": rate, "Currency": currency, "TimeZone": 8,
        "UpdatedDate": updated or f"{booked}T03:00:00.1234567+00:00",
        # PII the API returns that must never reach disk:
        "GuestName": "Jane Guest", "EmailAddress": "jane@example.com", "MobilePhone": "+6281",
        "IdentityNo": "X123", "Note": "allergic", "Remark": "vip", "ImageLocation": "/img.jpg",
    }


def test_ingest_keeps_master_folio_and_drops_pii(data_dir):
    rows = [api_row(1, "2026-10-01", "2026-10-20", "2026-10-23", folio=11, master=False),
            api_row(1, "2026-10-01", "2026-10-20", "2026-10-23", folio=10, master=True),
            api_row(2, "2026-10-02", "2026-10-21", "2026-10-22")]
    assert be.upsert(rows) == 2
    dump = "\n".join(sqlite3.connect(data_dir / be.DB_FILE).iterdump())
    for pii in ("Jane", "jane@example.com", "+6281", "X123", "allergic", "vip", "img.jpg"):
        assert pii not in dump
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    assert conn.execute("SELECT COUNT(*) FROM booking_nights WHERE reservation_id = 1").fetchone()[0] == 3
    # Re-ingesting replaces rather than duplicates (an amendment shortens the stay).
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-21")])
    assert conn.execute("SELECT COUNT(*) FROM booking_nights WHERE reservation_id = 1").fetchone()[0] == 1


def test_on_the_books_respects_booking_and_cancel_dates():
    be.upsert([
        api_row(1, "2026-10-01", "2026-10-20", "2026-10-22"),
        # Cancelled on 5 Oct local time (UTC 4 Oct 20:00 + 8h).
        api_row(2, "2026-10-02", "2026-10-20", "2026-10-21", status="L", updated="2026-10-04T20:00:00.5+00:00"),
        api_row(3, "2026-10-08", "2026-10-20", "2026-10-21", currency="USD", rate=120.0),
    ])
    otb = lambda as_of: be.on_the_books("2026-10-20", "2026-10-21", as_of)
    assert otb("2026-09-30") == {}
    assert otb("2026-10-04")["2026-10-20"]["rooms"] == 2
    assert otb("2026-10-05")["2026-10-20"]["rooms"] == 1          # cancellation counts from its day
    now = otb("2026-10-11")["2026-10-20"]
    assert (now["rooms"], now["revenue"], now["revenueUsd"]) == (2, 1_000_000, 120)
    assert otb("2026-10-11")["2026-10-21"]["rooms"] == 1


def test_first_cancel_date_is_kept_when_a_cancelled_booking_is_edited_later():
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", status="L",
                       updated="2026-10-03T01:00:00+00:00")])
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", status="L",
                       updated="2026-10-09T01:00:00+00:00")])
    assert be.on_the_books("2026-10-20", "2026-10-20", "2026-10-02")["2026-10-20"]["rooms"] == 1
    assert be.on_the_books("2026-10-20", "2026-10-20", "2026-10-03") == {}


def test_pace_table_pickup_and_same_time_last_year():
    be.upsert([
        api_row(1, "2026-09-01", "2026-10-20", "2026-10-21"),
        api_row(2, "2026-10-06", "2026-10-20", "2026-10-21"),           # within last 7 days: pickup
        api_row(3, "2025-09-01", "2025-10-21", "2025-10-22"),           # LY same weekday, booked early
        api_row(4, "2025-10-15", "2025-10-21", "2025-10-22"),           # LY, booked after STLY point
    ])
    row = be.pace_table("2026-10-20", "2026-10-20")[0]
    assert row["lyDate"] == "2025-10-21"
    assert (row["rooms"], row["pickupRooms"], row["stlyRooms"], row["lyFinalRooms"]) == (2, 1, 1, 2)
    future = be.pace_table("2027-12-01", "2027-12-01")[0]
    assert future["lyFinalRooms"] is None  # LY date hasn't happened yet


def test_pace_curve_counts_on_the_books_by_lead_time():
    be.upsert([api_row(1, "2026-10-10", "2026-10-20", "2026-10-21"),
               api_row(2, "2026-10-18", "2026-10-20", "2026-10-21")])
    curve = be.pace_curve("2026-10-20", max_lead=12)
    by_lead = {p["lead"]: p["rooms"] for p in curve["current"]}
    assert (by_lead[12], by_lead[10], by_lead[2], by_lead[0]) == (0, 1, 2, 2)


def test_sync_plans_cover_their_windows_in_30_day_chunks():
    backfill = be.plan("backfill", 95, TODAY)
    assert {m for m, *_ in backfill} == {"RESERVATION_DATE"}
    assert backfill[0][2] == TODAY and backfill[-1][1] == date(2026, 7, 8)
    assert all((end - start).days < 30 for _, start, end in backfill)
    assert sum((end - start).days + 1 for _, start, end in backfill) == 96
    weekly = be.plan("weekly", today=TODAY)
    assert {m for m, *_ in weekly} == {"RESERVATION_DATE", "ARRIVAL_DATE"}
    assert max(end for m, _, end in weekly if m == "ARRIVAL_DATE") == date(2027, 10, 11)


def test_scheduled_sync_waits_for_backfill_then_runs_weekly_and_daily():
    at = datetime(2026, 10, 11, 5, 0)
    assert be.due_scheduled_kind(at) is None  # no backfill yet
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-10-11")
    assert be.due_scheduled_kind(datetime(2026, 10, 11, 3, 0)) is None  # before 04:00
    assert be.due_scheduled_kind(at) == "weekly"
    with be._db() as conn:
        be._set_meta(conn, "lastWeekly", "2026-10-09")
    assert be.due_scheduled_kind(at) == "daily"
    with be._db() as conn:
        be._set_meta(conn, "lastDaily", "2026-10-11")
    assert be.due_scheduled_kind(at) is None


class FakeClient:
    hotel_id, user_id = 103, "TEST"

    def __init__(self, *a, **k):
        self.calls = []

    def login(self):
        return self

    def _api_post(self, name, payload):
        self.calls.append((name, payload))
        if name == "ReportReservationStatus":
            return [api_row(7, payload["TrxDate"], "2026-12-01", "2026-12-03")]
        return []


def test_sync_job_records_run_and_meta():
    assert be.start_sync("backfill", 60, client_factory=FakeClient)
    for _ in range(100):
        if not be.status()["job"]["running"]:
            break
        time.sleep(0.02)
    st = be.status()
    assert st["job"]["error"] is None and st["job"]["done"] == st["job"]["total"] == 3
    assert st["bookings"] == 1 and st["coverageFrom"] == "2026-08-12" and st["lastBackfill"] == "2026-10-11"


def test_expected_room_pivot_unpivots_across_new_year():
    row = {"TypeId": "DLT", "NoOfRooms": 138, "StartDate": "2026-12-29T00:00:00",
           "12-29": 1.0, "12-30": 2.0, "12-31": 3.0, "01-01": 4.0, "01-02": 5.0, "01-03": 6.0, "01-04": 7.0}
    out = rms_forecast._room_types([row])
    assert [r["date"] for r in out][2:4] == ["2026-12-31", "2027-01-01"]
    assert out[3] == {"date": "2027-01-01", "typeId": "DLT", "rooms": 4.0, "roomCount": 138}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_PIN", "123456")
    monkeypatch.setenv("APP_SESSION_SECRET", "b" * 48)
    monkeypatch.delenv("ALLOW_INSECURE_LOCAL_DEV", raising=False)
    application = create_app()
    application.testing = True
    c = application.test_client()
    csrf = c.post("/api/auth/login", json={"pin": "123456"}).get_json()["csrf_token"]
    c.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
    return c


def test_pace_routes(client):
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-22", type_id="PRKG")])
    assert client.get("/api/rms/pace?start=2026-10-20&end=2026-10-01").status_code == 400
    res = client.get("/api/rms/pace?start=2026-10-20&end=2026-10-21&roomType=PRKG").get_json()
    assert [r["rooms"] for r in res["rows"]] == [1, 1]
    assert client.get("/api/rms/pace?start=2026-10-20&end=2026-10-21&roomType=DLT").get_json()["rows"][0]["rooms"] == 0
    assert client.get("/api/rms/room-types").get_json()["roomTypes"] == ["PRKG"]
    assert client.post("/api/rms/sync", json={"kind": "nope"}).status_code == 400
