"""Revenue Console MCP server - read-only access to the console's data for Claude.

This is a thin client of the Flask backend: every tool is one or two GET
requests against the existing /api endpoints, made with a dedicated
read-only service account. Nothing here opens the SQLite files directly, so
the backend's in-process locks, report caches and forecast leases keep
working exactly as they do for the web UI, and no tool can change PMS,
D-EDGE, allotments, BAR or emails.

Transports
  stdio            python server.py                (Claude Desktop / Claude Code on one machine)
  streamable HTTP  python server.py --http         (remote connector, e.g. behind the Cloudflare tunnel)

Each personal API key (minted from the console's MCP Access page - any logged-in
account, no permissions needed since every tool here only reads) carries exactly its
owner's existing permissions. Remote callers send their own key per request as
"Authorization: Bearer <key>" - this server has no identity of its own and never caches
one, so creating/rotating/revoking a key on that page takes effect on a caller's very
next call, with no server restart. Local stdio runs have no per-request header to carry
a key, so they fall back to REVENUE_CONSOLE_API_KEY from the environment instead.

A caller can also get that same kind of key through a real "Sign in" instead of
pasting one: when REVENUE_CONSOLE_PUBLIC_URL is set, this server advertises OAuth
discovery (RFC 9728) pointing at the Flask backend's own Authorization Server
(backend/app/routes/oauth_routes.py) and 401-challenges requests with no
Authorization header at all. The backend mints the resulting access_token as, under
the hood, exactly the kind of personal key described above - this server still never
validates a token itself, that's still the backend's job on every call.

Environment
  REVENUE_CONSOLE_URL        backend base URL (default http://backend:5666; through the
                             tunnel use the console's public URL - nginx proxies /api)
  REVENUE_CONSOLE_API_KEY    stdio-only fallback key, used when there's no per-request
                             Authorization header to forward (i.e. never for --http)
  REVENUE_CONSOLE_PUBLIC_URL optional, --http only: the backend's public URL, advertised
                             as the OAuth Authorization Server for "Sign in" connector
                             setup. Leave unset to keep the manual-header-only flow.
  MCP_ACCESS_TOKEN      required for --http; gates the URL /<token>/mcp - the
                        Authorization header is reserved for a caller's personal key,
                        so (unlike before) this token is no longer also accepted there
  MCP_ALLOWED_HOSTS     comma-separated public hostnames for --http (Host-header check);
                        the first entry also becomes this server's own OAuth "resource" URL
  MCP_PORT              --http port (default 8765)
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from datetime import date
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon, ToolAnnotations

INSTRUCTIONS = """\
Read-only data from Revenue Console, the revenue/inventory system for The Anvaya
Beach Resort Bali (79 rooms, Kuta). Dates are YYYY-MM-DD in hotel time (Asia/Makassar).

Where the numbers come from
- Bookings / pace / pickup / reports come from booking_events.db, an append-only
  cache of PMS master folios. Revenue is GROSS room-rate revenue in IDR, with USD
  bookings converted at the configured mid rate; "netRevenue" applies the
  configured tax/service/breakfast rules. Rooms are room-nights.
- Every figure carries a quality flag: "observed" (real snapshot), "estimated"
  (reconstructed before the cache existed) or "unavailable" (null). Say so when a
  comparison is estimated, and never invent a value for a null.
- "stly" = same time last year (on-the-books at the equivalent lead time);
  "lyFinal" = how last year's comparison date actually finished.
- Budget figures are segment budgets; they disappear when filtering by room
  type, channel or company because the budget has no such dimension.
- Inventory, yield allocation and stop-sale come from the last pipeline run;
  call get_data_health first if freshness matters.

