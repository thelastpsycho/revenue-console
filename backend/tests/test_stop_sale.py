"""Stop sale emails: the rule against combined inventory, date grouping,
recipients/settings storage, the message, and the send endpoint."""
import sqlite3
import time
from datetime import date

import pytest

from app import create_app
from app.revenue import yield_engine
from app.stop_sale import mailer, rules, store

TODAY = date(2026, 10, 7)


def row(day, occupancy=50, **rooms):
    base = {room: 10 for room in rules.ROOM_TYPES}
    base.update({k.replace("_", " "): v for k, v in rooms.items()})
    return {"Date": day, "Occupancy": occupancy, **base}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    path = lambda name: str(tmp_path / name)
    monkeypatch.setattr(rules, "get_data_path", path)
    monkeypatch.setattr(store, "get_data_path", path)
    monkeypatch.setattr(rules, "_today", lambda: TODAY)
    return tmp_path


def write_combined(tmp_path, rows):
    conn = sqlite3.connect(tmp_path / "combined_inventory.db")
    cols = ["Date", "Occupancy", *rules.ROOM_TYPES]
    conn.execute(f"CREATE TABLE combined_inventory ({', '.join(f'[{c}]' for c in cols)})")
    conn.executemany(f"INSERT INTO combined_inventory VALUES ({', '.join('?' * len(cols))})",
                     [[r[c] for c in cols] for r in rows])
    conn.commit()
    conn.close()


def test_room_types_match_yield_engine():
    assert set(rules.ROOM_TYPES) == set(yield_engine.ROOM_CAPS)


def test_rule_occupancy_closes_everything_and_room_thresholds_close_one():
    rule = {"occupancyThreshold": 85, "roomThresholds": {"Deluxe Room": 2, "The Anvaya Villa": 0}}
    rows = [
        row("2026-10-06", occupancy=99),             # past: ignored
        row("2026-10-07", occupancy=85),             # whole hotel
        row("2026-10-08", Deluxe_Room=2),            # Deluxe at threshold
        row("2026-10-09", Deluxe_Room=-3, The_Anvaya_Villa=0),  # overbooked counts too
        row("2026-10-10", Deluxe_Room=3, Premiere_Room=0),      # Premiere has no threshold
    ]
    result = rules.evaluate(rows, rule)
    assert [c["date"] for c in result] == ["2026-10-07", "2026-10-08", "2026-10-09"]
    assert result[0]["allRooms"] and len(result[0]["rooms"]) == len(rules.ROOM_TYPES)
    assert [r["room"] for r in result[1]["rooms"]] == ["Deluxe Room"]
    assert [r["room"] for r in result[2]["rooms"]] == ["Deluxe Room", "The Anvaya Villa"]
    assert result[2]["rooms"][0]["remaining"] == -3


def test_unticked_room_types_are_left_out_even_when_the_hotel_is_full():
    rule = {"occupancyThreshold": 85, "roomThresholds": {"Deluxe Room": 2, "The Anvaya Villa": 0},
            "excludedRooms": ["The Anvaya Villa", "The Anvaya Residence"]}
    result = rules.evaluate([
        row("2026-10-07", occupancy=90),
        row("2026-10-08", The_Anvaya_Villa=0),          # only an excluded room closes
        row("2026-10-09", Deluxe_Room=1, The_Anvaya_Villa=0),
    ], rule)
    assert [c["date"] for c in result] == ["2026-10-07", "2026-10-09"]
    full = result[0]
    assert full["hotelFull"] and not full["allRooms"]
    assert [r["room"] for r in full["rooms"]] == [r for r in rules.ROOM_TYPES
                                                 if r not in ("The Anvaya Villa", "The Anvaya Residence")]
    assert [r["room"] for r in result[1]["rooms"]] == ["Deluxe Room"]
    by_room = rules.group_by_room(rules.group_ranges(result))
    assert "All room types" not in [g["room"] for g in by_room]
    assert "The Anvaya Villa" not in [g["room"] for g in by_room]


