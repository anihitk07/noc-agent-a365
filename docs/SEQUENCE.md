# Sequence Diagrams

## 1. End-to-end deployment sequence

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator (you)
    participant Az as Azure (az / azd)
    participant RG as New Resource Group
    participant Fab as Fabric (tenant)
    participant A365 as A365 CLI

    Op->>Az: az login / azd auth login (ME-M365CPI48286597-aganguly-1)
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
    Op->>Az: Portal — add Work IQ connection (UserEntraToken) + Foundry toolbox
    Op->>Az: azd deploy  (pushes agent/ to the App Service)

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
    participant FIQ as Foundry IQ (KB MCP)
    participant FabIQ as Fabric IQ (Data Agent MCP)
    participant WebIQ as Web IQ (web MCP)
    participant WorkIQ as Work IQ (FoundryToolbox)

    User->>A365: "What's the blast radius of the SYD-MEL fibre cut?"
    A365->>A365: on_message handler; start typing indicator
    A365->>Agent: process_user_message(message, auth, auth_handler_name, context)
    Agent->>A365: auth.exchange_token(scopes=[ai.azure.com/.default], AGENTIC)
    A365-->>Agent: user OBO token
    Agent->>Agent: build per-turn Fabric IQ + Work IQ tools from OBO token

    Agent->>Agent: agent.run(history, tools=[fabric_iq, work_iq_toolbox])
    Note over Agent: default tools (Foundry IQ, Web IQ) always available;<br/>per-turn tools merged for this call only

    Agent->>FabIQ: network-ontology tool call — blast radius for LINK-SYD-MEL-FIBRE-01
    FabIQ-->>Agent: dependent services (VPN-ACME-CORP, VPN-BIGBANK), shared conduit (CONDUIT-SYD-MEL-INLAND)
    Agent->>FIQ: knowledge-base tool call — fibre-cut runbook + SLA policy terms
    FIQ-->>Agent: runbook steps, SLA $/hr penalty terms
    Agent->>WebIQ: web-search tool call — vendor/carrier advisory for the affected route
    WebIQ-->>Agent: live advisory (if any)
    Agent->>WorkIQ: Microsoft 365 tool call — on-call roster / bridge chatter
    WorkIQ-->>Agent: on-call engineer, active bridge summary

    Agent->>Agent: synthesize response — cite each source, in order:<br/>blast radius → SLA exposure → shared-conduit finding → runbook → advisory → on-call
    Agent-->>A365: response text
    A365-->>User: "Blast radius: VPN-ACME-CORP + VPN-BIGBANK ($75k/hr exposure)...<br/>⚠️ Non-obvious: FIBRE-02 shares CONDUIT-SYD-MEL-INLAND...<br/>Runbook: reroute via Brisbane... On-call: ..."
```

## 3. The 5 narrative beats this sequence must produce

Ported from `PathfinderIQ-Demo-Version`'s hardened Sydney narrative
(`docs/SCENARIO_NARRATIVE.md`, capability C19). A correct end-to-end run must
surface all five, each traceable to a real tool call (verified via App
Insights traces in the `verify-e2e` step, not asserted from the model's
unaided knowledge):

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
