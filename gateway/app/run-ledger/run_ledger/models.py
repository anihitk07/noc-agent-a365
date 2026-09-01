from datetime import datetime

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    run_id: str = Field(min_length=1)
    budget_micros: int = Field(gt=0)
    policy_set: str = "default"
    ttl_seconds: int | None = Field(default=None, gt=0)
    intent: str | None = None
    user: str | None = None
    team: str | None = None
    task: str | None = None


class RunCreateResponse(BaseModel):
    run_id: str
    budget_micros: int
    policy_set: str
    run_token: str
    expires_at: datetime


class PrecallRequest(BaseModel):
    run_id: str
    agent: str
    step: str
    model: str
    est_input_tokens: int = Field(ge=0)
    max_output_tokens: int | None = Field(default=None, ge=0)
    prompt_hash: str


class PrecallResponse(BaseModel):
    action: str
    model_override: str | None = None
    max_output_tokens: int | None = None
    inject: str | None = None
    halt_reason: str | None = None
    reservation_id: str | None = None


class PostcallRequest(BaseModel):
    run_id: str
    reservation_id: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    model: str | None = None
    failed: bool = False