def test_group_ranges_merges_consecutive_identical_days():
    closures = rules.evaluate([
        row("2026-10-07", Deluxe_Room=0), row("2026-10-08", Deluxe_Room=0),
        row("2026-10-09", occupancy=90), row("2026-10-10", occupancy=95),
        row("2026-10-12", Deluxe_Room=0),  # gap on the 11th
    ], {"occupancyThreshold": 85, "roomThresholds": {"Deluxe Room": 0}})
    ranges = rules.group_ranges(closures)
    assert [(r["start"], r["end"], r["allRooms"]) for r in ranges] == [
        ("2026-10-07", "2026-10-08", False),
        ("2026-10-09", "2026-10-10", True),
        ("2026-10-12", "2026-10-12", False),
    ]
    assert rules.format_range("2026-10-09", "2026-10-10") == "Fri 9 Oct – Sat 10 Oct 2026"
    assert rules.format_range("2026-12-31", "2027-01-02") == "Thu 31 Dec 2026 – Sat 2 Jan 2027"


def test_group_by_room_lists_each_room_once_without_whole_hotel_days():
    ranges = [
        {"start": "2026-10-07", "end": "2026-10-08", "allRooms": False, "rooms": ["Deluxe Room"]},
        {"start": "2026-10-09", "end": "2026-10-10", "allRooms": True, "rooms": list(rules.ROOM_TYPES)},
        {"start": "2026-10-11", "end": "2026-10-11", "allRooms": False, "rooms": ["The Anvaya Villa", "Deluxe Room"]},
        {"start": "2026-10-12", "end": "2026-10-12", "allRooms": False, "rooms": ["Deluxe Room"]},
    ]
    assert rules.group_by_room(ranges) == [
        {"room": "All room types", "ranges": [{"start": "2026-10-09", "end": "2026-10-10"}]},
        {"room": "Deluxe Room", "ranges": [{"start": "2026-10-07", "end": "2026-10-08"},
                                           {"start": "2026-10-11", "end": "2026-10-12"}]},
        {"room": "The Anvaya Villa", "ranges": [{"start": "2026-10-11", "end": "2026-10-11"}]},
    ]


def test_recipients_crud_and_validation():
    r = store.add_recipient({"name": " Ana ", "email": "ana@partner.com", "company": "Partner", "segment": "Wholesale"})
    assert r["name"] == "Ana" and r["active"]
    with pytest.raises(store.ValidationError):
        store.add_recipient({"name": "Dup", "email": "ANA@partner.com"})
    with pytest.raises(store.ValidationError):
        store.add_recipient({"name": "Bad", "email": "not-an-email"})
    updated = store.update_recipient(r["id"], {**r, "active": False})
    assert updated["active"] is False and store.get_recipients() == []
    assert store.update_recipient(999, r) is None
    assert store.delete_recipient(r["id"]) and not store.delete_recipient(r["id"])


def test_settings_defaults_and_validation():
    settings = store.get_settings()
    assert settings["occupancyThreshold"] == 85
    assert settings["email"]["fromName"] == "The Anvaya Beach Resort Bali"
    assert all(v is None for v in settings["roomThresholds"].values())

    saved = store.save_settings({**settings, "roomThresholds": {"Deluxe Room": "2"}})
    assert store.get_settings()["roomThresholds"]["Deluxe Room"] == 2
    assert saved["roomThresholds"]["Premiere Room"] is None
    assert settings["excludedRooms"] == []
    store.save_settings({**settings, "excludedRooms": ["Deluxe Room", "The Anvaya Villa"]})
    assert store.get_settings()["excludedRooms"] == ["Deluxe Room", "The Anvaya Villa"]  # ROOM_TYPES order
    for bad in ({"excludedRooms": ["Penthouse"]}, {"excludedRooms": list(rules.ROOM_TYPES)},
                {"roomThresholds": {"Penthouse": 1}}, {"occupancyThreshold": 85.5},
                {"roomThresholds": {"Deluxe Room": -1}},
                {"email": {**settings["email"], "subject": "a\nBcc: x@y.z"}}):
        with pytest.raises(store.ValidationError):
            store.save_settings({**settings, **bad})


