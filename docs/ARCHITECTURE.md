# Architecture

## Summary

`noc-agent-a365` is a Teams / M365 Copilot–native NOC (Network Operations
Center) assistant. A single **Microsoft Agent Framework (MAF)** agent is
hosted on **Agent 365 (A365)** and exposes four Microsoft **IQ** knowledge
surfaces — **Foundry IQ**, **Fabric IQ**, **Web IQ**, and **Work IQ** — as MAF
tools. The model's own tool-selection performs the routing; there is no
hand-rolled dispatcher.

The demo scenario is a Sydney↔Melbourne fibre-cut incident. See
[SEQUENCE.md](SEQUENCE.md) §3 for the 5 narrative beats a correct
end-to-end run must surface, and the rest of that doc for the runtime
call sequence.

## Components

```
Teams / M365 Copilot
        │  A365 teammate account (AgenticUserAuthorization → OBO user token)
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ agent/  (Azure App Service, Linux, Python 3.13)                       │
│                                                                        │
│  host_agent_server.py   Generic A365 host: AgentApplication +          │
│                         Authorization + CloudAdapter, message/         │
│                         notification/installationUpdate handlers,      │
│                         typing indicators, /api/health, JWT middleware. │
│                         (Ported verbatim — no NOC-specific logic.)      │
│                                                                        │
│  agent.py               NocAgent(AgentInterface). Owns one MAF Agent   │
│                         built from FoundryChatClient(project_endpoint, │
│                         model=gpt-5.4). Default tools (built once,     │
│                         service-credentialed): Foundry IQ + Web IQ.    │
│                         Per-turn tools (rebuilt from the caller's OBO  │
│                         token, merged via agent.run(tools=...)):       │
│                         Fabric IQ + Work IQ.                           │
│                                                                        │
│  token_cache.py,        Generic A365 plumbing (observability token     │
│  agent_interface.py,    cache, the AgentInterface ABC, local dev auth  │
│  local_authentication_  options). Ported verbatim.                    │
│  options.py                                                            │
└───────────────────────────────────────────────────────────────────────┘
        │                    │                    │                  │
        ▼                    ▼                    ▼                  ▼
┌───────────────┐   ┌────────────────┐   ┌────────────────┐  ┌───────────────┐
│  Foundry IQ    │   │  Fabric IQ     │   │  Web IQ        │  │  Work IQ      │
│  Knowledge     │   │  Data Agent    │   │  Microsoft web │  │  M365 toolbox │
│  Base MCP      │   │  MCP over the  │   │  MCP server    │  │  (Teams,      │
│  over runbooks/│   │  NOC network   │   │                │  │  Outlook)     │
│  tickets/specs │   │  ontology      │   │                │  │               │
│  (Azure AI     │   │  (Fabric       │   │                │  │               │
│  Search)       │   │  Lakehouse)    │   │                │  │               │
└───────────────┘   └────────────────┘   └────────────────┘  └───────────────┘
```

## IQ auth-type matrix

| IQ surface | Purpose in this demo | Connection auth | Why |
|---|---|---|---|
| **Foundry IQ** | Runbooks, tickets, equipment/infra specs | Service credential (`AzureDeveloperCliCredential` / `ManagedIdentityCredential`) | Not user-scoped data — a shared corpus, safe for a service identity |
| **Fabric IQ** | Live network topology / blast-radius queries | **`UserEntraToken`** (OBO passthrough) | Fabric enforces per-user row/item security; must pass the caller's identity |
| **Web IQ** | Vendor advisories / public carrier status | **`CustomKeys`** (static `x-apikey`) | Public web data, identity-independent — a static key is correct and simpler |
| **Work IQ** | On-call roster, bridge chatter, change approvals | **`UserEntraToken`** (OBO passthrough) | Reads the *user's* Teams/Outlook data; app-only auth is blocked (`AADSTS82001`) |

Picking the wrong auth type per surface is the single most common integration
mistake in this class of solution (see `docs/TROUBLESHOOTING.md` for the
concrete failure modes hit in this repo). Getting Web IQ onto
`UserEntraToken`, or Work IQ / Fabric IQ onto `CustomKeys`/service
credentials, both silently degrade to either wrong-user data or hard
failures.

## Why one MAF agent instead of four specialist agents

An earlier design considered four specialist sub-agents (TopologyAnalyst,
KnowledgeAnalyst, ThreatIntelAnalyst, CommsCoordinator) behind a hand-rolled
router. Reading `microsoft/iqdeepdive`'s working samples
(`src/agent-workiq-maf`, `src/agent-foundryiq-mcp`,
`src/agent-toolbox-foundryiq-workiq`) showed the idiomatic and *supported*
MAF pattern is simpler: **one `agent_framework.Agent` with all tools bound**.
The chat model's native tool-selection already performs the routing an
explicit dispatcher would otherwise re-implement, with no loss of citation
fidelity as long as the system instructions tell the model which tool answers
which class of question (see the `NOC_AGENT_INSTRUCTIONS` prompt in
`agent/agent.py`).

## Per-turn tool: one Foundry Toolbox, one client-side MCP tool (the "genuine engineering delta")

