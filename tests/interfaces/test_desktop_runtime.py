import multiprocessing
import time
from pathlib import Path

from digital_child.inference.backend import RuleBasedBackend
from digital_child.infrastructure.repository import SQLiteRepository
from digital_child.interfaces.desktop.desktop_runtime import run_agent_session


class DelayedBackend(RuleBasedBackend):
    def generate_reply(self, context):
        time.sleep(2.2)
        return super().generate_reply(context)


def run_delayed_session(connection, database_path: str) -> None:
    from digital_child.application.agent import DigitalChildAgent
    from digital_child.interfaces.desktop import desktop_runtime

    def create_delayed_agent(path, **kwargs):
        return DigitalChildAgent(
            SQLiteRepository(path),
            cognitive_backend=DelayedBackend(),
            auto_research=False,
        )

    desktop_runtime.create_agent = create_delayed_agent
    run_agent_session(connection, database_path, False, False)


def test_desktop_session_streams_and_preserves_memory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DIGITAL_CHILD_LLM_PROVIDER", "disabled")
    monkeypatch.setenv("DIGITAL_CHILD_RESEARCH_PROVIDER", "disabled")
    database = tmp_path / "desktop.db"
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=run_agent_session,
        args=(child, str(database), False, True),
    )
    process.start()
    child.close()

    def receive_until(kind: str) -> list[dict]:
        messages = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if parent.poll(0.2):
                message = parent.recv()
                messages.append(message)
                assert message["type"] != "fatal", message
                if message["type"] == kind:
                    return messages
        raise AssertionError(f"No {kind} event: {messages}")

    try:
        initial = receive_until("ready")[-1]
        assert initial["snapshot"]["loop"]["running"]
        assert initial["snapshot"]["needs"]
        receive_until("health")
        parent.send({"type": "input", "text": "Привет!"})
        response = receive_until("complete")
        assert any(item["type"] == "token" and item["text"] for item in response)
        token = next(item for item in response if item["type"] == "token")
        assert token["face"]["process"] == "speaking"
        parent.send({"type": "input", "text": "/pause"})
        receive_until("complete")
        snapshot = receive_until("snapshot")[-1]["snapshot"]
        assert snapshot["loop"]["paused"]
        parent.send({"type": "input", "text": "/resume"})
        receive_until("complete")
        assert receive_until("snapshot")[-1]["snapshot"]["loop"]["running"]
        parent.send({"type": "close"})
        process.join(timeout=5)
        assert not process.is_alive()
        assert process.exitcode == 0
        with SQLiteRepository(database) as repository:
            history = repository.recent_conversation("local-user")
            assert history[0].content == "Привет!"
            assert len(history) == 2
            assert repository.load_snapshot() is not None
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        parent.close()


def test_state_updates_while_waiting_for_first_token(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=run_delayed_session, args=(child, str(tmp_path / "slow.db")))
    process.start()
    child.close()
    try:
        initial_curiosity = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert parent.poll(5)
            message = parent.recv()
            if message["type"] == "ready":
                initial_curiosity = message["snapshot"]["face"]["curiosity"]
            if message["type"] == "health":
                break
        assert initial_curiosity is not None
        parent.send({"type": "input", "text": "Почему небо голубое?"})
        saw_updated_state = False
        while time.monotonic() < deadline:
            assert parent.poll(5)
            message = parent.recv()
            if message["type"] == "snapshot":
                saw_updated_state |= message["snapshot"]["face"]["curiosity"] > initial_curiosity
            if message["type"] == "token":
                assert saw_updated_state, "Psychology must update before the LLM's first token"
            if message["type"] == "complete":
                assert saw_updated_state
                break
        else:
            raise AssertionError("No reply from the delayed backend")
        parent.send({"type": "close"})
        process.join(timeout=5)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        parent.close()