def test_message_is_personalised_and_escaped():
    email = {**store.DEFAULT_SETTINGS["email"], "intro": "Hello {company} <team>"}
    ranges = [{"start": "2026-10-09", "end": "2026-10-10", "allRooms": True, "rooms": []},
              {"start": "2026-10-12", "end": "2026-10-12", "allRooms": False, "rooms": ["Deluxe Room", "Premiere Room"]}]
    msg = mailer.build_message(email, ranges, {"name": "Ana", "email": "ana@partner.com", "company": "Partner"},
                               "rsvn@anvaya.com")
    assert msg["From"] == "The Anvaya Beach Resort Bali <rsvn@anvaya.com>"
    assert msg["To"] == "Ana <ana@partner.com>" and msg["Cc"] is None
    text = msg.get_body(("plain",)).get_content()
    assert "Dear Ana," in text and "Hello Partner <team>" in text
    assert ("All room types:\n  - Fri 9 Oct – Sat 10 Oct 2026\n"
            "Deluxe Room:\n  - Mon 12 Oct 2026\n"
            "Premiere Room:\n  - Mon 12 Oct 2026") in text
    assert "Hello Partner &lt;team&gt;" in msg.get_body(("html",)).get_content()


class FakeServer:
    def __init__(self, log, fail_first=False):
        self.log, self.fail_first = log, fail_first

    def send_message(self, msg):
        if self.fail_first:
            self.fail_first = False
            raise mailer.smtplib.SMTPServerDisconnected("gone")
        self.log.append(("send", msg["To"]))

    def quit(self):
        self.log.append(("quit",))


@pytest.fixture
def fake_smtp(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "rsvn@anvaya.com")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    log, opened = [], []

    def open_smtp(cfg):
        opened.append(1)
        log.append(("open",))
        return FakeServer(log, fail_first=len(opened) == 1 and getattr(open_smtp, "drop_first", False))
    monkeypatch.setattr(mailer, "_open_smtp", open_smtp)
    return log, open_smtp


PEOPLE = [{"id": i, "name": f"P{i}", "email": f"p{i}@x.com", "company": ""} for i in range(5)]
RANGES = [{"start": "2026-10-09", "end": "2026-10-09", "allRooms": True, "rooms": []}]


def test_throttle_delays_batches_and_reconnects_after_long_pauses(fake_smtp):
    log, _ = fake_smtp
    waits = []
    results = mailer.send_individually(
        store.DEFAULT_SETTINGS["email"], RANGES, PEOPLE,
        throttle={"delaySeconds": 2, "batchSize": 2, "batchPauseMinutes": 5},
        wait=lambda s: waits.append(s) or False)
    assert all(r["ok"] for r in results) and len(results) == 5
    assert waits == [2, 300, 2, 300]
    # The connection is closed over each 5-minute pause, not over the 2 s delays.
    assert [e[0] for e in log] == ["open", "send", "send", "quit", "open", "send", "send", "quit",
                                   "open", "send", "quit"]


def test_stop_ends_the_send_before_the_next_email(fake_smtp):
    waits = []
    results = mailer.send_individually(store.DEFAULT_SETTINGS["email"], RANGES, PEOPLE,
                                       throttle={"delaySeconds": 0}, wait=lambda s: waits.append(s) or len(waits) == 2)
    assert [r["email"] for r in results] == ["p0@x.com", "p1@x.com"]


