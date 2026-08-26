# TokenOps gateway app port

Ported from `C:\Flutter\apim-foundry-governance\app\...` into `gateway/app`.

## Ported directly

- `config-sync-worker/`:
  - `sync.py`, `budget.py`, `requirements.txt`, `Dockerfile`
  - existing tests under `tests/` (`test_budget.py`, `test_bundle.py`, `test_usage.py`)
- `admin-ui/bff/`:
  - FastAPI BFF modules, auth/deps/config/APIM/Cosmos/metrics/job wiring
  - existing tests under `bff/tests/`
- `admin-ui/spa/`:
  - existing React SPA structure/pages/components
- `admin-ui/Dockerfile`, `admin-ui/.dockerignore`

## New pricing work

- Added `config-sync-worker/pricing.py`.
  - Fetches Azure Retail Prices API (`Foundry Models`) for a region.
  - Normalizes rates to **USD per 1K tokens**.
  - Explicitly accepts only `1K` and `1M` units and raises on anything else, so a meter-unit mismatch cannot silently poison budget math by 1000x.
  - Exposes a CLI entrypoint: `python pricing.py <region>`.
- Added `config-sync-worker/tests/test_pricing.py` for:
  - unit normalization
  - model extraction from fabricated retail-price fixtures
  - pagination handling
- Added `admin-ui/bff/models_pricing.py`.
  - Reads/writes the Cosmos `pricing` document.
  - Preserves manual overrides separately from Retail-API-derived source prices.
  - Produces preview diffs before save.
- Added BFF pricing endpoints:
  - `GET /api/pricing`
  - `POST /api/pricing/preview`
  - `POST /api/pricing/refresh`
  - `PUT /api/pricing`
- Updated SPA `Models` page to:
  - show current model pricing
  - edit per-model manual overrides
  - preview Retail Prices refresh diffs
  - apply refreshed pricing
- Added `gateway/app/.dockerignore` and adjusted `admin-ui/Dockerfile` to support building from the `gateway/app` context while also copying `config-sync-worker/pricing.py` into the BFF image.

## Validation

- Worker tests: `28 passed`
  - `python -m pytest gateway/app/config-sync-worker/tests`
- BFF tests: `114 passed`
  - `python -m pytest gateway/app/admin-ui/bff/tests`
- SPA build: `npm run build` passed
  - Vite emitted the existing large-chunk warning only; no TypeScript/build errors.

## Deferred / follow-up

- Pricing meter selection is intentionally locked to the currently shipped four model ids (`gpt-5.4`, `gpt-5.4-mini`, `grok-4.3`, `DeepSeek-V4-Pro`). If the gateway adds more models later, `config-sync-worker/pricing.py` needs another explicit rule entry.
- No live Azure seeding/deployment was attempted here. This change only ports app code + tests.
