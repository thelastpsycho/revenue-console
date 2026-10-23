"""MCP server tests: tools against a fake backend, plus a contract check that every
backend path the server calls exists in the real Flask app as a GET route."""
import json
import os
import re
import sys

import httpx
import pytest
from mcp import Client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import server  # noqa: E402

PIN = "123456"

INVENTORY = [{"Date": "2026-10-30 00:00:00", "Occupancy": 81.0, "Deluxe": 3},
             {"Date": "2026-10-31 00:00:00", "Occupancy": 92.4, "Deluxe": 0},
             {"Date": "2026-11-01 00:00:00", "Occupancy": 60.0, "Deluxe": 9}]


class FakeBackend:
    """Mimics the Flask auth: 401 until POST /api/auth/login with the right PIN."""

    def __init__(self):
        self.requests = []
        self.logged_in = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/auth/login":
            ok = json.loads(request.content).get("pin") == PIN
            self.logged_in = ok
            return httpx.Response(200 if ok else 401, json={"status": "success" if ok else "error",
                                                            "message": None if ok else "Invalid PIN"})
        if request.method != "GET":
            return httpx.Response(405)
        if not self.logged_in:
            return httpx.Response(401, json={"status": "error", "message": "Authentication required"})
        if path == "/api/db/combined-inventory":
            return httpx.Response(200, json={"status": "success", "data": INVENTORY, "updated_at": "2026-10-23T01:00:00+00:00"})
        if path == "/api/rms/pace":
            return httpx.Response(200, json={"status": "success", "rows": [], "echo": dict(request.url.params)})
        if path == "/api/rms/briefing":
            return httpx.Response(200, json={"status": "success", "today": "2026-10-23", "periods": []})
        return httpx.Response(404, json={"status": "error", "message": "Database file not found"})


def make(pin=PIN):
    backend = FakeBackend()
    client = server.ConsoleClient("http://console.test", pin, transport=httpx.MockTransport(backend))
    return backend, server.build_server(client)


def payload(result):
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_logs_in_on_first_401_and_strips_status():
    backend, mcp = make()
    async with Client(mcp) as c:
        data = payload(await c.call_tool("get_revenue_briefing", {}))
        assert data["today"] == "2026-10-23" and "status" not in data
        payload(await c.call_tool("get_revenue_briefing", {}))
    paths = [r.url.path for r in backend.requests]
    assert paths == ["/api/rms/briefing", "/api/auth/login", "/api/rms/briefing", "/api/rms/briefing"]


@pytest.mark.anyio
async def test_pace_maps_arguments_to_backend_params():
    _, mcp = make()
    async with Client(mcp) as c:
        data = payload(await c.call_tool("get_pace", {
            "start": "2026-12-01", "end": "2026-12-31", "pickup_days": 14, "comparison": "calendar",
            "market_id": 8, "channels": ["booking", "agoda"], "company_ids": [3, 7]}))
    assert data["echo"] == {"start": "2026-12-01", "end": "2026-12-31", "pickupDays": "14",
                            "comparison": "calendar", "marketId": "8", "channels": "booking,agoda",
                            "companyIds": "3,7"}


@pytest.mark.anyio
async def test_inventory_filters_by_date_and_normalises_dates():
    _, mcp = make()
    async with Client(mcp) as c:
        data = payload(await c.call_tool("get_inventory", {"start": "2026-10-31", "end": "2026-11-30"}))
    assert [r["Date"] for r in data["rows"]] == ["2026-10-31", "2026-11-01"]


@pytest.mark.anyio
async def test_bad_range_and_backend_errors_are_tool_errors():
    _, mcp = make()
    async with Client(mcp) as c:
        bad = await c.call_tool("get_pace", {"start": "2026-12-31", "end": "2026-12-01"})
        assert bad.is_error and "end must be on or after start" in bad.content[0].text
        missing = await c.call_tool("get_stop_sale_preview", {})
        assert missing.is_error and "Database file not found" in missing.content[0].text


@pytest.mark.anyio
async def test_wrong_pin_is_reported():
    _, mcp = make(pin="000000")
    async with Client(mcp) as c:
        result = await c.call_tool("get_revenue_briefing", {})
    assert result.is_error and "Login to Revenue Console failed (401)" in result.content[0].text


@pytest.mark.anyio
async def test_every_tool_is_read_only():
    _, mcp = make()
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
    assert len(tools) >= 15
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.mark.anyio
@pytest.mark.parametrize("path,auth,expected", [
    ("/mcp", None, 401),
    ("/mcp", "Bearer wrong", 401),
    ("/wrong-token/mcp", None, 401),
    ("/mcp", "Bearer " + "t" * 40, 200),
    ("/" + "t" * 40 + "/mcp", None, 200),
])
async def test_http_auth(path, auth, expected):
    from asgi_lifespan import LifespanManager
    _, mcp = make()
    app = server.http_app(mcp, "t" * 40, ["mcp.example.com"])
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            headers = {**HEADERS, **({"authorization": auth} if auth else {})}
            resp = await http.post(path, json=INIT, headers=headers)
    assert resp.status_code == expected, resp.text


def test_short_token_refused():
    _, mcp = make()
    with pytest.raises(SystemExit):
        server.http_app(mcp, "short", [])


def test_backend_paths_exist_as_get_routes():
    backend_dir = os.path.join(HERE, "..", "..", "backend")
    if not os.path.isdir(backend_dir):
        pytest.skip("backend not present")
    sys.path.insert(0, os.path.abspath(backend_dir))
    try:
        from app import create_app
    except ImportError as exc:
        pytest.skip(f"backend dependencies not installed: {exc}")
    routes = {}
    for rule in create_app().url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(rule.methods)
    with open(os.path.join(HERE, "..", "server.py")) as fh:
        used = set(re.findall(r'client\.get\("(/api/[^"]+)"', fh.read()))
    assert used, "no backend paths found"
    for path in used:
        assert path in routes and "GET" in routes[path], path


@pytest.fixture
def anyio_backend():
    return "asyncio"