def test_dropped_connection_is_retried_once(fake_smtp):
    log, open_smtp = fake_smtp
    open_smtp.drop_first = True
    results = mailer.send_individually(store.DEFAULT_SETTINGS["email"], RANGES, PEOPLE[:2], wait=lambda s: False)
    assert all(r["ok"] for r in results)
    assert [e[0] for e in log].count("open") == 2


def test_throttle_settings_validation():
    settings = store.get_settings()
    assert settings["throttle"] == {"delaySeconds": 2, "batchSize": 0, "batchPauseMinutes": 0}
    saved = store.save_settings({**settings, "throttle": {"delaySeconds": 5, "batchSize": 50, "batchPauseMinutes": 10}})
    assert store.get_settings()["throttle"] == saved["throttle"] == {"delaySeconds": 5, "batchSize": 50, "batchPauseMinutes": 10}
    for bad in ({"delaySeconds": -1}, {"delaySeconds": 301}, {"batchSize": 50, "batchPauseMinutes": 0}):
        with pytest.raises(store.ValidationError):
            store.save_settings({**settings, "throttle": {**settings["throttle"], **bad}})


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


def wait_for_send(client):
    for _ in range(200):
        job = client.get("/api/stop-sale/send-status").get_json()["job"]
        if not job["running"]:
            return job
        time.sleep(0.01)
    raise AssertionError("send did not finish")


def test_send_uses_only_ticked_dates_that_still_qualify(client, data_dir, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "rsvn@anvaya.com")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    write_combined(data_dir, [row("2026-10-07", Deluxe_Room=0), row("2026-10-08", Deluxe_Room=0),
                              row("2026-10-09", occupancy=90), row("2026-10-10")])
    store.save_settings({**store.get_settings(), "roomThresholds": {"Deluxe Room": 0}})
    store.add_recipient({"name": "Ana", "email": "ana@partner.com", "company": "Partner"})
    store.add_recipient({"name": "Off", "email": "off@partner.com", "active": False})

    preview = client.get("/api/stop-sale/preview").get_json()
    assert [c["date"] for c in preview["closures"]] == ["2026-10-07", "2026-10-08", "2026-10-09"]

    sent = {}

    def fake_send(email_settings, ranges, recipients, on_result=None, throttle=None, wait=None):
        sent.update(ranges=ranges, to=[r["email"] for r in recipients])
        results = [{"id": r["id"], "name": r["name"], "email": r["email"], "company": r["company"],
                    "ok": True, "error": None} for r in recipients]
        for result in results:
            on_result(result)
        return results
    monkeypatch.setattr(mailer, "send_individually", fake_send)

    # 10-08 unticked; 10-10 doesn't qualify and is ignored even if sent.
    res = client.post("/api/stop-sale/send", json={"dates": ["2026-10-07", "2026-10-09", "2026-10-10"]})
    assert res.status_code == 202
    job = wait_for_send(client)
    assert job["sent"] == 1 and job["failed"] == 0 and job["error"] is None and job["logId"]
    assert sent["to"] == ["ana@partner.com"]
    assert [(r["start"], r["allRooms"]) for r in sent["ranges"]] == [("2026-10-07", False), ("2026-10-09", True)]
    assert store.list_history()[0]["sentCount"] == 1

    assert client.post("/api/stop-sale/send", json={"dates": ["2026-10-10"]}).status_code == 409
    assert client.post("/api/stop-sale/send", json={"dates": []}).status_code == 400


def test_send_without_smtp_reports_it(client, data_dir, monkeypatch):
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_FROM_EMAIL", "SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    write_combined(data_dir, [row("2026-10-07", occupancy=95)])
    store.add_recipient({"name": "Ana", "email": "ana@partner.com"})
    res = client.post("/api/stop-sale/send", json={"dates": ["2026-10-07"]})
    assert res.status_code == 503 and "SMTP_HOST" in res.get_json()["message"]
    assert store.list_history() == []
    assert client.get("/api/stop-sale/settings").get_json()["smtp"]["configured"] is False
