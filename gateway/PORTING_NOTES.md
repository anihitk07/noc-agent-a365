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
- APIM now defaults to **PremiumV2** instead of classic Developer. The Premium v2 Learn guidance says virtual network injection is available in the Premium v2 tier, uses API version `2024-05-01` or later, and provisions in minutes instead of the classic 45-70 minute VNet-injected Developer/Premium path. This keeps the gateway on the private-injection path the user asked for without the classic-tier wait.
- The jumpbox module was intentionally **not** ported. Cosmos seed data should be written later with either:
  - a one-off `az cosmosdb sql` CLI call, or
  - a one-off Container Apps Job run using the worker image.
  This repo already leans on azd + containerized jobs, so keeping jumpbox VM infrastructure out of the Bicep keeps Layer 1 smaller and closer to existing repo patterns.
- Monitoring resources were re-authored in one module instead of reusing the existing root-level `infra/core/monitor/*` modules because this stack also needs Cost Management budget wiring plus Log Analytics keys for the Container Apps environment.

## Known semantic gaps / follow-up checks

- `az bicep build` validates syntax and type-shape, not live regional capability. APIM VNet injection, Foundry model availability, and Container Apps environment behavior still need a deployment-time review.
- APIM runtime-owned named values (`allowed-models`, quotas, consumer bundle) are seeded here only with safe defaults. The app-layer config-sync worker will own updates later.
- The broad built-in roles from Terraform were preserved with the same rationale comments. Custom least-privilege roles are still a hardening follow-up, not part of Layer 1.

## APIM PremiumV2 networking note

- PremiumV2 VNet injection requires a **delegated** APIM subnet (`Microsoft.Web/hostingEnvironments`), a minimum **/27** subnet size (this stack already uses **/24**), and NSG outbound **443** rules to the `Storage` and `AzureKeyVault` service tags.
- The PremiumV2 Learn docs describe injection as the **private inbound + private outbound** path. If a future environment needs public inbound access again, use v2 **integration** instead of trying to recreate the old classic External/Developer behavior.

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
