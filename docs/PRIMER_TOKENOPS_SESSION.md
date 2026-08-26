# Primer: TokenOps governance gateway — session status (2026-08-25)

Branch: `feat/tokenops-gateway`. Deployed to `rg-noc-iq-demo`. Latest commit
pushed: `59b52af`.

## What this branch is

An APIM AI Gateway in front of Foundry, porting
`microsoft/apim-foundry-governance` (Terraform → Bicep), adding run-scoped
cost governance. Three components:

1. **Admin UI** (`ca-adminui-aigw-dev-eus2`) — FastAPI BFF + SPA, lets admins
   set throttling / max token limits, written to Cosmos.
2. **`config-sync-worker`** (Container App Job, `job-config-sync-aigw-dev-eus2`)
   — reads Cosmos config, evaluates usage vs. budget, pushes downgrades and
   the 4 allowed-model/quota named values into APIM. Also now refreshes
   real model pricing from the Azure Retail Prices API into Cosmos.
3. **CLI scripts** (`check_usage.py`, `check_usage_detail.py`, both under
   `gateway/app/config-sync-worker/`) — the actual way to see token
   usage/cost today, since the Admin UI is not publicly reachable (see
   below). Query Log Analytics/AppMetrics for usage, join against the
   Cosmos `pricing` doc for $ cost.

## Concepts / mental model

- **Cosmos `gateway/config` container** is the single source of truth:
  `id=global` (default quotas/allowed models), per-consumer docs, and
  `id=pricing` (per-model $/token, refreshed by the worker from Retail
  Prices API).
- **APIM named values** are the runtime-enforced mirror of that Cosmos
  config — the worker pushes to them; APIM policies read them at request
  time. Cosmos is desired-state, named values are enforced-state.
- **Cost = usage (from telemetry) × price (from the `pricing` doc)**. Before
  this session neither the `global` doc nor the `pricing` doc existed, so
  every cost figure was `$0` — not a bug in the display logic, just missing
  upstream data.
- **Cosmos is private-endpoint-only** (`publicNetworkAccess: Disabled`),
  enforced by an org-level Azure Policy that silently reverts any attempt to
  re-enable it (confirmed live this session — do not try again). This means
  any "seed missing Cosmos doc" fix must be done by code running *inside*
  the VNet (the worker job self-bootstrapping on first run), never from a
  laptop.
- **`az acr build` / `az containerapp job execution show` reliably crash
  the Windows CLI** on log streaming (`UnicodeEncodeError`/BOM bug) even
  when the underlying operation succeeds — always verify via a side-channel
  command (`az acr task list-runs`, `--query status`) instead of trusting
  the crash.
- **Container Apps Jobs pull `:latest` fresh every `job start`** — no
  revision-suffix dance needed (unlike the long-running Admin UI Container
  App, which does need `--revision-suffix` to pick up a same-tag image).

## Work done this session

1. Root-caused `check_usage.py`/`check_usage_detail.py` showing `$0.00`
   cost: the `global` and `pricing` Cosmos docs never existed.
2. Made `sync.py` self-bootstrap a `DEFAULT_GLOBAL_CONFIG` doc on
   `CosmosResourceNotFoundError` instead of crashing the job.
3. Discovered `pricing.py` was **already fully built and tested**
   (Retail Prices API fetcher, per-model meter regex matching, unit-of-
   measure normalization with a hard fail on unrecognized units) but was
   dead code — never imported by `sync.py`, and not even `COPY`'d into the
   Docker image.
4. Wired it in: `sync.py` now calls `sync_pricing(container)` every cycle
   (fail-safe — never fails the job on pricing-fetch error); fixed the
   `Dockerfile`'s `COPY` list to include `pricing.py`.
5. Fixed `check_usage.py`'s pricing lookup to degrade to `$0` gracefully
   on any Cosmos read error (matching `check_usage_detail.py`'s existing
   pattern), instead of crashing outright.
