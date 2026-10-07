"""D-EDGE device code hand-off: a headless session waiting on /Device gets
the emailed code from the UI, types it in, and survives a rejected code."""
import threading
import time

import pytest

from app.integrations.dedge import bar_updater, device_auth

GOOD_CODE = "AHUXX"
UNKNOWN_URL = "https://extranet.availpro.com/Device/Unknown"
HOME_URL = "https://extranet.availpro.com/Home?language=en&hotelId=22255"


class _El:
    def __init__(self, driver, kind, text=""):
        self.driver, self.kind, self.text, self.value = driver, kind, text, ""

    def is_displayed(self):
        return True

    def clear(self):
        self.value = ""

    def send_keys(self, value):
        self.value += value

    def click(self):
        d = self.driver
        if self.kind == "link":
            d.current_url = "https://extranet.availpro.com/Device"
        elif self.kind == "confirm":
            d.submitted.append(d.field.value)
            if d.field.value == GOOD_CODE:
                d.current_url = HOME_URL


class FakeDriver:
    def __init__(self):
        self.current_url = UNKNOWN_URL
        self.submitted, self.visited = [], []
        self.field = _El(self, "field")

    def execute_script(self, script, *args):
        return "complete"

    def get(self, url):
        self.visited.append(url)
        self.current_url = UNKNOWN_URL if "SendMailAgain" in url else url

    def find_element(self, by, value):
        return _El(self, "body", "An email has been sent to e*******e@theanvayabali.com to authorize this device")

    def find_elements(self, by, value):
        on_form = self.current_url.endswith("/Device")
        if value == "authorisation-link" and self.current_url == UNKNOWN_URL:
            return [_El(self, "link")]
        if value == "formCode" and on_form:
            return [self.field]
        if by == "xpath" and "confirm" in value and on_form:
            return [_El(self, "confirm")]
        return []


@pytest.fixture(autouse=True)
def fast_waits(monkeypatch):
    monkeypatch.setattr(bar_updater, "DEVICE_CODE_CHECK_SECONDS", 0.5)
    monkeypatch.setattr(bar_updater.time, "sleep", lambda s: None)
    monkeypatch.setattr(bar_updater, "log", lambda *a, **k: None)
    device_auth.end_wait(False)
    device_auth._state["last_error"] = None


def _wait_until(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _run_wait(driver, timeout=10):
    result = {}

    def target():
        try:
            bar_updater._wait_for_device_authorization(driver, timeout=timeout)
            result["ok"] = True
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    assert _wait_until(lambda: device_auth.get_status()["pending"])
    return thread, result


def test_code_from_ui_is_typed_into_dedge():
    driver = FakeDriver()
    thread, result = _run_wait(driver)
    assert device_auth.get_status()["email_hint"] == "e*******e@theanvayabali.com"
    assert device_auth.submit_code(GOOD_CODE)[0]
    thread.join(5)
    assert result == {"ok": True}
    assert driver.submitted == [GOOD_CODE]
    status = device_auth.get_status()
    assert status["pending"] is False and status["last_verified_at"]


def test_rejected_code_keeps_waiting_for_another():
    driver = FakeDriver()
    thread, result = _run_wait(driver)
    device_auth.submit_code("WRONG1")
    assert _wait_until(lambda: device_auth.get_status()["last_error"])
    assert device_auth.get_status()["pending"] is True
    device_auth.submit_code(GOOD_CODE)
    thread.join(5)
    assert result == {"ok": True}
    assert driver.submitted == ["WRONG1", GOOD_CODE]


def test_resend_then_code():
    driver = FakeDriver()
    thread, result = _run_wait(driver)
    assert device_auth.request_resend()[0]
    assert _wait_until(lambda: any("SendMailAgain" in u for u in driver.visited))
    device_auth.submit_code(GOOD_CODE)
    thread.join(5)
    assert result == {"ok": True}


def test_times_out_without_a_code():
    driver = FakeDriver()
    with pytest.raises(RuntimeError, match="timed out"):
        bar_updater._wait_for_device_authorization(driver, timeout=1)
    status = device_auth.get_status()
    assert status["pending"] is False
    assert "No valid code" in status["last_error"]


@pytest.mark.parametrize("code", ["", "  ", "ABC-12", "1234567"])
def test_malformed_codes_are_refused(code):
    device_auth.begin_wait(60)
    assert device_auth.submit_code(code)[0] is False


def test_code_refused_when_nothing_is_waiting():
    assert device_auth.submit_code(GOOD_CODE) == (False, "D-EDGE isn't waiting for a code right now")
