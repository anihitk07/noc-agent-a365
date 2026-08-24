from datetime import timedelta

from fastapi.testclient import TestClient

from bff.app import AppDeps, app_factory
from bff.auth import Principal
from bff.config import Settings
from bff.deps import current_principal
from bff.metrics import RANGES
from bff.runs import RunsQuery, RunsResponse, RunSummary, RunHalt


class FakeTable:
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows


class FakeResult:
    def __init__(self, tables):
        self.status = "Success"
        self.tables = tables


class FakeLogsClient:
    def __init__(self, mapping):
        self._mapping = mapping

    def query_workspace(self, workspace_id, query, timespan):
        for key, table in self._mapping.items():
            if key in query:
                return FakeResult([table])
        return FakeResult([FakeTable([], [])])


def _settings():
    return Settings(
        entra_tenant_id="tid",
        bff_api_audience="api://bff",
        spa_client_id="spa",
        admin_group_object_id="gid",
        subscription_id="sub",
        apim_rg="rg",
        apim_name="apim",
        cosmos_endpoint="https://c",
        cosmos_database="gateway",
        cosmos_map_container="maps",
        allowed_model_aliases=("gpt-5.4", "gpt-5.4-mini"),
        rate_tiers={"small": {"tpm": 500, "quota": 20000, "period": "Daily"}},
    )


class Dummy:
    def list(self):
        return []


class DummyConsumerConfig(Dummy):
    def global_defaults(self):
        return {}


class FakeRuns:
    def list(self, span):
        return RunsResponse(
            items=[
                RunSummary(
                    runId="run-1",
                    lastSeen="2026-01-01T00:00:00Z",
                    callCount=2,
                    steps=3,
                    agents=["noc-agent"],
                    costUsd=0.125,
                    halts=[RunHalt(time="2026-01-01T00:01:00Z", reason="cost_budget")],
                )
            ]
        )


def test_runs_query_aggregates_costs_halts_and_downgrades():
    client = FakeLogsClient({
        'Name == "run_tokens"': FakeTable(
            ["runId", "lastSeen", "callCount", "agents", "steps"],
            [["run-1", "2026-01-01T00:02:00Z", 3, ["noc-agent"], 4]],
        ),
        'Name in ("Prompt Tokens", "Completion Tokens")': FakeTable(
            ["runId", "model", "tok_kind", "tokens"],
            [["run-1", "gpt-5.4", "prompt", 1000], ["run-1", "gpt-5.4", "completion", 500]],
        ),
        "Message has 'Run halted'": FakeTable(
            ["TimeGenerated", "runId", "reason"],
            [["2026-01-01T00:03:00Z", "run-1", "step_cap"]],
        ),
        "Message has 'model downgraded'": FakeTable(
            ["TimeGenerated", "runId", "requestedModel", "effectiveModel", "downgradeLevel"],
            [["2026-01-01T00:01:30Z", "run-1", "gpt-5.4", "gpt-5.4-mini", "1"]],
        ),
    })
    query = RunsQuery(client, "ws", {"gpt-5.4": {"prompt": 0.0025, "completion": 0.015}})
    body = query.list(timedelta(days=1)).model_dump()
    assert body["items"][0]["runId"] == "run-1"
    assert body["items"][0]["callCount"] == 3
    assert body["items"][0]["steps"] == 4
    assert body["items"][0]["costUsd"] == 0.01
    assert body["items"][0]["halts"][0]["reason"] == "step_cap"
    assert body["items"][0]["downgrades"][0]["effectiveModel"] == "gpt-5.4-mini"


def test_runs_endpoint_requires_admin_and_returns_data():
    deps = AppDeps(
        settings=_settings(),
        apim=Dummy(),
        store=Dummy(),
        spa_dir=None,
        consumerconfig=DummyConsumerConfig(),
        metrics=Dummy(),
        consumerregistry=Dummy(),
        pricing=Dummy(),
        runs=FakeRuns(),
    )
    app = app_factory(deps)
    client = TestClient(app)

    app.dependency_overrides[current_principal] = lambda: Principal(oid="u", name="User", is_admin=False)
    assert client.get("/api/runs?range=24h").status_code == 403

    app.dependency_overrides[current_principal] = lambda: Principal(oid="a", name="Admin", is_admin=True)
    body = client.get("/api/runs?range=24h").json()
    assert body["items"][0]["runId"] == "run-1"
    assert client.get("/api/runs?range=99y").status_code == 400
    assert RANGES["24h"] == timedelta(days=1)
