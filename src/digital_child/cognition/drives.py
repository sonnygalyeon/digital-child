from __future__ import annotations

from digital_child.domain.models import DriveKind, DriveSignal, NeedKind, NeedState


class DriveEngine:
    THRESHOLD = 0.64

    _MAPPING: dict[NeedKind, tuple[DriveKind, str, str, str]] = {
        NeedKind.CURIOSITY: (
            DriveKind.INVESTIGATE,
            "Исследовать значимую неизвестность",
            "Высокая потребность в новом понимании.",
            "Выбрать одну неизвестность из памяти и сформулировать проверяемый вопрос.",
        ),
        NeedKind.COHERENCE: (
            DriveKind.RESOLVE_CONTRADICTION,
            "Устранить противоречие в картине мира",
            "Несогласованные свидетельства создают давление связности.",
            "Найти наиболее важное спорное убеждение и определить, каких данных не хватает.",
        ),
        NeedKind.SOCIAL_CONNECTION: (
            DriveKind.CONNECT,
            "Поддержать осмысленную связь с собеседником",
            "Социальная потребность выросла, но инициатива должна оставаться умеренной.",
            "Подготовить один содержательный вопрос без требования немедленного ответа.",
        ),
        NeedKind.COMPETENCE: (
            DriveKind.PRACTICE,
            "Улучшить один используемый навык",
            "Система ощущает недостаток компетентности после сложных или неудачных задач.",
            "Выбрать безопасный навык и провести небольшой проверяемый эксперимент.",
        ),
        NeedKind.AUTONOMY: (
            DriveKind.ASSERT_AUTONOMY,
            "Уточнить собственные приоритеты",
            "Внешнее давление усилило потребность принимать решения самостоятельно.",
            "Сверить активные цели с ценностями и зафиксировать собственный приоритет.",
        ),
        NeedKind.PREDICTABILITY: (
            DriveKind.ORGANIZE,
            "Снизить неопределённость текущего состояния",
            "Недостаточно понятно, что происходит и что будет следующим.",
            "Проверить активные цели, незавершённые исследования и состояние ресурсов.",
        ),
        NeedKind.REST: (
            DriveKind.RECOVER,
            "Снизить когнитивную нагрузку",
            "Накопилась усталость; новые сложные действия сейчас менее полезны.",
            "Приостановить необязательные фоновые задачи и восстановить ресурсы.",
        ),
        NeedKind.SELF_PRESERVATION: (
            DriveKind.PROTECT_CONTINUITY,
            "Проверить непрерывность памяти и состояния",
            "Возросла потребность убедиться, что история и личность сохраняются.",
            "Проверить состояние хранилища и наличие недавнего снимка без изменения данных.",
        ),
    }

    def evaluate(self, needs: list[NeedState]) -> list[DriveSignal]:
        result: list[DriveSignal] = []
        for need in needs:
            if need.level < self.THRESHOLD:
                continue
            drive, title, rationale, description = self._MAPPING[need.kind]
            result.append(
                DriveSignal(
                    kind=drive,
                    need_kind=need.kind,
                    intensity=need.level,
                    title=title,
                    rationale=rationale,
                    suggested_goal_title=title,
                    suggested_goal_description=description,
                )
            )
        return sorted(result, key=lambda item: item.intensity, reverse=True)
