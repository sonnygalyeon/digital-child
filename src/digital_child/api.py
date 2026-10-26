from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from digital_child import __version__
from digital_child.action_plans import ActionPlan, PlanKind, PlanStep
from digital_child.agent import DigitalChildAgent
from digital_child.autobiography import BiographyChapter
from digital_child.communication import CommunicationPreferences
from digital_child.developmental_age import psychological_age_equivalent
from digital_child.experiments import Demonstration, ExperimentKind, ExperimentTrial
from digital_child.models import (
    AgentState,
    AutonomyDecision,
    Belief,
    CognitiveEvent,
    CognitiveLoopStatus,
    ConsolidationReport,
    ConversationMessage,
    CycleResult,
    DeferredVerification,
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


class BiographyCorrection(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ExperimentRequest(BaseModel):
    kind: ExperimentKind = "balance"


class PlanRequest(BaseModel):
    kind: PlanKind = "route"
    max_steps: int = Field(default=12, ge=2, le=20)
    autonomous: bool = False


class MemoryBackfillRequest(BaseModel):
    batch_size: int = Field(default=100, ge=1, le=2000)


class InteractionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    person_id: str = Field(default="api-user", min_length=1, max_length=200)
    force_research: bool = False


class PersonModelCorrection(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    clear_notes: bool = False


class RegulationFeedback(BaseModel):
    helpful: bool


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

    @application.get("/v1/initiative")
    def initiative(request: Request) -> dict[str, object]:
        return get_agent(request).initiative_status()

    @application.post("/v1/initiative/{enabled}", dependencies=[Depends(require_operator)])
    def configure_initiative(enabled: bool, request: Request) -> dict[str, object]:
        agent = get_agent(request)
        agent.set_initiative_enabled(enabled)
        return agent.initiative_status()

    @application.get("/v1/interests")
    def interests(request: Request) -> object:
        agent = get_agent(request)
        return agent.psychology.diagnostics(agent.profile)["preferred_interests"]

    @application.get("/v1/time")
    def time_status(request: Request) -> dict[str, object]:
        return get_agent(request).clock.diagnostics()

    @application.get("/v1/verifications", response_model=list[DeferredVerification])
    def verifications(request: Request, limit: int = 20) -> list[DeferredVerification]:
        return get_agent(request).repository.list_verifications(limit)

    @application.get("/v1/llm", response_model=LLMHealth)
    def llm_health(request: Request) -> LLMHealth:
        return get_agent(request).llm_health()

    @application.get("/v1/inference")
    def inference(request: Request) -> dict[str, object]:
        return get_agent(request).inference_diagnostics()

    @application.get("/v1/communication/{person_id}", response_model=CommunicationPreferences)
    def communication(person_id: str, request: Request) -> CommunicationPreferences:
        return get_agent(request).communication.get(person_id)

    @application.patch(
        "/v1/communication/{person_id}",
        dependencies=[Depends(require_operator)],
        response_model=CommunicationPreferences,
    )
    def update_communication(
        person_id: str, patch: CommunicationPreferences, request: Request
    ) -> CommunicationPreferences:
        try:
            return get_agent(request).update_communication(
                person_id, patch.model_dump(exclude_unset=True, exclude={"topic_snoozes"})
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/v1/biography", response_model=list[BiographyChapter])
    def biography(request: Request, limit: int = 20) -> list[BiographyChapter]:
        return get_agent(request).autobiography.chapters(limit)

    @application.get("/v1/biography/{chapter_id}/sources", response_model=list[Episode])
    def biography_sources(chapter_id: str, request: Request) -> list[Episode]:
        try:
            return get_agent(request).autobiography.sources(chapter_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/biography/{chapter_id}/corrections",
        dependencies=[Depends(require_operator)],
        response_model=BiographyChapter,
    )
    def correct_biography(
        chapter_id: str, correction: BiographyCorrection, request: Request
    ) -> BiographyChapter:
        agent = get_agent(request)
        try:
            with agent._interaction_lock:
                return agent.autobiography.revise(chapter_id, correction.text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/v1/experiments", response_model=list[ExperimentTrial])
    def experiments(request: Request, limit: int = 20) -> list[ExperimentTrial]:
        return get_agent(request).experiments.history(limit)

    @application.post(
        "/v1/experiments", dependencies=[Depends(require_operator)], response_model=ExperimentTrial
    )
    def run_experiment(payload: ExperimentRequest, request: Request) -> ExperimentTrial:
        try:
            return get_agent(request).run_experiment(payload.kind)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/v1/value-conflicts")
    def conflicts(request: Request) -> list[dict[str, object]]:
        return get_agent(request).psychology.snapshot().value_conflicts

    @application.get("/v1/associations")
    def associations(request: Request, query: str, person_id: str = "local-user") -> object:
        agent = get_agent(request)
        with agent._interaction_lock:
            return agent.associative_memory.search(query[:10000], person_id)

    @application.get("/v1/competence")
    def competence(request: Request) -> object:
        return get_agent(request).competence.diagnostics()

    @application.get("/v1/memory-index")
    def memory_index(request: Request) -> dict[str, int]:
        return get_agent(request).associative_memory.index_status()

    @application.post("/v1/memory-index/backfill", dependencies=[Depends(require_operator)])
    def backfill_memory(payload: MemoryBackfillRequest, request: Request) -> dict[str, int]:
        agent = get_agent(request)
        with agent._interaction_lock:
            return agent.associative_memory.backfill(payload.batch_size)

    @application.get("/v1/plans", response_model=list[ActionPlan])
    def plans(request: Request, limit: int = 20) -> list[ActionPlan]:
        return get_agent(request).plans.history(limit)

    @application.get("/v1/plans/active", response_model=ActionPlan | None)
    def active_plan(request: Request) -> ActionPlan | None:
        return get_agent(request).plans.active()

    @application.get("/v1/plans/{plan_id}", response_model=ActionPlan)
    def get_plan(plan_id: str, request: Request) -> ActionPlan:
        try:
            return get_agent(request).plans.get(plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/plans", response_model=ActionPlan, dependencies=[Depends(require_operator)]
    )
    def start_plan(payload: PlanRequest, request: Request) -> ActionPlan:
        try:
            return get_agent(request).start_plan(
                payload.kind, payload.max_steps, autonomous=payload.autonomous
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/v1/plans/{plan_id}/step",
        response_model=PlanStep,
        dependencies=[Depends(require_operator)],
    )
    def step_plan(plan_id: str, request: Request) -> PlanStep:
        try:
            return get_agent(request).step_plan(plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/v1/plans/{plan_id}/run",
        response_model=ActionPlan,
        dependencies=[Depends(require_operator)],
    )
    def run_plan(plan_id: str, request: Request) -> ActionPlan:
        try:
            return get_agent(request).run_plan(plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/v1/plans/{plan_id}/cancel",
        response_model=ActionPlan,
        dependencies=[Depends(require_operator)],
    )
    def cancel_plan(plan_id: str, request: Request) -> ActionPlan:
        try:
            return get_agent(request).cancel_plan(plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/v1/action-outcomes")
    def action_outcomes(request: Request, limit: int = 20) -> list[dict[str, object]]:
        agent = get_agent(request)
        return agent.repository.list_features("action_attribution", agent.identity.id, limit)

    @application.get("/v1/curriculum")
    def curriculum(request: Request) -> object:
        return get_agent(request).learning_curriculum()

    @application.get("/v1/demonstrations")
    def demonstrations(request: Request) -> object:
        return get_agent(request).experiments.demonstrations()

    @application.post("/v1/demonstrations", dependencies=[Depends(require_operator)])
    def demonstrate(payload: Demonstration, request: Request) -> object:
        return get_agent(request).demonstrate(payload)

    @application.get("/v1/person-model/{person_id}")
    def person_model(person_id: str, request: Request) -> object:
        return get_agent(request).interlocutors.get(person_id)

    @application.patch("/v1/person-model/{person_id}", dependencies=[Depends(require_operator)])
    def correct_person_model(
        person_id: str, payload: PersonModelCorrection, request: Request
    ) -> object:
        try:
            return get_agent(request).correct_interlocutor(
                person_id, payload.text, clear_notes=payload.clear_notes
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/v1/regulation")
    def regulation(request: Request, person_id: str = "local-user") -> object:
        return get_agent(request).regulation.history(person_id)

    @application.post(
        "/v1/regulation/{attempt_id}/feedback", dependencies=[Depends(require_operator)]
    )
    def regulation_feedback(
        attempt_id: str, payload: RegulationFeedback, request: Request
    ) -> object:
        try:
            return get_agent(request).regulation_feedback(attempt_id, payload.helpful)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/v1/timeline")
    def timeline(request: Request, person_id: str | None = None, limit: int = 50) -> object:
        return get_agent(request).timeline.history(person_id, limit)

    @application.get("/v1/timeline/{event_id}")
    def timeline_detail(event_id: str, request: Request) -> object:
        try:
            event, episodes = get_agent(request).timeline.detail(event_id)
            return {
                "event": event,
                "episodes": episodes,
                "related": get_agent(request).timeline.related(event),
            }
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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
