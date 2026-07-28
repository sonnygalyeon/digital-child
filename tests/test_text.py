from digital_child.text import jaccard_similarity, normalize_text


def test_normalize_text_handles_case_and_punctuation() -> None:
    assert normalize_text("Красная, КНОПКА!") == "красная кнопка"


def test_jaccard_similarity() -> None:
    assert jaccard_similarity("red button lamp", "red button") == 2 / 3
