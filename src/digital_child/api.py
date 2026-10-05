from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from digital_child import __version__
from digital_child.agent import DigitalChildAgent
from digital_child.developmental_age import psychological_age_equivalent
from digital_child.models import (
    AgentState,
    AutonomyDecision,
    Belief,
    CognitiveEvent,
    CognitiveLoopStatus,
    ConsolidationReport,
    ConversationMessage,
    CycleResult,
    DevelopmentProfile,
    DriveSignal,
    EmotionState,
    Episode,
    EvidenceRecord,
    Goal,
    IdentityProfile,
    InteractionResult,
    LLMHealth,
    MemorySummary,
    NeedState,
    Observation,
    RelationshipProfile,
    ResearchReport,
    ResourceBudget,
    SourceRecord,
)
from digital_child.service import create_agent


class RestRequest(BaseModel):
    amount: float = Field(default=0.25, ge=0.0, le=1.0)


class InteractionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    person_id: str = Field(default="api-user", min_length=1, max_length=200)
    force_research: bool = False


class StateResponse(BaseModel):
    state: AgentState
    profile: DevelopmentProfile
    emotion: EmotionState
    psychological_age_equivalent: float


def create_app(database_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.agent = create_agent(database_path)
        app.state.agent.start_cognitive_loop()
        yield
        app.state.agent.close()

    application = FastAPI(
        title="Digital Child API",
        version=__version__,
        description=(
            "Event-driven needs, developmental psychology, self-generated goals, "
            "bounded cognitive loop, memory and LLM integration."
        ),
        lifespan=lifespan,
    )

    def get_agent(request: Request) -> DigitalChildAgent:
        return cast(DigitalChildAgent, request.app.state.agent)

    def require_operator(request: Request) -> None:
        expected = os.environ.get("DIGITAL_CHILD_OPERATOR_TOKEN", "").strip()
        provided = request.headers.get("X-Operator-Token", "")
        if not expected or provided != expected:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Operator token is required. Set DIGITAL_CHILD_OPERATOR_TOKEN and "
                    "send it in X-Operator-Token."
                ),
            )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @application.get("/v1/state", response_model=StateResponse)
    def get_state(request: Request) -> StateResponse:
        agent = get_agent(request)
        return StateResponse(
            state=agent.state,
            profile=agent.profile,
            emotion=agent.emotion,
            psychological_age_equivalent=psychological_age_equivalent(agent.profile),
        )

    @application.get("/v1/diagnostics")
    def diagnostics(request: Request) -> dict[str, object]:
        return get_agent(request).diagnostics()

    @application.get("/v1/psychology")
    def psychology(request: Request) -> dict[str, object]:
        agent = get_agent(request)
        return agent.psychology.diagnostics(agent.profile)

    @application.get("/v1/llm", response_model=LLMHealth)
    def llm_health(request: Request) -> LLMHealth:
        return get_agent(request).llm_health()

    @application.get("/v1/conversation/{person_id}", response_model=list[ConversationMessage])
    def conversation(
        person_id: str, request: Request, limit: int = 50
    ) -> list[ConversationMessage]:
        return get_agent(request).repository.recent_conversation(
            person_id,
            max(1, min(limit, 500)),
        )

    @application.get("/v1/identity", response_model=IdentityProfile)
    def identity(request: Request) -> IdentityProfile:
        return get_agent(request).identity

    @application.get("/v1/goals", response_model=list[Goal])
    def goals(request: Request, limit: int = 100, active_only: bool = True) -> list[Goal]:
        return get_agent(request).repository.list_goals(
            max(1, min(limit, 500)),
            active_only=active_only,
        )

    @application.get("/v1/needs", response_model=list[NeedState])
    def needs(request: Request) -> list[NeedState]:
        return get_agent(request).cognitive_loop.needs()

    @application.get("/v1/drives", response_model=list[DriveSignal])
    def drives(request: Request) -> list[DriveSignal]:
        return get_agent(request).cognitive_loop.drives()

    @application.get("/v1/background", response_model=CognitiveLoopStatus)
    def background(request: Request) -> CognitiveLoopStatus:
        return get_agent(request).cognitive_loop.status

    @application.get("/v1/background/events", response_model=list[CognitiveEvent])
    def background_events(request: Request, limit: int = 100) -> list[CognitiveEvent]:
        return get_agent(request).repository.recent_cognitive_events(max(1, min(limit, 500)))

    @application.get("/v1/background/budgets", response_model=list[ResourceBudget])
    def background_budgets(request: Request) -> list[ResourceBudget]:
        return get_agent(request).cognitive_loop.budgets.list()

    @application.post("/v1/background/pause", response_model=CognitiveLoopStatus)
    def pause_background(request: Request) -> CognitiveLoopStatus:
        return get_agent(request).pause_cognitive_loop()

    @application.post("/v1/background/resume", response_model=CognitiveLoopStatus)
    def resume_background(request: Request) -> CognitiveLoopStatus:
        return get_agent(request).resume_cognitive_loop()

    @application.post("/v1/background/tick", response_model=CognitiveLoopStatus)
    def tick_background(request: Request) -> CognitiveLoopStatus:
        return get_agent(request).cognitive_tick()

    @application.post("/v1/interactions", response_model=InteractionResult)
    def interact(payload: InteractionRequest, request: Request) -> InteractionResult:
        try:
            return get_agent(request).interact(
                payload.text,
                person_id=payload.person_id,
                force_research=payload.force_research,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get("/v1/relationships/{person_id}", response_model=RelationshipProfile)
    def relationship(person_id: str, request: Request) -> RelationshipProfile:
        return get_agent(request).trust_engine.get_or_create(person_id)

    @application.get("/v1/decisions", response_model=list[AutonomyDecision])
    def decisions(request: Request, limit: int = 100) -> list[AutonomyDecision]:
        return get_agent(request).repository.list_decisions(max(1, min(limit, 500)))

    @application.get("/v1/research", response_model=list[ResearchReport])
    def research_reports(request: Request, limit: int = 100) -> list[ResearchReport]:
        return get_agent(request).repository.list_research_reports(max(1, min(limit, 500)))

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
        require_operator(request)
        get_agent(request).reset()

    return application


app = create_app()
