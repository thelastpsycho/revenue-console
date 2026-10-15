"""RMS phase 1: booking cache ingest (PII-free, master folio only), pace
on-the-books/cancellation logic, sync planning, and forecast unpivoting."""
import json
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
            currency="IDR", type_id="DLT", market_id=8, updated=None, company_id=None, company=None):
    return {
        "ReservationId": rid, "FolioId": folio or rid * 10, "IsMasterFolio": master,
        "ReservationDate": f"{booked}T00:00:00", "ArrivalDate": f"{arrival}T00:00:00",
        "DepartureDate": f"{departure}T00:00:00",
        "Nights": (date.fromisoformat(departure) - date.fromisoformat(arrival)).days,
        "ReservationStatus": status, "TypeId": type_id, "RateType": "BAR", "MarketId": market_id,
        "MarketDescription": "Online", "CompanyId": company_id, "CompanyName": company,
        "RoomRate": rate, "Currency": currency, "TimeZone": 8,
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


def test_ingest_canonicalizes_bed_configuration_variants_to_the_sellable_room_type(data_dir):
    """PMS TypeId distinguishes bed configuration (e.g. PRTG = Premiere Twin
    Garden) within one sellable online room type - RMS must group/filter by
    the representative code (PRKG), matching pms_processor.py's physical-
    inventory grouping, or it silently drops a large share of bookings when
    filtered by room type."""
    be.upsert([
        api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", type_id="PRTG"),
        api_row(2, "2026-10-01", "2026-10-20", "2026-10-21", type_id="PRKP"),
        api_row(3, "2026-10-01", "2026-10-20", "2026-10-21", type_id="PRKG"),
    ])
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    rows = conn.execute("SELECT type_id FROM bookings ORDER BY reservation_id").fetchall()
    assert [r[0] for r in rows] == ["PRKG", "PRKG", "PRKG"]
    otb = be.on_the_books("2026-10-20", "2026-10-21", "2026-10-11", room_type="PRKG")
    assert otb["2026-10-20"]["rooms"] == 3


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
    usd_idr = 120.0 * 16000  # default usdIdrRate
    assert (now["rooms"], now["idrRooms"], now["revenue"]) == (2, 2, pytest.approx(1_000_000 + usd_idr))
    # netRevenue: both rooms, net of breakfast/tax - the USD room converted at the mid rate first.
    assert now["netRevenue"] == pytest.approx(
        (1_000_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE) +
        (usd_idr - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE))
    # Night 21 is covered by row 1 only (row 3's stay doesn't reach it, row 2 is cancelled).
    assert otb("2026-10-11")["2026-10-21"]["rooms"] == 1
    assert otb("2026-10-11")["2026-10-21"]["netRevenue"] == pytest.approx(
        (1_000_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE))


def test_ingest_computes_net_rate_net_of_breakfast_and_tax_excludes_usd(data_dir):
    be.upsert([
        api_row(1, "2026-10-01", "2026-10-20", "2026-10-21"),
        api_row(2, "2026-10-01", "2026-10-20", "2026-10-21", currency="USD", rate=120.0),
    ])
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    conn.row_factory = sqlite3.Row
    net_rates = {r["reservation_id"]: r["net_rate"] for r in conn.execute("SELECT reservation_id, net_rate FROM bookings")}
    assert net_rates[1] == pytest.approx((1_000_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE))
    assert net_rates[2] is None


def test_adr_basis_converts_usd_nights_and_floors_zero_rate_rooms():
    be.upsert([
        api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", rate=1_560_000.0),
        api_row(2, "2026-10-01", "2026-10-20", "2026-10-21", rate=0.0),               # comp: net 0, not negative
        api_row(3, "2026-10-01", "2026-10-20", "2026-10-21", currency="USD", rate=150.0),
    ])
    day = be.pace_table("2026-10-20", "2026-10-20")[0]
    assert (day["rooms"], day["idrRooms"]) == (3, 3)
    usd_idr = 150.0 * 16000  # default usdIdrRate
    expected_net = (1_560_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE) + (usd_idr - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE)
    assert day["netRevenue"] == pytest.approx(expected_net)               # (1,560,000 - 350,000)/1.21 + 0 + (USD converted - 350,000)/1.21
    assert day["netRevenue"] / day["idrRooms"] == pytest.approx(expected_net / 3)


def test_ingest_captures_company_id_and_name(data_dir):
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", company_id=11647, company="Booking.com")])
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT company_id, company FROM bookings WHERE reservation_id = 1").fetchone()
    assert (row["company_id"], row["company"]) == (11647, "Booking.com")
    version = json.loads(conn.execute(
        "SELECT payload FROM booking_versions WHERE reservation_id = 1 ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert (version["company_id"], version["company"]) == (11647, "Booking.com")


def test_migration_adds_company_columns_to_a_pre_existing_database(data_dir):
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    conn.execute("""CREATE TABLE bookings (
        reservation_id INTEGER PRIMARY KEY, reservation_date TEXT, arrival_date TEXT, departure_date TEXT,
        nights INTEGER, status TEXT, type_id TEXT, rate_type TEXT, market_id INTEGER, market TEXT,
        room_rate REAL, currency TEXT, cancelled_on TEXT, updated_at TEXT, synced_at TEXT)""")
    conn.execute("INSERT INTO bookings (reservation_id, room_rate, currency) VALUES (1, 1000000, 'IDR')")
    conn.commit()
    conn.close()
    with be._db():
        pass
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(bookings)")}
    assert {"company_id", "company"} <= columns


def test_migration_backfills_company_into_pre_existing_version_snapshots(data_dir):
    # A reservation whose earliest observed snapshot predates company
    # tracking: the bookings row (current state) already knows the company,
    # but that old version payload doesn't carry it, so an "as of" lookup
    # into the past (pace YoY) would see no company and get misclassified
    # as unassigned - even though the channel never actually changed.
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    conn.execute("""CREATE TABLE bookings (
        reservation_id INTEGER PRIMARY KEY, reservation_date TEXT, arrival_date TEXT, departure_date TEXT,
        nights INTEGER, status TEXT, type_id TEXT, rate_type TEXT, market_id INTEGER, market TEXT,
        company_id INTEGER, company TEXT,
        room_rate REAL, currency TEXT, cancelled_on TEXT, updated_at TEXT, synced_at TEXT)""")
    conn.execute("""CREATE TABLE booking_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, reservation_id INTEGER NOT NULL,
        observed_on TEXT NOT NULL, observed_at TEXT NOT NULL, payload TEXT NOT NULL)""")
    conn.execute("""INSERT INTO bookings (reservation_id, reservation_date, arrival_date, departure_date,
        nights, status, market_id, company_id, company, room_rate, currency)
        VALUES (1, '2025-09-01', '2025-10-01', '2025-10-02', 1, 'D', 8, 11647, 'Booking.com', 1000000, 'IDR')""")
    old_payload = json.dumps({"reservation_id": 1, "reservation_date": "2025-09-01",
                              "arrival_date": "2025-10-01", "departure_date": "2025-10-02",
                              "status": "D", "market_id": 8, "room_rate": 1000000, "currency": "IDR"})
    conn.execute("INSERT INTO booking_versions (reservation_id, observed_on, observed_at, payload) VALUES (1, '2025-09-01', '2025-09-01T00:00:00', ?)",
                (old_payload,))
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta (key, value) VALUES ('versionsSeeded', '1')")
    conn.commit()
    conn.close()
    with be._db():  # _connect() runs the migration as a side effect
        pass
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    payload = json.loads(conn.execute(
        "SELECT payload FROM booking_versions WHERE reservation_id = 1").fetchone()[0])
    assert (payload["company_id"], payload["company"]) == (11647, "Booking.com")


def test_migration_backfills_net_rate_for_a_pre_existing_database(data_dir):
    # Simulate a bookings table from before the net_rate column existed.
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    conn.execute("""CREATE TABLE bookings (
        reservation_id INTEGER PRIMARY KEY, reservation_date TEXT, arrival_date TEXT, departure_date TEXT,
        nights INTEGER, status TEXT, type_id TEXT, rate_type TEXT, market_id INTEGER, market TEXT,
        room_rate REAL, currency TEXT, cancelled_on TEXT, updated_at TEXT, synced_at TEXT)""")
    conn.execute("INSERT INTO bookings (reservation_id, room_rate, currency) VALUES (1, 1000000, 'IDR')")
    conn.execute("INSERT INTO bookings (reservation_id, room_rate, currency) VALUES (2, 120, 'USD')")
    conn.commit()
    conn.close()
    with be._db():  # _connect() runs the migration as a side effect
        pass
    conn = sqlite3.connect(data_dir / be.DB_FILE)
    conn.row_factory = sqlite3.Row
    net_rates = {r["reservation_id"]: r["net_rate"] for r in conn.execute("SELECT reservation_id, net_rate FROM bookings")}
    assert net_rates[1] == pytest.approx((1_000_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE))
    assert net_rates[2] is None


def test_first_cancel_date_is_kept_when_a_cancelled_booking_is_edited_later():
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", status="L",
                       updated="2026-10-03T01:00:00+00:00")])
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-21", status="L",
                       updated="2026-10-09T01:00:00+00:00")])
    assert be.on_the_books("2026-10-20", "2026-10-20", "2026-10-02")["2026-10-20"]["rooms"] == 1
    assert be.on_the_books("2026-10-20", "2026-10-20", "2026-10-03") == {}


