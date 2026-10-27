"""Compatibility imports. Implementation: digital_child.inference.backend."""

from digital_child.inference.backend import (
    CognitiveBackend,
    OpenAICompatibleBackend,
    RuleBasedBackend,
    build_cognitive_backend,
)

__all__ = [
    "CognitiveBackend",
    "OpenAICompatibleBackend",
    "RuleBasedBackend",
    "build_cognitive_backend",
]
