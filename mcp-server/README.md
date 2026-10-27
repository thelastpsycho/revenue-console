# Revenue Console MCP server

Lets Claude answer questions from the console's data ("how's December pacing vs last
year?", "who picked up last week?", "which dates hit stop-sale?") without opening the UI.

**Read-only.** Every tool is a GET against the existing backend API, logged in with the
operator PIN. It never opens the SQLite files itself (so the backend's locks and caches
stay authoritative) and has no tool that pushes allotments, BAR, stop-sale emails or
pipeline runs.

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

1. On the server, create `mcp-server/.env` from `.env.example`: the backend PIN, a new
   `MCP_ACCESS_TOKEN`, and `MCP_ALLOWED_HOSTS` set to the public hostname (e.g.
   `mcp.krisnatha.com`) - the server refuses to start `--http` without it.
2. Add `COMPOSE_PROFILES=mcp` to the root `.env`, then deploy as usual
   (`git pull` + `schtasks /run /tn revenue-console-deploy`).
3. Add a public hostname to the console's Cloudflare tunnel pointing at `http://mcp:8765`
   (in `cloudflared/config.yml` ingress, above the catch-all rule, or in the Zero Trust dashboard).
   Check `https://<host>/health` returns `ok`.
4. In claude.ai: Settings → Connectors → Add custom connector, URL
   `https://<host>/<MCP_ACCESS_TOKEN>/mcp`, no OAuth.

The URL contains the secret, so treat it like a password. To revoke, change
`MCP_ACCESS_TOKEN` and redeploy. Clients that can send headers (Claude Code) should use
`https://<host>/mcp` with `Authorization: Bearer <token>` instead.

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
      "env": {"REVENUE_CONSOLE_URL": "https://<console public URL>", "REVENUE_CONSOLE_PIN": "<PIN>"}
    }
  }
}
```

Claude Code: `claude mcp add revenue-console -e REVENUE_CONSOLE_URL=... -e REVENUE_CONSOLE_PIN=... -- python /path/to/mcp-server/server.py`,
or against the remote endpoint: `claude mcp add --transport http revenue-console https://<host>/mcp --header "Authorization: Bearer <token>"`.

## Notes

- Revenue is gross room-rate revenue in IDR (USD at the configured mid rate); every figure
  carries an observed/estimated/unavailable quality flag. These rules are in the server's
  instructions so Claude reports them correctly.
- The server logs in once and re-logs when the 8-hour backend session expires.
- Adding a tool: add a GET endpoint to the backend if needed, then one `@mcp.tool` function in
  `server.py`. `tests/test_server.py` checks every path the server calls exists as a GET route.

Tests: `pip install -r requirements-dev.txt -r ../backend/requirements.txt && pytest -q tests`
