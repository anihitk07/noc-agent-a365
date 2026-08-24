"""FastAPI app factory for the run-ledger service."""

from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Response

from run_ledger.models import PostcallRequest, PrecallRequest, RunCreateRequest
from run_ledger.service import RunLedgerService


@dataclass
class AppDeps:
    service: RunLedgerService


def app_factory(deps: AppDeps) -> FastAPI:
    app = FastAPI(title="Run Ledger")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.post("/v1/runs", status_code=201)
    async def create_run(body: RunCreateRequest):
        return await deps.service.create_run(body)

    @app.post("/v1/precall")
    async def precall(body: PrecallRequest):
        try:
            return await deps.service.precall(body)
        except KeyError:
            raise HTTPException(status_code=404, detail="run not found")

    @app.post("/v1/postcall", status_code=204)
    async def postcall(body: PostcallRequest):
        await deps.service.postcall(body)
        return Response(status_code=204)

    return app
