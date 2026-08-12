# PathfinderIQ — CURRENT_STATE

Single source of truth for current capability state. Ledger rows over prose.
Lineage: GridIQ → vm_agent → PathfinderIQ. Modernized 2026-06-19 to consume the
**agentkit** kernel and a **Cosmos-DB-only** data backend (Fabric retired).

Live target: `ca-pfiq-<suffix>` Container App, RG `rg-pathfinderiq-demo`
(eastus2), sub `67255afe-…`. Model: Foundry `gpt-5.4` (`aif-1-personal`,
`personal-llm` RG) via managed identity.

## Capability register

| ID | Capability | State | Canonical check | Notes |
|---|---|---|---|---|
| C1 | agentkit kernel vendored | GREEN | `import agentkit` under `app/backend/` | Domain-blind; adapters + contracts consumed by tools |
| C2 | Graph tool on Cosmos Gremlin | GREEN(local) | `query_graph('g.V().limit(1)')` | agentkit `GremlinToolAdapter`; MI auth; read-only guard + limit inject |
| C3 | Telemetry tool on Cosmos NoSQL | GREEN(local) | `query_telemetry`/`query_alerts` | NEW agentkit `CosmosNoSqlToolAdapter`; `{columns,rows}` envelope |
| C4 | Cosmos data seeded | GREEN | `g.V().count()` / `SELECT VALUE COUNT(1)` | Seeder `graph_data/scripts/seed_cosmos.py` from telecom CSVs |
| C5 | GPT-5.4 agent runtime | GREEN | live chat round-trip on deployed app | `AzureAIAgentClient` → `proj-default`, deployment `gpt-5.4`; verified 2026-06-19 (5 tool calls, 0 errors) |
| C6 | Config discipline (Cosmos via settings) | GREEN | `foundation/config.py` Cosmos fields | Tools read `settings.*`, not scattered getenv |
| C7 | Container App deploy | GREEN | `/health/ready` 200 + live URL | data tools live; AI Search live; live agent verified |
| C8 | Evidence ledger + AUTODEV | GREEN | this file + `AUTODEV.md` | lineage-aligned docs added |
| C9 | AI Search knowledge retrieval | GREEN | KnowledgeAnalyst `search_runbooks` live | Azure AI Search `srch-pfiq-*`; 4 indexes (hybrid vector+semantic, server-side embed); 0 error envelopes; runbook citation verified 2026-06-19 |
| C10 | Entra auth (AUTH_ENABLED=true) | GREEN | unauth `/api/sessions`→401 | app reg `2640ff33…`; `/api/auth_setup`→useLogin:true; SPA redirect + `access_as_user` |
| C11 | Capability fabric (discovery) | GREEN | `/api/catalog/search` + `find_capabilities` | 22 entries; ranked search verified; ported from vm_agent `catalog` |
| C12 | agentkit-ui adoption (build) | GREEN(bounded) | `npm run build` green w/ `@agentkit-ui/*` | kit vendored+aliased+type-checked+bundled+runtime seam; full component migration remains |
| C13 | Ed25519 dev-sign side-channel | GREEN | signed `/api/chat` under AUTH_ENABLED=true | agentkit `install_signed_request_auth` mounted when `DEV_PUBLIC_KEY_ED25519` set; `auth.py` honours `devauth_user` scope |
| C14 | SSE contract probe | GREEN | `scripts/sse_contract_probe.py` exit 0 | asserts 1 terminal frame, id-paired tool calls, known vocab, byte cap; signs via dev-sign |
| C15 | Capability fabric multi-kind | GREEN | `/api/catalog?kind=skill\|recipe` | agents+tools+**skills**(.skill.md)+**recipes**(.recipe.yaml) discovered + ranked |
| C16 | Deploy guardrails | GREEN | `deploy_app.sh` preflight + auth-gate | refuses AUTH=false / wildcard CORS; auto-disables ingress if unauth `/api/sessions`≠401 |
| C17 | Dead-Fabric removal (housekeeping) | GREEN | golden path held post-removal | 7 Fabric data-plane files removed (−1,230 LOC); `_registry` rewired to `cosmos_gremlin`; graph+telemetry verified live |
| C18 | Runtime scenario swap (modular use-case packs) | GREEN | `scripts/scenario_swap_probe.py` → `SWAP_PROBE_OK` (live) + O-RAN 3-surface probe (live) | `X-Scenario-Name` header → 3-tier resolve (header→user-pref→env); `/api/scenarios` catalog + `/api/scenarios/select` + `/api/preferences`; frontend `ScenarioSwitcher`; 2nd pack `demo-sandbox` (cloud-free) proves agents/prompts/tools/topology rebind over constant core. **P2**: per-scenario Cosmos bindings (`RequestScope.cosmos_*_config` → `tools/_cosmos.py` resolvers, fallback `settings.*`); bounded per-scenario scope cache. **Live-verified 2026-06-20** on `ca-pfiq-336705e3` (image `…-swap`): catalog+metadata+agents rebind, sandbox tool live chat, telecom SSE contract held (2 graph tool calls). **3rd pack `oran-5g-ran` (real-domain, all 3 cloud surfaces) live 2026-06-21** (image `…-oran`): own Cosmos `oran` namespace (Gremlin graph 261v/534e + NoSQL telemetry 3600 KPM/45 alarms) + 4 AI Search indexes; `RANInvestigator` drove `query_graph`+`query_telemetry`+`query_alerts`, `KnowledgeAnalyst` drove `search_runbooks`+`search_tickets`+`search_infra_specs` — all green. Seeding generalized: `seed_cosmos.py --schema-driven` reads pack `graph_schema.yaml` (vertices+edges) + `telemetry_schema.yaml` (CSV→container) so new datasets drop in without code edits. |
| C19 | Eval harness (generic) + Sydney narrative hardening | GREEN | `scripts/check_narrative_consistency.py` → `NARRATIVE_CONSISTENT`; live orchestrator **5/5 narrative beats** | GridIQ-lineage eval runner `graph_data/eval/run_eval.py` retained as generic tooling. **O-RAN pack + its battery/generators removed 2026-06-21** — focus consolidated on the single synthetic Sydney fibre-cut story (catalog = `telecom-playground-v2` + `demo-sandbox`); Cosmos `oran` db + `oran-*` indexes left (cost-only). **Sydney narrative hardened for C-suite:** orchestrator synthesis now mandates explicit `$/hr` SLA exposure (`$75,000/hr = ACME GOLD $50k + BigBank SILVER $25k`), a bounded-blast-radius exclusion (OzMine GOLD $40k unaffected), and an elevated "Non-Obvious Finding" (FIBRE-02 shares `CONDUIT-SYD-MEL-INLAND` → fake redundancy → reroute via Brisbane). Data⊨story guardrail re-derives blast radius+$ from CSVs. Live image `…-syd-narrative`; baseline 3/5 → **5/5** post-deploy. **Demo polish (live):** EN scripted replay synthesis aligned to the hardened agent (adds OzMine bounded-blast-radius exclusion + the truly-diverse Brisbane path); graph **"Incident Focus"** toggle highlights the 14-node fibre-cut blast radius (amber halo + dim rest) via `topology.json` `_incident` flags, default-OFF so the standard view is unchanged (images `…-syd-replay`, `…-syd-graph`). Deferred: JA/ZH replay re-translation; extend highlight to the map view. |