6. Verified live via 4 job runs: worker now bootstraps `global`, syncs all
   4 named values to APIM, and logs `"synced pricing for 4 model(s) from
   Retail Prices API (region=eastus2)"` — real meter matches were found for
   all 4 demo models (`gpt-5.4`, `gpt-5.4-mini`, `grok-4.3`,
   `DeepSeek-V4-Pro`).
7. Investigated the Admin UI's public unreachability
   (`ca-adminui-aigw-dev-eus2...azurecontainerapps.io`) — found this is a
   **systemic APIM → internal-Container-Apps networking gap**, not
   Admin-UI-specific: the pre-existing `run-ledger-gateway` API hits the
   identical ACA "app not found" 404 through APIM with a valid subscription
   key. DNS, NSGs, subscription-key auth, propagation delay, and
   `rewrite-uri` have all been ruled out as causes. Root cause still
   unknown. Paused per user decision — CLI scripts are the interim
   workaround.
8. Cleaned local `__pycache__` dirs (already gitignored, removed from disk
   anyway per standing "no venv/temp/node_modules leftover" instruction).
9. Committed and pushed all 8 modified files to `feat/tokenops-gateway`
   (commit `59b52af`), with a full write-up appended to
   `docs/TROUBLESHOOTING.md`.

## Files touched (all committed)

- `gateway/app/config-sync-worker/sync.py` — global-doc bootstrap +
  `sync_pricing()` wiring.
- `gateway/app/config-sync-worker/pricing.py` — unchanged, now load-bearing.
- `gateway/app/config-sync-worker/Dockerfile` — ships `pricing.py`.
- `gateway/app/config-sync-worker/check_usage.py` — fail-safe pricing read.
- `gateway/app/admin-ui/bff/main.py` — managed-identity client-id fix.
- `gateway/infra/core/host/container-apps.bicep` — env vars + port fix.
- `gateway/infra/core/apim/apim.bicep`, `gateway/infra/main.bicep` —
  admin-ui-gateway API IaC (still stale vs. live CLI-patched config).
- `docs/TROUBLESHOOTING.md` — full bug-chain log.

## Not yet done / next steps

1. **Generate a real Teams turn and re-run `check_usage.py` /
   `check_usage_detail.py`** — confirm non-zero $ cost renders end-to-end
   with real token data. Not yet done this session (test windows queried
   had no traffic).
2. **Optionally verify the `pricing` Cosmos doc's actual per-model rates**
   from inside the VNet — so far only the worker's log line ("synced
   pricing for 4 model(s)") has been confirmed, not the numbers themselves.
3. **APIM → internal-ACA networking gap** — still unresolved, blocks public
   Admin UI access and affects `run-ledger-gateway` too. Needs a fresh
   investigation angle (VNet integration mode, APIM subnet NSG/route table,
   or Container Apps ingress config) before resuming the Admin UI work.
4. **Reconcile `apim.bicep`/`main.bicep` with live state** — the
   admin-ui-gateway API definition in Bicep is stale versus what was
   CLI-patched live (per-verb operations, Host-header override, root-path
   rewrite-uri fix). Should be re-exported from live APIM once the
   networking gap above is fixed, so IaC stops drifting from reality.
5. **Broader plan context**: this branch is "Branch B" of a two-branch plan
   (see chat history / `plan.md` if present) — Branch A
   (`feat/foundry-multi-agent`, splitting the single MAF agent into 4
   Foundry Prompt Agents) is a separate, not-yet-started branch, planned
   but with zero code written.

## Standing user preferences (apply across this session)

- Log all troubleshooting/fixes in `docs/TROUBLESHOOTING.md` as they happen.
- Keep local working tree free of `venv`/`node_modules`/temp build
  artifacts.
- Keep the remote (`origin/feat/tokenops-gateway`) in sync — commit and
  push after each meaningful fix, don't let changes sit local-only.
- Never attempt to re-enable Cosmos `publicNetworkAccess` — blocked by
  root-level Azure Policy; always seed/read Cosmos from inside the VNet.
