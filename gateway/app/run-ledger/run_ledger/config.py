"""Environment-driven settings for the run-ledger service."""

import json
import os
from dataclasses import dataclass, field

from run_ledger.decide import Policies, Prices


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value in (None, "") else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return default if value in (None, "") else float(value)


@dataclass(frozen=True)
class Settings:
    key_vault_url: str
    run_token_signing_secret_name: str
    redis_host: str
    redis_port: int = 10000
    run_ttl_seconds: int = 3600
    reservation_ttl_seconds: int = 120
    jwt_issuer: str = "run-ledger"
    jwt_lifetime_seconds: int = 3600
    default_policy_set: str = "default"
    model_prices: dict = field(default_factory=dict)
    policies: Policies = field(default_factory=Policies)

    @classmethod
    def from_env(cls) -> "Settings":
        prices = json.loads(os.environ.get("MODEL_PRICES_JSON", "{}"))
        return cls(
            key_vault_url=os.environ["KEY_VAULT_URL"],
            run_token_signing_secret_name=os.environ["RUN_TOKEN_SIGNING_SECRET_NAME"],
            redis_host=os.environ.get("REDIS_HOST_NAME", ""),
            redis_port=_env_int("REDIS_PORT", 10000),
            run_ttl_seconds=_env_int("RUN_TTL_SECONDS", 3600),
            reservation_ttl_seconds=_env_int("RUN_RESERVATION_TTL_SECONDS", 120),
            jwt_issuer=os.environ.get("RUN_TOKEN_ISSUER", "run-ledger"),
            jwt_lifetime_seconds=_env_int("RUN_TOKEN_LIFETIME_SECONDS", 3600),
            default_policy_set=os.environ.get("DEFAULT_POLICY_SET", "default"),
            model_prices=prices,
            policies=Policies(
                max_steps=_env_int("RUN_MAX_STEPS", 20),
                max_concurrent=_env_int("RUN_MAX_CONCURRENT", 4),
                guard_threshold=_env_float("RUN_GUARD_THRESHOLD", 0.8),
                default_max_output=_env_int("RUN_DEFAULT_MAX_OUTPUT", 1024),
                cheap_model=os.environ.get("RUN_CHEAP_MODEL", "gpt-5.4-mini"),
                loop_window=_env_int("RUN_LOOP_WINDOW", 6),
                loop_repeats=_env_int("RUN_LOOP_REPEATS", 3),
            ),
        )

    def prices_for(self, model: str) -> Prices:
        # ponytail: unknown model prices fail open at $0 until pricing wiring is added.
        rate = self.model_prices.get(model, {})
        return Prices(
            input_micros=float(rate.get("prompt", 0.0)) * 1000.0,
            output_micros=float(rate.get("completion", 0.0)) * 1000.0,
        )