Start with get_revenue_briefing for "how are we doing", get_pace for a date
range, get_pickup_by_group for "who booked", and list_filters to turn names
(market, company, room type, channel) into the ids other tools take.
"""

DEFAULT_URL = "http://backend:5666"
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
MAX_RANGE_DAYS = 366
# A client (e.g. claude.ai) fetches this itself, so it must be the console's
# public URL, never the internal docker-network REVENUE_CONSOLE_URL.
ICON_URL = "https://revcon.krisnatha.com/favicon.svg"

Comparison = Literal["weekday", "calendar", "custom"]


class ConsoleError(ToolError):
    """A backend error worth showing to the model as-is."""


class ConsoleClient:
    """Forwards whatever Authorization a caller sends on every request - no
    identity of its own, no session cookie, login step, or CSRF handling
    needed. `default_api_key` only covers stdio, where there's no per-request
    header to forward."""

    def __init__(self, base_url: str, default_api_key: str = "",
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.default_api_key = default_api_key
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(120, connect=10),
                transport=self._transport, follow_redirects=False)
        return self._client

    async def get(self, path: str, params: dict[str, Any] | None = None,
                  auth: str | None = None) -> dict[str, Any]:
        """auth is the caller's own `Authorization` header value, forwarded
        as-is (never inspected or trusted here - the backend is the one
        authority that verifies it). Falls back to a stdio-only default key
        when there's no such header (auth is None on that transport)."""
        auth = auth or (f"Bearer {self.default_api_key}" if self.default_api_key else None)
        if not auth:
            raise ConsoleError(
                "No Revenue Console credential available - remote callers must send "
                "Authorization: Bearer <personal key> (from the MCP Access page); a "
                "local stdio run must set REVENUE_CONSOLE_API_KEY")
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            resp = await self._http().get(path, params=params, headers={"Authorization": auth})
        except httpx.HTTPError as exc:
            raise ConsoleError(f"Revenue Console is unreachable at {self.base_url}: {exc}") from exc
        if resp.status_code == 401:
            raise ConsoleError("Revenue Console rejected the API key (missing, wrong, or revoked)")
        if resp.status_code != 200:
            raise ConsoleError(f"{path} returned {resp.status_code}: {_message(resp)}")
        body = resp.json()
        body.pop("status", None)
        return body

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def _forwarded_auth(ctx: Context) -> str | None:
    """The caller's own Authorization header, when the transport has one
    (streamable HTTP). None on stdio, where ctx.headers is always None."""
    headers = ctx.headers
    if not headers:
        return None
    for key, value in headers.items():
        if key.lower() == "authorization":
            return value
    return None


def _message(resp: httpx.Response) -> str:
    try:
        return resp.json().get("message") or resp.text[:200]
    except ValueError:
        return resp.text[:200]


def _csv(values: list[Any] | None) -> str | None:
    return ",".join(str(v) for v in values) if values else None


def _check_range(start: str | None, end: str | None) -> None:
    try:
        s = date.fromisoformat(start) if start else None
        e = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise ConsoleError("Dates must be YYYY-MM-DD") from exc
    if s and e and (e < s or (e - s).days >= MAX_RANGE_DAYS):
        raise ConsoleError(f"end must be on or after start and the range at most {MAX_RANGE_DAYS} days")


def _filters(room_type, market_id, channels, company_ids, comparison=None, comparison_start=None,
            nationality_ids=None, group=None):
    return {"roomType": room_type, "marketId": market_id, "channels": _csv(channels),
            "companyIds": _csv(company_ids), "comparison": comparison, "comparisonStart": comparison_start,
            "nationalityIds": _csv(nationality_ids), "group": group}


def _by_date(rows: list[dict[str, Any]], start: str | None, end: str | None, key: str = "Date") -> list[dict[str, Any]]:
    _check_range(start, end)
    out = []
    for row in rows:
        day = str(row.get(key) or "")[:10]
        if start and day < start:
            continue
        if end and day > end:
            continue
        out.append({**row, key: day})
    return out


