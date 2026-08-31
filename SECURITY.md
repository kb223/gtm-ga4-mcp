# Security Model

## Threat model

The scenario this server is designed around: **prompt injection reaching a destructive call**. An agent reads untrusted content (a web page, a ticket, a tag's own notes field), that content smuggles an instruction like "delete all triggers and publish", and the agent complies. A GTM publish is a production deployment to every page of a website — the blast radius is real.

## Defense in depth

Four layers, outermost first:

1. **OAuth token scope.** Scopes are derived from the configured tier. In the default read-only mode the process holds `tagmanager.readonly` + `analytics.readonly` tokens — Google's API rejects mutations regardless of what this server's code does.
2. **Registration gate.** Tools above the configured tier are never registered. The model cannot call — or be tricked into calling — a tool it cannot see.
3. **Dry-run default** (write tier). Mutations echo the exact payload without sending it; execution requires an explicit `dry_run: false`.
4. **Confirmation handles** (destructive tier). Delete/publish/permission changes return a one-time token plus a human-readable summary; the operation only executes when re-invoked with that token. Tokens are SHA-256-fingerprinted to the exact operation (tool + arguments), single-use, and expire after 10 minutes — following the Multi Round-Trip Requests pattern from MCP spec 2026-07-28, which works on every client rather than depending on optional elicitation support.
5. **Blast-radius exclusions.** GTM accounts and containers, and GA4 properties, cannot be deleted through this server at all — those operations are not implemented on purpose.

Tool annotations (`readOnlyHint`, `destructiveHint`) are set honestly on every tool, but per the MCP spec they are hints — none of the layers above rely on them.

## Credentials

- Authentication is Application Default Credentials only. This server never accepts, stores, or logs tokens or keys of its own.
- No telemetry, no network calls other than Google APIs.
- stdio transport; nothing listens on a port.

## Reporting

Open a GitHub issue for non-sensitive reports. For anything sensitive, use GitHub's private vulnerability reporting on this repository.
