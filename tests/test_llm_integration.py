from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.models import EvidenceJudgment, LLMHealth
from digital_child.storage import SQLiteRepository


class StreamingBackend:
    name = "test-stream"
    model = "test-model"
    supports_streaming = True

    def generate_reply(self, context):
        return "Привет из модели."

    def stream_reply(self, context):
        yield "Привет "
        yield "из модели."

    def assess_sources(self, claim, results) -> list[EvidenceJudgment]:
        return []

    def health_check(self) -> LLMHealth:
        return LLMHealth(
            enabled=True,
            healthy=True,
            backend=self.name,
            model=self.model,
            base_url="http://test/v1",
            supports_streaming=True,
            detail="ok",
        )


def test_streamed_reply_is_persisted_as_conversation(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "agent.db")
    agent = DigitalChildAgent(
        repository,
        cognitive_backend=StreamingBackend(),
        auto_research=False,
    )
    chunks: list[str] = []

    result = agent.interact("Привет, кто ты?", on_token=chunks.append)

    assert "".join(chunks) == "Привет из модели."
    assert result.response == "Привет из модели."
    history = repository.recent_conversation("local-user", 10)
    assert [item.role.value for item in history] == ["user", "agent"]
    assert history[-1].backend == "test-stream"
    assert history[-1].model == "test-model"
    repository.close()


def test_llm_health_is_exposed(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "agent.db")
    agent = DigitalChildAgent(
        repository,
        cognitive_backend=StreamingBackend(),
        auto_research=False,
    )

    status = agent.llm_health()

    assert status.enabled is True
    assert status.healthy is True
    assert status.supports_streaming is True
    repository.close()


class NonStreamingBackend:
    name = "test-non-stream"
    model = "test-fallback-model"
    supports_streaming = False

    def generate_reply(self, context):
        return "Ответ непотокового backend."

    def stream_reply(self, context):
        yield self.generate_reply(context)

    def assess_sources(self, claim, results) -> list[EvidenceJudgment]:
        return []

    def health_check(self) -> LLMHealth:
        return LLMHealth(
            enabled=False,
            healthy=True,
            backend=self.name,
            model=self.model,
            base_url=None,
            supports_streaming=False,
            detail="ok",
        )


def test_non_streaming_backend_still_emits_to_terminal_callback(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "agent.db")
    agent = DigitalChildAgent(
        repository,
        cognitive_backend=NonStreamingBackend(),
        auto_research=False,
    )
    chunks: list[str] = []

    result = agent.interact("Привет!", on_token=chunks.append)

    assert chunks == ["Ответ непотокового backend."]
    assert result.response == "Ответ непотокового backend."
    repository.close()
