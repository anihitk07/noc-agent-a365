"""Ad-hoc CLI: print today's token usage + estimated USD cost per consumer/model.

Reuses the exact KQL and cost logic the config-sync worker runs every 5 minutes
(sync.py:_USAGE_KQL, budget.cost_for) — this is a read-only, no-deploy way to check
usage without the Admin UI (which isn't publicly reachable; see chat).

Usage:
  az login   # once, if not already
  python check_usage.py [--workspace-id GUID] [--days 1]

Defaults: workspace-id = law-aigw-dev-eus2's customerId, days = 1 (matches the
worker's daily budget window). Requires azure-identity, azure-cosmos,
azure-monitor-query (already in requirements.txt) and network access to Azure.
"""
import argparse
import datetime
import os

from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from sync import _USAGE_KQL, _shape_usage, PRICING_DOC_ID
import budget

DEFAULT_WORKSPACE_ID = "56328e58-fdce-43b0-8890-bff106377864"  # law-aigw-dev-eus2
DEFAULT_COSMOS_ENDPOINT = "https://cosaigwdeveus2n2tjinbhnbln6.documents.azure.com:443/"


def query_usage(cred, workspace_id: str, days: int) -> dict:
    client = LogsQueryClient(cred)
    resp = client.query_workspace(workspace_id=workspace_id, query=_USAGE_KQL,
                                   timespan=datetime.timedelta(days=days))
    tables = resp.tables if resp.status == LogsQueryStatus.SUCCESS else (resp.partial_data or [])
    rows = []
    if tables:
        cols = [str(c) for c in tables[0].columns]
        rows = [dict(zip(cols, row)) for row in tables[0].rows]
    return _shape_usage(rows)


def read_pricing(cred, cosmos_endpoint: str) -> dict:
    # ponytail: Cosmos is private-endpoint-only, so this raises when run off-VNet (e.g. a
    # laptop). Cost is a nice-to-have; degrade to $0 cost rather than crashing the whole report.
    try:
        client = CosmosClient(cosmos_endpoint, credential=cred)
        container = client.get_database_client("gateway").get_container_client(
            os.environ.get("COSMOS_CONFIG_CONTAINER", "config")
        )
        return container.read_item(item=PRICING_DOC_ID, partition_key=PRICING_DOC_ID).get("models", {})
    except CosmosResourceNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        print(f"(pricing lookup failed, showing $0 cost: {exc})\n")
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    ap.add_argument("--cosmos-endpoint", default=DEFAULT_COSMOS_ENDPOINT)
    ap.add_argument("--days", type=int, default=1)
    args = ap.parse_args()

    cred = DefaultAzureCredential()
    usage = query_usage(cred, args.workspace_id, args.days)
    pricing = read_pricing(cred, args.cosmos_endpoint)

    if not usage:
        print("No usage rows found (empty window, or caller lacks Log Analytics Reader).")
        return 0

    print(f"{'consumer':<20}{'model':<25}{'prompt':>10}{'completion':>12}{'est_cost_usd':>14}")
    grand_total = 0.0
    for consumer, models in sorted(usage.items()):
        cost = budget.cost_for(models, pricing)
        grand_total += cost
        for model, toks in sorted(models.items()):
            print(f"{consumer:<20}{model:<25}{toks['prompt']:>10}{toks['completion']:>12}{'':>14}")
        print(f"{'':<20}{'-- consumer total --':<25}{'':>10}{'':>12}{cost:>14.4f}")
    print(f"\nGrand total (est.): ${grand_total:.4f} over last {args.days} day(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
