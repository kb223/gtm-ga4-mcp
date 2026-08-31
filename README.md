# gtm-ga4-mcp

An MCP server for **Google Tag Manager + Google Analytics 4** with **tiered safety controls**.

Existing servers cover slices of this surface: Google's official GA4 server is read-only, and GTM servers expose the API without a safety model. `gtm-ga4-mcp` is built for the full surface — read, write, and admin operations — with safeguards you opt into deliberately.

## The safety model

Every tool belongs to a tier. Higher tiers are **off by default** and enforced twice:

| Tier | Examples | Default | Enable with |
|---|---|---|---|
| **Read** | list, get, reports, metadata | ✅ on | — |
| **Write** | create/update tags, triggers, custom dimensions | ❌ off | `--allow-write` or `GTM_GA4_MCP_ALLOW_WRITE=1` |
| **Destructive** | delete, publish, user permissions | ❌ off | `--allow-destructive` or `GTM_GA4_MCP_ALLOW_DESTRUCTIVE=1` |

1. **Registration gate** — tools above your tier are never registered, so they're invisible to the model (not just erroring at call time).
2. **Token gate** — the OAuth scopes requested from Google are derived from the same tier. A read-only process asks for `tagmanager.readonly` + `analytics.readonly` and holds a token that *cannot* mutate anything, even if the application code misbehaves.

Individual tools can also be disabled by name: `--deny gtm_get` (repeatable) or `GTM_GA4_MCP_DENY=tool_a,tool_b`.

> v0.1 ships the read tier. Write and destructive tiers (with dry-run defaults and confirmation handles for deletes/publishes) are next — see the roadmap.

## Tools (v0.1)

| Tool | What it does |
|---|---|
| `gtm_list` | List GTM entities level by level (accounts → containers → workspaces → tags/triggers/variables/templates/…), trimmed summaries |
| `gtm_get` | Full JSON for one GTM entity by path (including container versions) |
| `ga4_account_summaries` | Every GA4 account + property you can access — the entry point |
| `ga4_property_get` | One property's full configuration |
| `ga4_admin_list` | Data streams, key events, custom dimensions/metrics, Ads/Firebase links |
| `ga4_run_report` | GA4 report over a date range, rows as clean dicts |
| `ga4_run_realtime_report` | Last-30-minutes activity (verify events are firing) |
| `ga4_metadata` | Discover dimension/metric API names (standard + custom), searchable |

Design choices worth knowing: ~8 consolidated tools instead of ~120 endpoint wrappers (smaller agent context, deterministic alphabetical ordering for prompt caching), list results are trimmed summaries with `gtm_get` for deep dives, and all GTM calls flow through a rate limiter tuned to the GTM API's ~15 requests/minute default quota with backoff on 429/5xx.

## Setup

**1. Enable APIs** in a Google Cloud project: [Tag Manager API](https://console.cloud.google.com/apis/library/tagmanager.googleapis.com), [Analytics Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com), [Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com).

**2. Authenticate** with Application Default Credentials, requesting only read scopes:

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform
```

(When you later enable the write tier, re-login with the matching edit scopes — the server tells you the exact command.)

**3. Add the server.** Claude Code:

```bash
claude mcp add gtm-ga4 -- uvx --from git+https://github.com/kb223/gtm-ga4-mcp gtm-ga4-mcp
```

Or any MCP client via `.mcp.json` / Claude Desktop config:

```json
{
  "mcpServers": {
    "gtm-ga4": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/kb223/gtm-ga4-mcp", "gtm-ga4-mcp"]
    }
  }
}
```

PyPI package coming with v1.0 (`uvx gtm-ga4-mcp`).

## Try it

Ask your agent things like:

- "List my GTM accounts, then show me every tag in the main container's default workspace."
- "Which GA4 properties do I have access to, and what custom dimensions does property 123456 define?"
- "Run a report on sessions and conversions by default channel group for the last 28 days."
- "Is the `purchase` event firing right now?"

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
npx @modelcontextprotocol/inspector uv run gtm-ga4-mcp   # interactive testing
```

CI runs the test suite plus an [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) CLI smoke test (`tools/list` over stdio, no credentials needed).

## Roadmap

- **v0.2 — write tier**: GTM tag/trigger/variable create+update, GA4 custom dimensions/key events, dry-run by default
- **v0.3 — destructive tier**: delete/publish/permissions behind one-time confirmation handles (MRTR pattern from MCP spec 2026-07-28)
- **v1.0**: PyPI, MCP registry listing, MCPB bundle

## License

MIT
