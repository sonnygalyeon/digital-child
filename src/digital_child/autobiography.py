from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field

from digital_child.appraisal import topic_tokens
from digital_child.models import DevelopmentProfile, Episode, ResearchReport, StrictModel
from digital_child.storage import SQLiteRepository


class BiographyChapter(StrictModel):
    id: str
    title: str
    stage: str
    episode_ids: list[str] = Field(default_factory=list, max_length=20)
    people: list[str] = Field(default_factory=list, max_length=20)
    milestones: list[str] = Field(default_factory=list, max_length=20)
    themes: list[str] = Field(default_factory=list, max_length=12)
    summary: str = ""
    revisions: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    research_outcomes: list[dict[str, str]] = Field(default_factory=list, max_length=20)


class Autobiography:
    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def chapters(self, limit: int = 20) -> list[BiographyChapter]:
        return [
            BiographyChapter.model_validate(item)
            for item in self.repository.list_features("biography", self.subject_id, limit)
        ]

    def record(
        self,
        episode: Episode,
        profile: DevelopmentProfile,
        person_id: str | None = None,
        decision: str = "",
        relationship_change: float = 0.0,
    ) -> None:
        chapters = self.chapters(1)
        chapter = chapters[0] if chapters else None
        if (
            chapter is None
            or len(chapter.episode_ids) >= 20
            or chapter.stage != profile.stage.value
            or (chapter.people and chapter.people != [person_id])
        ):
            chapter = BiographyChapter(
                id=str(uuid4()),
                stage=profile.stage.value,
                title=f"Опыт {profile.stage.value}: с эпизода {episode.sequence}",
            )
        if episode.id in chapter.episode_ids:
            return
        chapter.episode_ids.append(episode.id)
        if person_id and person_id not in chapter.people:
            chapter.people.append(person_id)
        chapter.themes = list(dict.fromkeys(chapter.themes + topic_tokens(episode.content)))[:12]
        event = (
            f"Эпизод {episode.sequence}: действие {episode.action}, результат {episode.outcome}; "
            f"получено {episode.effective_units:.2f} DEU"
        )
        if decision:
            event += f"; выбор в диалоге: {decision}"
        if abs(relationship_change) > 0.001:
            event += f"; изменение эмоционального доверия: {relationship_change:+.3f}"
        chapter.milestones.append(event)
        self._refresh_summary(chapter)
        self._save(chapter)

    @staticmethod
    def _refresh_summary(chapter: BiographyChapter) -> None:
        chapter.summary = (
            f"Сохранено эпизодов: {len(chapter.episode_ids)}. "
            f"Темы: {', '.join(chapter.themes[:6])}. "
            + " ".join(chapter.milestones[-3:])
            + " ".join(item["summary"] for item in chapter.research_outcomes[-2:])
        )

    def record_research(self, report: ResearchReport, source_episode_id: str | None) -> None:
        if source_episode_id is None:
            return
        chapter = next(
            (item for item in self.chapters(500) if source_episode_id in item.episode_ids), None
        )
        if chapter is None or any(
            item["report_id"] == report.id for item in chapter.research_outcomes
        ):
            return
        summary = (
            f" Проверка прежнего утверждения «{report.claim[:180]}»: {report.summary[:250]}. "
            "Сохранён результат проверки по внешним свидетельствам."
        )
        chapter.research_outcomes = (
            chapter.research_outcomes
            + [
                {
                    "report_id": report.id,
                    "source_episode_id": source_episode_id,
                    "summary": summary,
                    "sources": "; ".join(result.url for result in report.results[:3]),
                }
            ]
        )[-20:]
        self._refresh_summary(chapter)
        self._save(chapter)

    def revise(self, chapter_id: str, correction: str) -> BiographyChapter:
        payload = self.repository.load_feature("biography", chapter_id, self.subject_id)
        if payload is None:
            raise ValueError("Глава не найдена")
        if not correction.strip() or len(correction) > 2000:
            raise ValueError("Поправка должна содержать от 1 до 2000 символов")
        chapter = BiographyChapter.model_validate(payload)
        chapter.revisions = (
            chapter.revisions
            + [
                {
                    "at": datetime.now(UTC).isoformat(),
                    "text": correction.strip(),
                    "status": "user_correction_unverified",
                }
            ]
        )[-20:]
        self._save(chapter)
        return chapter

    def sources(self, chapter_id: str) -> list[Episode]:
        payload = self.repository.load_feature("biography", chapter_id, self.subject_id)
        if payload is None:
            raise ValueError("Глава не найдена")
        chapter = BiographyChapter.model_validate(payload)
        return [
            episode
            for item in chapter.episode_ids
            if (episode := self.repository.get_episode(item)) is not None
        ]

    def summary(self, person_id: str) -> str:
        chapters = [
            item for item in self.chapters(12) if not item.people or item.people == [person_id]
        ]
        return (
            " | ".join(
                item.summary[:550]
                + (
                    " Причина пересмотра: " + item.research_outcomes[-1]["summary"][:350]
                    if item.research_outcomes
                    else ""
                )
                + (
                    " Поправка собеседника (не проверена): " + item.revisions[-1]["text"][:200]
                    if item.revisions
                    else ""
                )
                for item in chapters[:3]
            )
            or "Значимые главы ещё не сформированы."
        )

    def _save(self, chapter: BiographyChapter) -> None:
        self.repository.save_feature(
            "biography", chapter.id, self.subject_id, chapter.model_dump(mode="json")
        )
