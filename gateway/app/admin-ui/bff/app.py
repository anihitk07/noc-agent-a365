"""FastAPI app factory. Dependencies are injected via AppDeps so the app is testable with fakes.
Routes:
  GET    /api/config   anonymous   -> MSAL config for the SPA
  GET    /api/me       auth        -> current principal (name + is_admin)
  GET    /api/keys     admin       -> list APIM subscriptions (joined with consumer mapping)
  POST   /api/keys     admin       -> issue an APIM subscription (returns primary key ONCE)
  DELETE /api/keys/{id} admin      -> revoke an APIM subscription
  GET    /healthz      anonymous
  GET    /api/consumers          admin  -> distinct consumers + key counts
  GET    /api/consumers/{consumer}/config  admin -> consumer config (or global fallback, isDefault)
  PUT    /api/consumers/{consumer}/config  admin -> upsert consumer config (merge; 400 on invalid)
  GET    /api/pricing             admin  -> current pricing doc
  POST   /api/pricing/preview     admin  -> fetch Retail Prices preview + diff
  POST   /api/pricing/refresh     admin  -> fetch Retail Prices and upsert pricing doc
  PUT    /api/pricing             admin  -> save manual overrides onto the current pricing doc
  GET    /{full_path}  anonymous   -> serve the built SPA (index.html fallback)
"""
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bff.apim import ApimKeys
from bff.auth import Principal
from bff.config import Settings
from bff.consumerconfig import ConsumerConfigStore
from bff.consumerregistry import ConsumerRegistryStore
from bff.cost import cost_usd
from bff.deps import current_principal, require_admin
from bff.metrics import MetricsQuery, RANGES
from bff.models_pricing import PricingStore, apply_overrides, default_region, preview_refresh, save_doc
from bff.runs import RunsQuery
from bff.store import MappingStore


def _consumer_config_response(consumer: str, doc: dict, *, is_default: bool,
                              default_models: list | None = None,
                              usage_usd: float | None = None, pct: float | None = None) -> dict:
    return {
        "consumer": consumer,
        "isDefault": is_default,
        "allowed_models": doc.get("allowed_models") or list(default_models or []),
        "tier": doc.get("tier"),
        "daily_budget": doc.get("daily_budget"),
        "daily_budget_usd": doc.get("daily_budget_usd"),
        "downgrade_ladder": doc.get("downgrade_ladder", []),
        "usage_usd": usage_usd,
        "pct": pct,
        "active_downgrade": doc.get("active_downgrade"),
    }


def _translate_by_consumer(data: dict, group_to_consumer: dict) -> dict:
    rows = data.get("by_consumer")
    if isinstance(rows, list):
        for r in rows:
            g = r.get("consumer")
            if g in group_to_consumer:
                r["consumer"] = group_to_consumer[g]
    return data


@dataclass
class AppDeps:
    settings: Settings
    apim: ApimKeys
    store: MappingStore
    spa_dir: Optional[Path]
    consumerconfig: ConsumerConfigStore
    metrics: MetricsQuery
    consumerregistry: ConsumerRegistryStore
    pricing: PricingStore
    model_prices: dict = field(default_factory=dict)
    job_starter: object = None
    runs: RunsQuery | None = None


class CreateKeyRequest(BaseModel):
    consumer: str


class ConsumerConfigRequest(BaseModel):
    allowed_models: list[str] | None = None
    tier: str | None = None
    daily_budget: int | None = None
    daily_budget_usd: float | None = None
    downgrade_ladder: list[str] | None = None


class ConsumerRegistryRequest(BaseModel):
    consumer: str | None = None
    entra_group_id: str | None = None
    display_name: str | None = None
    description: str | None = None


class PriceOverrideRequest(BaseModel):
    prompt: float | None = None
    completion: float | None = None


class PricingRequest(BaseModel):
    region: str | None = None
    overrides: dict[str, PriceOverrideRequest | None] | None = None

def _pricing_overrides(body: PricingRequest) -> dict:
    return {model: rate.model_dump(exclude_none=True) for model, rate in (body.overrides or {}).items() if rate is not None}


