# Primer: persistent MCP "cancel scope" crash -- RESOLVED

## Root cause and fix (resolved)

The "cancel scope" error was a **misleading symptom**, not a real anyio/MCP
bug. The actual cause: the toolbox MCP endpoint's data-plane authorization
check requires the caller's Azure RBAC role (`Azure AI Developer`, or
`Foundry User` for OAuth-flow identities) to be assigned **at the Foundry
*project* scope** (`.../accounts/{account}/projects/{project}`) --
assignments scoped only to the parent **account** are silently *not*
honored by this specific preview data-plane check, unlike normal ARM RBAC
inheritance. A 403 at that layer surfaces up through
`agent_framework`/anyio as a "Cancelled via cancel scope" `ToolException`
during `session.initialize()`, which is why every fix attempt aimed at the
anyio/task-cancellation layer itself (see "Ruled out" below) never worked --
the real failure was one layer up, in Azure RBAC scope, and never visible in
the exception message itself.

**Fix applied**: granted `Azure AI Developer` (and `Foundry User`) at the
*project* scope, not just the account scope, to: the Teams users
(`nocagent`, `admin`), the `noc-iq-demo-teams-users` AAD group, and the
App Service's own system-assigned managed identity. Also added the
real Teams users and the App Service identity as Fabric workspace Members
(`<fabric-workspace-id>`) so Fabric IQ's data agent can
actually be read once the outer call succeeds. `agent.py`'s
`_build_turn_tool` forwards the calling user's own OBO token to the
toolbox (falling back to the service identity only when no OBO token is
available).

**Still outstanding (separate issue, not part of this bug)**: the `WorkIQ`
Foundry connection was created with `authType=UserEntraToken` and a bare
app-id audience (`fdcc1f02-fc51-4226-8753-f668596af7f7`), which has no
`identifierUris` and can't be used as an OBO resource (`AADSTS500016`). Per
Microsoft's Work IQ Foundry quickstart, Work IQ actually requires a
dedicated **OAuth2** connection (a BYO Entra app registration with a client
secret, the `WorkIQAgent.Ask` delegated permission + admin consent, and
Foundry-managed OAuth redirect-URI registration) -- a fundamentally
different connection type than the current one. This has **not** been
built; Work IQ will keep failing (`AADSTS500016`) until that OAuth2
connection is created from scratch per
<https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/mcp/quickstart/foundry>.

**Not required going forward, but worth knowing**: `TYPING_INDICATOR_LOOP`
was flipped to `false` on the live App Service during troubleshooting (to
rule out a race with the MCP connect) and confirmed not the cause, but was
never reverted -- it's still `false` today (see docs/TROUBLESHOOTING.md).

---

Paste the section below (the original mid-investigation primer) if you need
the full history of every hypothesis that was ruled out before the actual
root cause (RBAC project-scope) was found -- it's kept for reference only,
everything in it describes an already-resolved investigation.

## Goal (historical -- issue is now resolved, see above)

`noc-agent-a365` (MAF orchestrator over Foundry IQ / Fabric IQ / Web IQ / Work
IQ, deployed to Azure App Service `app-<token>` in RG
`rg-<env-name>`, surfaced in Teams via A365) was failing on **every single
turn** with:

```
Sorry, I encountered an error: MCP server failed to initialize: Cancelled via cancel scope <id>
```

This primer captured everything ruled out, everything still suspected, and
the exact next debugging step, before the real cause (RBAC project scope,
see above) was found.

## Full confirmed exception chain

```
anyio.WouldBlock -> asyncio.exceptions.CancelledError: Cancelled via cancel scope <id>
  (mcp/shared/session.py send_request -> response_stream_reader.receive())
-> agent_framework/_mcp.py:1360 _connect_on_owner: await session.initialize()
-> agent_framework/_mcp.py:1376: raise ToolException(...) from ex
```

App Insights shows this on the dedicated **MCP lifecycle-owner task**
(`mcp-lifecycle:noc-iq-toolbox`, `agent_framework/_mcp.py:1135
_run_lifecycle_owner`) itself — every attempt (all 3 retries) — plus:
`Task was destroyed but it is pending!` warnings referencing that same
owner task, and `Could not cleanly close MCP exit stack due to cleanup
error group. Error: unhandled errors in a TaskGroup (1 sub-exception)`
right before each retry.

## Ruled OUT this session (all tested against the live app, all failed to fix it)

1. **Shared `_async_exit_stack` across turns** (`agent_framework/_agents.py`)
   — real bug, fixed by connecting/disconnecting the per-turn
   `MCPStreamableHTTPTool` via `async with tool:` inside its own task
   (agent.py `_run_turn`). Crash persisted identically after this fix.
2. **Toolbox version staleness** — standalone probe script proved current
   toolbox version (v22+) works fine 3/3 in isolation from a dev machine.
   Not the live-app cause (app always uses its own fresh version).
3. **A365 Observability instrumentation** (`ENABLE_OBSERVABILITY`) —
   disabled, restarted, crash unchanged. Reverted back to `true`.
4. **Bounded retry with a fresh tool per attempt** (3 attempts, 1s backoff,
   `MCP_CONNECT_MAX_ATTEMPTS`/`MCP_CONNECT_RETRY_DELAY_SECONDS` in
   agent.py) — confirmed via traces to actually fire correctly, but **all 3
   attempts fail identically** every time. Not transient/racy — deterministic
   in the live app.
5. **Per-user OBO token caching** (new `self._token_cache` in agent.py,
   keyed by `(user_id, scope)`, using the JWT `exp` claim) — added to
   eliminate the ~5-6s of sequential token-broker round trips
   (Graph/Observability/ai.azure.com scopes) that precede every MCP connect
   attempt, on the theory this stalls the event loop right before
   `session.initialize()`. Deployed, crash persisted identically.
6. **Recurring typing-indicator task racing the MCP connect**
   (`TYPING_INDICATOR_LOOP` env var added in a *prior* session,
   `host_agent_server.py`'s `_typing_loop`, a `create_task` running
   concurrently with `agent.run()`) — flipped to `false`, restarted app.
   Crash persisted identically. Reverted or leave off, doesn't matter,
   confirmed not the cause.


> Historical session-planning sections (next steps, environment constraints,
> local file references) were removed when this repo was prepared for public release.

