"""Ad-hoc CLI: print per-request usage (user, query, agent, token breakdown, est. cost).

Reads the `usage_event` structured log lines agent.py emits per specialist call
(agent/agent.py:_call_specialist) from the orchestrator's Application Insights
workspace (customDimensions), and joins with the same Cosmos `pricing` doc +
budget.cost_for the config-sync worker already uses -- no new infra, no new
storage; this is a read-only report over what's already flowing.

Usage:
  az login   # once, if not already
  python check_usage_detail.py [--hours 24] [--workspace-id GUID]

Requires azure-identity, azure-monitor-query, azure-cosmos (already in
requirements.txt) plus Log Analytics Reader on the orchestrator's workspace
and Cosmos DB Built-in Data Reader on the gateway account.
"""
import argparse
import datetime

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

import budget
from check_usage import read_pricing, DEFAULT_COSMOS_ENDPOINT

DEFAULT_WORKSPACE_ID = "bc8bf4ca-439d-48f9-80dd-78131d30795a"  # logs-z4u5lniaf25kw (orchestrator App Insights)

_KQL = (
    "AppTraces | where Message == \"usage_event\" "
    "| extend p = customDimensions "
    "| project TimeGenerated, "
    "user_name = tostring(p.user_name), user_id = tostring(p.user_id), "
    "agent = tostring(p.agent), model = tostring(p.model), query = tostring(p.query), "
    "input_tokens = toint(p.input_tokens), output_tokens = toint(p.output_tokens), "
    "cached_tokens = toint(p.cached_tokens), reasoning_tokens = toint(p.reasoning_tokens), "
    "run_id = tostring(p.run_id) "
    "| order by TimeGenerated desc"
)


def query_events(cred, workspace_id: str, hours: int) -> list[dict]:
    client = LogsQueryClient(cred)
    resp = client.query_workspace(workspace_id=workspace_id, query=_KQL,
                                   timespan=datetime.timedelta(hours=hours))
    tables = resp.tables if resp.status == LogsQueryStatus.SUCCESS else (resp.partial_data or [])
    if not tables:
        return []
    cols = [str(c) for c in tables[0].columns]
    return [dict(zip(cols, row)) for row in tables[0].rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    ap.add_argument("--cosmos-endpoint", default=DEFAULT_COSMOS_ENDPOINT)
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()

    cred = DefaultAzureCredential()
    events = query_events(cred, args.workspace_id, args.hours)
    if not events:
        print("No usage_event rows found in the window (check --hours, or that the agent has been called).")
        return 0
    pricing = read_pricing(cred, args.cosmos_endpoint)

    header = f"{'time':<20}{'user':<15}{'agent':<22}{'model':<15}{'in':>7}{'out':>7}{'cached':>8}{'reason':>8}{'cost_usd':>10}  query"
    print(header)
    grand_total = 0.0
    for e in events:
        model_usage = {e["model"]: {"prompt": e["input_tokens"], "completion": e["output_tokens"]}}
        cost = budget.cost_for(model_usage, pricing)
        grand_total += cost
        ts = str(e["TimeGenerated"])[:19]
        print(
            f"{ts:<20}{e['user_name']:<15}{e['agent']:<22}{e['model']:<15}"
            f"{e['input_tokens']:>7}{e['output_tokens']:>7}{e['cached_tokens']:>8}"
            f"{e['reasoning_tokens']:>8}{cost:>10.5f}  {e['query'][:60]}"
        )
    print(f"\n{len(events)} request(s), est. total cost ${grand_total:.4f} over last {args.hours}h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
