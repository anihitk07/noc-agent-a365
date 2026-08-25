# Sequence Diagrams

## 1. End-to-end deployment sequence

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator (you)
    participant Az as Azure (az / azd)
    participant RG as New Resource Group
    participant Fab as Fabric (tenant)
    participant Agent as App Service (NocAgent)
    participant A365 as A365 CLI

    Op->>Az: az login / azd auth login (target subscription)
    Op->>Az: azd up  (infra/main.bicep)
    Az->>RG: Create RG (tags: purpose=noc-iq-demo, DeleteBy=<date>)
    Az->>RG: Create AI Foundry account + project + gpt-5.4/text-embedding-3-small deployments
    Az->>RG: Create Azure AI Search + Storage + App Insights + Log Analytics
    Az->>RG: Create Fabric capacity (F2)
    Az->>RG: Create App Service (agent host) + project-scope RBAC
    Az-->>Op: outputs (project endpoint, search endpoint, capacity name, app host name)

    Op->>Az: python scripts/create_foundry_iq_kb.py
    Az-->>Op: Foundry IQ knowledge base MCP endpoint

    Op->>Fab: python scripts/create_fabric_ontology.py
    Fab->>Fab: Create workspace on F2 capacity, lakehouse, load NOC CSVs as Delta tables
    Fab->>Fab: Create ontology (CoreRouter/TransportLink/PhysicalConduit/... + relationships)
    Fab-->>Op: FABRIC_ONTOLOGY_ID, ontology UI + MCP URLs

    Op->>Fab: python scripts/create_fabric_data_agent.py
    Fab->>Fab: Create/publish Fabric Data Agent over the ontology
    Fab-->>Op: FABRIC_DATA_AGENT_MCP_URL

    Op->>Az: Portal — add Web IQ connection (CustomKeys/x-apikey) [done via Bicep if key supplied]
    Op->>Az: python scripts/create_workiq_toolbox.py  (WorkIQ connection, authType=UserEntraToken)
    Op->>Az: ARM PUT fabric-iq-connection  (authType=UserEntraToken, see DEPLOYMENT.md Sec4c)
    Op->>Az: python scripts/create_foundry_agents.py
    Az->>Az: For each of 4 IQ connections: resolve connection, project.agents.create_version(<br/>  name, PromptAgentDefinition(model, instructions, tools=[MCPTool(project_connection_id)]))
    Az-->>Op: noc-knowledge-agent, noc-topology-agent, noc-threatintel-agent,<br/>noc-comms-agent — 4 persisted Prompt Agents, idempotent (re-run is a no-op<br/>unless the definition actually changed)

    Op->>Az: azd deploy  (pushes agent/ to the App Service)
    Az->>Agent: App Service cold-starts NocAgent.initialize()
    Agent->>Az: confirm each of the 4 specialist agents exists (project.agents.get(name))
    Agent->>Agent: build the orchestrator MAF Agent, binding 4 agents-as-tools<br/>(ask_knowledge_agent, ask_topology_agent, ask_threatintel_agent, ask_comms_agent)
    Note over Agent,Az: No shared Toolbox anymore — each specialist agent already holds<br/>its own single MCPTool, created once by create_foundry_agents.py.

    Op->>A365: a365 setup all  (mint teammate identity + blueprint permissions)
    A365->>A365: Register app, create agentic user, apply customBlueprintPermissions
    A365-->>Op: agent published to Teams / M365 Copilot (tenant admin consent required)
    Op->>Az: az role assignment create --role "Foundry Agent Consumer" --scope <project><br/>--assignee-object-id <noc-iq-demo-teams-users group> (infra/core/ai/rbac.bicep<br/>teamsUsersPrincipalId param) — required for Fabric IQ/Work IQ OAuth passthrough
