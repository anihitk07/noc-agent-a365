# TokenOps gateway Layer 1 Bicep port

Ported from `C:\Flutter\apim-foundry-governance` into `gateway/infra` as a standalone subscription-scope Bicep stack.

## What ported directly

- Root orchestration pattern: subscription-scope resource-group creation, deterministic `resourceToken`, teardown tags, and resource-per-module layout.
- Network layout: VNet, APIM subnet, private-endpoint subnet, Container Apps delegated subnet, APIM NSG, and the private DNS zones used by Key Vault, Cosmos DB, OpenAI, Cognitive Services, and AI Services.
- Core services: APIM, Azure OpenAI, Azure AI Services / Foundry, Cosmos DB SQL API, Key Vault, ACR, Log Analytics, Application Insights, budgets, user-assigned identities, and Container Apps host resources.
- APIM policy logic: consumer bundle lookup, allowed-model enforcement, named-value-driven rate tiers, managed-identity backend auth, and cross-backend downgrade rewrites between Azure OpenAI and Foundry.

## Adaptations in this port

- Terraform `map(object(...))` inputs became Bicep arrays-of-objects where that keeps loops and parameter files simpler.
- Terraform `templatefile()` policy rendering became `loadTextContent()` + `replace()` in `core/apim/apim.bicep` because Bicep has no native text template engine.
- Terraform `count` / `for_each` became Bicep `if (...)` and resource loops.
- The jumpbox module was intentionally **not** ported. Cosmos seed data should be written later with either:
  - a one-off `az cosmosdb sql` CLI call, or
  - a one-off Container Apps Job run using the worker image.
  This repo already leans on azd + containerized jobs, so keeping jumpbox VM infrastructure out of the Bicep keeps Layer 1 smaller and closer to existing repo patterns.
- Monitoring resources were re-authored in one module instead of reusing the existing root-level `infra/core/monitor/*` modules because this stack also needs Cost Management budget wiring plus Log Analytics keys for the Container Apps environment.

## Known semantic gaps / follow-up checks

- `az bicep build` validates syntax and type-shape, not live regional capability. APIM VNet injection, Foundry model availability, and Container Apps environment behavior still need a deployment-time review.
- APIM runtime-owned named values (`allowed-models`, quotas, consumer bundle) are seeded here only with safe defaults. The app-layer config-sync worker will own updates later.
- The broad built-in roles from Terraform were preserved with the same rationale comments. Custom least-privilege roles are still a hardening follow-up, not part of Layer 1.

## How to deploy later

- Raw ARM/Bicep flow:
  - `az deployment sub create --location <region> --template-file gateway\infra\main.bicep --parameters @gateway\infra\main.parameters.json`
- Natural azd fit for a later step:
  - create a second azd environment (for example `noc-iq-gateway`)
  - point that environment's infra path at `gateway/infra`
  - keep it separate from the existing app-host stack instead of reusing `infra/main.bicep`

## Deferred to the next phase

- app code port for the config-sync worker image
- app code port for the admin UI / BFF image
- deploy-time review, secrets/bootstrap, and live Azure validation
