# Revenue Console MCP server

Lets Claude answer questions from the console's data ("how's December pacing vs last
year?", "who picked up last week?", "which dates hit stop-sale?") without opening the UI.

**Read-only.** Every tool is a GET against the existing backend API, authenticated with a
personal API key (no permissions needed - reads are open to any logged-in account). This
server has no identity of its own: a remote caller sends their own key per request as an
`Authorization` header, which is forwarded as-is - so creating, rotating or revoking a key
on the console's **MCP Access** page takes effect on that caller's very next call, with no
`.env` edit or server restart. It never opens the SQLite files itself (so the backend's
locks and caches stay authoritative) and has no tool that pushes allotments, BAR,
stop-sale emails or pipeline runs.

## Tools

| Tool | Backend endpoint | Use for |
|---|---|---|
| `get_revenue_briefing` | `/api/rms/briefing` | 7/30-day summary + dates needing attention |
| `get_pace` | `/api/rms/pace` | Day-by-day OTB, pickup, STLY, LY final, budget |
| `get_pickup_by_group` | `/api/rms/pace/pickup-groups` | Pickup by market segment or company |
| `get_booking_curve` | `/api/rms/pace/curve` | Booking curve for one stay date vs LY |
| `get_production_report` | `/api/rms/reports` | Production by market/company/room/rate/channel, lead time, LOS, cancellations |
| `get_room_rate_breakdown` | `/api/rms/pace/breakdown` | OTB by room type and rate plan |
| `get_online_mix` | `/api/rms/online/*` | OTA/source production and direct share |
| `get_pms_forecast` | `/api/rms/forecast` | PMS forecast reports (cached) |
| `get_channel_mix` | `/api/rms/channel` | PMS channel mix (cached) |
| `get_inventory` | `/api/db/combined-inventory` | Rooms remaining per type, by date |
| `get_yield_allocation` | `/api/db/inventory-allocation` | Yield engine output: demand, BAR level, online allocation |
| `get_bar_rate_table` | `/api/db/bar-rates` | BAR grid |
| `get_stop_sale_preview` | `/api/stop-sale/preview` | Dates meeting stop-sale rules (preview only) |
| `list_filters` | `/api/rms/room-types` | Ids for room types, markets, channels, companies |
| `get_data_health` | admin overview, sync, pipeline | Data freshness |

## Option A — claude.ai / mobile (remote, via the tunnel)

This is a one-time setup per *client* (one tunnel URL, shared by everyone), separate from
your *personal key* (which you alone create and can rotate any time with no server access).

1. On the server, create `mcp-server/.env` from `.env.example`: a new `MCP_ACCESS_TOKEN`
   and `MCP_ALLOWED_HOSTS` set to the public hostname (e.g. `mcp.krisnatha.com`) - the
   server refuses to start `--http` without these. No personal key goes in this file -
   the server never holds one.
2. Add `COMPOSE_PROFILES=mcp` to the root `.env`, then deploy as usual
   (`git pull` + `schtasks /run /tn revenue-console-deploy`).
3. Add a public hostname to the console's Cloudflare tunnel pointing at `http://mcp:8765`
   (in `cloudflared/config.yml` ingress, above the catch-all rule, or in the Zero Trust dashboard).
   Check `https://<host>/health` returns `ok`.
4. In claude.ai: Settings → Connectors → Add custom connector, URL
   `https://<host>/<MCP_ACCESS_TOKEN>/mcp`, Authentication **No sign-in**, and a
   `Authorization` request header set to `Bearer <your personal key>` (minted from the
   console's **MCP Access** page).

The URL's `<MCP_ACCESS_TOKEN>` segment gates the tunnel itself, so treat it like a
password - to revoke it, change `MCP_ACCESS_TOKEN` and redeploy (this does affect every
client at once, unlike a personal key). The `Authorization` header is yours alone: create
a new key on the MCP Access page any time and just update that one header value in your
client's settings - nothing on the server needs to change.

## Option B — Claude Desktop / Claude Code on your own machine (stdio)

```bash
cd mcp-server && pip install -r requirements.txt
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "revenue-console": {
      "command": "python",
      "args": ["/path/to/revenue-console/mcp-server/server.py"],
      "env": {"REVENUE_CONSOLE_URL": "https://<console public URL>",
              "REVENUE_CONSOLE_API_KEY": "<key from the MCP Access page>"}
    }
  }
}
```

Claude Code: `claude mcp add revenue-console -e REVENUE_CONSOLE_URL=... -e REVENUE_CONSOLE_API_KEY=... -- python /path/to/mcp-server/server.py`,
or against the remote endpoint: `claude mcp add --transport http revenue-console https://<host>/<MCP_ACCESS_TOKEN>/mcp --header "Authorization: Bearer <your personal key>"`.

`REVENUE_CONSOLE_API_KEY` only applies here (stdio has no per-request header to carry a
key) - it's ignored entirely for `--http`, where each caller's own `Authorization` header
is what's used.

## Notes

- Revenue is gross room-rate revenue in IDR (USD at the configured mid rate); every figure
  carries an observed/estimated/unavailable quality flag. These rules are in the server's
  instructions so Claude reports them correctly.
- A personal key never expires on its own - revoke it from the MCP Access page (or the
  Users page, as an admin) to cut off that caller immediately; nothing else is affected.
- Adding a tool: add a GET endpoint to the backend if needed, then one `@mcp.tool` function in
  `server.py`. `tests/test_server.py` checks every path the server calls exists as a GET route.

Tests: `pip install -r requirements-dev.txt -r ../backend/requirements.txt && pytest -q tests`
