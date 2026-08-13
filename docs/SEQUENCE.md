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
    Op->>Az: azd deploy  (pushes agent/ to the App Service)
    Az->>Agent: App Service cold-starts NocAgent.initialize()
    Agent->>Az: resolve all 4 project connections (kb-mcp, web-iq, fabric-iq, WorkIQ)
    Agent->>Az: project.toolboxes.create_version("noc-iq-toolbox", tools=[4x MCPToolboxTool])
    Note over Agent,Az: One Foundry Toolbox bundles all 4 IQ connections behind ONE MCP endpoint.<br/>Rebuilt fresh on every app start — no manual toolbox step in the portal.

    Op->>A365: a365 setup all  (mint teammate identity + blueprint permissions)
    A365->>A365: Register app, create agentic user, apply customBlueprintPermissions
    A365-->>Op: agent published to Teams / M365 Copilot (tenant admin consent required)
```

## 2. Runtime turn — Teams user asks about the Sydney fibre cut

```mermaid
sequenceDiagram
    autonumber
    participant User as Teams user
    participant A365 as A365 host (host_agent_server.py)
    participant Agent as NocAgent (agent.py, MAF)
    participant TB as noc-iq-toolbox<br/>(ONE Foundry Toolbox MCP endpoint)
    participant FIQ as Foundry IQ connection
    participant FabIQ as Fabric IQ connection
    participant WebIQ as Web IQ connection
    participant WorkIQ as Work IQ connection

    User->>A365: "What's the blast radius of the SYD-MEL fibre cut?"
    A365->>A365: on_message handler, start typing indicator
    A365->>Agent: process_user_message(message, auth, auth_handler_name, context)
    Agent->>A365: auth.exchange_token(scopes=[ai.azure.com/.default], AGENTIC)
    A365-->>Agent: user OBO token
    Agent->>Agent: _build_turn_tool() — build ONE fresh MCPStreamableHTTPTool<br/>this turn, pointed at the noc-iq-toolbox MCP URL,<br/>with the user's OBO token injected as the Authorization header

    Agent->>Agent: agent.run(history, tools=[noc-iq-toolbox])
    Note over Agent,TB: Single Responses API call, ONE MCP tool exposed to the model.<br/>The toolbox — not the agent — fans out to whichever of the<br/>4 bundled IQ connections the model decides to invoke — there is<br/>no separate direct call per IQ surface and no hand-rolled<br/>sequencing/aggregation logic in agent.py.

    Agent->>TB: MCP initialize + tools/list (one HTTP connection, this turn)
    TB-->>Agent: 4 tool definitions advertised: foundry-iq, web-iq, fabric-iq, work-iq

    par Model decides which of the 4 to call, in whatever order/count it needs
        Agent->>TB: call tool "fabric-iq" — blast radius for LINK-SYD-MEL-FIBRE-01
        TB->>FabIQ: forwards call, Authorization: <OBO token> (UserEntraToken passthrough)
        FabIQ-->>TB: dependent services (VPN-ACME-CORP, VPN-BIGBANK), shared conduit (CONDUIT-SYD-MEL-INLAND)
        TB-->>Agent: tool result
    and
        Agent->>TB: call tool "foundry-iq" — fibre-cut runbook + SLA policy terms
        TB->>FIQ: forwards call (service-credentialed connection)
        FIQ-->>TB: runbook steps, SLA $/hr penalty terms
        TB-->>Agent: tool result
    and
        Agent->>TB: call tool "web-iq" — vendor/carrier advisory for the affected route
        TB->>WebIQ: forwards call, x-apikey (CustomKeys)
        WebIQ-->>TB: live advisory (if any)
        TB-->>Agent: tool result
    and
        Agent->>TB: call tool "work-iq" — on-call roster / bridge chatter
        TB->>WorkIQ: forwards call, Authorization: <OBO token> (UserEntraToken passthrough)
        WorkIQ-->>TB: on-call engineer, active bridge summary
        TB-->>Agent: tool result
    end

    Agent->>Agent: model synthesizes ONE response from whatever tool results<br/>came back over that single MCP connection — cite each source,<br/>in order: blast radius → SLA exposure → shared-conduit finding →<br/>runbook → advisory → on-call
    Agent-->>A365: response text
    A365-->>User: "Blast radius: VPN-ACME-CORP + VPN-BIGBANK ($75k/hr exposure)...<br/>⚠️ Non-obvious: FIBRE-02 shares CONDUIT-SYD-MEL-INLAND...<br/>Runbook: reroute via Brisbane... On-call: ..."
```

**Key point this diagram must make clear**: there is exactly **one** MCP tool
attached to the agent per turn (`noc-iq-toolbox`), and exactly **one**
`agent.run()` model call. The 4 IQ surfaces are connections *behind* that one
Toolbox, not 4 separate tools the agent code calls in sequence — the `par`
block above shows the model's own tool-selection deciding which (and how
many) of the 4 to invoke through that single MCP channel; nothing in
`agent.py` iterates over the 4 tools or aggregates their results itself.

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
