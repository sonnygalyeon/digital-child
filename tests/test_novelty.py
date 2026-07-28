from pathlib import Path

from digital_child.models import Episode
from digital_child.novelty import NoveltyEngine
from digital_child.storage import SQLiteRepository
from digital_child.text import normalize_text


def test_duplicate_content_has_low_novelty(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "novelty.db")
    repository.save_episode(
        Episode(
            observation_id="1",
            content="Красная кнопка включает лампу",
            normalized_content=normalize_text("Красная кнопка включает лампу"),
            action="observe",
            outcome="ok",
            reward=0,
            importance=0.5,
            effective_units=1,
        )
    )
    engine = NoveltyEngine(repository)
    assert engine.calculate("Красная кнопка включает лампу") == 0.0
    assert engine.calculate("Кошка спит на окне") > 0.8
    repository.close()