def test_pace_table_pickup_and_same_time_last_year():
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    be.upsert([
        api_row(1, "2026-09-01", "2026-10-20", "2026-10-21"),
        api_row(2, "2026-10-06", "2026-10-20", "2026-10-21"),           # within last 7 days: pickup
        api_row(3, "2025-09-01", "2025-10-21", "2025-10-22"),           # LY same weekday, booked early
        api_row(4, "2025-10-15", "2025-10-21", "2025-10-22"),           # LY, booked after STLY point
    ])
    row = be.pace_table("2026-10-20", "2026-10-20")[0]
    assert row["lyDate"] == "2025-10-21"
    assert (row["rooms"], row["pickupRooms"], row["stlyRooms"], row["lyFinalRooms"]) == (2, 1, 1, 2)
    net_rate = (1_000_000 - be.BREAKFAST_IDR) / (1 + be.TAX_SERVICE_RATE)
    assert row["netRevenue"] == pytest.approx(2 * net_rate)
    assert row["stlyNetRevenue"] == pytest.approx(net_rate)
    future = be.pace_table("2027-12-01", "2027-12-01")[0]
    assert future["lyFinalRooms"] is None  # LY date hasn't happened yet


def test_pace_curve_counts_on_the_books_by_lead_time():
    with be._db() as conn:
        be._set_meta(conn, "backfillFrom", "2023-01-01")
    be.upsert([api_row(1, "2026-10-10", "2026-10-20", "2026-10-21"),
               api_row(2, "2026-10-18", "2026-10-20", "2026-10-21")])
    curve = be.pace_curve("2026-10-20", max_lead=12)
    by_lead = {p["lead"]: p["rooms"] for p in curve["current"]}
    assert (by_lead[12], by_lead[10], by_lead[9]) == (0, 1, 1)
    assert 2 not in by_lead and 0 not in by_lead  # future observations must not be drawn


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
    row = {"TypeId": "DLT", "NoOfRooms": 138, "StartDate": "2026-12-29T00:00:00", "EndDate": "2027-01-04T00:00:00",
           "12-29": 1.0, "12-30": 2.0, "12-31": 3.0, "01-01": 4.0, "01-02": 5.0, "01-03": 6.0, "01-04": 7.0}
    out = rms_forecast._room_types([row])
    assert [r["date"] for r in out][2:4] == ["2026-12-31", "2027-01-01"]
    assert out[3] == {"date": "2027-01-01", "typeId": "DLT", "rooms": 4.0, "roomCount": 138}


