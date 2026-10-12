from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field

from digital_child.models import Episode, ResearchReport, StrictModel
from digital_child.storage import SQLiteRepository


class StateChange(StrictModel):
    before: float | str | None = None
    after: float | str | None = None


class DevelopmentEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: str
    title: str
    person_id: str | None = None
    changes: dict[str, StateChange] = Field(default_factory=dict)
    episode_ids: list[str] = Field(default_factory=list)
    report_id: str | None = None
    evidence: list[dict[str, str]] = Field(default_factory=list)
    related_records: dict[str, str] = Field(default_factory=dict)


class DevelopmentTimeline:
    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def record(
        self,
        kind: str,
        title: str,
        before: dict[str, float | str],
        after: dict[str, float | str],
        *,
        person_id: str | None = None,
        episode_ids: list[str] | None = None,
        report: ResearchReport | None = None,
        now: datetime | None = None,
        related_records: dict[str, str] | None = None,
    ) -> DevelopmentEvent:
        changes = {
            key: StateChange(before=before.get(key), after=after.get(key))
            for key in after.keys()
            if before.get(key) != after.get(key)
        }
        event = DevelopmentEvent(
            kind=kind,
            title=title[:400],
            person_id=person_id,
            related_records=related_records or {},
            changes=changes,
            episode_ids=episode_ids or [],
            created_at=now or datetime.now(UTC),
            report_id=None if report is None else report.id,
            evidence=[]
            if report is None
            else [
                {"url": item.url, "title": item.title, "excerpt": item.snippet[:700]}
                for item in report.results[:5]
            ],
        )
        self.repository.save_feature(
            "timeline", event.id, self.subject_id, event.model_dump(mode="json")
        )
        return event

    def history(self, person_id: str | None = None, limit: int = 50) -> list[DevelopmentEvent]:
        rows = [
            DevelopmentEvent.model_validate(item)
            for item in self.repository.list_features("timeline", self.subject_id, 500)
        ]
        return [item for item in rows if person_id is None or item.person_id in (None, person_id)][
            : max(1, min(limit, 500))
        ]

    def detail(self, event_id: str) -> tuple[DevelopmentEvent, list[Episode]]:
        row = self.repository.load_feature("timeline", event_id, self.subject_id)
        if row is None:
            raise ValueError("Событие развития не найдено")
        event = DevelopmentEvent.model_validate(row)
        return event, [
            episode
            for key in event.episode_ids
            if (episode := self.repository.get_episode(key)) is not None
        ]

    def related(self, event: DevelopmentEvent) -> dict[str, object]:
        return {
            kind: payload
            for kind, key in event.related_records.items()
            if (payload := self.repository.load_feature(kind, key, self.subject_id)) is not None
        }