```

## 2. Runtime turn — Teams user asks about the Sydney fibre cut

```mermaid
sequenceDiagram
    autonumber
    participant User as Teams user
    participant Bot as Azure Bot Service<br/>(channel connector)
    participant A365 as App Service — host_agent_server.py<br/>(/api/messages, CloudAdapter)
    participant Orc as NocAgent orchestrator (agent.py, MAF, ephemeral)
    participant KA as noc-knowledge-agent<br/>(persisted, Foundry IQ)
    participant TA as noc-topology-agent<br/>(persisted, Fabric IQ)
    participant TI as noc-threatintel-agent<br/>(persisted, Web IQ)
    participant CA as noc-comms-agent<br/>(persisted, Work IQ)

    User->>Bot: "What's the blast radius of the SYD-MEL fibre cut?"
    Bot->>A365: POST /api/messages (Bot Framework Activity JSON)
    A365->>A365: on_message handler, start typing indicator
    A365->>Orc: process_user_message(message, auth, auth_handler_name, context)
    Orc->>A365: auth.exchange_token(scopes=[ai.azure.com/.default], AGENTIC)
    A365-->>Orc: user OBO token
    Orc->>Orc: _current_user_token.set(token) — per-turn contextvar,<br/>isolated to this asyncio Task tree

    Orc->>Orc: self._agent.run(history) — orchestrator model call,<br/>4 specialist tool functions bound as tools
    Note over Orc,CA: The ORCHESTRATOR's model decides which specialists to call and how many times.<br/>Each call is a full Prompt Agent turn (its own model + its own MCP tool), not a raw MCP tool call.

    par Orchestrator model decides which specialists to call, in whatever order/count it needs
        Orc->>TA: ask_topology_agent("blast radius for LINK-SYD-MEL-FIBRE-01")
        Orc->>TA: get_openai_client(agent_name="noc-topology-agent") — credential =<br/>_StaticTokenCredential(user OBO token) (UserEntraToken passthrough)
        TA-->>Orc: dependent services (VPN-ACME-CORP, VPN-BIGBANK),<br/>shared conduit (CONDUIT-SYD-MEL-INLAND)
    and
        Orc->>KA: ask_knowledge_agent("fibre-cut runbook + SLA policy terms")
        Orc->>KA: get_openai_client(agent_name="noc-knowledge-agent") — service credential
        KA-->>Orc: runbook steps, SLA $/hr penalty terms
    and
        Orc->>TI: ask_threatintel_agent("vendor/carrier advisory for the affected route")
        Orc->>TI: get_openai_client(agent_name="noc-threatintel-agent") — service credential
        TI-->>Orc: live advisory (if any)
    and
        Orc->>CA: ask_comms_agent("on-call roster / bridge chatter")
        Orc->>CA: get_openai_client(agent_name="noc-comms-agent") — credential =<br/>_StaticTokenCredential(user OBO token) (UserEntraToken passthrough)
        CA-->>Orc: on-call engineer, active bridge summary
    end

    Orc->>Orc: check each specialist's response.output for an oauth_consent_request item<br/>(_extract_oauth_consent_url) — if found, set the _pending_consent contextvar<br/>instead of returning text (see step below)
    Orc->>Orc: orchestrator model synthesizes ONE response from whatever specialist<br/>results came back — cite each source, in order: blast radius → SLA exposure →<br/>shared-conduit finding → runbook → advisory → on-call
    Orc-->>A365: response text (or, if _pending_consent was set by any specialist,<br/>an empty string — the consent Adaptive Card is sent directly instead)
    A365-->>Bot: response text
    Bot-->>User: "Blast radius: VPN-ACME-CORP + VPN-BIGBANK ($75k/hr exposure)...<br/>⚠️ Non-obvious: FIBRE-02 shares CONDUIT-SYD-MEL-INLAND...<br/>Runbook: reroute via Brisbane... On-call: ..."
