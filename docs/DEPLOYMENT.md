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

Work IQ has no dedicated SDK connection class, and the Foundry portal's
"Add connection" wizard defaults new Work IQ connections to `authType: OAuth2`
(interactive browser consent) — that works fine in the Foundry **playground**
but dead-ends in Teams/A365 (a non-interactive caller) with a repeating
`oauth_consent_request` loop, silently falling back to a hallucinated answer.

Use `scripts/create_workiq_toolbox.py` instead, which automates both steps
correctly:

```bash
cd scripts
python create_workiq_toolbox.py
```

This:

1. `PUT`s the Foundry project connection `WorkIQ` directly against ARM with
   `authType: UserEntraToken` (identity passthrough — Foundry forwards the
   caller's own Entra token via OBO and mints a Work IQ-scoped token; no
   client secret or Entra app registration required, unlike an OAuth2
   connection). Target `https://workiq.svc.cloud.microsoft/mcp`, audience
   `fdcc1f02-fc51-4226-8753-f668596af7f7` (`api://workiq.svc.cloud.microsoft`,
   scope `WorkIQAgent.Ask`).
2. Creates and promotes a toolbox version named `work-iq-tools` containing a
   `WorkIQPreviewToolboxTool` bound to that connection — this is the toolbox
   `agent/agent.py`'s `FoundryToolbox` targets via
   `{project_endpoint}/toolboxes/work-iq-tools/mcp?api-version=v1`.

The account-rp preview connections API is intermittently flaky and returns a
bare `500 InternalServerError`; the script retries with a short backoff and is
otherwise idempotent (re-running skips the connection PUT if it already has
the correct config).

`customBlueprintPermissions` in `a365.config.json` still needs the
`ea9ffc3e-8a23-4a7d-836d-234d7c7565c1` (Agent 365 Tools) app's
`McpServers.Mail.All`, `McpServers.Teams.All`, `McpServersMetadata.Read.All`
scopes — applied by `a365 setup all` (step 8), separate from the Foundry
connection above.

## 7. Push IQ endpoints to the App Service

Steps 3-6 print/`set_key()` into the local `.env` (`AZURE_AI_SEARCH_KNOWLEDGE_BASE_NAME`,
`FABRIC_DATA_AGENT_MCP_URL`, `WEB_IQ_MCP_ENDPOINT`, `WEB_IQ_API_KEY`,
`CUSTOM_FOUNDRY_WORKIQ_TOOLBOX_NAME`) but the **deployed** agent only reads
its own App Service application settings, not this file. Push them explicitly:

```bash
az webapp config appsettings set -g "rg-$AZURE_ENV_NAME" -n "<webAppName>" --settings \
  AZURE_AI_SEARCH_KNOWLEDGE_BASE_NAME=noc-knowledge-kb \
  FABRIC_DATA_AGENT_MCP_URL="$FABRIC_DATA_AGENT_MCP_URL" \
  WEB_IQ_MCP_ENDPOINT="https://api.microsoft.ai/v3/mcp" \
  WEB_IQ_API_KEY="$WEB_IQ_API_KEY" \
  CUSTOM_FOUNDRY_WORKIQ_TOOLBOX_NAME=work-iq-tools
```

## 8. Deploy the agent code

```bash
cd ..
azd deploy
```

Pushes `agent/` to the App Service created in step 2, running
`python start_with_generic_host.py`.

> **Managed identity detection.** `agent.py`'s `_get_service_credential()`
> uses `ManagedIdentityCredential` when the `WEBSITE_INSTANCE_ID` env var is
> present (always set by the App Service platform) and falls back to
> `AzureDeveloperCliCredential` otherwise (local dev, where `azd` is on PATH).
> If this check is ever changed to something not guaranteed to be set inside
> the container, every service-credential call fails at startup with
> `CredentialUnavailableError: Azure Developer CLI could not be found` — the
> container has no `azd` binary.

## 9. Publish to Teams / M365 Copilot (Agent 365)

```bash
cp a365.config.template.json a365.config.json   # gitignored — fill in real values
a365 setup all --aiteammate --m365 --agent-name <agent-name> \
  --messaging-endpoint "https://<webAppName>.azurewebsites.net/api/messages"
```

This mints the agentic teammate identity, registers the blueprint, applies
`customBlueprintPermissions` (tenant admin consent required), and registers
the messaging endpoint. In a headless/non-interactive shell (stdin
redirected), the browser-based admin-consent flow can't be detected, and the
CLI automatically falls back to granting delegated permissions
programmatically instead — confirm with `y` if prompted.

`a365 setup all` writes secrets into `a365.generated.config.json` and
`agent/.env` (both gitignored): `AGENT_ID`,
`CONNECTIONS__SERVICE_CONNECTION__SETTINGS__{CLIENTID,CLIENTSECRET,TENANTID,SCOPES}`,
and `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__*`.
Push these into the App Service's application settings the same way as step 7
(`az webapp config appsettings set --settings @<file>` with a JSON array of
`{name, value}` built from `agent/.env`), then restart the app
(`az webapp restart`) so the `microsoft_agents` SDK picks up real service
connection credentials instead of failing at startup with
`ValueError: No service connection configuration provided.`

