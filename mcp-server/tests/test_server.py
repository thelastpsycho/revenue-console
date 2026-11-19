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

API_KEY = "rck_test-key-123"

INVENTORY = [{"Date": "2026-10-30 00:00:00", "Occupancy": 81.0, "Deluxe": 3},
             {"Date": "2026-10-31 00:00:00", "Occupancy": 92.4, "Deluxe": 0},
             {"Date": "2026-11-01 00:00:00", "Occupancy": 60.0, "Deluxe": 9}]


class FakeBackend:
    """Mimics the Flask bearer-token auth: 401 unless Authorization matches
    one of `valid_keys`."""

    def __init__(self, valid_keys=(API_KEY,)):
        self.requests = []
        self.valid_tokens = {f"Bearer {k}" for k in valid_keys}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method != "GET":
            return httpx.Response(405)
        if request.headers.get("Authorization") not in self.valid_tokens:
            return httpx.Response(401, json={"status": "error", "message": "Invalid or revoked API key"})
        if path == "/api/db/combined-inventory":
            return httpx.Response(200, json={"status": "success", "data": INVENTORY, "updated_at": "2026-10-23T01:00:00+00:00"})
        if path == "/api/rms/pace":
            return httpx.Response(200, json={"status": "success", "rows": [], "echo": dict(request.url.params)})
        if path == "/api/rms/briefing":
            return httpx.Response(200, json={"status": "success", "today": "2026-10-23", "periods": [],
                                             "caller": request.headers.get("Authorization")})
        return httpx.Response(404, json={"status": "error", "message": "Database file not found"})


def make(default_api_key=API_KEY, valid_keys=None):
    backend = FakeBackend(valid_keys if valid_keys is not None else (API_KEY,))
    client = server.ConsoleClient("http://console.test", default_api_key, transport=httpx.MockTransport(backend))
    return backend, server.build_server(client)


def payload(result):
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


# --- stdio fallback (no per-request header: ctx.headers is None) -------------

@pytest.mark.anyio
async def test_stdio_falls_back_to_default_api_key_and_strips_status():
    backend, mcp = make()
    async with Client(mcp) as c:
        data = payload(await c.call_tool("get_revenue_briefing", {}))
        assert data["today"] == "2026-10-23" and "status" not in data
    assert backend.requests[0].headers["Authorization"] == f"Bearer {API_KEY}"


@pytest.mark.anyio
async def test_wrong_default_api_key_is_reported():
    _, mcp = make(default_api_key="wrong-key")
    async with Client(mcp) as c:
        result = await c.call_tool("get_revenue_briefing", {})
    assert result.is_error and "rejected the API key" in result.content[0].text


@pytest.mark.anyio
async def test_no_credential_at_all_gives_a_clear_error():
    _, mcp = make(default_api_key="")
    async with Client(mcp) as c:
        result = await c.call_tool("get_revenue_briefing", {})
    assert result.is_error and "No Revenue Console credential available" in result.content[0].text


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
async def test_every_tool_is_read_only():
    _, mcp = make()
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
    assert len(tools) >= 15
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


@pytest.mark.anyio
async def test_ctx_is_not_exposed_as_a_tool_argument():
    # Context is auto-injected by the SDK (type-detected), not a model-visible arg.
    _, mcp = make()
    async with Client(mcp) as c:
        tool = next(t for t in (await c.list_tools()).tools if t.name == "get_pace")
    assert "ctx" not in tool.input_schema.get("properties", {})


# --- remote --http: no server identity, every caller's own key forwarded ----

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}
HTTP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
TOKEN = "t" * 40
TOKEN_PATH = f"/{TOKEN}/mcp"


def call_tool_request(name="get_revenue_briefing", arguments=None):
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}}}


@pytest.mark.anyio
async def test_remote_callers_each_use_their_own_key_with_no_server_default():
    from asgi_lifespan import LifespanManager
    backend, mcp = make(default_api_key="", valid_keys=["rck_alice", "rck_bob"])
    app = server.http_app(mcp, TOKEN, ["mcp.example.com"])
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            alice = await http.post(TOKEN_PATH, json=call_tool_request(),
                                    headers={**HTTP_HEADERS, "authorization": "Bearer rck_alice"})
            bob = await http.post(TOKEN_PATH, json=call_tool_request(),
                                  headers={**HTTP_HEADERS, "authorization": "Bearer rck_bob"})
    assert alice.status_code == bob.status_code == 200
    assert '"caller":"Bearer rck_alice"' in alice.text
    assert '"caller":"Bearer rck_bob"' in bob.text
    # No restart, no shared server-side key, no ordering dependency between callers.


