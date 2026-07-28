from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from digital_child.agent import DigitalChildAgent
from digital_child.models import (
    AgentState,
    Belief,
    ConsolidationReport,
    CycleResult,
    DevelopmentProfile,
    Episode,
    EvidenceRecord,
    MemorySummary,
    Observation,
    SourceRecord,
)
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
        version="0.2.0",
        description="Developmental memory, evidence and belief core.",
        lifespan=lifespan,
    )

    def get_agent(request: Request) -> DigitalChildAgent:
        return request.app.state.agent

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.2.0"}

    @application.get("/v1/state", response_model=StateResponse)
    def get_state(request: Request) -> StateResponse:
        agent = get_agent(request)
        return StateResponse(state=agent.state, profile=agent.profile)

    @application.post("/v1/observations", response_model=CycleResult)
    def add_observation(observation: Observation, request: Request) -> CycleResult:
        try:
            return get_agent(request).process_observation(observation)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/v1/sources", response_model=SourceRecord, status_code=201)
    def add_source(source: SourceRecord, request: Request) -> SourceRecord:
        get_agent(request).repository.save_source(source)
        return source

    @application.get("/v1/sources", response_model=list[SourceRecord])
    def sources(request: Request, limit: int = 100) -> list[SourceRecord]:
        return get_agent(request).repository.list_sources(max(1, min(limit, 500)))

    @application.get("/v1/beliefs", response_model=list[Belief])
    def beliefs(request: Request, limit: int = 100) -> list[Belief]:
        return get_agent(request).repository.list_beliefs(max(1, min(limit, 500)))

    @application.get("/v1/beliefs/{belief_id}/evidence", response_model=list[EvidenceRecord])
    def belief_evidence(belief_id: str, request: Request) -> list[EvidenceRecord]:
        return get_agent(request).repository.evidence_for_belief(belief_id)

    @application.get("/v1/memory", response_model=list[Episode])
    def memory(
        request: Request,
        limit: int = 20,
        include_archived: bool = False,
    ) -> list[Episode]:
        return get_agent(request).repository.recent_episodes(
            max(1, min(limit, 500)),
            include_archived=include_archived,
        )

    @application.get("/v1/memory/summaries", response_model=list[MemorySummary])
    def memory_summaries(request: Request, limit: int = 100) -> list[MemorySummary]:
        return get_agent(request).repository.list_memory_summaries(max(1, min(limit, 500)))

    @application.post("/v1/memory/consolidate", response_model=ConsolidationReport)
    def consolidate(request: Request) -> ConsolidationReport:
        return get_agent(request).consolidate_memory()

    @application.post("/v1/rest", response_model=AgentState)
    def rest(payload: RestRequest, request: Request) -> AgentState:
        return get_agent(request).rest(payload.amount)

    @application.delete("/v1/state", status_code=204)
    def reset(request: Request) -> None:
        get_agent(request).reset()

    return application


app = create_app()