**Also push `AUTH_HANDLER_NAME=AGENTIC`** in this same step (it is already the
default in `infra/main.bicep`, but re-applying app settings from a `.env` file
can overwrite it if that name is not included). Without it,
`host_agent_server.py`'s `self.auth_handler_name` stays `None`, so the agent
never attempts the OBO user-token exchange, and `_exchange_user_token()`
silently degrades every turn to Foundry IQ + Web IQ only, logging just
`" No auth handler configured — Fabric IQ/Work IQ will be unavailable this
turn"` (a WARNING, not an error, easy to miss). This is a distinct root cause
from the earlier "Cancelled via cancel scope" RBAC bug — that one broke
Foundry IQ outright; this one silently disables Fabric IQ/Work IQ while
Foundry IQ and Web IQ keep working, which is why the agent still returns a
plausible, well-cited answer that just quietly omits two of the four IQ
surfaces. Verify the fix by checking Application Insights `traces` for
`"🔐 Using auth handler: AGENTIC"` at startup and the absence of the "No auth
handler configured" warning on subsequent turns.

## 9b. Publish the Teams app package (manual, one-time, requires Global/Teams Admin)

`a365 publish --aiteammate` (already run) produces
`agent/manifest/manifest.zip` — a ready-to-upload custom Teams app package
(gitignored, since it contains tenant-specific IDs). Uploading it to the org
catalog via Microsoft Graph (`POST /appCatalogs/teamsApps`) was investigated
and found to be **not fully automatable**:

- A delegated token (e.g. via `az`/`azd`'s cached CLI login) needs the
  `AppCatalog.ReadWrite.All` scope, which Microsoft blocks for its own
  first-party CLI app registrations (`AADSTS65002: ... must be configured via
  preauthorization`) — granting tenant admin consent for that scope on the
  Azure CLI/azd app id does not work.
- An application-only (client-credentials) token with the
  `AppCatalog.ReadWrite.All` **application** permission granted directly via
  Graph still returns `403 Forbidden — User not authorized to perform this
  operation` for this endpoint, which appears to additionally require the
  calling identity to hold the **Teams Administrator** directory role — a
  role that cannot be cleanly assigned to a service principal for this
  legacy catalog endpoint.

**Do this instead (~30 seconds, one time) — use the dedicated Agents admin
surface, NOT the classic Teams app catalog:**

The manifest here uses the Agent 365 agentic schema (`manifestVersion:
devPreview` + `agenticUserTemplates`), which the classic **Teams apps → Manage
apps → Upload a custom app** page does not understand — uploading there fails
with a generic "We can't upload the app" error with no useful diagnostics.
Use the dedicated Agents surface instead:

1. Go to `https://admin.microsoft.com` → **Settings → Integrated apps →
   Agents** (or **Agents → All agents**, depending on tenant UI version).
2. Click **Upload custom agent** and upload `agent/manifest/manifest.zip`.
3. Complete the wizard to **create an instance** — this is the step that
   actually provisions the agentic teammate user
   (`nocagent@M365CPI48286597.onmicrosoft.com`) as a real M365 principal, not
   just a catalog entry. `a365 setup all` already created the blueprint and
   messaging endpoint; this step is what makes it installable/chattable in
   Teams.

## 9c. Grant the agentic user identity the Foundry Agent Consumer role

**Required — without this, every turn fails with a 403, not just a degraded
tool.** Building the per-turn `FoundryChatClient`/`Agent` with the calling
Teams user's own OBO token (so Fabric IQ/Work IQ's `UserEntraToken`
connections get real identity passthrough — see `docs/ARCHITECTURE.md`) means
that user's identity is now the one calling the Foundry Responses API
directly. That's a separate RBAC check from anything the app's own managed
identity holds on the Cognitive Services account: the caller needs the
`Foundry Agent Consumer` role **on the Foundry project**. Grant it to the
auto-provisioned agentic user identity (its object id appears in Application
Insights `traces` as `agentic_user_id`, once the human user has messaged the
agent at least once so the identity exists):

```bash
az role assignment create \
  --assignee-object-id <agentic_user_id> \
  --assignee-principal-type User \
  --role "Foundry Agent Consumer" \
  --scope <Foundry project ARM resource id>
```

This must be repeated for every new distinct human user of the agent (each
gets their own agentic user identity). RBAC propagation can take a couple of
minutes before the next turn succeeds. See `docs/TROUBLESHOOTING.md`'s
"Foundry project RBAC" entry for the full symptom/diagnosis.

## 10. Verify end-to-end

In Teams, message the agent and drive the Sydney fibre-cut scenario (see
`docs/SEQUENCE.md` §3 for the 5 narrative beats to confirm). Cross-check in
Application Insights (`Transaction search` / `Logs`) that all four IQ tools
were genuinely invoked for that conversation — not just cited from the
model's general knowledge. This step requires a real Teams client signed in
as a user the teammate app has been installed for — it cannot be simulated by
posting synthetic activities to `/api/messages` directly, since those lack a
valid Bot Framework JWT and a real `serviceUrl` to deliver the reply to.
**This is the one step in this whole deployment that genuinely cannot be
automated or delegated — it requires a human driving a real Teams client.**

## 11. Teardown (after E2E passes)

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

# 4. Remove the temporary automation service principal created during this
#    session to restore non-interactive `az` CLI access (Contributor scoped
#    only to the RG being deleted above): search Entra ID → App registrations
#    for "noc-iq-demo-temp-automation" and delete it, or:
az ad app delete --id "16af29e6-541c-4103-9913-640204d32e98"
```

## Cost note

The Fabric **F2** capacity is billable (~US$0.36/hr, ~US$260/mo if left
running). Pause it (Fabric admin portal → Capacity settings → Pause) whenever
not actively demoing, and delete it with the resource group at teardown
(step 11.3).
