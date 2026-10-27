from __future__ import annotations

import re

from pydantic import Field

from digital_child.domain.models import MessageAnalysis, MessageIntent, StrictModel
from digital_child.infrastructure.repository import SQLiteRepository
from digital_child.memory.associative_memory import concepts


class PersonNote(StrictModel):
    kind: str
    text: str = Field(min_length=1, max_length=1000)
    episode_id: str
    status: str = "speaker_report_unverified"


class InterlocutorModel(StrictModel):
    person_id: str
    notes: list[PersonNote] = Field(default_factory=list, max_length=40)
    explanations: dict[str, int] = Field(default_factory=dict, max_length=40)
    example_preference: str = "не сообщено"
    revisions: list[str] = Field(default_factory=list, max_length=20)


class InterlocutorMemory:
    def __init__(self, repository: SQLiteRepository, subject_id: str) -> None:
        self.repository, self.subject_id = repository, subject_id

    def get(self, person_id: str) -> InterlocutorModel:
        saved = self.repository.load_feature("interlocutor", person_id, self.subject_id)
        return (
            InterlocutorModel.model_validate(saved)
            if saved
            else InterlocutorModel(person_id=person_id)
        )

    def observe(self, person_id: str, analysis: MessageAnalysis, episode_id: str) -> None:
        model = self.get(person_id)
        # Only direct self-reports, never inferred intelligence or private attributes.
        text = analysis.pragmatic_text.strip()
        if not analysis.quoted_speech and analysis.irony_probability < 0.5:
            if analysis.intent == MessageIntent.OPINION or analysis.is_subjective:
                model.notes = (
                    model.notes
                    + [PersonNote(kind="expressed_view", text=text[:1000], episode_id=episode_id)]
                )[-40:]
            if re.search(
                r"я (?:уже )?(?:знаю|понимаю|не понимаю|не знаю)|мне (?:понятно|непонятно)",
                text,
                re.I,
            ):
                model.notes = (
                    model.notes
                    + [
                        PersonNote(
                            kind="reported_understanding", text=text[:1000], episode_id=episode_id
                        )
                    ]
                )[-40:]
            if re.search(
                r"(?:объясняй|показывай|мне понятнее|лучше понимаю).*(?:пример|схем|аналог)",
                text,
                re.I,
            ):
                model.example_preference = text[:240]
        self._save(model)

    def record_explanation(self, person_id: str, text: str) -> None:
        model = self.get(person_id)
        for topic in concepts(text):
            model.explanations[topic] = model.explanations.get(topic, 0) + 1
        model.explanations = dict(list(model.explanations.items())[-40:])
        self._save(model)

    def correct(self, person_id: str, text: str, *, clear_notes: bool = False) -> InterlocutorModel:
        if not text.strip() or len(text) > 1000:
            raise ValueError("Поправка должна содержать от 1 до 1000 символов")
        model = self.get(person_id)
        if clear_notes:
            model.notes = []
            model.explanations = {}
            model.example_preference = "не сообщено"
        model.revisions = (model.revisions + [text.strip()])[-20:]
        self._save(model)
        return model

    def summary(self, person_id: str, query: str) -> str:
        model = self.get(person_id)
        relevant = set(concepts(query))
        notes = [
            item for item in model.notes if not relevant or relevant & set(concepts(item.text))
        ][-3:]
        return (
            "Последняя поправка собеседника имеет приоритет: "
            + (model.revisions[-1][:280] if model.revisions else "нет")
            + f". Предпочтения примеров: {model.example_preference[:180]}. "
            + "Объяснения уже давались (это не доказывает понимание): "
            + str({key: value for key, value in model.explanations.items() if key in relevant})
            + ". Высказывания, не внешние факты: "
            + "; ".join(f"{item.text[:180]} [эпизод {item.episode_id}]" for item in notes[-2:])
            + ". Учитывай предыдущие объяснения, не повторяй их дословно."
        )

    def _save(self, model: InterlocutorModel) -> None:
        self.repository.save_feature(
            "interlocutor", model.person_id, self.subject_id, model.model_dump(mode="json")
        )
