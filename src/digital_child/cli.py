from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from digital_child.models import (
    ClaimEvidenceInput,
    DevelopmentDomain,
    EvidenceStance,
    Observation,
    SourceKind,
)
from digital_child.service import create_agent


HELP_TEXT = """Команды:
  /help                     показать справку
  /state                    показать развитие и внутреннее состояние
  /teach <утверждение>      свидетельство в пользу утверждения
  /contradict <утверждение> свидетельство против утверждения
  /beliefs [N]              показать N убеждений
  /sources [N]              показать источники
  /memory [N]               показать активные эпизоды
  /summaries [N]            показать консолидированные воспоминания
  /consolidate              выполнить забывание и консолидацию
  /rest [0..1]              восстановить энергию
  /reset                    удалить память и начать заново
  /quit                     завершить программу
"""


def build_caregiver_observation(
    text: str,
    attention: float,
    stance: EvidenceStance | None = None,
) -> Observation:
    claims = [] if stance is None else [ClaimEvidenceInput(claim=text, stance=stance)]
    return Observation(
        content=text,
        source_kind=SourceKind.CAREGIVER,
        raw_units=float(max(1, len(text.split()))),
        novelty=None,
        attention=attention,
        comprehension=0.65,
        reliability=0.80,
        integration=0.55,
        practical_confirmation=0.0,
        domains={
            DevelopmentDomain.LANGUAGE: 0.35,
            DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.40,
            DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.15,
            DevelopmentDomain.CAUSAL_REASONING: 0.10,
        },
        claims=claims,
    )


def _parse_limit(text: str, default: int = 10) -> int | None:
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return default
    try:
        return max(1, min(int(parts[1]), 100))
    except ValueError:
        return None


def run_chat(database_path: Path) -> None:
    agent = create_agent(database_path)
    print("Digital Child v0.2")
    print(HELP_TEXT)

    try:
        while True:
            try:
                text = input("\nНаставник> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not text:
                continue
            if text == "/quit":
                break
            if text == "/help":
                print(HELP_TEXT)
                continue
            if text == "/state":
                print("\nПрофиль развития:")
                print(agent.profile.model_dump_json(indent=2))
                print("\nТекущее состояние:")
                print(agent.state.model_dump_json(indent=2))
                continue

            if text.startswith("/beliefs"):
                limit = _parse_limit(text)
                if limit is None:
                    print("Количество должно быть целым числом.")
                    continue
                beliefs = agent.repository.list_beliefs(limit)
                if not beliefs:
                    print("Убеждений пока нет.")
                for belief in beliefs:
                    print(
                        f"- [{belief.status.value}] p={belief.confidence:.3f} "
                        f"за={belief.support_score:.3f} "
                        f"против={belief.contradiction_score:.3f} | {belief.claim}"
                    )
                continue

            if text.startswith("/sources"):
                limit = _parse_limit(text)
                if limit is None:
                    print("Количество должно быть целым числом.")
                    continue
                for source in agent.repository.list_sources(limit):
                    print(
                        f"- {source.id} | {source.kind.value} | "
                        f"reliability={source.reliability:.2f} | {source.name}"
                    )
                continue

            if text.startswith("/memory"):
                limit = _parse_limit(text)
                if limit is None:
                    print("Количество должно быть целым числом.")
                    continue
                episodes = agent.repository.recent_episodes(limit)
                if not episodes:
                    print("Активная память пока пуста.")
                for episode in episodes:
                    print(
                        f"- #{episode.sequence} strength={episode.access_strength:.3f} "
                        f"DEU={episode.effective_units:.3f} | {episode.content}"
                    )
                continue

            if text.startswith("/summaries"):
                limit = _parse_limit(text)
                if limit is None:
                    print("Количество должно быть целым числом.")
                    continue
                summaries = agent.repository.list_memory_summaries(limit)
                if not summaries:
                    print("Консолидированных воспоминаний пока нет.")
                for summary in summaries:
                    print(
                        f"- повторов={summary.episode_count} "
                        f"DEU={summary.total_deu:.3f} | {summary.representative_text}"
                    )
                continue

            if text == "/consolidate":
                print(agent.consolidate_memory().model_dump_json(indent=2))
                continue

            if text.startswith("/rest"):
                parts = text.split(maxsplit=1)
                amount = 0.25
                if len(parts) == 2:
                    try:
                        amount = float(parts[1])
                    except ValueError:
                        print("Значение отдыха должно быть числом от 0 до 1.")
                        continue
                if not 0.0 <= amount <= 1.0:
                    print("Значение отдыха должно быть от 0 до 1.")
                    continue
                print(agent.rest(amount).model_dump_json(indent=2))
                continue

            if text == "/reset":
                confirmation = input("Удалить всю память? Введите YES: ").strip()
                if confirmation == "YES":
                    agent.reset()
                    print("Состояние и память сброшены.")
                else:
                    print("Сброс отменён.")
                continue

            stance: EvidenceStance | None = None
            payload = text
            if text.startswith("/teach "):
                stance = EvidenceStance.SUPPORT
                payload = text.removeprefix("/teach ").strip()
            elif text.startswith("/contradict "):
                stance = EvidenceStance.CONTRADICT
                payload = text.removeprefix("/contradict ").strip()

            if not payload:
                print("После команды требуется утверждение.")
                continue

            result = agent.process_observation(
                build_caregiver_observation(
                    text=payload,
                    attention=agent.state.attention_capacity,
                    stance=stance,
                )
            )
            print(f"Ребёнок> {result.response}")
            print(f"Новизна: {result.calculated_novelty:.3f}")
    finally:
        agent.repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="digital-child",
        description="Developmental core for a digital agent.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Run the local mentor console")
    chat_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/digital_child.db"),
    )

    serve_parser = subparsers.add_parser("serve", help="Run the HTTP API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8000, type=int)

    args = parser.parse_args()
    if args.command == "chat":
        run_chat(args.db)
        return
    if args.command == "serve":
        uvicorn.run("digital_child.api:app", host=args.host, port=args.port, reload=False)
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
