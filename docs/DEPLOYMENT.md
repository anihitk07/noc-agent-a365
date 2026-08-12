# Deployment Guide

Reproducible, exact steps to deploy `noc-agent-a365` into a **brand-new**
resource group in a target Azure subscription, wire all four IQ surfaces, and
publish to Teams / M365 Copilot via Agent 365 (A365). Every resource is new —
nothing is reused from any other deployment.

Prerequisites: `az` (Azure CLI), `azd` (Azure Developer CLI), `a365` (Agent
365 CLI), Python 3.11+, and Git Bash (for the `.sh` helper scripts below —
run these from **Git Bash on Windows**, not PowerShell/cmd).

## 0. Configuration

```bash
export AZURE_SUBSCRIPTION_ID="<your-subscription-id>"      # e.g. ME-M365CPI48286597-aganguly-1
export AZURE_LOCATION="eastus2"
export AZURE_ENV_NAME="noc-iq-demo"
export WEB_IQ_API_KEY="<your Web IQ x-apikey value>"        # never commit this
```

## 1. Sign in

```bash
az login --tenant "<your-tenant-id>"
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
azd auth login
```

## 2. Provision infrastructure (`azd up`)

```bash
cd noc-agent-a365
azd env new "$AZURE_ENV_NAME"
azd env set AZURE_LOCATION "$AZURE_LOCATION"
azd env set AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
azd env set webIqApiKey "$WEB_IQ_API_KEY"
azd up
```

This creates, in a new resource group (`rg-<AZURE_ENV_NAME>` by default):

- AI Foundry account + project with `gpt-5.4` + `text-embedding-3-small`
  deployments
- Azure AI Search, Storage account, Application Insights + Log Analytics
- Fabric capacity (F2 SKU — billable, see `README.md` cost note)
- Linux App Service (B1) for the agent host, with project-scope RBAC on its
  managed identity
- A Web IQ `CustomKeys` connection (only if `webIqApiKey` was set)

Capture the outputs — `azd env get-values` prints them all, including
`AZURE_AI_PROJECT_ENDPOINT`, the Search endpoint, and the agent host name.

## 3. Foundry IQ — build the knowledge base

```bash
cd scripts
pip install -r requirements.txt
python create_foundry_iq_kb.py
```

Populates `noc-knowledge-kb` from `data/{runbooks,tickets,equipment_specs,infra_specs}`
and prints the KB MCP endpoint (`{search}/knowledgebases/noc-knowledge-kb/mcp?api-version=...`).

## 4. Fabric IQ — ontology + Data Agent

Requires the signed-in account to have a Fabric/Power BI license and be an
admin (or Contributor) on the target capacity.

```bash
python create_fabric_ontology.py
python create_fabric_data_agent.py
```

The first script creates a Fabric workspace on the F2 capacity, a lakehouse,
loads every `data/ontology_entities/*.csv` as a Delta table, and builds the
`NOCNetworkOntology` ontology. The second publishes a Fabric Data Agent over
that ontology and prints `FABRIC_DATA_AGENT_MCP_URL`.

> **Note — Fabric workspace lifetime.** The workspace is a Fabric-tenant
> object, not an ARM resource in the resource group. It must be deleted
> separately at teardown (§7) or it will orphan after `az group delete`.

## 5. Web IQ

If `webIqApiKey` was set in step 2, the connection already exists — skip this
step. Otherwise, add it manually in the Foundry portal: **Tools → + Add tool
→ Custom MCP**, auth type `CustomKeys`, header `x-apikey`, target
`https://api.microsoft.ai/v3/mcp`.

## 6. Work IQ

Work IQ has no ARM/Bicep surface — configure it in the Foundry portal:

1. In the Foundry project, **Connections → + New connection → Custom**.
2. `authType`: **`UserEntraToken`** (not `OAuth2` — OAuth2 works in the
   playground but dead-ends in Teams with an `oauth_consent_request` loop).
3. Target: the project's toolbox MCP endpoint
   (`{project_endpoint}/toolboxes/work-iq-tools/mcp?api-version=v1`).
4. Grant the connection the `ea9ffc3e-8a23-4a7d-836d-234d7c7565c1` (Agent 365
   Tools) app's `McpServers.Mail.All`, `McpServers.Teams.All`,
   `McpServersMetadata.Read.All` scopes — these are also declared in
   `a365.config.template.json`'s `customBlueprintPermissions` and get applied
   when `a365 setup all` runs (step 8).

## 7. Deploy the agent code

```bash
cd ..
azd deploy
```

Pushes `agent/` to the App Service created in step 2, running
`python start_with_generic_host.py`.

## 8. Publish to Teams / M365 Copilot (Agent 365)

```bash
cp a365.config.template.json a365.config.json   # gitignored — fill in real values
a365 setup all
```

This mints the agentic teammate identity, registers the blueprint, applies
`customBlueprintPermissions` (tenant admin consent required), and publishes
the Teams app manifest. `a365 setup all` writes secrets into
`a365.generated.config.json` and `agent/.env` (both gitignored) — copy the
`AGENT365OBSERVABILITY__*` and `AUTH_HANDLER_NAME`/`AGENTAPPLICATION__*`
values from there into the App Service's application settings (or re-run
`azd deploy` after updating `agent/.env` if using local env sync).

## 9. Verify end-to-end

In Teams, message the agent and drive the Sydney fibre-cut scenario (see
`docs/SEQUENCE.md` §3 for the 5 narrative beats to confirm). Cross-check in
Application Insights (`Transaction search` / `Logs`) that all four IQ tools
were genuinely invoked for that conversation — not just cited from the
model's general knowledge.

## 10. Teardown (after E2E passes)

**Confirm the resource group name explicitly before deleting — this is
destructive and irreversible.**

```bash
# 1. Delete the Fabric workspace (tenant object, not part of the RG)
#    Fabric portal → workspace settings → Remove this workspace
#    or: az rest --method delete --url "https://api.fabric.microsoft.com/v1/workspaces/$FABRIC_WORKSPACE_ID"

# 2. Decommission the A365 teammate account
a365 teardown   # or remove the agentic user + blueprint via the M365 admin center

# 3. Delete the resource group (removes the Fabric F2 capacity, App Service,
#    Foundry account/project, Search, Storage, App Insights -- everything)
az group show --name "rg-$AZURE_ENV_NAME"   # confirm this is the right RG
az group delete --name "rg-$AZURE_ENV_NAME" --yes --no-wait
```

## Cost note

The Fabric **F2** capacity is billable (~US$0.36/hr, ~US$260/mo if left
running). Pause it (Fabric admin portal → Capacity settings → Pause) whenever
not actively demoing, and delete it with the resource group at teardown
(step 10.3).
