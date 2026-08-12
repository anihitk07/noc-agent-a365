# Architecture

## Summary

`noc-agent-a365` is a Teams / M365 Copilot–native NOC (Network Operations
Center) assistant. A single **Microsoft Agent Framework (MAF)** agent is
hosted on **Agent 365 (A365)** and exposes four Microsoft **IQ** knowledge
surfaces — **Foundry IQ**, **Fabric IQ**, **Web IQ**, and **Work IQ** — as MAF
tools. The model's own tool-selection performs the routing; there is no
hand-rolled dispatcher.

The demo scenario (ported from `PathfinderIQ-Demo-Version`) is a Sydney↔Melbourne
fibre-cut incident. See [SCENARIO_NARRATIVE.md](SCENARIO_NARRATIVE.md) for the
full narrative and [SEQUENCE.md](SEQUENCE.md) for the runtime call sequence.

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
mistake in this class of solution (see `iq-samples/refund-agent-a365/TROUBLESHOOTING.md`
for the concrete failure modes). Getting Web IQ onto `UserEntraToken`, or Work
IQ / Fabric IQ onto `CustomKeys`/service credentials, both silently degrade to
either wrong-user data or hard failures.

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

## Per-turn tool rebuild (the "genuine engineering delta")

All four IQ tools are **native Foundry-hosted MCP tools**
(`FoundryChatClient.get_mcp_tool(project_connection_id=...)`), each pointing
at a pre-registered Foundry project Connection. These are plain Responses-API
tool-definition objects with **no client-side connect/disconnect lifecycle**
at all — Foundry's own service runs the actual MCP session server-side. This
replaced an earlier hand-rolled `MCPStreamableHTTPTool`/`FoundryToolbox`
design that hit three separate bug classes trying to manage that connection
lifecycle in this process (see `docs/TROUBLESHOOTING.md`).

What's still genuinely per-turn is the **identity** the tools run as. Fabric
IQ and Work IQ's Foundry connections are `UserEntraToken` (identity
passthrough): Foundry performs its own server-side OBO exchange from the
credential used to build the calling `FoundryChatClient`/`Agent` to each
connection's registered audience. That means the chat client itself — not
just the tool list — must be rebuilt every turn as the caller:

1. `NocAgent._exchange_user_token()` calls the A365 `AgenticUserAuthorization`
   handler (`auth.exchange_token(...)`) once, for the `https://ai.azure.com/.default`
   scope, to get the caller's OBO token.
2. `NocAgent.process_user_message()` builds a fresh `FoundryChatClient`/`Agent`
   for this turn, authenticated with `_StaticTokenCredential(foundry_user_token)`
   if a user token was obtained, else the app's own service credential.
3. `NocAgent._build_turn_tools()` builds the 4 native tool definitions from
   `self._connection_ids` (resolved once at startup via `AIProjectClient`),
   skipping Fabric IQ/Work IQ entirely if no user token is available this turn.
4. `agent.run(history, tools=turn_tools)` runs the turn.

This keeps per-user identity isolated to the credential used to build each
turn's chat client — no risk of one user's Fabric/Work IQ session leaking
into another's turn — while the tool *definitions* themselves are cheap,
stateless dicts with nothing to close afterward.

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