State key: GREEN=verified; AMBER=in-progress/awaiting live proof; RED=deferred/broken.

## Live verification (2026-06-19)

NetworkInvestigator on GPT-5.4 investigated `LINK-SYD-MEL-FIBRE-01` end-to-end:
5 tool calls (`query_graph` Gremlin + `query_telemetry`/`query_alerts` Cosmos SQL),
**0 error envelopes**, correct diagnosis — fibre cut between CORE-SYD-01↔CORE-MEL-01,
blast radius VPN-ACME-CORP + VPN-BIGBANK, CRITICAL FIBRE_CUT + HIGH_BER, dead-link
metrics (0% util / -35 dBm / 9999 ms). Foundry Agents API required **project-scope**
RBAC (Azure AI Developer + Cognitive Services User on `…/projects/proj-default`),
not just account scope — see AUTODEV L9.

## Deferred (RED — human-gated)

| ID | Item | Why deferred |
|---|---|---|
| D1 | Deep agentkit runtime swap (`agentkit.core`/`run_engine` replacing `agents/_builder` + `services/llm/agent` MAF loop; MAF rc1→rc4) | Requires reconciling PathfinderIQ's scenario-driven config + `{…_backend_prompt}` placeholder assembly + per-agent UI metadata with `agentkit.core`'s config model, AND remapping the SSE event contract, AND the rc1→rc4 SDK bump (PathfinderIQ pins rc1 + azure-ai-agents/projects). High blast radius on the shared live deploy; needs a live regression loop. Substantial agentkit adoption already shipped (vendored kernel + 2 live datasource adapters + error-envelope contract + capability fabric). |
| D2-full | Full UI component migration onto agentkit-ui | Kit is vendored/aliased/type-checked/bundled + a runtime adoption seam is live (C12); swapping every chat component (message list, input, tool cards) onto `@agentkit-ui/chat` is incremental UI work + visual regression. |

## Performed deferrals (2026-06-19 pass)

- **D3 → C10** Entra auth enabled + gate verified.
- **D4 → C9** Azure AI Search provisioned, 4 indexes populated + indexed, live agent citation verified.
- **D5 → C11** Capability fabric (catalog search + `find_capabilities` + `/api/catalog`) ported from vm_agent, live.
- **D2 → C12** agentkit-ui vendored + aliased + built (bounded adoption).
- **D1** Reasoned-deferred (see above) — runtime kept on proven MAF path to protect the shared deploy.

## Lineage deviations (vs GridIQ/vm_agent gates)

- AUTH_ENABLED=false on the live demo (both lineage apps enforce true).
- No live signed-probe regression protocol bound yet; verification is golden-path chat + data-tool round-trips.
- Telemetry backend is Cosmos NoSQL (not Kusto/Eventhouse) by explicit design — `CosmosNoSqlToolAdapter` is the Cosmos-native analogue of GridIQ's `KqlToolAdapter`.

## Data model (Cosmos)

- **Graph** (Gremlin acct `cosmos-pfiq-graph-*`, db `pfiq`, graph `topology`, pk `/pk`): one vertex per `Dim*` row (label=type, id=natural key); edges from `Fact*` + FK columns. Edge labels: `connects_source/connects_target/uplinks_to/backhauls_via/monitors/peers/governs/services/stationed_at/depends_on/traverses/amplifies/routed_through/affects`.
- **Telemetry** (NoSQL acct `cosmos-pfiq-sql-*`, db `pfiq`): `alerts` (pk `/SourceNodeId`) = AlertStream; `telemetry` (pk `/entityId`) = LinkTelemetry + SensorReadings merged with `kind` ∈ {link,sensor}.
- **Sessions** (same NoSQL acct, db `sessions`, container `conversations`, pk `/session_id`).
