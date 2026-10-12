from __future__ import annotations

import threading
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from digital_child.agent import DigitalChildAgent
from digital_child.behavioral_development import developmental_dynamics
from digital_child.developmental_age import psychological_age_equivalent
from digital_child.face_state import FaceState
from digital_child.interest_catalog import preferred_interests
from digital_child.models import ConversationMessage
from digital_child.service import create_agent


def desktop_snapshot(agent: DigitalChildAgent) -> dict[str, Any]:
    psyche = agent.psychology.snapshot()
    development = developmental_dynamics(agent.profile)
    active_goal = next(
        (
            goal
            for goal in agent.repository.list_goals(100, active_only=True)
            if goal.id == agent.cognitive_loop.status.active_goal_id
        ),
        None,
    )
    return {
        "face": FaceState.from_emotion(agent.emotion).to_message()["payload"],
        "name": agent.identity.display_name,
        "stage": agent.profile.stage.value,
        "age": psychological_age_equivalent(agent.profile),
        "deu": agent.profile.total_deu,
        "backend": agent.cognitive_backend.name,
        "model": agent.cognitive_backend.model,
        "loop": agent.cognitive_loop.status.model_dump(mode="json"),
        "needs": [need.model_dump(mode="json") for need in agent.cognitive_loop.needs()],
        "goal": None if active_goal is None else active_goal.title,
        "time": agent.clock.diagnostics(),
        "pending_verifications": agent.repository.pending_verification_count(),
        "psychology": {
            "character": psyche.character.model_dump(mode="json"),
            "mood": psyche.mood.model_dump(mode="json"),
            "self_model": psyche.self_model.model_dump(mode="json"),
            "regulation": development.regulation,
            "stage_progress": development.progress,
            "style": None if psyche.last_behavior is None else psyche.last_behavior.style,
            "coping": None if psyche.last_behavior is None else psyche.last_behavior.coping,
            "interests": [item.topic for item in preferred_interests(psyche, agent.profile, 5)],
            "initiative_enabled": psyche.initiative_enabled and agent.initiative.settings.enabled,
        },
    }


def run_agent_session(
    connection: Connection,
    database_path: str,
    auto_research: bool = True,
    cognitive_loop: bool = True,
) -> None:
    """One serial command stream; all Qt rendering stays in the parent process."""
    from digital_child.cli import ChatCommandRouter

    send_lock = threading.Lock()
    snapshot_stop = threading.Event()
    snapshot_thread: threading.Thread | None = None
    agent: DigitalChildAgent | None = None

    def send(kind: str, **payload: Any) -> None:
        with send_lock:
            connection.send({"type": kind, **payload})

    try:
        agent = create_agent(Path(database_path), auto_research=auto_research)
        router = ChatCommandRouter(agent)
        agent.set_background_notifier(lambda message: send("notice", text=message))

        def publish_initiative(message: ConversationMessage) -> None:
            if message.person_id == router.person_id:
                send("initiative", message=message.model_dump(mode="json"))

        agent.set_initiative_notifier(publish_initiative)
        history = agent.repository.recent_conversation(router.person_id, 100)
        opening = (
            agent.genesis_event.monologue
            if agent.genesis_event is not None
            else ["Личность восстановлена из долговременной памяти."]
        )
        send(
            "ready",
            snapshot=desktop_snapshot(agent),
            opening=opening,
            history=[item.model_dump(mode="json") for item in history],
        )
        if cognitive_loop:
            agent.start_cognitive_loop()

        def publish_snapshots() -> None:
            assert agent is not None
            while not snapshot_stop.wait(1):
                try:
                    send("snapshot", snapshot=desktop_snapshot(agent))
                except (BrokenPipeError, EOFError, OSError):
                    break

        snapshot_thread = threading.Thread(
            target=publish_snapshots,
            name="digital-child-desktop-state",
            daemon=True,
        )
        snapshot_thread.start()
        send("health", health=agent.llm_health().model_dump(mode="json"))

        def on_token(token: str) -> None:
            assert agent is not None
            send(
                "token",
                text=token,
                face=FaceState.from_emotion(
                    agent.emotion,
                    process="speaking",
                    speaking_level=min(1.0, 0.25 + len(token.strip()) / 12),
                ).to_message()["payload"],
            )

        while True:
            if connection.poll(0.2):
                message = connection.recv()
                if message.get("type") == "close":
                    break
                if message.get("type") != "input":
                    continue
                text = str(message.get("text", "")).strip()
                if not text:
                    continue
                if text == "/quit":
                    break
                started = time.monotonic()
                try:
                    if text.startswith("/"):
                        result = router.handle(text)
                        send(
                            "complete", text=result, metadata="", elapsed=time.monotonic() - started
                        )
                    else:
                        metadata = router.handle_stream(text, on_token)
                        send(
                            "complete",
                            text="",
                            metadata=metadata,
                            elapsed=time.monotonic() - started,
                        )
                except Exception as exc:
                    send("error", text=f"Ошибка обработки: {exc}")
                send("snapshot", snapshot=desktop_snapshot(agent))
    except (BrokenPipeError, EOFError):
        pass
    except Exception as exc:
        try:
            send("fatal", text=f"Не удалось запустить агента: {exc}")
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        snapshot_stop.set()
        if snapshot_thread is not None:
            snapshot_thread.join(timeout=1)
        if agent is not None:
            agent.set_background_notifier(None)
            agent.set_initiative_notifier(None)
            agent.close()
        connection.close()
