"""Revenue Console MCP server - read-only access to the console's data for Claude.

This is a thin client of the Flask backend: every tool is one or two GET
requests against the existing /api endpoints, made with the operator PIN.
Nothing here opens the SQLite files directly, so the backend's in-process
locks, report caches and forecast leases keep working exactly as they do for
the web UI, and no tool can change PMS, D-EDGE, allotments, BAR or emails.

Transports
  stdio            python server.py                (Claude Desktop / Claude Code on one machine)
  streamable HTTP  python server.py --http         (remote connector, e.g. behind the Cloudflare tunnel)

Environment
  REVENUE_CONSOLE_URL   backend base URL (default http://backend:5666; through the
                        tunnel use the console's public URL - nginx proxies /api)
  REVENUE_CONSOLE_PIN   the backend's APP_ACCESS_PIN
  MCP_ACCESS_TOKEN      required for --http; callers send it as
                        "Authorization: Bearer <token>" or use the URL /<token>/mcp
  MCP_ALLOWED_HOSTS     comma-separated public hostnames for --http (Host-header check)
  MCP_PORT              --http port (default 8765)
"""
from __future__ import annotations

import argparse
import hmac
import os
from datetime import date
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

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

Comparison = Literal["weekday", "calendar", "custom"]


class ConsoleError(ToolError):
    """A backend error worth showing to the model as-is."""


class ConsoleClient:
    """Logs in with the operator PIN and retries once when the session expires."""

    def __init__(self, base_url: str, pin: str, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.pin = pin
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(120, connect=10),
                                             transport=self._transport, follow_redirects=False)
        return self._client

    async def _login(self) -> None:
        if not self.pin:
            raise ConsoleError("REVENUE_CONSOLE_PIN is not set on the MCP server")
        resp = await self._http().post("/api/auth/login", json={"pin": self.pin})
        if resp.status_code != 200:
            raise ConsoleError(f"Login to Revenue Console failed ({resp.status_code}): {_message(resp)}")

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            resp = await self._http().get(path, params=params)
            if resp.status_code == 401:
                await self._login()
                resp = await self._http().get(path, params=params)
        except httpx.HTTPError as exc:
            raise ConsoleError(f"Revenue Console is unreachable at {self.base_url}: {exc}") from exc
        if resp.status_code != 200:
            raise ConsoleError(f"{path} returned {resp.status_code}: {_message(resp)}")
        body = resp.json()
        body.pop("status", None)
        return body

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


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


