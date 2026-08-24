from __future__ import annotations

import datetime
import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

from azure.cosmos.exceptions import CosmosResourceNotFoundError

PRICING_DOC_ID = "pricing"


def _load_worker_module():
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "config-sync-worker" / "pricing.py",
        here.parents[1] / "config-sync-worker" / "pricing.py",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("worker_pricing", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    return None


_worker_pricing = _load_worker_module()
if _worker_pricing is None:  # ponytail: keep the BFF container working without copying the worker tree.
    raise RuntimeError("config-sync-worker/pricing.py is required for pricing refresh")


class PricingStore:
    def __init__(self, container):
        self._c = container

    def get(self) -> dict:
        try:
            return self._c.read_item(item=PRICING_DOC_ID, partition_key=PRICING_DOC_ID)
        except CosmosResourceNotFoundError:
            return {"id": PRICING_DOC_ID, "doc_type": "pricing", "currency": "USD", "unit": "per_1k_tokens", "models": {}, "overrides": {}}

    def put(self, doc: dict) -> dict:
        body = {"id": PRICING_DOC_ID, "doc_type": "pricing", "currency": "USD", "unit": "per_1k_tokens", **doc}
        return self._c.upsert_item(body=body)


def _copy_rates(rates: dict | None) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for model, rate in (rates or {}).items():
        out[model] = {"prompt": float(rate["prompt"]), "completion": float(rate["completion"])}
    return out


def normalize_overrides(overrides: dict | None) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for model, rate in (overrides or {}).items():
        if rate is None:
            continue
        prompt = rate.get("prompt") if isinstance(rate, dict) else None
        completion = rate.get("completion") if isinstance(rate, dict) else None
        if prompt in (None, "") or completion in (None, ""):
            continue
        prompt = float(prompt)
        completion = float(completion)
        if prompt <= 0 or completion <= 0:
            raise ValueError(f"override for {model} must be positive")
        out[model] = {"prompt": round(prompt, 6), "completion": round(completion, 6)}
    return out


def apply_overrides(base_rates: dict | None, overrides: dict | None) -> dict[str, dict[str, float]]:
    merged = _copy_rates(base_rates)
    for model, rate in normalize_overrides(overrides).items():
        merged[model] = rate
    return merged


def diff_models(current: dict | None, next_rates: dict | None) -> list[dict]:
    rows = []
    keys = sorted(set((current or {}).keys()) | set((next_rates or {}).keys()))
    for model in keys:
        old = (current or {}).get(model, {})
        new = (next_rates or {}).get(model, {})
        if old == new:
            continue
        rows.append({"model": model, "current": old or None, "next": new or None})
    return rows


def default_region(current_doc: dict | None = None) -> str:
    return ((current_doc or {}).get("region") or os.environ.get("AZURE_LOCATION") or "eastus2").strip()


def preview_refresh(current_doc: dict, region: str, *, overrides: Optional[dict] = None) -> dict:
    source_models = _worker_pricing.fetch_model_pricing(region)
    final_overrides = normalize_overrides(overrides if overrides is not None else current_doc.get("overrides"))
    next_models = apply_overrides(source_models, final_overrides)
    current_models = _copy_rates(current_doc.get("models"))
    return {
        "region": region,
        "sourceModels": source_models,
        "overrides": final_overrides,
        "models": next_models,
        "diff": diff_models(current_models, next_models),
    }


def save_doc(store: PricingStore, *, region: str, source_models: dict, overrides: dict | None, current_doc: Optional[dict] = None) -> dict:
    current_doc = current_doc or store.get()
    clean_overrides = normalize_overrides(overrides)
    merged = apply_overrides(source_models, clean_overrides)
    doc = {
        **current_doc,
        "region": region,
        "source": "azure-retail-prices",
        "sourceModels": source_models,
        "overrides": clean_overrides,
        "models": merged,
        "refreshed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return store.put(doc)
