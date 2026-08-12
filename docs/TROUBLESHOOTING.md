# Troubleshooting

Known gotchas surfaced while researching and building this solution, recorded
here so `fix-loop` doesn't have to rediscover them.

## Auth-type mistakes (the #1 failure class)

| Symptom | Cause | Fix |
|---|---|---|
| Work IQ tool call loops on `oauth_consent_request` / never succeeds headless in Teams | Work IQ connection configured with `OAuth2` instead of `UserEntraToken` | Reconfigure the connection as `UserEntraToken`. `OAuth2` works in the Foundry *playground* (interactive browser) but cannot complete headless inside a Teams turn. |
| Work IQ call fails with `AADSTS82001` | Attempting app-only (client-credentials / Managed Identity) auth against Work IQ | Work IQ only accepts delegated (OBO) user tokens. There is no service-identity path — always forward the caller's token. |
| Fabric IQ / Work IQ returns another user's data, or nothing | Fabric/Work IQ tool built once at process start with a service credential instead of rebuilt per-turn with the caller's OBO token | See `agent/agent.py: NocAgent._build_turn_tools()` — these two tools must be constructed fresh per message from `auth.exchange_token(...)`. |
| `"Sorry, I encountered an error: MCP server failed to initialize: Cancelled via cancel scope ..."` | **Real root cause: the App Service managed identity had zero RBAC role assignments on the Azure AI Search service**, so the Foundry IQ knowledge-base MCP `initialize` call failed data-plane auth — the `mcp`/`anyio` client library mis-surfaces a 401/403 as a raw `anyio.CancelledError`-derived cancel-scope error instead of a clean HTTP error, which looked like a concurrency bug. (A retry-once safety net and a per-turn tool rebuild were tried first as reasonable hypotheses given the error text, and are kept as defensive measures, but neither was the actual fix.) | Grant `Search Index Data Reader` to the identity on the Search service — see `searchIndexDataReaderRole` in `infra/core/ai/rbac.bicep`. To isolate which of the 4 IQ tools is actually failing, read the full `exception.stacktrace` in the Application Insights span export and check `server.address` on the sibling `"initialize"` CLIENT span. |
| Web IQ configured with `UserEntraToken` fails for anonymous/service scenarios | Wrong auth type — Web IQ is public data and doesn't need identity | Use `CustomKeys` with an `x-apikey` header instead. |
| Agent answers fine but says it has no Fabric IQ / Work IQ / "live topology" / "M365 bridge" access, with only a WARNING (not an error) in the logs: `"No auth handler configured — Fabric IQ/Work IQ will be unavailable this turn"` | The `AUTH_HANDLER_NAME` app setting was never set on the App Service, so `host_agent_server.py`'s `self.auth_handler_name` stayed `None` and was never passed into `agent.py`; `_exchange_user_token()` silently returns `None` whenever `auth_handler_name` is falsy (by design — see its docstring), so `_build_turn_tools()` only builds Foundry IQ + Web IQ and skips Fabric IQ/Work IQ for that turn without raising any visible error. | Set `AUTH_HANDLER_NAME=AGENTIC` (must match the handler name in the `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__<name>__SETTINGS__*` settings written by `a365 setup all`) — now the default in `infra/main.bicep`. Verify via Application Insights `traces`: look for `"🔐 Using auth handler: AGENTIC"` at startup and the absence of the warning above on later turns. |

## MCP tool wiring gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Foundry IQ / Fabric IQ MCP tool fails during session init even though a `header_provider`/token exists | `MCPStreamableHTTPTool`'s auth was supplied late (e.g. via a callback) instead of attached to the `httpx.AsyncClient` at construction | Always construct `httpx.AsyncClient(auth=<httpx.Auth>)` before passing it into `MCPStreamableHTTPTool(http_client=...)`. |
| Fabric IQ MCP call returns a generic `500 Internal Server Error` | The `httpx.AsyncClient` defaulted to `follow_redirects=False`; Fabric's MCP endpoint routes through a redirect layer | Always set `follow_redirects=True` on the Fabric IQ HTTP client (already done in `agent/agent.py`). |
| A Work IQ `a2a_preview` consent requirement surfaces as a raw, unhandled `McpError` instead of a friendly message | MAF's built-in consent-URL extraction (`agent_framework_foundry_hosting._responses.consent_url_from_error`) only recognizes MCP-sourced consent errors, and only when the call goes through `ResponsesHostServer` — this agent calls `agent.run()` directly | `agent/agent.py: _extract_a2a_consent_url()` re-implements the same JSON parsing standalone; the caught `McpError` is converted into a "please consent at &lt;url&gt;" chat reply. |

## Fabric Data Agent / ontology gotchas

| Symptom | Cause | Fix |
|---|---|---|
| NL2GQL-generated query against the Graph source times out | The model wrote Cypher-style `WHERE` after `MATCH` | Fabric Graph GQL requires `FILTER`, not `WHERE`. Not applicable to this demo's Ontology-only source, but relevant if a Graph Model is ever added. |
| `ORDER BY` in a generated Ontology query references a column that doesn't exist | NL2GQL invented a different capitalization/alias than the one it projected in `RETURN` | Instruction-only fix — tell the Data Agent's ontology instructions to always preserve the exact `RETURN` alias (see `scripts/create_fabric_data_agent.py: ONTOLOGY_INSTRUCTIONS`). Few-shot examples are **not** supported for Ontology sources (only Graph sources), so this can't be fixed with examples. |
| `fabric-data-agent-sdk` install fails or throws `RuntimeError: Can not determine dotnet root` outside a notebook | The SDK pins conflicting `azure-identity`/`httpx` versions and relies on Semantic-Link workspace resolution that only works inside a Fabric notebook | Don't use the SDK. `scripts/create_fabric_data_agent.py` and `create_fabric_ontology.py` both call the raw Fabric REST API directly instead. |
| `UserNotLicensed` error creating the lakehouse | The signed-in Entra account has no Fabric/Power BI license | Assign a Fabric (or Power BI Pro/PPU) license to the account running the provisioning scripts. |

## Bicep gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `BCP139`/`BCP120` on `infra/main.bicep` | A subscription-scope Bicep file tried to declare a resource-group-scoped resource (e.g. a role assignment) directly | Wrap it in a `module` with `scope: rg` — see `infra/core/ai/rbac.bicep`. |
| Foundry Agents API calls fail with 403 even though RBAC roles are assigned | RBAC was granted at the Foundry **account** scope, not the **project** sub-resource | Scope Azure AI Developer (`64702f94-c441-49e6-a78b-ef80e0188fee`) and Cognitive Services User (`a97b65f3-24c7-4388-baec-2e87135dc908`) to `.../accounts/{account}/projects/{project}`, not just the account (`infra/core/ai/rbac.bicep`). |

## GitHub / tooling gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `gh repo clone microsoft/...` or GitHub MCP tools fail with `GraphQL: Resource protected by organization SAML enforcement` | The `microsoft` org enforces SAML SSO on the GitHub App token used by `gh`/MCP | Use a plain `git clone https://github.com/microsoft/<repo>.git` instead — works for public repos without hitting the SAML gate. |
