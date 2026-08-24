"""Run-ledger service layer: Redis state + JWT minting."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from redis.exceptions import WatchError

from run_ledger.config import Settings
from run_ledger.decide import RunState, decide
from run_ledger.models import PostcallRequest, PrecallRequest, PrecallResponse, RunCreateRequest, RunCreateResponse

log = logging.getLogger("run-ledger")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_int(value: str | int | None, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _to_bool(value: str | int | None) -> bool:
    return str(value or "0").lower() in {"1", "true", "yes"}


def _step_value(step: str) -> int:
    try:
        return max(0, int(step))
    except ValueError:
        return 0


def _decode_reservation(raw: str | bytes | None) -> dict[str, Any] | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


@dataclass
class RunTokenSigner:
    issuer: str
    secret: str
    lifetime_seconds: int

    def mint(self, *, run_id: str, budget_micros: int, policy_set: str, lifetime_seconds: int | None = None) -> tuple[str, datetime]:
        expires_at = _utcnow() + timedelta(seconds=lifetime_seconds or self.lifetime_seconds)
        token = jwt.encode(
            {
                "iss": self.issuer,
                "run_id": run_id,
                "budget_micros": budget_micros,
                "policy_set": policy_set,
                "exp": expires_at,
            },
            self.secret,
            algorithm="HS256",
        )
        return token, expires_at


@dataclass
class RunLedgerService:
    redis: Any
    signer: RunTokenSigner
    settings: Settings

    def _run_key(self, run_id: str) -> str:
        return f"run:{run_id}"

    def _prompt_key(self, run_id: str) -> str:
        return f"run:{run_id}:prompts"

    def _reservation_key(self, reservation_id: str) -> str:
        return f"resv:{reservation_id}"

    def _map_run(self, payload: dict[str, str], prompt_hashes: list[str], step: str) -> RunState:
        halted = _to_bool(payload.get("halt"))
        halted_reason = payload.get("halt_reason") if halted else None
        return RunState(
            budget_micros=_to_int(payload.get("budget_micros")),
            spend_micros=_to_int(payload.get("spend_micros")),
            inflight_micros=_to_int(payload.get("inflight_micros")),
            halted_reason=halted_reason,
            steps=max(_to_int(payload.get("steps")), _step_value(step)),
            concurrent=_to_int(payload.get("concurrent")),
            steered=_to_bool(payload.get("steered")),
            recent_prompt_hashes=prompt_hashes,
        )

    async def create_run(self, body: RunCreateRequest) -> RunCreateResponse:
        ttl = body.ttl_seconds or self.settings.run_ttl_seconds
        run_key = self._run_key(body.run_id)
        current = await self.redis.hgetall(run_key)
        if not current:
            mapping = {
                "budget_micros": str(body.budget_micros),
                "spend_micros": "0",
                "inflight_micros": "0",
                "halt": "0",
                "halt_reason": "",
                "steps": "0",
                "concurrent": "0",
                "steered": "0",
                "policy_set": body.policy_set or self.settings.default_policy_set,
                "intent": body.intent or "",
                "user": body.user or "",
                "team": body.team or "",
                "task": body.task or "",
            }
            await self.redis.hset(run_key, mapping=mapping)
            await self.redis.expire(run_key, ttl)
            current = mapping
        else:
            await self.redis.expire(run_key, ttl)
        budget_micros = _to_int(current.get("budget_micros"), body.budget_micros)
        policy_set = current.get("policy_set") or body.policy_set or self.settings.default_policy_set
        token, expires_at = self.signer.mint(
            run_id=body.run_id,
            budget_micros=budget_micros,
            policy_set=policy_set,
            lifetime_seconds=min(ttl, self.signer.lifetime_seconds),
        )
        return RunCreateResponse(
            run_id=body.run_id,
            budget_micros=budget_micros,
            policy_set=policy_set,
            run_token=token,
            expires_at=expires_at,
        )

    async def precall(self, body: PrecallRequest) -> PrecallResponse:
        run_key = self._run_key(body.run_id)
        prompt_key = self._prompt_key(body.run_id)
        prices = self.settings.prices_for(body.model)
        while True:
            async with self.redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(run_key)
                    current = await pipe.hgetall(run_key)
                    if not current:
                        raise KeyError(body.run_id)
                    prompt_hashes = await self.redis.lrange(prompt_key, 0, self.settings.policies.loop_window - 1)
                    run = self._map_run(current, prompt_hashes, body.step)
                    decision = decide(
                        run=run,
                        prices=prices,
                        est_input_tokens=body.est_input_tokens,
                        max_output_tokens=body.max_output_tokens,
                        prompt_hash=body.prompt_hash,
                        pol=self.settings.policies,
                    )
                    if decision.action not in {"allow", "mutate"}:
                        return PrecallResponse(
                            action=decision.action,
                            model_override=decision.model_override,
                            max_output_tokens=decision.max_output_tokens,
                            inject=decision.inject,
                            halt_reason=decision.halt_reason,
                            reservation_id=None,
                        )

                    reservation_id = str(uuid4())
                    reserved_micros = decision.reserve_micros
                    step_value = str(max(_to_int(current.get("steps")), _step_value(body.step)))
                    steered = current.get("steered", "0")
                    if (
                        not run.steered
                        and run.spend_micros >= run.budget_micros * self.settings.policies.guard_threshold
                        and (decision.model_override is not None or decision.inject is not None)
                    ):
                        steered = "1"
                    pipe.multi()
                    pipe.hincrby(run_key, "inflight_micros", reserved_micros)
                    pipe.hincrby(run_key, "concurrent", 1)
                    pipe.hset(
                        run_key,
                        mapping={
                            "steps": step_value,
                            "steered": steered,
                        },
                    )
                    pipe.expire(run_key, self.settings.run_ttl_seconds)
                    pipe.setex(
                        self._reservation_key(reservation_id),
                        self.settings.reservation_ttl_seconds,
                        json.dumps({"run_id": body.run_id, "reserved_micros": reserved_micros, "model": body.model}),
                    )
                    pipe.lpush(prompt_key, body.prompt_hash)
                    pipe.ltrim(prompt_key, 0, self.settings.policies.loop_window - 1)
                    pipe.expire(prompt_key, self.settings.run_ttl_seconds)
                    await pipe.execute()
                    return PrecallResponse(
                        action=decision.action,
                        model_override=decision.model_override,
                        max_output_tokens=decision.max_output_tokens,
                        inject=decision.inject,
                        halt_reason=decision.halt_reason,
                        reservation_id=reservation_id,
                    )
                except WatchError:
                    continue
                finally:
                    await pipe.reset()

    async def postcall(self, body: PostcallRequest) -> None:
        run_key = self._run_key(body.run_id)
        reservation_key = self._reservation_key(body.reservation_id)
        raw_reservation = await self.redis.get(reservation_key)
        reservation = _decode_reservation(raw_reservation)
        if reservation is None:
            return

        reserved_micros = _to_int(reservation.get("reserved_micros"))
        model_name = body.model or reservation.get("model") or ""
        prices = self.settings.prices_for(model_name)
        spend_micros = 0
        if not body.failed:
            spend_micros = round(body.input_tokens * prices.input_micros + body.output_tokens * prices.output_micros)

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hincrby(run_key, "inflight_micros", -reserved_micros)
            pipe.hincrby(run_key, "concurrent", -1)
            if spend_micros:
                pipe.hincrby(run_key, "spend_micros", spend_micros)
            pipe.delete(reservation_key)
            pipe.expire(run_key, self.settings.run_ttl_seconds)
            await pipe.execute()

        current = await self.redis.hgetall(run_key)
        if current and _to_int(current.get("spend_micros")) >= _to_int(current.get("budget_micros")):
            await self.redis.hset(
                run_key,
                mapping={
                    "halt": "1",
                    "halt_reason": "cost_budget",
                },
            )
