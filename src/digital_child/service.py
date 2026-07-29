from __future__ import annotations

import os
from pathlib import Path

from digital_child.agent import DigitalChildAgent
from digital_child.config import load_dotenv
from digital_child.llm import CognitiveBackend, build_cognitive_backend
from digital_child.research import SearchProvider, build_search_provider
from digital_child.storage import SQLiteRepository


def create_agent(
    database_path: str | Path | None = None,
    *,
    search_provider: SearchProvider | None = None,
    cognitive_backend: CognitiveBackend | None = None,
    auto_research: bool | None = None,
) -> DigitalChildAgent:
    load_dotenv()
    path = Path(database_path or os.environ.get("DIGITAL_CHILD_DB", "data/digital_child.db"))
    if auto_research is None:
        auto_research = os.environ.get("DIGITAL_CHILD_AUTO_RESEARCH", "1").lower() not in {
            "0",
            "false",
            "off",
            "no",
        }
    return DigitalChildAgent(
        SQLiteRepository(path),
        search_provider=search_provider or build_search_provider(),
        cognitive_backend=cognitive_backend or build_cognitive_backend(),
        auto_research=auto_research,
    )
