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

## 3. The 5 narrative beats this sequence must produce

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
