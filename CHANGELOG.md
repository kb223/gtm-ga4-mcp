# Changelog

## 0.3.1 — 2026-08-31

- Fix: per-thread Google API client cache. googleapiclient's httplib2 transport is not thread-safe, so two concurrent tool calls sharing one client corrupted the TLS connection (`SSL: RECORD_LAYER_FAILURE`). Found running parallel GA4 reports during a real audit.

## 0.3.0 — 2026-08-31

Destructive tier (enable with `--allow-destructive` or `GTM_GA4_MCP_ALLOW_DESTRUCTIVE=1`):

- `gtm_delete` — delete tags/triggers/variables/workspaces/versions/... behind a two-phase confirmation handle; accounts and containers are excluded by design
- `gtm_publish` — compile a workspace into a version and publish it live, two-phase, with compile-error abort
- `gtm_permissions` — grant/update/revoke GTM account access, two-phase
- `ga4_admin_delete` — archive custom dimensions/metrics, delete key events/data streams, two-phase
- Confirmation handles are one-time tokens fingerprinted to the exact operation (MRTR pattern, MCP spec 2026-07-28)
- `gtm_list`/`gtm_get` learned `user_permissions`

## 0.2.0 — 2026-08-31

Write tier (enable with `--allow-write` or `GTM_GA4_MCP_ALLOW_WRITE=1`):

- `gtm_create` / `gtm_update` — workspace-level GTM entities plus workspaces/environments, dry-run by default
- `ga4_admin_create` / `ga4_admin_update` — custom dimensions/metrics, key events, data streams, and property settings, dry-run by default
- OAuth scopes now follow the enabled tier (write tier requests edit scopes)

## 0.1.0 — 2026-08-31

Initial release: 8 read tools over GTM API v2, GA4 Admin API, and GA4 Data API on the MCP Python SDK v2 (2026-07-28 protocol era). Tiered safety config, GTM rate limiting with backoff, MCP Inspector CI smoke test.
