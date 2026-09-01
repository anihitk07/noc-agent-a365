"""Read-only Log Analytics queries for the Runs page.

Designs against the future TokenOps/APIM telemetry shape:
  - AppMetrics Name == "run_tokens" with Properties JSON carrying run_id / agent / step
  - Prompt/Completion token metrics carrying run_id + effectiveModel/deployment
  - AppTraces rows for halt and downgrade events carrying run_id in Properties
"""
from datetime import timedelta

from pydantic import BaseModel, Field

from bff.cost import cost_usd
from bff.metrics import _rows

_Q_RUNS = (
    'AppMetrics | where Name == "run_tokens" | extend p=parse_json(Properties) '
    '| summarize lastSeen=max(TimeGenerated), callCount=count(), agents=make_set(tostring(p.agent)), '
    'steps=max(toint(p.step)) by runId=tostring(p.run_id) | order by lastSeen desc | take 100'
)
_Q_COST = (
    'AppMetrics | where Name in ("Prompt Tokens", "Completion Tokens") | extend p=parse_json(Properties) '
    '| where isnotempty(tostring(p.run_id)) '
    '| extend tok_kind=iff(Name == "Prompt Tokens", "prompt", "completion"), '
    'model=tostring(coalesce(p.effectiveModel, p.deployment)) '
    '| summarize tokens=sum(Sum) by runId=tostring(p.run_id), model, tok_kind'
)
_Q_HALTS = (
    "AppTraces | where Message has 'run_halted' or Message has 'Run halted' | extend p=parse_json(Properties) "
    '| project TimeGenerated, runId=tostring(p.run_id), reason=tostring(coalesce(p.halt_reason, p.reason))'
)
_Q_DOWNGRADES = (
    "AppTraces | where Message has 'model downgraded' | extend p=parse_json(Properties) "
    '| project TimeGenerated, runId=tostring(p.run_id), requestedModel=tostring(p.requestedModel), '
    'effectiveModel=tostring(p.effectiveModel), downgradeLevel=tostring(p.downgradeLevel)'
)


class RunHalt(BaseModel):
    time: str | None = None
    reason: str


class RunDowngrade(BaseModel):
    time: str | None = None
    requestedModel: str | None = None
    effectiveModel: str | None = None
    downgradeLevel: str | None = None


class RunSummary(BaseModel):
    runId: str
    lastSeen: str | None = None
    callCount: int = 0
    steps: int = 0
    agents: list[str] = Field(default_factory=list)
    costUsd: float = 0.0
    halts: list[RunHalt] = Field(default_factory=list)
    downgrades: list[RunDowngrade] = Field(default_factory=list)


class RunsResponse(BaseModel):
    items: list[RunSummary]


class RunsQuery:
    def __init__(self, client, workspace_id: str, model_prices: dict):
        self._c = client
        self._ws = workspace_id
        self._model_prices = model_prices

    def _q(self, kql: str, span: timedelta):
        return self._c.query_workspace(workspace_id=self._ws, query=kql, timespan=span)

    def list(self, span: timedelta) -> RunsResponse:
        runs = {row.get("runId"): row for row in _rows(self._q(_Q_RUNS, span)) if row.get("runId")}
        costs = _rows(self._q(_Q_COST, span))
        halts = _rows(self._q(_Q_HALTS, span))
        downgrades = _rows(self._q(_Q_DOWNGRADES, span))

        cost_by_run: dict[str, dict] = {}
        for row in costs:
            run_id = row.get("runId")
            model = row.get("model")
            tok_kind = row.get("tok_kind")
            if not run_id or not model or tok_kind not in {"prompt", "completion"}:
                continue
            cost_by_run.setdefault(run_id, {}).setdefault(model, {"prompt": 0, "completion": 0})[tok_kind] = int(row.get("tokens") or 0)

        halt_by_run: dict[str, list[RunHalt]] = {}
        for row in halts:
            run_id = row.get("runId")
            reason = row.get("reason")
            if not run_id or not reason:
                continue
            halt_by_run.setdefault(run_id, []).append(RunHalt(time=row.get("TimeGenerated"), reason=reason))

        downgrade_by_run: dict[str, list[RunDowngrade]] = {}
        for row in downgrades:
            run_id = row.get("runId")
            if not run_id:
                continue
            downgrade_by_run.setdefault(run_id, []).append(
                RunDowngrade(
                    time=row.get("TimeGenerated"),
                    requestedModel=row.get("requestedModel"),
                    effectiveModel=row.get("effectiveModel"),
                    downgradeLevel=row.get("downgradeLevel"),
                )
            )

        run_ids = set(runs) | set(cost_by_run) | set(halt_by_run) | set(downgrade_by_run)
        items = []
        for run_id in sorted(run_ids, key=lambda rid: str((runs.get(rid) or {}).get("lastSeen", "")), reverse=True):
            row = runs.get(run_id, {})
            agents = [a for a in row.get("agents", []) if a]
            items.append(
                RunSummary(
                    runId=run_id,
                    lastSeen=row.get("lastSeen"),
                    callCount=int(row.get("callCount") or 0),
                    steps=int(row.get("steps") or 0),
                    agents=agents,
                    costUsd=cost_usd(cost_by_run.get(run_id, {}), self._model_prices),
                    halts=halt_by_run.get(run_id, []),
                    downgrades=downgrade_by_run.get(run_id, []),
                )
            )
        return RunsResponse(items=items)