def _filters(room_type, market_id, channels, company_ids, comparison=None, comparison_start=None):
    return {"roomType": room_type, "marketId": market_id, "channels": _csv(channels),
            "companyIds": _csv(company_ids), "comparison": comparison, "comparisonStart": comparison_start}


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
                    instructions=INSTRUCTIONS, version="1.0.0")

    # ---- RMS: briefing, pace, pickup -------------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def get_revenue_briefing() -> dict[str, Any]:
        """Whole-hotel briefing for the next 7 and 30 days: rooms on the books, occupancy,
        gross revenue, ADR, 7-day pickup, budget gap vs same time last year, plus the dates
        that need attention (high occupancy, behind last year with weak pickup, negative
        pickup) and any data-freshness warnings. Best first call for "how are we doing"."""
        return await client.get("/api/rms/briefing")

    @mcp.tool(annotations=READ_ONLY)
    async def get_pace(start: str | None = None, end: str | None = None, pickup_days: int = 7,
                       as_of: str | None = None, comparison: Comparison = "weekday",
                       comparison_start: str | None = None, room_type: str | None = None,
                       market_id: int | None = None, channels: list[str] | None = None,
                       company_ids: list[int] | None = None) -> dict[str, Any]:
        """Day-by-day pace for stay dates start..end (default: today + 29 days, max 366).

        Per date: rooms, revenue, netRevenue, idrRooms (rooms with a usable IDR rate),
        pickupRooms/pickupRevenue over the last `pickup_days` (new/cancelled breakdown),
        stlyRooms/stlyRevenue (same time last year), lyFinalRooms/lyFinalRevenue,
        budgetRooms/budgetRevenue, and quality flags. Also returns booking-sync status,
        the operator's day notes and BAR context for the range.

        comparison: "weekday" = same weekday 364 days earlier, "calendar" = same date,
        "custom" = range starting at comparison_start. as_of pins the pickup window's
        later end to a past date (e.g. pickup during last week). Filters: room_type
        (type code), market_id, channels (channel bucket ids), company_ids - get ids
        from list_filters."""
        _check_range(start, end)
        return await client.get("/api/rms/pace", {
            "start": start, "end": end, "pickupDays": pickup_days, "asOf": as_of,
            **_filters(room_type, market_id, channels, company_ids, comparison, comparison_start)})

    @mcp.tool(annotations=READ_ONLY)
    async def get_pickup_by_group(start: str | None = None, end: str | None = None,
                                  dimension: Literal["market", "company"] = "market",
                                  pickup_days: int = 7, as_of: str | None = None, limit: int | None = 20,
                                  room_type: str | None = None, market_id: int | None = None,
                                  channels: list[str] | None = None,
                                  company_ids: list[int] | None = None) -> dict[str, Any]:
        """Who drove pickup: rooms/revenue picked up over the last `pickup_days` for stay
        dates start..end, grouped by market segment or by company (travel agent / OTA /
        corporate account), largest first. Use for "who booked last week for December"."""
        _check_range(start, end)
        return await client.get("/api/rms/pace/pickup-groups", {
            "start": start, "end": end, "dimension": dimension, "pickupDays": pickup_days,
            "asOf": as_of, "limit": limit, **_filters(room_type, market_id, channels, company_ids)})

    @mcp.tool(annotations=READ_ONLY)
    async def get_booking_curve(stay_date: str, max_lead: int = 120, room_type: str | None = None,
                                market_id: int | None = None, channels: list[str] | None = None,
                                company_ids: list[int] | None = None) -> dict[str, Any]:
        """Booking curve for one stay date: rooms and revenue on the books at each lead
        time (days before arrival, up to max_lead, 7-365) for this year and the comparison
        date last year. Use to judge whether a date is building ahead of or behind LY."""
        return await client.get("/api/rms/pace/curve", {
            "date": stay_date, "maxLead": max_lead, **_filters(room_type, market_id, channels, company_ids)})

    @mcp.tool(annotations=READ_ONLY)
    async def get_production_report(start: str | None = None, end: str | None = None,
                                    date_basis: Literal["stay", "booking"] = "stay",
                                    pickup_days: int = 7, comparison: Comparison = "weekday",
                                    comparison_start: str | None = None, room_type: str | None = None,
                                    market_id: int | None = None, channels: list[str] | None = None,
                                    company_ids: list[int] | None = None) -> dict[str, Any]:
        """Production report for start..end: rooms, revenue and ADR by market, company,
        room type, rate plan and channel, each with pickup, new/cancelled/amended rooms,
        last-year comparison and segment budget; market trend; booking behaviour (lead
        time and length-of-stay distributions, booking/arrival weekdays, cancellations and
        no-shows by market). date_basis "booking" analyses bookings MADE in the range
        instead of stays in the range."""
        _check_range(start, end)
        return await client.get("/api/rms/reports", {
            "start": start, "end": end, "dateBasis": date_basis, "pickupDays": pickup_days,
            **_filters(room_type, market_id, channels, company_ids, comparison, comparison_start)})

    @mcp.tool(annotations=READ_ONLY)
    async def get_room_rate_breakdown(start: str | None = None, end: str | None = None,
                                      room_type: str | None = None, market_id: int | None = None,
                                      channels: list[str] | None = None,
                                      company_ids: list[int] | None = None) -> dict[str, Any]:
        """Rooms, revenue and average rate on the books for start..end broken down by room
        type and rate plan."""
        _check_range(start, end)
        return await client.get("/api/rms/pace/breakdown", {
            "start": start, "end": end, **_filters(room_type, market_id, channels, company_ids)})

    @mcp.tool(annotations=READ_ONLY)
    async def get_online_mix(start: str | None = None, end: str | None = None,
                             market_id: int | None = None, room_type: str | None = None,
                             channels: list[str] | None = None) -> dict[str, Any]:
        """Online segment for start..end: production by source/OTA (Booking.com, Agoda,
        Expedia, Traveloka, direct web, ...) and direct-booking share. market_id defaults to
        the Online segment."""
        _check_range(start, end)
        params = {"start": start, "end": end, "marketId": market_id, "roomType": room_type,
                  "channels": _csv(channels)}
        return {"sources": await client.get("/api/rms/online/source", params),
                "directShare": await client.get("/api/rms/online/direct-share", params)}

    # ---- PMS forecast ----------------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def get_pms_forecast(start: str | None = None, days: int = 14,
                               sections: list[Literal["hotel", "segments", "roomTypes", "availability"]] | None = None
                               ) -> dict[str, Any]:
        """The PMS's own forecast reports for `days` days from start (1-366): hotel totals
        and room capacity, segment forecast, room-type forecast and availability. Served
        from a persistent cache that refreshes in the background - check each section's
        stale/error/updatedAt before relying on it."""
        return await client.get("/api/rms/forecast", {"start": start, "days": days,
                                                      "sections": _csv(sections)})

    @mcp.tool(annotations=READ_ONLY)
    async def get_channel_mix() -> dict[str, Any]:
        """Channel mix from the PMS reports (cached): production by OTA / source."""
        return await client.get("/api/rms/channel")

    # ---- Inventory, yield, BAR, stop sale --------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def get_inventory(start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Combined PMS + channel-manager inventory from the last pipeline run, one row per
        date: occupancy and rooms remaining per room type. Filter with start/end (inclusive);
        updated_at is when the pipeline last rebuilt it."""
        body = await client.get("/api/db/combined-inventory")
        return {"updated_at": body.get("updated_at"), "rows": _by_date(body.get("data", []), start, end)}

    @mcp.tool(annotations=READ_ONLY)
    async def get_yield_allocation(start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Yield-engine output from the last pipeline run, one row per date: season, demand
        level, occupancy, remaining vs online inventory per room type, recommended BAR level
        and allocation status."""
        body = await client.get("/api/db/inventory-allocation")
        return {"updated_at": body.get("updated_at"), "rows": _by_date(body.get("data", []), start, end)}

    @mcp.tool(annotations=READ_ONLY)
    async def get_bar_rate_table() -> dict[str, Any]:
        """The BAR rate grid: rate per room type and BAR level, with discount %."""
        body = await client.get("/api/db/bar-rates")
        return {"updated_at": body.get("updated_at"), "rows": body.get("data", [])}

    @mcp.tool(annotations=READ_ONLY)
    async def get_stop_sale_preview() -> dict[str, Any]:
        """Dates that currently meet the stop-sale rules (whole hotel above the occupancy
        threshold, or a room type at/below its remaining-rooms threshold), with the
        inventory coverage it was computed from. Preview only - nothing is sent."""
        return await client.get("/api/stop-sale/preview")

    # ---- Reference and health --------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY)
    async def list_filters() -> dict[str, Any]:
        """Ids and names for filters: room type codes and labels, market segments, channel
        buckets and companies seen in the booking cache."""
        return await client.get("/api/rms/room-types")

    @mcp.tool(annotations=READ_ONLY)
    async def get_data_health() -> dict[str, Any]:
        """How fresh the data is: last update of each data file, booking-sync status and
        coverage, whether a pipeline is running, and the most recent automated runs."""
        overview = await client.get("/api/administration/overview")
        overview.pop("access", None)
        overview.pop("reportTimings", None)
        return {"files": overview.get("dataHealth"), "mappings": overview.get("mappings"),
                "bookingSync": await client.get("/api/rms/sync"),
                "pipeline": await client.get("/api/fast-pipeline/status"),
                "recentRuns": (await client.get("/api/fast-pipeline/history", {"limit": 5})).get("runs")}

    return mcp