```

**Key point this diagram must make clear**: there are **four persisted Foundry
Prompt Agents**, each with its own single MCP tool baked into its own
definition, called via **agents-as-tools** from one ephemeral MAF
orchestrator `Agent`. The `par` block above shows the orchestrator model's
own tool-selection deciding which (and how many) specialists to invoke;
`agent.py` still does not iterate over the 4 IQ surfaces or hand-aggregate
their results itself — only the granularity of what's being routed to has
changed, from a raw MCP tool call to a whole persisted-agent turn.

## 3. Run-scoped token governance (TokenOps) — mixed routing, not a blanket APIM hop

**Why not simply route all 5 model calls (orchestrator + 4 specialists) through
APIM?** Two hard blockers, both discovered while wiring this up:

- **OAuth identity passthrough breaks.** `fabric_iq` and `work_iq` authenticate
  each `responses.create()` call as the *calling Teams user* (a
  `_StaticTokenCredential` wrapping their OBO token), so Agent Service attributes
  the stored per-user consent grant correctly. APIM's `authentication-managed-identity`
  policy substitutes **its own** identity before the call reaches Foundry —
  fine for the 2 service-identity specialists, but it would silently break
  consent attribution for these 2.
- **Persisted-agent request bodies don't fit the gateway's assumptions.**
  `openai-gateway`/`foundry-gateway`'s policies parse a `model` field and a
  `messages`/`input` field out of the request body for token estimation and
  the allowed-model check. A persisted Prompt Agent's model is baked into its
  *own* definition — the client-side `responses.create(input=question)` call
  often carries neither a `model` field nor a `messages` array, so those
  policies' assumptions (now fixed for Responses-API field names, see below)
  still don't fully describe what this app actually sends per specialist.

**What actually ships**: the orchestrator and all 4 specialists keep calling
Foundry **directly** (unchanged data path, so consent passthrough keeps
working for all 4 uniformly). Token governance is achieved by having
`agent.py` itself call the run ledger's `/v1/precall` and `/v1/postcall`
directly — the same decision contract (`allow` / `mutate` / `queue` / `halt`)
APIM's own policies use, just invoked from Python instead of from policy XML,
using the real `response.usage` each call already returns. Since the run
ledger's Container App has **internal-only ingress** (unreachable from the
non-VNet-integrated App Service), these calls go through a thin `/ledger`
pass-through API added to APIM (`run-ledger-gateway` in `apim.bicep`) — APIM
is already VNet-injected and can reach it; this is a plain reverse-proxy hop
with no body inspection, so it doesn't inherit either blocker above.

The deployed `openai-gateway`/`foundry-gateway` APIs (now fixed for
Responses-API field names: `input`/`max_output_tokens`/`input_tokens`/
`output_tokens`, with defensive fallback to the old Chat-Completions field
names) remain live and available for any *other* direct AOAI/Foundry caller
that does send REST-shaped, model-in-body traffic — they are just not in this
app's own hot path.

```mermaid
sequenceDiagram
    autonumber
    participant Orc as NocAgent orchestrator (agent.py)
    participant Ledger as APIM /ledger pass-through<br/>→ Run Ledger (internal Container App)
    participant KA as noc-knowledge-agent (Foundry IQ)
    participant TA as noc-topology-agent (Fabric IQ, OBO)
    participant TI as noc-threatintel-agent (Web IQ)
    participant CA as noc-comms-agent (Work IQ, OBO)

    Note over Orc,Ledger: Once per turn: mint/reuse a run token (POST /v1/runs),<br/>run_id derived deterministically from conversation_id + activity_id

    Orc->>Ledger: POST /v1/precall (run_id, agent=noc-agent, step, model,<br/>est_input_tokens) — orchestrator's own model call
    Ledger-->>Orc: {action: allow|mutate|queue|halt, reservation_id}
    alt halt or queue
        Orc-->>Orc: raise _RunHaltedError → Teams Adaptive Card ("Run paused by policy")
    else allow / mutate
        Orc->>Orc: self._agent.run(history) (direct to Foundry, unchanged)
        Orc->>Ledger: POST /v1/postcall (reservation_id, real usage_details<br/>input_token_count/output_token_count)
    end

    par For each specialist the orchestrator's model decides to call
        Orc->>Ledger: POST /v1/precall (run_id, agent=knowledge, step, model=noc-knowledge-agent, est_input_tokens)
        Ledger-->>Orc: decision
        Orc->>KA: responses.create(input=question) — service credential, direct to Foundry
        KA-->>Orc: response (usage.input_tokens/output_tokens)
        Orc->>Ledger: POST /v1/postcall (real usage)
    and
        Orc->>Ledger: POST /v1/precall (run_id, agent=topology, step, model=noc-topology-agent, ...)
        Ledger-->>Orc: decision
        Orc->>TA: responses.create(input=question) — _StaticTokenCredential(user OBO token), direct to Foundry
        TA-->>Orc: response (or oauth_consent_request item — unaffected by any of this)
        Orc->>Ledger: POST /v1/postcall (real usage, or failed=true on error)
    and
        Orc->>Ledger: POST /v1/precall (agent=threatintel, model=noc-threatintel-agent, ...)
        Orc->>TI: responses.create(input=question) — service credential, direct to Foundry
        TI-->>Orc: response
        Orc->>Ledger: POST /v1/postcall (real usage)
    and
        Orc->>Ledger: POST /v1/precall (agent=comms, model=noc-comms-agent, ...)
        Orc->>CA: responses.create(input=question) — _StaticTokenCredential(user OBO token), direct to Foundry
        CA-->>Orc: response
        Orc->>Ledger: POST /v1/postcall (real usage, or failed=true on error)
    end
```

**Answering "how is fabric_iq/work_iq's usage governed if it never goes through
APIM?"**: identically to the other two, via this direct precall/postcall pair —
the OAuth-passthrough identity used for the Foundry call is completely
orthogonal to which channel reports the resulting token usage to the ledger.
The run ledger enforces the same run-scoped budget/halt/steer decisions either
way; only the transport of the *governed* call itself (direct vs. through
APIM) differs, and that choice is driven purely by which of the two blockers
above applies to that specialist.

## 4. The 5 narrative beats this sequence must produce


A correct end-to-end run must surface all five, each traceable to a real
tool call (verified via App Insights traces in the `verify-e2e` step, not
asserted from the model's unaided knowledge):

1. **Blast radius** — `VPN-ACME-CORP` + `VPN-BIGBANK` depend on the cut link
   (Fabric IQ).
2. **SLA exposure** — `$75,000/hr` = ACME (GOLD, `$50k/hr`) + BigBank (SILVER,
   `$25k/hr`) (Foundry IQ — SLA policy docs / Fabric IQ — SLA policy entity).
3. **Bounded exclusion** — `OzMine` (GOLD, `$40k/hr`) is **not** affected;
   the blast radius must be shown as bounded, not maximal (Fabric IQ).
4. **Non-obvious finding** — `LINK-SYD-MEL-FIBRE-02` (the "backup") shares
   `CONDUIT-SYD-MEL-INLAND` with the cut primary link — fake redundancy
   (Fabric IQ `RIDES_ON` relationship).
5. **Reroute** — the runbook-prescribed mitigation is a reroute via Brisbane
   (Foundry IQ knowledge base).