def test_expected_room_pivot_merges_bed_configuration_variants():
    """PRKG (Premiere King Garden) and PRTG (Premiere Twin Garden) are the
    same online room type at different bed configurations - the PMS reports
    them as separate rows, but RMS must sum them into one "Premiere" entry
    or it fragments inventory/occupancy the same way bookings used to."""
    rows = [
        {"TypeId": "PRKG", "NoOfRooms": 40, "StartDate": "2026-10-01", "EndDate": "2026-10-01", "10-01": 10.0},
        {"TypeId": "PRTG", "NoOfRooms": 20, "StartDate": "2026-10-01", "EndDate": "2026-10-01", "10-01": 5.0},
    ]
    out = rms_forecast._room_types(rows)
    assert out == [{"date": "2026-10-01", "typeId": "PRKG", "rooms": 15.0, "roomCount": 60}]


def test_canonicalize_counts_merges_variants_and_leaves_other_fields_alone():
    values = {"DLT": 6, "DLK": 0, "PRKG": -18, "PRTG": 33, "PRKP": 2, "TotalRoom": 493, "RoomAvailable": 26}
    assert rms_forecast._canonicalize_counts(values) == {
        "DLT": 6, "PRKG": 17, "TotalRoom": 493, "RoomAvailable": 26,
    }


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


def test_dimensions_lists_companies_seen_in_bookings():
    be.upsert([api_row(1, "2026-10-01", "2026-10-20", "2026-10-22", company_id=5, company="Corporate X"),
               api_row(2, "2026-10-01", "2026-10-20", "2026-10-22", company_id=7, company="Travel Co")])
    companies = be.dimensions()["companies"]
    assert {"id": 5, "name": "Corporate X"} in companies
    assert {"id": 7, "name": "Travel Co"} in companies


def test_matches_filters_by_company_ids():
    row = {"company_id": 5}
    assert be._matches(row, None, None, company_ids=[5])
    assert not be._matches(row, None, None, company_ids=[7])
    assert be._matches(row, None, None, company_ids=None)