@pytest.mark.anyio
async def test_remote_caller_revoked_key_fails_independently_of_others():
    from asgi_lifespan import LifespanManager
    _, mcp = make(default_api_key="", valid_keys=["rck_alice"])
    app = server.http_app(mcp, TOKEN, ["mcp.example.com"])
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            revoked = await http.post(TOKEN_PATH, json=call_tool_request(),
                                      headers={**HTTP_HEADERS, "authorization": "Bearer rck_was_revoked"})
    assert revoked.status_code == 200  # transport-level 200; the error is in the JSON-RPC body
    assert "rejected the API key" in revoked.text


@pytest.mark.anyio
@pytest.mark.parametrize("path,auth,expected", [
    ("/mcp", None, 401),                       # no tunnel token in the URL at all
    (f"/{TOKEN}/mcp", None, 200),               # correct tunnel token, no Authorization needed for initialize
    ("/wrong-token/mcp", None, 401),            # wrong tunnel token
    ("/mcp", f"Bearer {TOKEN}", 401),           # Authorization no longer doubles as the tunnel token
])
async def test_http_tunnel_gate_is_url_only(path, auth, expected):
    from asgi_lifespan import LifespanManager
    _, mcp = make()
    app = server.http_app(mcp, TOKEN, ["mcp.example.com"])
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            headers = {**HTTP_HEADERS, **({"authorization": auth} if auth else {})}
            resp = await http.post(path, json=INIT, headers=headers)
    assert resp.status_code == expected, resp.text


# --- OAuth discovery: off unless REVENUE_CONSOLE_PUBLIC_URL is configured ----

AS_URL = "https://revcon.example.com"


@pytest.mark.anyio
async def test_no_oauth_metadata_or_challenge_when_unconfigured():
    from asgi_lifespan import LifespanManager
    _, mcp = make()
    app = server.http_app(mcp, TOKEN, ["mcp.example.com"])  # no authorization_server_url
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            metadata = await http.get("/.well-known/oauth-protected-resource")
            # initialize with no Authorization still works - unchanged from before OAuth support.
            init = await http.post(TOKEN_PATH, json=INIT, headers=HTTP_HEADERS)
    assert metadata.status_code == 401  # not a recognized /<token>/... path, same as any other
    assert init.status_code == 200


@pytest.mark.anyio
async def test_oauth_protected_resource_metadata():
    from asgi_lifespan import LifespanManager
    _, mcp = make()
    app = server.http_app(mcp, TOKEN, ["mcp.example.com"], AS_URL)
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            direct = await http.get("/.well-known/oauth-protected-resource")
            # RFC 9728 path-insertion discovery may prefix the resource's own path.
            inserted = await http.get(f"/.well-known/oauth-protected-resource{TOKEN_PATH}")
    for resp in (direct, inserted):
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource"] == "https://mcp.example.com"
        assert body["authorization_servers"] == [AS_URL]
        # The tunnel's secret path segment must never appear in a pre-auth response.
        assert TOKEN not in resp.text


@pytest.mark.anyio
async def test_oauth_challenge_on_missing_authorization_header():
    from asgi_lifespan import LifespanManager
    _, mcp = make()
    app = server.http_app(mcp, TOKEN, ["mcp.example.com"], AS_URL)
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app),
                                     base_url="https://mcp.example.com") as http:
            missing = await http.post(TOKEN_PATH, json=INIT, headers=HTTP_HEADERS)
            present = await http.post(TOKEN_PATH, json=INIT,
                                      headers={**HTTP_HEADERS, "authorization": "Bearer rck_whatever"})
    assert missing.status_code == 401
    challenge = missing.headers["www-authenticate"]
    assert challenge == 'Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"'
    # A present-but-wrong token still isn't inspected here - initialize doesn't call the backend.
    assert present.status_code == 200


def test_short_token_refused():
    _, mcp = make()
    with pytest.raises(SystemExit):
        server.http_app(mcp, "short", [])


def test_missing_allowed_hosts_refused():
    _, mcp = make()
    with pytest.raises(SystemExit):
        server.http_app(mcp, "t" * 40, [])


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
