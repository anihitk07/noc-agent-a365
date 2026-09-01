import json

import jwt
from fastapi.testclient import TestClient

from run_ledger.app import AppDeps, app_factory
from run_ledger.config import Settings
from run_ledger.service import RunLedgerService, RunTokenSigner


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def watch(self, *_args):
        return None

    def multi(self):
        return None

    def hincrby(self, name, key, amount):
        self.ops.append(("hincrby", name, key, amount))

    def hset(self, name, mapping):
        self.ops.append(("hset", name, mapping))

    def expire(self, name, ttl):
        self.ops.append(("expire", name, ttl))

    def setex(self, name, ttl, value):
        self.ops.append(("setex", name, ttl, value))

    def lpush(self, name, value):
        self.ops.append(("lpush", name, value))

    def ltrim(self, name, start, end):
        self.ops.append(("ltrim", name, start, end))

    def delete(self, name):
        self.ops.append(("delete", name))

    async def hgetall(self, name):
        return await self.redis.hgetall(name)

    async def execute(self):
        for op in self.ops:
            kind = op[0]
            if kind == "hincrby":
                _, name, key, amount = op
                await self.redis.hincrby(name, key, amount)
            elif kind == "hset":
                _, name, mapping = op
                await self.redis.hset(name, mapping=mapping)
            elif kind == "expire":
                _, name, ttl = op
                await self.redis.expire(name, ttl)
            elif kind == "setex":
                _, name, ttl, value = op
                await self.redis.setex(name, ttl, value)
            elif kind == "lpush":
                _, name, value = op
                await self.redis.lpush(name, value)
            elif kind == "ltrim":
                _, name, start, end = op
                await self.redis.ltrim(name, start, end)
            elif kind == "delete":
                _, name = op
                await self.redis.delete(name)
        self.ops.clear()

    async def reset(self):
        self.ops.clear()


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.strings = {}
        self.lists = {}
        self.expiry = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    async def hset(self, name, mapping=None, key=None, value=None):
        bucket = self.hashes.setdefault(name, {})
        if mapping:
            bucket.update({k: str(v) for k, v in mapping.items()})
        elif key is not None:
            bucket[key] = str(value)

    async def hgetall(self, name):
        return dict(self.hashes.get(name, {}))

    async def hincrby(self, name, key, amount):
        bucket = self.hashes.setdefault(name, {})
        bucket[key] = str(int(bucket.get(key, "0")) + int(amount))
        return int(bucket[key])

    async def expire(self, name, ttl):
        self.expiry[name] = ttl
        return True

    async def ttl(self, name):
        return self.expiry.get(name, -1)

    async def setex(self, name, ttl, value):
        self.strings[name] = value
        self.expiry[name] = ttl

    async def get(self, name):
        return self.strings.get(name)

    async def delete(self, name):
        self.strings.pop(name, None)
        self.hashes.pop(name, None)
        self.lists.pop(name, None)
        self.expiry.pop(name, None)
        return 1

    async def lrange(self, name, start, end):
        values = list(self.lists.get(name, []))
        if end == -1:
            end = len(values) - 1
        return values[start:end + 1]

    async def lpush(self, name, value):
        self.lists.setdefault(name, []).insert(0, value)

    async def ltrim(self, name, start, end):
        values = self.lists.get(name, [])
        self.lists[name] = values[start:end + 1]


def _settings():
    return Settings(
        key_vault_url="https://kv.example.vault.azure.net/",
        run_token_signing_secret_name="run-token",
        redis_host="redis.example.redis.azure.net",
        model_prices={
            "gpt-5.4": {"prompt": 0.0025, "completion": 0.01},
            "gpt-5.4-mini": {"prompt": 0.001, "completion": 0.002},
        },
    )


def _make_client():
    settings = _settings()
    signer = RunTokenSigner(issuer="run-ledger", secret="test-secret", lifetime_seconds=3600)
    service = RunLedgerService(redis=FakeRedis(), signer=signer, settings=settings)
    app = app_factory(AppDeps(service=service))
    return TestClient(app), service


def test_healthz():
    client, _ = _make_client()
    assert client.get("/healthz").json() == {"status": "ok"}


def test_create_run_returns_signed_token_and_initializes_run():
    client, service = _make_client()
    response = client.post("/v1/runs", json={"run_id": "run-1", "budget_micros": 500000, "policy_set": "default"})
    assert response.status_code == 201
    body = response.json()
    claims = jwt.decode(body["run_token"], "test-secret", algorithms=["HS256"], issuer="run-ledger")
    assert claims["run_id"] == "run-1"
    assert claims["budget_micros"] == 500000
    run = service.redis.hashes["run:run-1"]
    assert run["spend_micros"] == "0"
    assert run["inflight_micros"] == "0"
    assert run["halt"] == "0"