def app_factory(deps: AppDeps) -> FastAPI:
    app = FastAPI(title="AI Gateway Admin BFF")
    s = deps.settings

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {
            "tenantId": s.entra_tenant_id,
            "clientId": s.spa_client_id,
            "apiScope": f"{s.bff_api_audience}/access_as_user",
            "aliasModels": s.alias_models,
            "modelPrices": deps.model_prices,
        }

    @app.get("/api/me")
    def me(principal: Principal = Depends(current_principal)):
        return {"name": principal.name, "oid": principal.oid, "isAdmin": principal.is_admin}

    @app.get("/api/keys")
    def list_keys(_: Principal = Depends(require_admin)):
        consumers = {row["id"]: row.get("consumer") for row in deps.store.list()}
        return [{"id": k.id, "displayName": k.display_name, "state": k.state, "consumer": consumers.get(k.id)} for k in deps.apim.list()]

    @app.post("/api/keys", status_code=201)
    def create_key(body: CreateKeyRequest, principal: Principal = Depends(require_admin)):
        consumer = body.consumer.strip()
        if not consumer:
            raise HTTPException(status_code=400, detail="consumer is required")
        vk = deps.apim.create(display_name=consumer)
        try:
            deps.store.record(
                key_id=vk.id,
                consumer=consumer,
                display_name=vk.display_name,
                created_by=principal.oid,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
        except Exception:
            deps.apim.delete(vk.id)
            raise
        return {"id": vk.id, "consumer": consumer, "displayName": vk.display_name, "primaryKey": vk.primary_key, "secondaryKey": vk.secondary_key}

    @app.delete("/api/keys/{key_id}", status_code=204)
    def delete_key(key_id: str, _: Principal = Depends(require_admin)):
        deps.apim.delete(key_id)
        deps.store.remove(key_id)
        return Response(status_code=204)

    @app.get("/api/tiers")
    def list_tiers(_: Principal = Depends(require_admin)):
        return [{"name": n, "tpm": t["tpm"], "quota": t["quota"], "period": t["period"]} for n, t in s.rate_tiers.items()]

    @app.get("/api/consumers")
    def list_consumers(_: Principal = Depends(require_admin)):
        counts: dict[str, int] = {}
        for row in deps.store.list():
            t = row.get("consumer")
            if t:
                counts[t] = counts.get(t, 0) + 1
        reg = {d["consumer"]: d for d in deps.consumerregistry.list()}
        config_consumers = {d["consumer"] for d in deps.consumerconfig.list()}
        consumers = set(counts) | set(reg)
        return [{
            "consumer": t,
            "keyCount": counts.get(t, 0),
            "displayName": reg.get(t, {}).get("display_name"),
            "entraGroupId": reg.get(t, {}).get("entra_group_id"),
            "hasConfig": t in config_consumers,
            "source": "both" if (t in reg and t in counts) else ("registry" if t in reg else "keys"),
        } for t in sorted(consumers)]

    @app.post("/api/consumers", status_code=201)
    def create_consumer(body: ConsumerRegistryRequest, principal: Principal = Depends(require_admin)):
        consumer = (body.consumer or "").strip()
        if not consumer:
            raise HTTPException(status_code=400, detail="consumer is required")
        if deps.consumerregistry.get(consumer) is not None:
            raise HTTPException(status_code=409, detail=f"consumer '{consumer}' already registered")
        fields = {
            "entra_group_id": body.entra_group_id,
            "display_name": body.display_name,
            "description": body.description,
            "created_by": principal.oid,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            deps.consumerregistry.put(consumer, fields, existing_group_owners=deps.consumerregistry.group_index())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"consumer": consumer, "created": True}

    @app.put("/api/consumers/{consumer}")
    def update_consumer(consumer: str, body: ConsumerRegistryRequest, _: Principal = Depends(require_admin)):
        existing = deps.consumerregistry.get(consumer) or {}
        incoming = {k: v for k, v in {"entra_group_id": body.entra_group_id, "display_name": body.display_name, "description": body.description}.items() if v is not None}
        merged = {k: existing[k] for k in ("entra_group_id", "display_name", "description") if k in existing}
        merged.update(incoming)
        if body.entra_group_id is not None and not str(body.entra_group_id).strip():
            raise HTTPException(status_code=400, detail="entra_group_id cannot be blank")
        try:
            deps.consumerregistry.put(consumer, merged, existing_group_owners=deps.consumerregistry.group_index())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"consumer": consumer, "saved": True}

    @app.delete("/api/consumers/{consumer}")
    def delete_consumer(consumer: str, _: Principal = Depends(require_admin)):
        key_count = sum(1 for row in deps.store.list() if row.get("consumer") == consumer)
        if key_count:
            raise HTTPException(status_code=409, detail=(f"'{consumer}' still has {key_count} key(s); revoke them in 6 API Keys before deleting the consumer"))
        deps.consumerregistry.remove(consumer)
        deps.consumerconfig.remove(consumer)
        return {"consumer": consumer, "deleted": True}

    def _live_spend(consumer: str, doc: dict) -> tuple[float | None, float | None]:
        budget = doc.get("daily_budget_usd")
        try:
            model_usage = deps.metrics.consumer_usage(consumer, RANGES["24h"])
            usage_usd = cost_usd(model_usage, deps.model_prices)
            pct = round(usage_usd / budget, 4) if budget else None
            return usage_usd, pct
        except Exception:
            ad = doc.get("active_downgrade") or {}
            return ad.get("usage_usd"), ad.get("pct")

    @app.get("/api/consumers/{consumer}/config")
    def get_consumer_config(consumer: str, _: Principal = Depends(require_admin)):
        default_models = list(s.allowed_model_aliases)
        doc = deps.consumerconfig.get(consumer)
        effective = doc if doc is not None else deps.consumerconfig.global_defaults()
        usage_usd, pct = _live_spend(consumer, effective)
        return _consumer_config_response(consumer, effective, is_default=doc is None, default_models=default_models, usage_usd=usage_usd, pct=pct)

    @app.put("/api/consumers/{consumer}/config")
    def put_consumer_config(consumer: str, body: ConsumerConfigRequest, _: Principal = Depends(require_admin)):
        incoming = body.model_dump(exclude_none=True)
        if not incoming:
            raise HTTPException(status_code=400, detail="request body must contain at least one field")
        existing = deps.consumerconfig.get(consumer) or {}
        merged = {k: existing[k] for k in ("allowed_models", "tier", "daily_budget", "daily_budget_usd", "downgrade_ladder", "active_downgrade") if k in existing}
        merged.update(incoming)
        aliases = list(s.allowed_model_aliases) if s.allowed_model_aliases else None
        try:
            deps.consumerconfig.put(consumer, merged, valid_aliases=aliases)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        triggered = False
        if "daily_budget_usd" in incoming and deps.job_starter is not None:
            triggered = bool(deps.job_starter.start())
        return {"consumer": consumer, "saved": True, "reevaluationTriggered": triggered}

    def _resolve_range(r: str):
        span = RANGES.get(r)
        if span is None:
            raise HTTPException(status_code=400, detail=f"range must be one of {list(RANGES)}")
        return span

    @app.get("/api/links")
    def links(_: Principal = Depends(require_admin)):
        return {"apimAnalyticsUrl": s.apim_analytics_url}

    @app.get("/api/metrics/dashboard")
    def metrics_dashboard(range: str = "24h", _: Principal = Depends(require_admin)):
        data = deps.metrics.dashboard(_resolve_range(range))
        data = _translate_by_consumer(data, deps.consumerregistry.group_index())
        data["downgrades"] = [{"consumer": d["consumer"], "level": (d.get("active_downgrade") or {}).get("level", 0)} for d in deps.consumerconfig.list() if (d.get("active_downgrade") or {}).get("level", 0) > 0]
        return data

    @app.get("/api/metrics/monitoring")
    def metrics_monitoring(range: str = "1h", _: Principal = Depends(require_admin)):
        return deps.metrics.monitoring(_resolve_range(range))

    @app.get("/api/runs")
    def list_runs(range: str = "24h", _: Principal = Depends(require_admin)):
        if deps.runs is None:
            return {"items": []}
        return deps.runs.list(_resolve_range(range)).model_dump()

    @app.get("/api/pricing")
    def get_pricing(_: Principal = Depends(require_admin)):
        doc = deps.pricing.get()
        return {
            "region": default_region(doc),
            "models": doc.get("models", {}),
            "overrides": doc.get("overrides", {}),
            "sourceModels": doc.get("sourceModels", doc.get("models", {})),
            "refreshed_at": doc.get("refreshed_at"),
        }

    @app.post("/api/pricing/preview")
    def pricing_preview(body: PricingRequest, _: Principal = Depends(require_admin)):
        current = deps.pricing.get()
        region = (body.region or default_region(current)).strip()
        try:
            return preview_refresh(current, region, overrides=_pricing_overrides(body))
        except (LookupError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/pricing/refresh")
    def pricing_refresh(body: PricingRequest, _: Principal = Depends(require_admin)):
        current = deps.pricing.get()
        region = (body.region or default_region(current)).strip()
        try:
            preview = preview_refresh(current, region, overrides=_pricing_overrides(body))
            doc = save_doc(deps.pricing, region=region, source_models=preview["sourceModels"], overrides=preview["overrides"], current_doc=current)
        except (LookupError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        deps.model_prices = doc.get("models", {})
        return {
            "region": region,
            "models": deps.model_prices,
            "overrides": doc.get("overrides", {}),
            "diff": preview["diff"],
            "refreshed_at": doc.get("refreshed_at"),
        }

    @app.put("/api/pricing")
    def pricing_put(body: PricingRequest, _: Principal = Depends(require_admin)):
        current = deps.pricing.get()
        region = (body.region or default_region(current)).strip()
        base = current.get("sourceModels") or current.get("models") or {}
        try:
            doc = save_doc(deps.pricing, region=region, source_models=base, overrides=_pricing_overrides(body), current_doc=current)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        deps.model_prices = doc.get("models", {})
        return {
            "region": region,
            "models": deps.model_prices,
            "overrides": doc.get("overrides", {}),
            "diff": [],
            "refreshed_at": doc.get("refreshed_at"),
        }

    if deps.spa_dir is not None:
        assets = deps.spa_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            return FileResponse(str(deps.spa_dir / "index.html"))

    return app
