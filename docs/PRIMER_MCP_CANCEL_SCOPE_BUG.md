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
(`ddf56a0f-9dff-4022-887f-73f5c4795d15`) so Fabric IQ's data agent can
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
IQ, deployed to Azure App Service `app-n2tjinbhnbln6` in RG
`rg-noc-iq-demo`, surfaced in Teams via A365) was failing on **every single
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

## Still suspected / not yet tested

1. **`host_agent_server.py`'s aiohttp `run_app(..., handle_signals=True)`**
   (line ~492 in `create_and_run_host`) — aiohttp installs its own
   SIGTERM/SIGINT handlers for graceful shutdown when `handle_signals=True`.
   If Azure App Service's Linux container sends periodic signals (health
   probes, idle-timeout enforcement, scaling operations) to the process,
   aiohttp's shutdown sequence could cancel all pending tasks — including
   the in-flight MCP lifecycle-owner task — from a context anyio sees as
   "cancelled via a different task's cancel scope." **This was the active
   thread when the last session got interrupted mid-investigation — test
   next by setting `handle_signals=False` and redeploying.**
2. Was mid-read of `agent_framework/_mcp.py`'s `MCPTool` internals
   (`_ensure_lifecycle_owner` L1124, `_run_lifecycle_owner` L1135,
   `_lifecycle_owner_task` L530, `_is_lifecycle_owner_task` L1181) on the
   local machine
   (`C:\Users\aganguly\AppData\Local\Programs\Python\Python313\Lib\site-packages\agent_framework\_mcp.py`)
   to understand exactly what could destroy/cancel that owner task from
   outside — **not yet concluded**.
3. Environment/runtime differences between the Windows dev machine (where
   the standalone probe succeeds) and the Linux App Service container
   (where the live app always fails): event loop implementation
   differences, DNS/TLS stack behavior, outbound connection
   keep-alive/idle-timeout handling possibly reset by the platform.
4. Whether the ~5-6s of sequential token-broker calls (still happening on
   cache-miss turns even after fix #5 above) is itself normal A365 SDK
   behavior or a misconfiguration forcing fresh acquisition instead of using
   MSAL's own token cache.

## Fast next steps (in order)

1. **Test `handle_signals=False`** in `host_agent_server.py`'s `run_app(...)`
   call — smallest possible change, directly tests the leading unconfirmed
   hypothesis. Redeploy (`azd deploy`, ~5 min), have user retest in Teams,
   check App Insights traces for the same signature.
2. If that doesn't fix it: add a diagnostic log right before
   `session.initialize()` (or monkeypatch a wrapper) capturing
   `asyncio.all_tasks()` state / any pending cancellation on the current
   task, to see directly what's cancelling the owner task, rather than
   inferring from behavior.
3. If still unresolved after that: give the user an honest time-boxed
   verdict — either escalate to Microsoft/agent_framework maintainers with
   the full evidence trail (this primer + docs/TROUBLESHOOTING.md), or
   fall back to bypassing `agent_framework.MCPStreamableHTTPTool` entirely
   and call the toolbox via raw MCP JSON-RPC HTTP calls directly (proven
   reliable standalone and via direct calls).

## Standing constraints (do not violate)

- **Do not delete any Azure resources** in `rg-noc-iq-demo` — user will
  explicitly trigger teardown after the demo/E2E passes.
- All infra is a fresh RG/all-new resources under `anihitk07`'s
  subscription (`ME-M365CPI48286597-aganguly-1`), region `eastus2`
  (App Insights/agent traces show `westus3` for the agentic-token-broker
  region detection — this is a red herring, unrelated to a separate
  resource region and not yet fully explained but not implicated in the
  crash by any evidence so far).
- Commit all `agent.py`/`host_agent_server.py`/scripts/docs fixes once the
  bug is actually resolved — several real bugs were found and fixed this
  session already (exit-stack, NameError regression, token caching) but are
  not yet committed to git.
- Repo: `C:\Flutter\noc-agent-a365` (local git, not yet pushed to a remote
  this session).

## Key files

- `agent/agent.py` — MAF orchestrator, `_run_turn`/retry loop (~line 480),
  `_build_turn_tool` (~line 403), `_exchange_user_token` + new
  `_token_cache` (~line 673), module docstring has full auth-type-matrix
  rationale.
- `agent/host_agent_server.py` — A365/aiohttp host. `create_and_run_host`
  (~line 76), `run_app(..., handle_signals=True)` (~line 492, next test
  target), `on_message`/`_typing_loop` (~line 209-280).
- `agent/token_cache.py` — unrelated pre-existing cache for A365
  Observability exporter tokens, do not confuse with the new
  `self._token_cache` in agent.py.
- `docs/TROUBLESHOOTING.md` — existing history table, needs this session's
  findings appended once resolved.
- Third-party (not in repo, read-only reference):
  `C:\Users\aganguly\AppData\Local\Programs\Python\Python313\Lib\site-packages\agent_framework\_mcp.py`
  — `MCPTool` class ~L396, lifecycle-owner-task pattern L1124-1273.
