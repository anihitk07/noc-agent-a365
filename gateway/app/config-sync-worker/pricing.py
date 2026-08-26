from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable

API_VERSION = "2023-01-01-preview"
BASE_URL = "https://prices.azure.com/api/retail/prices"
SERVICE_NAME = "Foundry Models"


@dataclass(frozen=True)
class MeterRule:
    model: str
    kind: str
    patterns: tuple[str, ...]


# ponytail: lock to the four shipped model ids; add more entries when the gateway exposes more.
MODEL_RULES: tuple[MeterRule, ...] = (
    MeterRule("gpt-5.4", "prompt", (r"\b5\.4 inp gl\b", r"\bgpt 5 inpt glbl\b", r"\bgpt 5 inpt dzone\b")),
    MeterRule("gpt-5.4", "completion", (r"\b5\.4 opt gl\b", r"\bgpt 5 outpt glbl\b", r"\bgpt 5 outpt dzone\b", r"\b5\.4 opt dz\b")),
    MeterRule("gpt-5.4-mini", "prompt", (r"\b5\.4 mini inp gl\b", r"\bgpt 5 mini inpt glbl\b", r"\bgpt 5 mini inpt dzone\b")),
    MeterRule("gpt-5.4-mini", "completion", (r"\b5\.4 mini opt gl\b", r"\bgpt 5 mini outpt glbl\b", r"\bgpt 5 mini outpt dzone\b", r"\b5\.4 mini opt dz\b")),
    MeterRule("grok-4.3", "prompt", (r"\b4\.3 inp glbl\b", r"\b4\.3 inp dz\b", r"\b4\.3 inp glbl l\b", r"\b4\.3 inp dz l\b")),
    MeterRule("grok-4.3", "completion", (r"\b4\.3 outp glbl\b", r"\b4\.3 outp dz\b", r"\b4\.3 outp dz l\b")),
    MeterRule("DeepSeek-V4-Pro", "prompt", (r"\bv4 pro inp glbl\b", r"\bv4 pro inp dz\b", r"\bfw deepseek-v4-pro ch inp dz\b")),
    MeterRule("DeepSeek-V4-Pro", "completion", (r"\bv4 pro outp glbl\b", r"\bv4 pro outp dz\b", r"\bfw deepseek-v4-pro outp dz\b")),
)


def normalize_unit_price(retail_price: float, unit_of_measure: str) -> float:
    unit = (unit_of_measure or "").strip().upper()
    if unit == "1K":
        return round(float(retail_price), 6)
    if unit == "1M":
        return round(float(retail_price) / 1000.0, 6)
    raise ValueError(f"unrecognized unit_of_measure '{unit_of_measure}'")


def _meter_text(item: dict) -> str:
    return " ".join(
        str(item.get(k) or "")
        for k in ("productName", "skuName", "meterName", "armSkuName")
    ).lower()


def _retail_items_url(region: str) -> str:
    filter_expr = f"serviceName eq '{SERVICE_NAME}' and armRegionName eq '{region}'"
    return f"{BASE_URL}?api-version={API_VERSION}&$filter={urllib.parse.quote(filter_expr, safe='')}"


def fetch_retail_items(region: str, *, urlopen=urllib.request.urlopen) -> list[dict]:
    url = _retail_items_url(region)
    items: list[dict] = []
    while url:
        with urlopen(url) as resp:
            payload = json.load(resp)
        items.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
    return items


def _pick_rate(items: Iterable[dict], rule: MeterRule) -> float:
    token_items = [item for item in items if "token" in _meter_text(item)]
    for pattern in rule.patterns:
        for item in token_items:
            if re.search(pattern, _meter_text(item)):
                return normalize_unit_price(item["retailPrice"], item.get("unitOfMeasure", ""))
    raise LookupError(f"missing {rule.kind} meter for {rule.model}")


def extract_model_prices(items: Iterable[dict]) -> dict[str, dict[str, float]]:
    materialized = list(items)
    out: dict[str, dict[str, float]] = {}
    for rule in MODEL_RULES:
        out.setdefault(rule.model, {})[rule.kind] = _pick_rate(materialized, rule)
    return out


def fetch_model_pricing(region: str, *, urlopen=urllib.request.urlopen) -> dict[str, dict[str, float]]:
    return extract_model_prices(fetch_retail_items(region, urlopen=urlopen))


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if len(argv) != 1 or not argv[0].strip():
        print("usage: python pricing.py <region>", file=sys.stderr)
        return 2
    print(json.dumps(fetch_model_pricing(argv[0].strip()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
