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

Beyond the two gates, mutations carry their own guards:

- **Write tools default to dry-run** — they echo the exact API request without sending it; execution requires an explicit `dry_run: false`.
- **Destructive tools are two-phase** — the first call changes nothing and returns a one-time `confirm_token` plus a plain-language summary; only a second call with that token executes. Tokens are fingerprinted to the exact operation (a confirmation for deleting tag X can never authorize deleting tag Y), single-use, and expire in 10 minutes. This follows the Multi Round-Trip Requests pattern from MCP spec 2026-07-28 and works on every client.
- **Blast-radius exclusions** — accounts, containers, and GA4 properties can never be deleted through this server, by design.

## Tools

**Read tier (always on):**

| Tool | What it does |
|---|---|
| `gtm_list` | List GTM entities level by level (accounts → containers → workspaces → tags/triggers/variables/templates/permissions/…), trimmed summaries |
| `gtm_get` | Full JSON for one GTM entity by path (including container versions) |
| `ga4_account_summaries` | Every GA4 account + property you can access — the entry point |
| `ga4_property_get` | One property's full configuration |
| `ga4_admin_list` | Data streams, key events, custom dimensions/metrics, Ads/Firebase links |
| `ga4_run_report` | GA4 report over a date range, rows as clean dicts |
| `ga4_run_realtime_report` | Last-30-minutes activity (verify events are firing) |
| `ga4_metadata` | Discover dimension/metric API names (standard + custom), searchable |

**Write tier (`--allow-write`), all dry-run by default:**

| Tool | What it does |
|---|---|
| `gtm_create` | Create tags, triggers, variables, folders, templates, clients, transformations, zones, workspaces, environments |
| `gtm_update` | Replace a GTM entity (full-body update with optional optimistic-lock fingerprint) |
| `ga4_admin_create` | Create custom dimensions/metrics, key events, data streams |
| `ga4_admin_update` | Patch GA4 entities or property settings (partial update via update mask) |

**Destructive tier (`--allow-destructive`), all two-phase confirmed:**

| Tool | What it does |
|---|---|
| `gtm_delete` | Delete workspace entities, workspaces, versions, environments (never accounts/containers) |
| `gtm_publish` | Compile a workspace into a version and publish it LIVE (aborts on compile errors) |
| `gtm_permissions` | Grant / update / revoke GTM account access |
| `ga4_admin_delete` | Archive custom dimensions/metrics, delete key events/data streams (never properties) |

Design choices worth knowing: ~8 consolidated tools instead of ~120 endpoint wrappers (smaller agent context, deterministic alphabetical ordering for prompt caching), list results are trimmed summaries with `gtm_get` for deep dives, and all GTM calls flow through a rate limiter tuned to the GTM API's ~15 requests/minute default quota with backoff on 429/5xx.

## Setup

**1. Enable APIs** in a Google Cloud project: [Tag Manager API](https://console.cloud.google.com/apis/library/tagmanager.googleapis.com), [Analytics Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com), [Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com).

**2. Authenticate** with Application Default Credentials. Log in with the scopes matching the tier you run — this is the token-level gate, so a read-only login is a hard guarantee:

Read-only (default):

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform
```

Everything, for a full read/write/destructive session:

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/tagmanager.delete.containers,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/tagmanager.manage.users,https://www.googleapis.com/auth/cloud-platform
```

**3. Add the server.** Claude Code (read-only):

```bash
claude mcp add gtm-ga4 -- uvx --from git+https://github.com/kb223/gtm-ga4-mcp gtm-ga4-mcp
```

Append `--allow-write` or `--allow-destructive` to that command to enable higher tiers.

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

### "This app is blocked" during login

Google blocks Tag Manager / Analytics scopes on gcloud's shared default OAuth client, so the plain `gcloud auth application-default login` above may fail with *"This app tried to access sensitive info in your Google Account."* The fix — same as Google documents for their own analytics-mcp — is a two-minute OAuth client of your own:

1. In a Google Cloud project with the three APIs enabled, open **APIs & Services → OAuth consent screen**: user type **External**, publishing status **Testing**, and add your own Google account as a test user.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app**, then download the client JSON.
3. Re-run the login with your client:

```bash
gcloud auth application-default login --client-id-file=path/to/client_secret.json --scopes=<same scopes as above>
```

Heads-up: while the consent screen is in Testing mode, Google expires the refresh token after ~7 days, so expect to re-run the login weekly (or publish the app and click through the unverified-app warning).

## Try it

Ask your agent things like:

- "List my GTM accounts, then show me every tag in the main container's default workspace."
- "Which GA4 properties do I have access to, and what custom dimensions does property 123456 define?"
- "Run a report on sessions and conversions by default channel group for the last 28 days."
- "Is the `purchase` event firing right now?"
- (write tier) "Create a `lead_type` event-scoped custom dimension on property 123456." — you'll see the dry-run payload first
- (destructive tier) "Delete the paused tag called Old Pixel." — you'll get a summary + confirmation token before anything happens

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
npx @modelcontextprotocol/inspector uv run gtm-ga4-mcp   # interactive testing
```

CI runs the test suite plus an [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) CLI smoke test (`tools/list` over stdio, no credentials needed).

## Roadmap

- ~~v0.2 — write tier~~ ✅ shipped
- ~~v0.3 — destructive tier~~ ✅ shipped
- **v1.0**: PyPI, MCP registry listing, MCPB bundle

## License

MIT
