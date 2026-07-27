from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from digital_child.agent import DigitalChildAgent
from digital_child.models import AgentState, CycleResult, DevelopmentProfile, Episode, Observation
from digital_child.service import create_agent


class RestRequest(BaseModel):
    amount: float = Field(default=0.25, ge=0.0, le=1.0)


class StateResponse(BaseModel):
    state: AgentState
    profile: DevelopmentProfile


def create_app(database_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.agent = create_agent(database_path)
        yield
        app.state.agent.repository.close()

    application = FastAPI(
        title="Digital Child API",
        version="0.1.0",
        description="Measurable developmental core for a digital agent.",
        lifespan=lifespan,
    )

    def get_agent(request: Request) -> DigitalChildAgent:
        return request.app.state.agent

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/state", response_model=StateResponse)
    def get_state(request: Request) -> StateResponse:
        agent = get_agent(request)
        return StateResponse(state=agent.state, profile=agent.profile)

    @application.post("/v1/observations", response_model=CycleResult)
    def add_observation(observation: Observation, request: Request) -> CycleResult:
        return get_agent(request).process_observation(observation)

    @application.post("/v1/rest", response_model=AgentState)
    def rest(payload: RestRequest, request: Request) -> AgentState:
        return get_agent(request).rest(payload.amount)

    @application.get("/v1/memory", response_model=list[Episode])
    def memory(request: Request, limit: int = 20) -> list[Episode]:
        bounded_limit = max(1, min(limit, 200))
        return get_agent(request).repository.recent_episodes(bounded_limit)

    @application.delete("/v1/state", status_code=204)
    def reset(request: Request) -> None:
        get_agent(request).reset()

    return application


app = create_app()
