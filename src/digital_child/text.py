from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.UNICODE)


def normalize_text(text: str) -> str:
    return " ".join(token.lower().replace("ё", "е") for token in _TOKEN_RE.findall(text))


def token_set(text: str) -> set[str]:
    normalized = normalize_text(text)
    return set(normalized.split()) if normalized else set()


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