All four IQ connections are bundled into a single **Foundry Toolbox**
(`project_client.toolboxes.create_version("noc-iq-toolbox", tools=[...])`),
built once in `NocAgent.initialize()`. Each entry is an `MCPToolboxTool`
(`server_label`, `server_url=connection.target`,
`project_connection_id=connection.id`, `require_approval="never"`). The
toolbox exposes its own combined MCP endpoint:
`{PROJECT_ENDPOINT}/toolboxes/noc-iq-toolbox/versions/{version}/mcp?api-version=v1`.

This replaced two earlier designs, in order:

1. A hand-rolled `MCPStreamableHTTPTool`/`FoundryToolbox` wrapper managing raw
   `httpx.AsyncClient` connect/close lifecycles itself — hit three separate
   bug classes (see `docs/TROUBLESHOOTING.md`).
2. `FoundryChatClient.get_mcp_tool(project_connection_id=...)` — this is a
   **Prompt Agent** pattern (persisted `project.agents.create_version(...)` +
   `extra_body={"agent_reference": {...}}`), not valid for the **Hosted
   Agent** pattern this app uses (ephemeral MAF `Agent`/`FoundryChatClient`,
   direct `responses.create(...)` calls). Mixing the two surfaced as a 400
   `missing_mutually_exclusive_parameters` error — see
   `docs/TROUBLESHOOTING.md`.

The current design follows the official ["Hosted agents" MCP tool
sample](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol):
bundle project connections into one Toolbox, then attach that ONE endpoint on
the **client side** via `agent_framework.MCPStreamableHTTPTool`.

**Chat client / agent are long-lived, not per-turn.** `self._chat_client` and
`self._agent` are built once in `initialize()`, always authenticated with the
app's own **service credential** — matching the doc sample, which uses a
fixed credential rather than a per-user one for the chat client itself.

**What's still genuinely per-turn is the identity used to call the toolbox.**
Fabric IQ and Work IQ's underlying Foundry connections are `UserEntraToken`
(identity passthrough). That passthrough now happens one layer below the chat
client, at the toolbox's own MCP HTTP call:

1. `NocAgent._exchange_user_token()` calls the A365 `AgenticUserAuthorization`
   handler (`auth.exchange_token(...)`) once, for the `https://ai.azure.com/.default`
   scope, to get the caller's OBO token.
2. `NocAgent._build_turn_tool()` builds a fresh `MCPStreamableHTTPTool` for
   this turn, pointed at `self._toolbox_mcp_url`, with a `header_provider`
   closure that returns `{"Authorization": f"Bearer {token}"}` — the caller's
   OBO token if available, else a freshly-fetched service-credential token.
   `MCPStreamableHTTPTool` manages its own internal `httpx.AsyncClient` and
   only injects the header on same-origin requests (a security feature
   against cross-origin token leaks on redirects); our code never touches
   raw `httpx` directly.
3. `NocAgent.process_user_message()` calls `self._agent.run(history,
   tools=[turn_tool])`, then closes the turn tool (`await turn_tool.close()`)
   in a `finally` block to release its internal HTTP client.

This keeps per-user identity isolated to the header injected on that turn's
MCP calls — no risk of one user's Fabric/Work IQ session leaking into
another's turn — while the toolbox definition itself (the set of 4 bundled
connections) is shared, built once, and reused across all turns and users.

**Known cost/smell**: a new toolbox *version* is created on every app
start/restart (no dedup/reuse logic). Acceptable for this demo; would
accumulate garbage versions in a long-lived deployment — see
`docs/TROUBLESHOOTING.md`.

## Infrastructure (`infra/`)

All resources are provisioned brand-new into a dedicated resource group (no
existing resources are reused), tagged `purpose=noc-iq-demo` plus an optional
`DeleteBy` teardown marker:

| Resource | Bicep module | Notes |
|---|---|---|
| Resource group | `infra/main.bicep` | Subscription-scope entry point |
| AI Foundry account + project | `infra/core/ai/ai-project.bicep` | Hosts the `gpt-5.4` deployment, Foundry IQ KB connection, Web IQ connection |
| Model deployments | `infra/core/ai/ai-project.bicep` (`sequentialDeployments`) | `gpt-5.4` (chat) + `text-embedding-3-small` (KB vectorization) |
| Azure AI Search | `infra/core/search/azure_ai_search.bicep` | Backs the Foundry IQ knowledge base |
| Storage account | `infra/core/storage/storage.bicep` | KB source-document staging |
| Application Insights + Log Analytics | `infra/core/monitor/*.bicep` | End-to-end tracing for `verify-e2e` |
| Fabric capacity (F2) | `infra/core/fabric/fabric-capacity.bicep` | Backs the Fabric IQ workspace/lakehouse/ontology (billable — paused/deleted at teardown) |
| App Service (Linux, B1) | `infra/core/host/appservice.bicep` | Hosts `agent/` via `start_with_generic_host.py` |
| Project-scope RBAC | `infra/core/ai/rbac.bicep` | Grants the App Service's managed identity Azure AI Developer + Cognitive Services User **scoped to the Foundry project**, not just the account — required for the Agents API |

The Fabric **workspace** itself is a Fabric-tenant object, not an ARM
resource, and is created/deleted separately from the resource group (see
`scripts/create_fabric_ontology.py` and `docs/DEPLOYMENT.md` §7 for teardown).
