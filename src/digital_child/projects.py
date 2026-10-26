from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field

from digital_child.budgets import BudgetManager
from digital_child.models import Goal, GoalStatus, NeedKind, ResourceBudget, StrictModel
from digital_child.project_tools import ProjectTools, ToolResult
from digital_child.storage import SQLiteRepository

ToolName = Literal["memory_search", "note_write", "note_read"]
ProjectStatus = Literal["proposed", "active", "paused", "blocked", "completed", "cancelled"]


class ProjectStep(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: ToolName
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    expected_result: str
    expected_success: float = Field(default=0.5, ge=0, le=1)
    prediction_error: float | None = Field(default=None, ge=0, le=1)
    attempts: int = Field(default=0, ge=0, le=3)
    prepared_content: str | None = None
    result: ToolResult | None = None
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ProjectRevision(StrictModel):
    at: datetime
    reason: str
    previous_title: str
    title: str


class PersonalProject(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=500)
    person_id: str = Field(min_length=1, max_length=200)
    goal_id: str | None = None
    scope: Literal["memory_dossier"] = "memory_dossier"
    created_at: datetime
    updated_at: datetime
    status: ProjectStatus = "active"
    autonomous: bool = False
    steps: list[ProjectStep] = Field(default_factory=list, max_length=96)
    milestone_titles: list[str] = Field(default_factory=list, max_length=32)
    revisions: list[ProjectRevision] = Field(default_factory=list, max_length=20)
    stop_reason: str = ""

    @property
    def progress(self) -> float:
        return sum(item.status == "completed" for item in self.steps) / max(1, len(self.steps))


class ProjectSummary(StrictModel):
    id: str
    title: str
    person_id: str
    goal_id: str | None
    updated_at: datetime
    status: ProjectStatus
    autonomous: bool
    progress: float
    stop_reason: str
    next_step: str


class ProjectManager:
    """Durable goal-linked plans for local memory dossiers, independent of LLMs."""

    def __init__(
        self,
        repository: SQLiteRepository,
        subject_id: str,
        tools: ProjectTools,
        budgets: BudgetManager,
    ) -> None:
        self.repository, self.subject_id = repository, subject_id
        self.tools, self.budgets = tools, budgets

    def _save(self, project: PersonalProject) -> None:
        pending = next((s for s in project.steps if s.status != "completed"), None)
        summary = ProjectSummary(
            id=project.id,
            title=project.title,
            person_id=project.person_id,
            goal_id=project.goal_id,
            updated_at=project.updated_at,
            status=project.status,
            autonomous=project.autonomous,
            progress=project.progress,
            stop_reason=project.stop_reason,
            next_step="" if pending is None else pending.expected_result,
        )
        with self.repository.transaction():
            self.repository.save_feature(
                "personal_project", project.id, self.subject_id, project.model_dump(mode="json")
            )
            self.repository.save_feature(
                "project_summary", project.id, self.subject_id, summary.model_dump(mode="json")
            )

    def get(self, project_id: str) -> PersonalProject:
        saved = self.repository.load_feature("personal_project", project_id, self.subject_id)
        if saved is None:
            raise ValueError("Проект не найден")
        return PersonalProject.model_validate(saved)

    def history(self, person_id: str | None = None, limit: int = 30) -> list[ProjectSummary]:
        projects = [
            ProjectSummary.model_validate(item)
            for item in self.repository.list_features("project_summary", self.subject_id, 500)
        ]
        return [p for p in projects if person_id is None or p.person_id in {person_id, "agent"}][
            : max(1, min(limit, 500))
        ]

    @staticmethod
    def _milestone() -> list[ProjectStep]:
        return [
            ProjectStep(
                tool="memory_search", expected_result="Поиск доступных эпизодов с источниками"
            ),
            ProjectStep(tool="note_write", expected_result="Создание заметки в каталоге проектов"),
            ProjectStep(tool="note_read", expected_result="Чтение заметки и совпадение SHA-256"),
        ]

    def create(
        self,
        title: str,
        person_id: str,
        now: datetime,
        *,
        goal: Goal | None = None,
        proposed: bool = False,
    ) -> PersonalProject:
        project = PersonalProject(
            title=title.strip(),
            person_id=person_id,
            goal_id=None if goal is None else goal.id,
            created_at=now,
            updated_at=now,
            status="proposed" if proposed else "active",
            steps=self._milestone(),
            milestone_titles=[title.strip()],
        )

        def commit(budget: ResourceBudget) -> None:
            with self.repository.transaction():
                self._save(project)
                if goal is not None:
                    self.repository.save_feature(
                        "goal_project", goal.id, self.subject_id, {"project_id": project.id}
                    )
                self.repository.save_budget(budget)

        if not self.budgets.consume_with("personal_projects", commit):
            raise ValueError("Дневной лимит новых проектов исчерпан")
        return project

    def propose_goal(self, goal: Goal, now: datetime) -> PersonalProject | None:
        link = self.repository.load_feature("goal_project", goal.id, self.subject_id)
        if link is not None:
            return None
        if goal.need_kind not in {NeedKind.CURIOSITY, NeedKind.COHERENCE, NeedKind.COMPETENCE}:
            return None
        # A self-generated proposal searches shared agent memory only.
        return self.create(goal.title, "agent", now, goal=goal, proposed=True)

    def change(
        self,
        project_id: str,
        action: str,
        now: datetime,
        text: str = "",
        *,
        person_id: str | None = None,
    ) -> PersonalProject:
        project = self.get(project_id)
        if action in {"start", "resume"}:
            if project.status not in {"proposed", "paused"}:
                raise ValueError("Можно запустить предложенный или приостановленный проект")
            project.status, project.stop_reason = "active", ""
        elif action == "pause":
            if project.status != "active":
                raise ValueError("Проект не выполняется")
            project.status, project.stop_reason = "paused", "Приостановлен пользователем"
        elif action == "cancel":
            project.status, project.stop_reason = "cancelled", "Отменён пользователем"
            project.autonomous = False
        elif action == "retry":
            if project.status != "blocked":
                raise ValueError("Нет заблокированного шага")
            pending = next((s for s in project.steps if s.status == "failed"), None)
            if pending is None or pending.attempts >= 3:
                raise ValueError("Повторы исчерпаны; отмените проект и создайте новый")
            pending.status, pending.error = "pending", ""
            pending.finished_at, pending.prediction_error = None, None
            project.status, project.stop_reason = "active", ""
        elif action == "auto":
            if text not in {"on", "off"}:
                raise ValueError("Укажите on или off")
            project.autonomous = text == "on"
        elif action in {"extend", "revise"}:
            if not text.strip() or len(text.strip()) > 500:
                raise ValueError("Название должно содержать от 1 до 500 символов")
            if project.status == "cancelled":
                raise ValueError("Отменённый проект не изменяется")
            if action == "extend":
                if project.status != "completed" or len(project.milestone_titles) >= 32:
                    raise ValueError(
                        "Новый этап добавляется после завершения предыдущего; максимум 32"
                    )
                project.milestone_titles.append(text.strip())
                project.steps.extend(self._milestone())
                project.status, project.stop_reason = "active", ""
            else:
                if project.status not in {"proposed", "active", "paused"}:
                    raise ValueError("Для завершённого проекта добавьте новый этап")
                # Changing a query mid-milestone would detach output from its evidence.
                if any(s.status != "pending" for s in project.steps[-3:]):
                    raise ValueError("Текущий этап уже начат; сначала завершите или отмените его")
                project.revisions = (
                    project.revisions
                    + [
                        ProjectRevision(
                            at=now,
                            reason="Пересмотр пользователем",
                            previous_title=project.title,
                            title=text.strip(),
                        )
                    ]
                )[-20:]
                project.title = text.strip()
                project.milestone_titles[-1] = text.strip()
                project.status = "paused"
                project.stop_reason = "Цель пересмотрена; ожидает возобновления"
        else:
            raise ValueError("Неизвестное действие проекта")
        if project.person_id == "agent" and person_id and action in {"start", "extend", "revise"}:
            # Accepting/editing a shared proposal makes it this person's project.
            project.person_id = person_id
        project.updated_at = now
        self._save(project)
        return project

    def step(
        self,
        project_id: str,
        now: datetime,
        *,
        autonomous: bool = False,
        expected_success: float = 0.5,
    ) -> PersonalProject:
        project = self.get(project_id)
        if project.status != "active":
            raise ValueError("Проект не активен: " + (project.stop_reason or project.status))
        if autonomous and not project.autonomous:
            raise ValueError("Самостоятельные действия проекта отключены")
        if project.goal_id:
            goal = self.repository.get_goal(project.goal_id)
            if goal is None or goal.status != GoalStatus.ACTIVE:
                project.status, project.stop_reason = "paused", "Связанная цель не активна"
                self._save(project)
                return project
        step = next((s for s in project.steps if s.status != "completed"), None)
        if step is None:
            raise ValueError("Нет следующего шага")
        index = project.steps.index(step)
        # Retry interrupted running steps using the original prepared arguments.
        if step.status == "pending":
            step.expected_success = max(0.0, min(1.0, expected_success))
            if step.tool == "note_write":
                source = project.steps[index - 1].result
                if source is None:
                    raise ValueError("Нет результатов поиска для заметки")
                step.prepared_content = (
                    f"# {project.milestone_titles[index // 3]}\n\n"
                    "Выдержки из памяти; достоверность исходных утверждений "
                    "отдельно не проверена.\n\n" + source.content
                )
            if step.attempts >= 3:
                raise ValueError("Лимит повторов шага исчерпан")
            step.status, step.started_at = "running", now
            step.attempts += 1
            project.updated_at = now

            def commit(budget: ResourceBudget) -> None:
                with self.repository.transaction():
                    if autonomous and not self.budgets.consume("autonomous_project_steps"):
                        raise ValueError("Дневной лимит самостоятельных шагов проекта исчерпан")
                    self._save(project)
                    self.repository.save_budget(budget)

            if not self.budgets.consume_with("project_steps", commit):
                raise ValueError("Дневной лимит шагов проектов исчерпан")
        elif step.status != "running":
            raise ValueError("Сначала явно повторите заблокированный шаг")
        try:
            if step.tool == "memory_search":
                result = self.tools.search(project.milestone_titles[index // 3], project.person_id)
            elif step.tool == "note_write":
                if step.prepared_content is None:
                    raise ValueError("Отсутствуют сохранённые аргументы записи")
                result = self.tools.write(project.id, step.id, step.prepared_content)
            else:
                previous = project.steps[index - 1]
                if previous.result is None:
                    raise ValueError("Нет записанной заметки")
                result = self.tools.read(project.id, previous.id, previous.result.sha256)
            step.result, step.status, step.error = result, "completed", ""
        except (OSError, ValueError) as exc:
            step.status, step.error = "failed", str(exc)[:1000]
            project.status, project.stop_reason = "blocked", step.error
        step.prediction_error = abs(float(step.status == "completed") - step.expected_success)
        step.finished_at = now
        project.updated_at = now
        if all(s.status == "completed" for s in project.steps):
            project.status = "completed"
            project.stop_reason = (
                "Заметка сохранена и прочитана; общая цель отдельно не оценивалась"
            )
        with self.repository.transaction():
            self._save(project)
            self.repository.save_audit(
                "project_step",
                {
                    "project_id": project.id,
                    "step_id": step.id,
                    "tool": step.tool,
                    "status": step.status,
                    "goal_id": project.goal_id,
                },
            )
        return project

    def guidance(self, person_id: str) -> str:
        project = next(
            (p for p in self.history(person_id) if p.status in {"active", "blocked"}), None
        )
        if project is None:
            return ""
        detail = project.stop_reason or project.next_step or "Этап завершён"
        return f"Проект «{project.title}», {project.progress:.0%}. Следующий шаг: {detail}."
