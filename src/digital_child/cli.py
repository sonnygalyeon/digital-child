from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from digital_child.models import DevelopmentDomain, Observation, SourceKind
from digital_child.service import create_agent


def run_chat(database_path: Path) -> None:
    agent = create_agent(database_path)

    print("Digital Child v0.1")
    print("Команды: /state, /rest, /memory, /quit")

    try:
        while True:
            try:
                text = input("\nНаставник> ").strip()
            except EOFError:
                print()
                break

            if not text:
                continue

            if text == "/quit":
                break

            if text == "/state":
                print("\nПрофиль развития:")
                print(agent.profile.model_dump_json(indent=2))

                print("\nТекущее состояние:")
                print(agent.state.model_dump_json(indent=2))
                continue

            if text == "/rest":
                state = agent.rest()
                print(state.model_dump_json(indent=2))
                continue

            if text == "/memory":
                episodes = agent.memory.recent_episodes(10)

                if not episodes:
                    print("Память пока пуста.")
                    continue

                for episode in episodes:
                    print(
                        f"- {episode.created_at.isoformat()} "
                        f"| {episode.content} "
                        f"| DEU={episode.effective_units:.3f}"
                    )
                continue

            word_count = max(1, len(text.split()))

            observation = Observation(
                content=text,
                source_kind=SourceKind.CAREGIVER,
                raw_units=float(word_count),
                novelty=0.8,
                attention=agent.state.attention_capacity,
                comprehension=0.6,
                reliability=0.8,
                integration=0.5,
                practical_confirmation=0.0,
                domains={
                    DevelopmentDomain.LANGUAGE: 0.4,
                    DevelopmentDomain.FACTUAL_KNOWLEDGE: 0.4,
                    DevelopmentDomain.SOCIAL_UNDERSTANDING: 0.2,
                },
            )

            result = agent.process_observation(observation)
            print(f"Ребёнок> {result.response}")

    finally:
        agent.memory.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="digital-child",
        description="Developmental core for a digital agent.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    chat_parser = subparsers.add_parser(
        "chat",
        help="Запустить локальную консоль наставника.",
    )
    chat_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/digital_child.db"),
        help="Путь к SQLite-базе памяти.",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Запустить HTTP API.",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
    )
    serve_parser.add_argument(
        "--port",
        default=8000,
        type=int,
    )

    args = parser.parse_args()

    if args.command == "chat":
        run_chat(args.db)
        return

    if args.command == "serve":
        uvicorn.run(
            "digital_child.api:app",
            host=args.host,
            port=args.port,
            reload=False,
        )
        return

    parser.error(f"Неизвестная команда: {args.command}")


if __name__ == "__main__":
    main()