class BearerAuth:
    """ASGI wrapper: accept `Authorization: Bearer <token>` or a /<token>/... URL prefix.

    The URL form exists for clients that can only be given a URL (a custom connector
    without OAuth). Treat that URL like a password."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == "/health":
            return await _plain(send, 200, b"ok")
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"")
        if auth.lower().startswith(b"bearer ") and hmac.compare_digest(auth[7:].strip(), self.token):
            return await self.app(scope, receive, send)
        parts = scope["path"].split("/", 2)
        if len(parts) == 3 and hmac.compare_digest(parts[1].encode(), self.token):
            path = "/" + parts[2]
            scope = {**scope, "path": path, "raw_path": path.encode()}
            return await self.app(scope, receive, send)
        return await _plain(send, 401, b"unauthorized")


async def _plain(send, status, body):
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": body})


def http_app(server: MCPServer, token: str, allowed_hosts: list[str]):
    if len(token) < 32:
        raise SystemExit("MCP_ACCESS_TOKEN must be at least 32 characters for --http "
                         "(python -c \"import secrets; print(secrets.token_urlsafe(32))\")")
    local = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed_hosts),
        allowed_hosts=allowed_hosts + local,
        allowed_origins=[f"https://{h}" for h in allowed_hosts] + ["http://" + h for h in local])
    app = server.streamable_http_app(stateless_http=True, json_response=True,
                                     transport_security=security, host="0.0.0.0")
    return BearerAuth(app, token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    args = parser.parse_args()

    client = ConsoleClient(os.environ.get("REVENUE_CONSOLE_URL", DEFAULT_URL),
                           os.environ.get("REVENUE_CONSOLE_PIN", ""))
    server = build_server(client)
    if not args.http:
        server.run("stdio")
        return

    import uvicorn
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    app = http_app(server, os.environ.get("MCP_ACCESS_TOKEN", ""), hosts)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "8765")),
                proxy_headers=True, forwarded_allow_ips="*",
                # The access log would write the /<token>/mcp URL form to disk.
                access_log=False)


if __name__ == "__main__":
    main()
