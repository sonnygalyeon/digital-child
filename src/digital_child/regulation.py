from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field

from digital_child.associative_memory import concepts, features
from digital_child.models import StrictModel
from digital_child.storage import SQLiteRepository

RegulationStrategy = Literal["clarify", "split", "switch", "pause"]
GUIDANCE: dict[RegulationStrategy, str] = {
    "clarify": "Снизь неопределённость: попроси объяснить один конкретный непонятный момент.",
    "split": "Предложи только первый небольшой шаг и разбей дальнейшую задачу на части.",
    "switch": "Предложи временно сменить способ решения или занятие, сохранив исходный вопрос.",
    "pause": "Предложи короткую паузу и обозначь, с какого шага можно продолжить после неё.",
}


class RegulationAttempt(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    person_id: str
    episode_id: str
    strategy: RegulationStrategy
    load_before: float
    energy_before: float
    applied: bool = False
    status: str = "pending"
    load_after: float | None = None
    relief: float | None = None
    resumed: bool | None = None
    outcome_episode_id: str | None = None
    feedback: bool | None = None
    task_features: list[str] = Field(default_factory=list)


class RegulationLearner:
    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def history(self, person_id: str | None = None, limit: int = 100) -> list[RegulationAttempt]:
        rows = [
            RegulationAttempt.model_validate(item)
            for item in self.repository.list_features("regulation", self.subject_id, limit)
        ]
        return [item for item in rows if person_id is None or item.person_id == person_id]

    def observe_next(
        self,
        person_id: str,
        load: float,
        resumed: bool,
        episode_id: str,
        now: datetime,
        text: str = "",
    ) -> None:
        for item in self.history(person_id):
            if item.status != "pending":
                continue
            if (now - item.created_at).total_seconds() > 3600:
                item.status = "expired"
            elif item.task_features and not set(item.task_features) & features(
                text, concepts(text)
            ):
                item.status = "context_changed"
                item.outcome_episode_id = episode_id
            else:
                item.load_after = load
                item.relief = max(-1.0, min(1.0, item.load_before - load))
                item.resumed = resumed
                item.outcome_episode_id = episode_id
                item.status = "observed_association"
            self.save(item)

    def choose(
        self,
        person_id: str,
        load: float,
        energy: float,
        episode_id: str,
        now: datetime,
        ambiguous: bool,
        text: str = "",
    ) -> RegulationAttempt | None:
        if load < 0.45 and energy >= 0.35 and not ambiguous:
            return None
        choices: list[RegulationStrategy] = ["clarify", "split", "switch"]
        if energy < 0.35:
            choices = ["pause", "split"]
        elif ambiguous:
            choices = ["clarify", "split"]
        history = self.history(person_id)

        def score(strategy: RegulationStrategy) -> float:
            trials = [
                item
                for item in history
                if item.strategy == strategy
                and (item.feedback is not None or item.status == "observed_association")
            ]
            total = sum(
                float(item.feedback)
                if item.feedback is not None
                else 0.5 + 0.4 * (item.relief or 0) + 0.1 * bool(item.resumed)
                for item in trials
            )
            # Exploration bonus diminishes with actual observed uses.
            return (1 + total) / (2 + len(trials)) + 0.15 / (1 + len(trials))

        return RegulationAttempt(
            person_id=person_id,
            episode_id=episode_id,
            strategy=max(choices, key=score),
            load_before=load,
            energy_before=energy,
            created_at=now,
            task_features=sorted(features(text, concepts(text))),
        )

    def finish(self, attempt: RegulationAttempt, response: str) -> None:
        patterns = {
            "clarify": r"\?",
            "split": r"шаг|част[ьи]|сначала|1[.)]",
            "switch": r"друг|смен|переключ",
            "pause": r"пауз|перерыв|отдох",
        }
        attempt.applied = bool(re.search(patterns[attempt.strategy], response, re.I))
        if not attempt.applied:
            attempt.status = "not_applied"
        self.save(attempt)

    def feedback(self, attempt_id: str, helpful: bool) -> RegulationAttempt:
        row = self.repository.load_feature("regulation", attempt_id, self.subject_id)
        if not row:
            raise ValueError("Попытка саморегуляции не найдена")
        item = RegulationAttempt.model_validate(row)
        if not item.applied:
            raise ValueError("Стратегия не была выражена в ответе")
        item.feedback = helpful
        self.save(item)
        return item

    def save(self, item: RegulationAttempt) -> None:
        self.repository.save_feature(
            "regulation", item.id, self.subject_id, item.model_dump(mode="json")
        )