def test_create_run_reuses_existing_run_budget():
    client, service = _make_client()
    service.redis.hashes["run:run-1"] = {
        "budget_micros": "700000",
        "spend_micros": "0",
        "inflight_micros": "0",
        "halt": "0",
        "halt_reason": "",
        "steps": "0",
        "concurrent": "0",
        "steered": "0",
        "policy_set": "joined",
    }
    response = client.post("/v1/runs", json={"run_id": "run-1", "budget_micros": 500000, "policy_set": "default"})
    assert response.status_code == 201
    body = response.json()
    assert body["budget_micros"] == 700000
    assert body["policy_set"] == "joined"


def test_precall_returns_reservation_for_allowed_call():
    client, service = _make_client()
    client.post("/v1/runs", json={"run_id": "run-1", "budget_micros": 500000, "policy_set": "default"})
    response = client.post(
        "/v1/precall",
        json={
            "run_id": "run-1",
            "agent": "planner",
            "step": "1",
            "model": "gpt-5.4",
            "est_input_tokens": 100,
            "max_output_tokens": 50,
            "prompt_hash": "abc",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "allow"
    assert body["reservation_id"]
    assert int(service.redis.hashes["run:run-1"]["inflight_micros"]) > 0


def test_precall_returns_halt_for_exhausted_budget():
    client, service = _make_client()
    service.redis.hashes["run:run-1"] = {
        "budget_micros": "100",
        "spend_micros": "100",
        "inflight_micros": "0",
        "halt": "0",
        "halt_reason": "",
        "steps": "0",
        "concurrent": "0",
        "steered": "0",
        "policy_set": "default",
    }
    response = client.post(
        "/v1/precall",
        json={
            "run_id": "run-1",
            "agent": "planner",
            "step": "1",
            "model": "gpt-5.4",
            "est_input_tokens": 1,
            "max_output_tokens": 1,
            "prompt_hash": "abc",
        },
    )
    assert response.status_code == 200
    assert response.json()["halt_reason"] == "cost_budget"


def test_precall_mutates_on_repeat_prompt():
    client, service = _make_client()
    client.post("/v1/runs", json={"run_id": "run-1", "budget_micros": 500000, "policy_set": "default"})
    service.redis.lists["run:run-1:prompts"] = ["loop", "loop", "loop"]
    response = client.post(
        "/v1/precall",
        json={
            "run_id": "run-1",
            "agent": "planner",
            "step": "1",
            "model": "gpt-5.4",
            "est_input_tokens": 10,
            "max_output_tokens": 20,
            "prompt_hash": "loop",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "mutate"
    assert "repeating" in body["inject"].lower()


def test_postcall_releases_reservation_and_records_spend():
    client, service = _make_client()
    client.post("/v1/runs", json={"run_id": "run-1", "budget_micros": 500000, "policy_set": "default"})
    precall = client.post(
        "/v1/precall",
        json={
            "run_id": "run-1",
            "agent": "planner",
            "step": "1",
            "model": "gpt-5.4",
            "est_input_tokens": 100,
            "max_output_tokens": 50,
            "prompt_hash": "abc",
        },
    ).json()
    reservation_id = precall["reservation_id"]
    response = client.post(
        "/v1/postcall",
        json={
            "run_id": "run-1",
            "reservation_id": reservation_id,
            "input_tokens": 100,
            "output_tokens": 50,
            "model": "gpt-5.4",
        },
    )
    assert response.status_code == 204
    run = service.redis.hashes["run:run-1"]
    assert run["inflight_micros"] == "0"
    assert run["concurrent"] == "0"
    assert run["spend_micros"] == str(round(100 * 2.5 + 50 * 10.0))
    assert reservation_id not in "".join(service.redis.strings.keys())


def test_postcall_failed_only_releases_reservation():
    client, service = _make_client()
    client.post("/v1/runs", json={"run_id": "run-1", "budget_micros": 500000, "policy_set": "default"})
    reservation_id = client.post(
        "/v1/precall",
        json={
            "run_id": "run-1",
            "agent": "planner",
            "step": "1",
            "model": "gpt-5.4",
            "est_input_tokens": 100,
            "max_output_tokens": 50,
            "prompt_hash": "abc",
        },
    ).json()["reservation_id"]
    response = client.post(
        "/v1/postcall",
        json={"run_id": "run-1", "reservation_id": reservation_id, "failed": True},
    )
    assert response.status_code == 204
    run = service.redis.hashes["run:run-1"]
    assert run["spend_micros"] == "0"
    assert run["inflight_micros"] == "0"