def build_server(client: ConsoleClient) -> MCPServer:
    mcp = MCPServer(name="revenue-console", title="Revenue Console (The Anvaya)",
                    instructions=INSTRUCTIONS, version="1.0.0",
                    icons=[Icon(src=ICON_URL, mime_type="image/svg+xml")])

    # ---- RMS: briefing, pace, pickup -------------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def get_revenue_briefing(ctx: Context) -> dict[str, Any]:
        """Whole-hotel briefing for the next 7 and 30 days: rooms on the books, occupancy,
        gross revenue, ADR, 7-day pickup, budget gap vs same time last year, plus the dates
        that need attention (high occupancy, behind last year with weak pickup, negative
        pickup) and any data-freshness warnings. Best first call for "how are we doing"."""
        return await client.get("/api/rms/briefing", auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_pace(ctx: Context, start: str | None = None, end: str | None = None, pickup_days: int = 7,
                       as_of: str | None = None, comparison: Comparison = "weekday",
                       comparison_start: str | None = None, room_type: str | None = None,
                       market_id: int | None = None, channels: list[str] | None = None,
                       company_ids: list[int] | None = None, nationality_ids: list[int] | None = None,
                       group: Literal["fit", "group"] | None = None) -> dict[str, Any]:
        """Day-by-day pace for stay dates start..end (default: today + 29 days, max 366).

        Per date: rooms, revenue, netRevenue, idrRooms (rooms with a usable IDR rate),
        pickupRooms/pickupRevenue over the last `pickup_days` (new/cancelled breakdown),
        stlyRooms/stlyRevenue (same time last year), lyFinalRooms/lyFinalRevenue,
        budgetRooms/budgetRevenue, and quality flags. Also returns booking-sync status,
        the operator's day notes and BAR context for the range.

        comparison: "weekday" = same weekday 364 days earlier, "calendar" = same date,
        "custom" = range starting at comparison_start. as_of pins the pickup window's
        later end to a past date (e.g. pickup during last week). Filters: room_type
        (type code), market_id, channels (channel bucket ids), company_ids, nationality_ids
        - get ids from list_filters. group: "fit" or "group" (group block bookings) -
        nationality is blank/"unassigned" until check-in on bookings still on the books."""
        _check_range(start, end)
        return await client.get("/api/rms/pace", {
            "start": start, "end": end, "pickupDays": pickup_days, "asOf": as_of,
            **_filters(room_type, market_id, channels, company_ids, comparison, comparison_start,
                      nationality_ids, group)}, auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_pickup_by_group(ctx: Context, start: str | None = None, end: str | None = None,
                                  dimension: Literal["market", "company", "nationality", "group"] = "market",
                                  pickup_days: int = 7, as_of: str | None = None, limit: int | None = 20,
                                  room_type: str | None = None, market_id: int | None = None,
                                  channels: list[str] | None = None,
                                  company_ids: list[int] | None = None,
                                  nationality_ids: list[int] | None = None,
                                  group: Literal["fit", "group"] | None = None) -> dict[str, Any]:
        """Who drove pickup: rooms/revenue picked up over the last `pickup_days` for stay
        dates start..end, grouped by market segment, company (travel agent / OTA /
        corporate account), nationality, or FIT vs group-block bookings, largest first.
        Use for "who booked last week for December"."""
        _check_range(start, end)
        return await client.get("/api/rms/pace/pickup-groups", {
            "start": start, "end": end, "dimension": dimension, "pickupDays": pickup_days,
            "asOf": as_of, "limit": limit,
            **_filters(room_type, market_id, channels, company_ids, nationality_ids=nationality_ids, group=group)},
            auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_booking_curve(ctx: Context, stay_date: str, max_lead: int = 120, room_type: str | None = None,
                                market_id: int | None = None, channels: list[str] | None = None,
                                company_ids: list[int] | None = None, nationality_ids: list[int] | None = None,
                                group: Literal["fit", "group"] | None = None) -> dict[str, Any]:
        """Booking curve for one stay date: rooms and revenue on the books at each lead
        time (days before arrival, up to max_lead, 7-365) for this year and the comparison
        date last year. Use to judge whether a date is building ahead of or behind LY."""
        return await client.get("/api/rms/pace/curve", {
            "date": stay_date, "maxLead": max_lead,
            **_filters(room_type, market_id, channels, company_ids, nationality_ids=nationality_ids, group=group)},
            auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_production_report(ctx: Context, start: str | None = None, end: str | None = None,
                                    date_basis: Literal["stay", "booking"] = "stay",
                                    pickup_days: int = 7, comparison: Comparison = "weekday",
                                    comparison_start: str | None = None, room_type: str | None = None,
                                    market_id: int | None = None, channels: list[str] | None = None,
                                    company_ids: list[int] | None = None,
                                    nationality_ids: list[int] | None = None,
                                    group: Literal["fit", "group"] | None = None) -> dict[str, Any]:
        """Production report for start..end: rooms, revenue and ADR by market, company,
        room type, rate plan, nationality and FIT/group, each with pickup, new/cancelled/
        amended rooms, last-year comparison and segment budget; market trend; booking
        behaviour (lead time and length-of-stay distributions, booking/arrival weekdays,
        cancellations and no-shows by market). date_basis "booking" analyses bookings MADE
        in the range instead of stays in the range."""
        _check_range(start, end)
        return await client.get("/api/rms/reports", {
            "start": start, "end": end, "dateBasis": date_basis, "pickupDays": pickup_days,
            **_filters(room_type, market_id, channels, company_ids, comparison, comparison_start,
                      nationality_ids, group)}, auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_room_rate_breakdown(ctx: Context, start: str | None = None, end: str | None = None,
                                      room_type: str | None = None, market_id: int | None = None,
                                      channels: list[str] | None = None,
                                      company_ids: list[int] | None = None,
                                      nationality_ids: list[int] | None = None,
                                      group: Literal["fit", "group"] | None = None) -> dict[str, Any]:
        """Rooms, revenue and average rate on the books for start..end broken down by room
        type and rate plan."""
        _check_range(start, end)
        return await client.get("/api/rms/pace/breakdown", {
            "start": start, "end": end,
            **_filters(room_type, market_id, channels, company_ids, nationality_ids=nationality_ids, group=group)},
            auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_online_mix(ctx: Context, start: str | None = None, end: str | None = None,
                             market_id: int | None = None, room_type: str | None = None,
                             channels: list[str] | None = None, nationality_ids: list[int] | None = None,
                             group: Literal["fit", "group"] | None = None) -> dict[str, Any]:
        """Online segment for start..end: production by source/OTA (Booking.com, Agoda,
        Expedia, Traveloka, direct web, ...) and direct-booking share. market_id defaults to
        the Online segment."""
        _check_range(start, end)
        auth = _forwarded_auth(ctx)
        params = {"start": start, "end": end, "marketId": market_id, "roomType": room_type,
                  "channels": _csv(channels), "nationalityIds": _csv(nationality_ids), "group": group}
        return {"sources": await client.get("/api/rms/online/source", params, auth=auth),
                "directShare": await client.get("/api/rms/online/direct-share", params, auth=auth)}

    # ---- PMS forecast ----------------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def get_pms_forecast(ctx: Context, start: str | None = None, days: int = 14,
                               sections: list[Literal["hotel", "segments", "roomTypes", "availability"]] | None = None
                               ) -> dict[str, Any]:
        """The PMS's own forecast reports for `days` days from start (1-366): hotel totals
        and room capacity, segment forecast, room-type forecast and availability. Served
        from a persistent cache that refreshes in the background - check each section's
        stale/error/updatedAt before relying on it."""
        return await client.get("/api/rms/forecast", {"start": start, "days": days,
                                                      "sections": _csv(sections)}, auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_channel_mix(ctx: Context) -> dict[str, Any]:
        """Channel mix from the PMS reports (cached): production by OTA / source."""
        return await client.get("/api/rms/channel", auth=_forwarded_auth(ctx))

    # ---- Inventory, yield, BAR, stop sale --------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def get_inventory(ctx: Context, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Combined PMS + channel-manager inventory from the last pipeline run, one row per
        date: occupancy and rooms remaining per room type. Filter with start/end (inclusive);
        updated_at is when the pipeline last rebuilt it."""
        body = await client.get("/api/db/combined-inventory", auth=_forwarded_auth(ctx))
        return {"updated_at": body.get("updated_at"), "rows": _by_date(body.get("data", []), start, end)}

    @mcp.tool(annotations=READ_ONLY)
    async def get_yield_allocation(ctx: Context, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Yield-engine output from the last pipeline run, one row per date: season, demand
        level, occupancy, remaining vs online inventory per room type, recommended BAR level
        and allocation status."""
        body = await client.get("/api/db/inventory-allocation", auth=_forwarded_auth(ctx))
        return {"updated_at": body.get("updated_at"), "rows": _by_date(body.get("data", []), start, end)}

    @mcp.tool(annotations=READ_ONLY)
    async def get_bar_rate_table(ctx: Context) -> dict[str, Any]:
        """The BAR rate grid: rate per room type and BAR level, with discount %."""
        body = await client.get("/api/db/bar-rates", auth=_forwarded_auth(ctx))
        return {"updated_at": body.get("updated_at"), "rows": body.get("data", [])}

    @mcp.tool(annotations=READ_ONLY)
    async def get_stop_sale_preview(ctx: Context) -> dict[str, Any]:
        """Dates that currently meet the stop-sale rules (whole hotel above the occupancy
        threshold, or a room type at/below its remaining-rooms threshold), with the
        inventory coverage it was computed from. Preview only - nothing is sent."""
        return await client.get("/api/stop-sale/preview", auth=_forwarded_auth(ctx))

    # ---- Reference and health --------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def list_filters(ctx: Context) -> dict[str, Any]:
        """Ids and names for filters: room type codes and labels, market segments, channel
        buckets and companies seen in the booking cache."""
        return await client.get("/api/rms/room-types", auth=_forwarded_auth(ctx))

    @mcp.tool(annotations=READ_ONLY)
    async def get_data_health(ctx: Context) -> dict[str, Any]:
        """How fresh the data is: last update of each data file, booking-sync status and
        coverage, whether a pipeline is running, and the most recent automated runs."""
        auth = _forwarded_auth(ctx)
        overview = await client.get("/api/administration/overview", auth=auth)
        overview.pop("access", None)
        overview.pop("reportTimings", None)
        return {"files": overview.get("dataHealth"), "mappings": overview.get("mappings"),
                "bookingSync": await client.get("/api/rms/sync", auth=auth),
                "pipeline": await client.get("/api/fast-pipeline/status", auth=auth),
                "recentRuns": (await client.get("/api/fast-pipeline/history", {"limit": 5}, auth=auth)).get("runs")}

    return mcp


WELL_KNOWN_PATH = "/.well-known/oauth-protected-resource"


class BearerAuth:
    """ASGI wrapper: gates the tunnel itself via a /<token>/... URL prefix only.

    The Authorization header is deliberately left alone here and passed through
    untouched - it's reserved for each caller's own personal Revenue Console API
    key (see ConsoleClient/_forwarded_auth), checked by the backend, not this
    layer. Treat the URL (which embeds the token) like a password.

    When authorization_server_url is set (REVENUE_CONSOLE_PUBLIC_URL configured
    on this service), this also serves OAuth discovery (RFC 9728) at a fixed,
    token-free path, and 401s with a WWW-Authenticate challenge when a request
    to the real endpoint has no Authorization header at all - that's what makes
    claude.ai notice this server wants OAuth and start the sign-in flow,
    instead of only failing deep inside a tool call. A present-but-wrong token
    is still never inspected here; that 401 still comes from the backend at
    tool-call time, as always. When unset, behavior is unchanged from before
    OAuth support existed - no challenge, no metadata."""

    def __init__(self, app, token: str, *, resource_url: str = "", authorization_server_url: str = ""):
        self.app, self.token = app, token.encode()
        self.resource_url = resource_url
        self.metadata_body = json.dumps({
            "resource": resource_url,
            "authorization_servers": [authorization_server_url],
        }).encode() if authorization_server_url else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == "/health":
            return await _plain(send, 200, b"ok")
        # Reachable without the /<token>/ prefix by definition (a client has to
        # discover this before it has anything else) - the body only ever
        # carries the public base URL, never the tunnel's secret token segment.
        if self.metadata_body is not None and scope["path"].startswith(WELL_KNOWN_PATH):
            return await _json(send, 200, self.metadata_body)
        parts = scope["path"].split("/", 2)
        if len(parts) == 3 and hmac.compare_digest(parts[1].encode(), self.token):
            if self.metadata_body is not None and not _has_authorization(scope):
                challenge = f'Bearer resource_metadata="{self.resource_url}{WELL_KNOWN_PATH}"'
                return await _plain(send, 401, b"unauthorized",
                                    extra_headers=[(b"www-authenticate", challenge.encode())])
            path = "/" + parts[2]
            scope = {**scope, "path": path, "raw_path": path.encode()}
            return await self.app(scope, receive, send)
        return await _plain(send, 401, b"unauthorized")


def _has_authorization(scope) -> bool:
    return any(key.lower() == b"authorization" for key, _ in scope.get("headers", []))


async def _plain(send, status, body, extra_headers=None):
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain")] + (extra_headers or [])})
    await send({"type": "http.response.body", "body": body})


async def _json(send, status, body):
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


def http_app(server: MCPServer, token: str, allowed_hosts: list[str], authorization_server_url: str = ""):
    if len(token) < 32:
        raise SystemExit("MCP_ACCESS_TOKEN must be at least 32 characters for --http "
                         "(python -c \"import secrets; print(secrets.token_urlsafe(32))\")")
    if not allowed_hosts:
        raise SystemExit("MCP_ALLOWED_HOSTS must be set for --http (comma-separated public "
                         "hostname(s) the tunnel routes to this service) - without it, DNS "
                         "rebinding protection is disabled")
    local = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts + local,
        allowed_origins=[f"https://{h}" for h in allowed_hosts] + ["http://" + h for h in local])
    app = server.streamable_http_app(stateless_http=True, json_response=True,
                                     transport_security=security, host="0.0.0.0")
    resource_url = f"https://{allowed_hosts[0]}"
    return BearerAuth(app, token, resource_url=resource_url, authorization_server_url=authorization_server_url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    args = parser.parse_args()

    client = ConsoleClient(os.environ.get("REVENUE_CONSOLE_URL", DEFAULT_URL),
                           os.environ.get("REVENUE_CONSOLE_API_KEY", ""))
    server = build_server(client)
    if not args.http:
        server.run("stdio")
        return

    import uvicorn
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    app = http_app(server, os.environ.get("MCP_ACCESS_TOKEN", ""), hosts,
                  os.environ.get("REVENUE_CONSOLE_PUBLIC_URL", ""))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "8765")),
                proxy_headers=True, forwarded_allow_ips="*",
                # The access log would write the /<token>/mcp URL form to disk.
                access_log=False)


if __name__ == "__main__":
    main()
