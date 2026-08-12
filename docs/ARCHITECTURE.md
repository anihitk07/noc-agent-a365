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

## Per-turn OBO tool rebuild (the "genuine engineering delta")

`MCPStreamableHTTPTool` and `FoundryToolbox` both need their auth attached at
construction time (a `httpx.Auth` on the `httpx.AsyncClient`, or a
`TokenCredential`), not applied later. Because Fabric IQ and Work IQ must be
scoped to *the Teams user currently chatting*, `agent.py` cannot build them
once at process start like Foundry IQ / Web IQ. Instead, on every turn:

1. `NocAgent._exchange_user_token()` calls the A365 `AgenticUserAuthorization`
   handler (`auth.exchange_token(...)`) to get the caller's OBO token.
2. `NocAgent._build_obo_tools()` wraps that token in a fixed-token
   `httpx.Auth` (Fabric IQ) and a `TokenCredential` shim (`FoundryToolbox` /
   Work IQ), builds fresh tool objects, and returns them.
3. `agent.run(history, tools=obo_tools)` merges them with the agent's default
   (Foundry IQ + Web IQ) tools for that single call.
4. The per-turn `httpx.AsyncClient`s are closed in a `finally` block after the
   call completes.

This keeps the shared MAF `Agent` instance stateless with respect to identity
— no risk of one user's Fabric/Work IQ session leaking into another's turn.

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
